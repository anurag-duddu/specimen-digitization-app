import 'dart:io';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/caveat_text.dart';
import 'package:specimen_digitization/src/models.dart';
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
    expect(find.text('0 of 2 accepted'), findsOneWidget);
    await submitBatch(tester);
    expect(repo.attempts, 1);
  });

  const scope = CollectionScope(
    organizationId: 'org',
    collectionId: 'insects',
    name: 'Synthetic insects',
  );
  final bytes = File(
    'test/fixtures/synthetic-wide-label.png',
  ).readAsBytesSync();
  testWidgets(
    'interrupted camera recovery requires the same user and collection and never uploads automatically',
    (tester) async {
      SharedPreferences.setMockInitialValues({
        'pending-camera-owner-v1': 'owner:org/insects',
      });
      var recovered = 0;
      Widget app(String user) => MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: IntakeScreen(
            key: ValueKey(user),
            repository: TestRepository(),
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
      await tester.runAsync(() async {
        await tester.pumpWidget(app('owner'));
        await Future<void>.delayed(const Duration(milliseconds: 100));
      });
      await tester.pumpAndSettle();
      expect(recovered, 1);
      await tester.ensureVisible(find.text('recovered.png'));
      await tester.pumpAndSettle();
      expect(find.text('recovered.png'), findsOneWidget);
      expect(
        find.textContaining('Recovered an interrupted photograph'),
        findsOneWidget,
      );
      // A recovered photograph is queued, never sent: the batch confirmation
      // was cleared by the file arriving.
      await tester.ensureVisible(uploadButton);
      await tester.pumpAndSettle();
      expect(buttonEnabled(tester, uploadButton), isFalse);
      expect(
        (await SharedPreferences.getInstance()).containsKey(
          'pending-camera-owner-v1',
        ),
        isFalse,
      );
    },
  );
  testWidgets('choosing another file resets the manual quality confirmation', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: IntakeScreen(
            repository: TestRepository(),
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
    await confirmBatch(tester);
    expect(batchConfirmed(tester), isTrue);
    await chooseFiles(tester);
    expect(batchConfirmed(tester), isFalse);
    await tester.ensureVisible(find.text('chosen.png'));
    await tester.pumpAndSettle();
    expect(find.text('chosen.png'), findsOneWidget);
    expect(find.text('Not calibrated'), findsOneWidget);
  });
  testWidgets(
    'server preflight requires explicit transmission and leaves quality confirmation unchecked',
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
      await tester.ensureVisible(confirmCheckbox);
      await tester.pumpAndSettle();
      expect(batchConfirmed(tester), isFalse);
    },
  );
}
