import 'dart:io';
import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/capture_card.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'capture_screen_test.dart' show FakeCaptureCamera;
import 'intake_harness.dart';
import 'widget_test.dart' show TestRepository;

const _scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'insects',
  name: 'Insects',
);
const _otherScope = CollectionScope(
  organizationId: 'org',
  collectionId: 'plants',
  name: 'Plants',
);
final _mode = find.byKey(const ValueKey('intake-auto-ingest'));

class _RecordingRepository extends TestRepository {
  final List<IntakeFile> created = [];

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async {
    created.add(file);
    return super.createIntake(scope, file, key);
  }
}

class _OversizedPhoto extends XFile {
  _OversizedPhoto() : super('large.png');

  @override
  Future<int> length() async => intakeMaximumBytes + 1;
}

class _UnavailableCheckRepository extends TestRepository {
  int checks = 0;

  @override
  Future<Json> preflight(CollectionScope scope, IntakeFile file) async {
    checks++;
    throw StateError('Synthetic check failure');
  }
}

class _UnreadablePhoto extends XFile {
  _UnreadablePhoto() : super('unreadable.png');

  @override
  Future<int> length() async => throw const FileSystemException('unreadable');
}

Widget _app(
  SpecimenRepository repository, {
  CollectionScope scope = _scope,
  String userId = 'owner',
  bool web = false,
  List<XFile> files = const [],
  bool camera = false,
}) => MaterialApp(
  theme: AppTheme.light(),
  home: Scaffold(
    body: IntakeScreen(
      repository: repository,
      scope: scope,
      userId: userId,
      onComplete: () {},
      webOverride: web,
      pickImages: camera ? null : (_) async => files,
      cameraFactory: camera ? () async => FakeCaptureCamera() : null,
    ),
  ),
);

Future<void> _pump(WidgetTester tester, Widget app, {double scale = 1}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(390, 844);
  tester.platformDispatcher.textScaleFactorTestValue = scale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  await tester.pumpWidget(app);
  await tester.pumpAndSettle();
}

// Text renders a RichText child. Count that rendered paragraph once, including
// Text.rich and standalone RichText, rather than counting both widgets. Icon
// font glyphs are pictures, not words (the baseline's five icons add no words).
List<String> _visibleText(WidgetTester tester) {
  final body = tester.getRect(find.byType(IntakeScreen));
  return [
    for (final element
        in find
            .descendant(
              of: find.byType(IntakeScreen),
              matching: find.byType(RichText),
            )
            .evaluate())
      if (element.findAncestorWidgetOfExactType<Icon>() == null &&
          tester
              .getRect(find.byElementPredicate((e) => e == element))
              .overlaps(body))
        (element.widget as RichText).text.toPlainText(
          includeSemanticsLabels: false,
        ),
  ];
}

bool _sensitivity(WidgetTester tester) =>
    switch (tester.widget(sensitivityControl)) {
      UiSwitch(:final value) => value,
      UiCheckbox(:final value) =>
        value!, // Allows assertion-based red runs on main.
      _ => throw StateError('Sensitivity control missing'),
    };

