import 'dart:convert';
import 'dart:io';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/caveat_text.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'intake_harness.dart';
import 'widget_test.dart' show TestRepository;

class PreflightRepository extends TestRepository {
  int checks = 0;
  int uploads = 0;
  @override
  Future<Json> preflight(CollectionScope scope, IntakeFile file) async {
    checks++;
    return {
      'status': 'blocked',
      'input_sha256': file.sha256,
      'size_bytes': file.bytes.length,
      'decode': {'reason': 'memory_limit_unavailable'},
      'issues': ['memory_limit_unavailable'],
      'unmeasured': ['focus', 'glare', 'label_coverage'],
    };
  }

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    uploads++;
    return super.createIntake(scope, file, key);
  }
}

class DeniedIntakeRepository extends TestRepository {
  int attempts = 0;
  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    attempts++;
    throw const ApiFailure('Collection access denied.', status: 403);
  }
}

const _captureKey = 'pending-camera-owner-v1';
const _captureSensitiveKey = '$_captureKey:sensitive';
const _recoveryScope = CollectionScope(
  organizationId: 'org',
  collectionId: 'insects',
  name: 'Synthetic insects',
  permissions: ['upload'],
);

Widget _recoveryApp(
  SpecimenRepository repository, {
  String user = 'owner',
  Future<List<XFile>> Function()? recover,
  Future<List<XFile>> Function(bool)? pick,
}) => MaterialApp(
  theme: AppTheme.light(),
  home: Scaffold(
    body: IntakeScreen(
      repository: repository,
      scope: _recoveryScope,
      userId: user,
      onComplete: () {},
      recoverCamera: recover,
      pickImages: pick,
      openCapture: (_) async =>
          const CaptureResult(unavailable: CaptureUnavailable.failed),
    ),
  ),
);