Future<void> _markSensitive(WidgetTester tester) async {
  if (!_sensitivity(tester)) {
    await tester.tap(sensitivityControl);
    await tester.pumpAndSettle();
  }
  expect(_sensitivity(tester), isTrue);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  for (final web in [false, true]) {
    testWidgets('entry has at most 15 visible words at 390x844, web=$web', (
      tester,
    ) async {
      await _pump(tester, _app(TestRepository(), web: web));
      final text = _visibleText(tester);
      final words = text.join(' ').trim().split(RegExp(r'\s+'));
      expect(words.length, lessThanOrEqualTo(15), reason: text.join(' | '));
      expect(find.text('Intake'), findsOneWidget);
      expect(find.text('One photo per specimen.'), findsOneWidget);
      expect(find.text('Add specimens'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  for (final platform in [TargetPlatform.android, TargetPlatform.iOS]) {
    testWidgets(
      'native primary action is Take photos with an Intake heading',
      (tester) async {
        await _pump(tester, _app(TestRepository()));
        expect(find.text('Intake'), findsOneWidget);
        expect(
          tester.widget<UiButton>(takePhotographButton).variant,
          UiButtonVariant.primary,
        );
        expect(
          tester.widget<UiButton>(chooseFilesButton).variant,
          UiButtonVariant.secondary,
        );
      },
      variant: TargetPlatformVariant({platform}),
    );
  }

  testWidgets('web primary action is Choose files', (tester) async {
    await _pump(tester, _app(TestRepository(), web: true));
    expect(
      tester.widget<UiButton>(chooseFilesButton).variant,
      UiButtonVariant.primary,
    );
    expect(
      tester.widget<UiButton>(takePhotographButton).variant,
      UiButtonVariant.secondary,
    );
  });

  for (final scale in [1.0, 2.0]) {
    testWidgets(
      'entry shows mode and sensitivity without disclosures at text $scale',
      (tester) async {
        await _pump(tester, _app(TestRepository()), scale: scale);
        expect(
          find.byKey(const ValueKey('intake-camera-settings')),
          findsNothing,
        );
        expect(find.byKey(const ValueKey('intake-add-photos')), findsNothing);
        expect(tester.widget(_mode), isA<UiSegmented<bool>>());
        expect(tester.widget(sensitivityControl), isA<UiSwitch>());
        for (final label in ['Review', 'Send now', 'Mark sensitive']) {
          expect(find.text(label).hitTestable(), findsOneWidget);
          expect(
            tester.getRect(find.text(label)).bottom,
            lessThanOrEqualTo(844),
          );
        }
        if (scale == 1) {
          expect(
            tester.getTopLeft(find.byType(UiMenuTrigger)).dy,
            tester.getTopLeft(chooseFilesButton).dy,
          );
        }
        for (final control in [
          takePhotographButton,
          chooseFilesButton,
          _mode,
          sensitivityControl,
        ]) {
          expect(tester.getSize(control).height, greaterThanOrEqualTo(48));
        }
        expect(tester.widget<UiSegmented<bool>>(_mode).value, isFalse);
        expect(_sensitivity(tester), isFalse);
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets('More lists Import from link and invokes it', (tester) async {
    var imported = 0;
    await _pump(
      tester,
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: IntakeCaptureCard(
            web: true,
            cameraAvailable: true,
            onChooseFiles: () {},
            onTakePhotograph: () {},
            onDropFiles: null,
            onImportFromLink: () => imported++,
          ),
        ),
      ),
    );
    expect(find.text('Import from link'), findsNothing);
    expect(find.byType(UiMenuTrigger), findsOneWidget);
    expect(
      tester.getTopLeft(find.byType(UiMenuTrigger)).dy,
      tester.getTopLeft(chooseFilesButton).dy,
    );
    expect(find.byType(UiPopoverMenu), findsOneWidget);
    await tester.tap(find.text('More'));
    await tester.pumpAndSettle();
    expect(find.text('Import from link').hitTestable(), findsOneWidget);
    await tester.tap(find.text('Import from link'));
    await tester.pumpAndSettle();
    expect(imported, 1);
  });

  testWidgets('adding photos keeps the source controls open', (tester) async {
    final photo = XFile.fromData(
      File('test/fixtures/synthetic-label.png').readAsBytesSync(),
      path: 'photo.png',
      name: 'photo.png',
    );
    await _pump(tester, _app(TestRepository(), files: [photo]));
    await chooseFiles(tester);
    expect(find.byKey(const ValueKey('intake-add-photos')), findsNothing);
    expect(chooseFilesButton.hitTestable(), findsOneWidget);
    expect(takePhotographButton.hitTestable(), findsOneWidget);
  });

  for (final changeUser in [false, true]) {
    testWidgets(
      'scope change resets sensitivity to off, changeUser=$changeUser',
      (tester) async {
        final repository = TestRepository();
        await _pump(tester, _app(repository));
        await _markSensitive(tester);
        await tester.pumpWidget(
          _app(
            repository,
            scope: changeUser ? _scope : _otherScope,
            userId: changeUser ? 'other' : 'owner',
          ),
        );
        await tester.pumpAndSettle();
        expect(_sensitivity(tester), isFalse);
      },
    );
  }

  testWidgets('new Intake session starts off after sensitivity was on', (
    tester,
  ) async {
    final repository = TestRepository();
    await _pump(tester, _app(repository));
    await _markSensitive(tester);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
    await tester.pumpWidget(_app(repository));
    await tester.pumpAndSettle();
    expect(_sensitivity(tester), isFalse);
  });

  testWidgets('default photo reaches the repository with explicit false', (
    tester,
  ) async {
    final repository = _RecordingRepository();
    final photo = XFile.fromData(
      File('test/fixtures/synthetic-label.png').readAsBytesSync(),
      path: 'photo.png',
      name: 'photo.png',
    );
    await _pump(tester, _app(repository, files: [photo]));
    await chooseFiles(tester);
    expect(repository.created, isEmpty);
    await submitBatch(tester);
    expect(repository.created, hasLength(1));
    expect(repository.created.single.sensitive, isFalse);
  });

  testWidgets(
    'mode shares the existing camera callback and scoped preference',
    (tester) async {
      final repository = TestRepository();
      await _pump(tester, _app(repository, camera: true));
      expect(_mode, findsOneWidget);
      expect(tester.widget(_mode), isA<UiSegmented<bool>>());
      await tester.tap(find.text('Send now'));
      await tester.pumpAndSettle();
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getBool('camera-auto-ingest-v1:owner:org/insects'), isTrue);
      await tester.tap(takePhotographButton);
      await tester.pumpAndSettle();
      final capture = tester.widget<CaptureScreen>(find.byType(CaptureScreen));
      expect(capture.autoIngest, isTrue);
      expect(capture.activitySnapshot!().label, 'No photos');
      // Exercise the current camera API; lane 3 owns its visual control.
      capture.onAutoIngestChanged!(false);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(tester.widget<UiSegmented<bool>>(_mode).value, isFalse);
      expect(prefs.getBool('camera-auto-ingest-v1:owner:org/insects'), isFalse);
      await tester.tap(find.text('Send now'));
      await tester.pumpAndSettle();
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
      await tester.pumpWidget(_app(repository));
      await tester.pumpAndSettle();
      expect(tester.widget<UiSegmented<bool>>(_mode).value, isTrue);
      await tester.pumpWidget(_app(repository, scope: _otherScope));
      await tester.pumpAndSettle();
      expect(tester.widget<UiSegmented<bool>>(_mode).value, isFalse);
      await tester.pumpWidget(_app(repository));
      await tester.pumpAndSettle();
      expect(tester.widget<UiSegmented<bool>>(_mode).value, isTrue);
    },
  );

  testWidgets(
    'unavailable photo check explains what to do without banned terms',
    (tester) async {
      final repository = _UnavailableCheckRepository();
      final photo = XFile.fromData(
        File('test/fixtures/synthetic-label.png').readAsBytesSync(),
        path: 'photo.png',
        name: 'photo.png',
      );
      await _pump(tester, _app(repository, files: [photo]));
      await chooseFiles(tester);
      await tester.ensureVisible(find.text('photo.png'));
      await tester.tap(find.text('photo.png'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Send for server check'));
      await tester.tap(find.text('Send for server check'));
      await tester.pumpAndSettle();
      expect(repository.checks, 1);
      const message = 'Photo not checked. Try again.';
      expect(find.text(message), findsOneWidget);
      expect(message.split(' ').length, lessThanOrEqualTo(8));
      expect(message.length, lessThanOrEqualTo(55));
      expect(
        tester.widget<Text>(find.text(message)).data,
        isNot(
          matches(
            RegExp(
              r'\b(Intake queue|main Queue|derivative|server offset|offset|classification|checksum|SHA-256|preflight|server check|codec|collection profile|runtime|batch|upload handle|Not calibrated|failed|invalid|please|sorry|we)\b',
              caseSensitive: false,
            ),
          ),
        ),
      );
      expect(
        find.textContaining('The server check did not run.'),
        findsNothing,
      );
      expect(tester.takeException(), isNull);
    },
  );

  final refusals = <String, XFile Function()>{
    'Empty file. Choose another.': () =>
        XFile.fromData(Uint8List(0), path: 'empty.png', name: 'empty.png'),
    'Over 25 MB. Choose a smaller photo.': _OversizedPhoto.new,
    'Use JPEG, PNG, HEIC, TIFF or DNG.': () => XFile.fromData(
      Uint8List.fromList([1]),
      path: 'notes.txt',
      name: 'notes.txt',
    ),
    'Could not read this photo. Choose it again.': _UnreadablePhoto.new,
  };
  for (final refusal in refusals.entries) {
    testWidgets('local refusal uses catalogue: ${refusal.key}', (tester) async {
      await _pump(tester, _app(TestRepository(), files: [refusal.value()]));
      await chooseFiles(tester);
      expect(find.text(refusal.key), findsOneWidget);
      expect(uploadButton, findsNothing);
      final primary = _visibleText(tester).join(' ');
      expect(
        primary,
        isNot(
          matches(
            RegExp(
              r'\b(Intake queue|main Queue|derivative|server offset|offset|classification|checksum|SHA-256|preflight|server check|codec|collection profile|runtime|batch|upload handle|Not calibrated|failed|invalid|please|sorry|we)\b',
              caseSensitive: false,
            ),
          ),
        ),
      );
    });
  }
}