// Snapshot the preferences while the real device-picker path is open. The
// returned snapshot represents what survives an Android process restart.
Future<Map<String, Object>> _writeCameraMarker(
  WidgetTester tester, {
  required bool sensitive,
  String user = 'owner',
}) async {
  SharedPreferences.setMockInitialValues({});
  const channel = MethodChannel('plugins.flutter.io/image_picker');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  Map<String, Object>? marker;
  messenger.setMockMethodCallHandler(channel, (call) async {
    expect(call.method, 'pickImage');
    final prefs = await SharedPreferences.getInstance();
    marker = {for (final key in prefs.getKeys()) key: prefs.get(key)!};
    return null;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
  await tester.pumpWidget(_recoveryApp(TestRepository(), user: user));
  await tester.pumpAndSettle();
  await selectSensitivity(tester, sensitive ? 'Sensitive' : 'Not sensitive');
  await tester.tap(takePhotographButton);
  await tester.pumpAndSettle();
  expect(marker, isNotNull);
  expect(marker![_captureKey], '$user:${_recoveryScope.key}');
  final prefs = await SharedPreferences.getInstance();
  expect(prefs.containsKey(_captureKey), isFalse);
  expect(prefs.containsKey(_captureSensitiveKey), isFalse);
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pumpAndSettle();
  return marker!;
}

Future<void> _pumpRecovery(WidgetTester tester, Widget app) async {
  await tester.runAsync(() async {
    await tester.pumpWidget(app);
    for (var attempt = 0; attempt < 200; attempt++) {
      await Future<void>.delayed(const Duration(milliseconds: 25));
      await tester.pump();
      if (tester.widget<UiButton>(chooseFilesButton).onPressed != null) return;
    }
    fail('Camera recovery did not finish');
  });
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('first denied upload stops remaining selected files', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1200, 2500));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    SharedPreferences.setMockInitialValues({});
    final repo = DeniedIntakeRepository();
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: IntakeScreen(
            repository: repo,
            scope: const CollectionScope(
              organizationId: 'o',
              collectionId: 'c',
              name: 'Fixture',
            ),
            userId: 'u',
            onComplete: () => fail('No item accepted'),
            pickImages: (_) async => [
              for (final name in [
                'synthetic-label.png',
                'synthetic-wide-label.png',
              ])
                XFile.fromData(
                  File('test/fixtures/$name').readAsBytesSync(),
                  path: name,
                  name: name,
                ),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await chooseFiles(tester);
    expect(find.text('2 ready'), findsOneWidget);
    expect(repo.attempts, 0);
    await submitBatch(tester);
    expect(repo.attempts, 1);
    expect(find.text('2 ready'), findsOneWidget);
    // The current row widget labels UploadState.ready this way.
    expect(find.text('Ready'), findsNWidgets(2));
  });

  const scope = CollectionScope(
    organizationId: 'org',
    collectionId: 'insects',
    name: 'Synthetic insects',
  );
  final bytes = File(
    'test/fixtures/synthetic-wide-label.png',
  ).readAsBytesSync();
  XFile recoveredPhoto() =>
      XFile.fromData(bytes, path: 'recovered.png', name: 'recovered.png');

  ApiSpecimenRepository recordingRepository(List<Json> bodies) =>
      ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8016'),
        token: () async => 'synthetic-test-token',
        client: MockClient((request) async {
          if (request.url.path.endsWith('/batches') ||
              request.url.path.endsWith('/items')) {
            expect(request.method, 'POST');
            final body = jsonDecode(request.body) as Json;
            bodies.add(body);
            return http.Response(
              jsonEncode({
                'batch_id': 'b',
                'upload_id': 'u',
                'sensitive': body['sensitive'],
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'upload_id': 'u',
              'offset': bytes.length,
              'revision': 2,
            }),
            200,
          );
        }),
      );

  for (final sensitive in [true, false]) {
    testWidgets(
      'device camera marker recovers sensitive=$sensitive in both creation requests',
      (tester) async {
        final marker = await _writeCameraMarker(tester, sensitive: sensitive);
        SharedPreferences.setMockInitialValues(marker);
        final bodies = <Json>[];
        final repository = recordingRepository(bodies);
        addTearDown(repository.close);
        await _pumpRecovery(
          tester,
          _recoveryApp(repository, recover: () async => [recoveredPhoto()]),
        );
        expect(tester.widget<UiSwitch>(sensitivityControl).value, isFalse);
        expect(
          find.text('Recovered a photo. Check it, then send.'),
          findsOneWidget,
        );
        expect(bodies, isEmpty);
        await submitBatch(tester);
        expect(bodies.map((body) => body['sensitive']), [sensitive, sensitive]);
        expect(marker[_captureSensitiveKey], sensitive);
      },
      variant: TargetPlatformVariant.only(TargetPlatform.android),
    );
  }

  for (final declaration in <Object?>[null, 'false']) {
    testWidgets(
      'legacy camera marker declaration=$declaration recovers as Sensitive',
      (tester) async {
        SharedPreferences.setMockInitialValues({
          _captureKey: 'owner:${_recoveryScope.key}',
          _captureSensitiveKey: ?declaration,
        });
        final bodies = <Json>[];
        final repository = recordingRepository(bodies);
        addTearDown(repository.close);
        await _pumpRecovery(
          tester,
          _recoveryApp(repository, recover: () async => [recoveredPhoto()]),
        );
        expect(tester.widget<UiSwitch>(sensitivityControl).value, isFalse);
        expect(bodies, isEmpty);
        await submitBatch(tester);
        expect(bodies.map((body) => body['sensitive']), [true, true]);
      },
    );
  }

  for (final throws in [false, true]) {
    testWidgets('camera recovery clears both marker keys, throws=$throws', (
      tester,
    ) async {
      SharedPreferences.setMockInitialValues({
        _captureKey: 'owner:${_recoveryScope.key}',
        _captureSensitiveKey: true,
      });
      await _pumpRecovery(
        tester,
        _recoveryApp(
          TestRepository(),
          recover: () async {
            if (throws) throw StateError('Synthetic recovery failure');
            return [recoveredPhoto()];
          },
        ),
      );
      expect(
        find.text(
          throws
              ? 'Could not read this photo. Choose it again.'
              : 'Recovered a photo. Check it, then send.',
        ),
        findsOneWidget,
      );
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.containsKey(_captureKey), isFalse);
      expect(prefs.containsKey(_captureSensitiveKey), isFalse);
    });
  }

  testWidgets(
    'another owner camera marker is ignored without applying its declaration',
    (tester) async {
      final marker = await _writeCameraMarker(
        tester,
        sensitive: true,
        user: 'other',
      );
      SharedPreferences.setMockInitialValues(marker);
      var recoveries = 0;
      final bodies = <Json>[];
      final repository = recordingRepository(bodies);
      addTearDown(repository.close);
      await _pumpRecovery(
        tester,
        _recoveryApp(
          repository,
          recover: () async {
            recoveries++;
            return [recoveredPhoto()];
          },
          pick: (_) async => [recoveredPhoto()],
        ),
      );
      expect(recoveries, 0);
      expect(
        find.text('Recovered a photo. Check it, then send.'),
        findsNothing,
      );
      expect(uploadButton, findsNothing);
      expect(tester.widget<UiSwitch>(sensitivityControl).value, isFalse);
      await chooseFiles(tester);
      await submitBatch(tester);
      expect(bodies.map((body) => body['sensitive']), [false, false]);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString(_captureKey), 'other:${_recoveryScope.key}');
      expect(prefs.get(_captureSensitiveKey), isTrue);
    },
    variant: TargetPlatformVariant.only(TargetPlatform.android),
  );

  testWidgets(
    'interrupted camera recovery requires the same user and collection and never uploads automatically',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        'pending-camera-owner-v1': 'owner:org/insects',
      });
      var recovered = 0;
      final repository = PreflightRepository();
      Widget app(String user) => MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: IntakeScreen(
            key: ValueKey(user),
            repository: repository,
            scope: scope,
            userId: user,
            onComplete: () {},
            recoverCamera: () async {
              recovered++;
              return [
                XFile.fromData(
                  bytes,
                  path: 'recovered.png',
                  name: 'recovered.png',
                ),
              ];
            },
          ),
        ),
      );
      await tester.pumpWidget(app('other'));
      await tester.pumpAndSettle();
      expect(recovered, 0);
      await _pumpRecovery(tester, app('owner'));
      expect(recovered, 1);
      await tester.ensureVisible(find.text('recovered.png'));
      await tester.pumpAndSettle();
      expect(find.text('recovered.png'), findsOneWidget);
      expect(
        find.text('Recovered a photo. Check it, then send.'),
        findsOneWidget,
      );
      // Recovery only queues the photograph; Upload remains an explicit action.
      await tester.ensureVisible(uploadButton);
      await tester.pumpAndSettle();
      expect(buttonEnabled(tester, uploadButton), isTrue);
      expect(repository.uploads, 0);
      expect(repository.checks, 0);
      expect(
        (await SharedPreferences.getInstance()).containsKey(
          'pending-camera-owner-v1',
        ),
        isFalse,
      );
    },
  );
  testWidgets('choosing a file waits for Upload and keeps quality in details', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    final repository = PreflightRepository();
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: IntakeScreen(
            repository: repository,
            scope: scope,
            userId: 'owner',
            onComplete: () {},
            pickImages: (_) async => [
              XFile.fromData(bytes, path: 'chosen.png', name: 'chosen.png'),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(uploadButton, findsNothing);
    await chooseFiles(tester);
    expect(repository.uploads, 0);
    expect(repository.checks, 0);
    expect(buttonEnabled(tester, uploadButton), isTrue);
    expect(confirmCheckbox, findsNothing);
    await tester.ensureVisible(find.text('chosen.png'));
    await tester.pumpAndSettle();
    expect(find.text('chosen.png'), findsOneWidget);
    await tester.ensureVisible(find.text('chosen.png'));
    await tester.tap(find.text('chosen.png'));
    await tester.pumpAndSettle();
    expect(find.text('Not calibrated'), findsOneWidget);
  });
  testWidgets(
    'server preflight requires explicit transmission and never starts upload',
    (tester) async {
      SharedPreferences.setMockInitialValues({});
      final repository = PreflightRepository();
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: IntakeScreen(
              repository: repository,
              scope: scope,
              userId: 'owner',
              onComplete: () {},
              pickImages: (_) async => [
                XFile.fromData(
                  bytes,
                  path: 'preflight.png',
                  name: 'preflight.png',
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await chooseFiles(tester);
      expect(repository.checks, 0);
      expect(repository.uploads, 0);
      await tester.ensureVisible(find.text('preflight.png'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('preflight.png'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Send for server check'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Send for server check'));
      await tester.pumpAndSettle();
      expect(repository.checks, 1);
      expect(repository.uploads, 0);
      expect(
        find.textContaining('The server check is not available.'),
        findsOneWidget,
      );
      // The format caveat moved behind this row's own "Why" and must still be
      // reachable there, not at some other caveat on the screen.
      final Finder unavailable = find.ancestor(
        of: find.textContaining('The server check is not available.'),
        matching: find.byType(CaveatText),
      );
      expect(unavailable, findsOneWidget);
      final Finder why = find.descendant(
        of: unavailable,
        matching: find.text('Why'),
      );
      await tester.ensureVisible(why);
      await tester.pumpAndSettle();
      await tester.tap(why);
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Changing the image format will not help.'),
        findsOneWidget,
      );
      expect(repository.uploads, 0);
      expect(confirmCheckbox, findsNothing);
      expect(buttonEnabled(tester, uploadButton), isTrue);
    },
  );
}
