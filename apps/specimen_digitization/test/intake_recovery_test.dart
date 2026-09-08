import 'dart:io';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
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

void main() {
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
      await tester.scrollUntilVisible(find.text('recovered.png'), 300);
      expect(find.text('recovered.png'), findsOneWidget);
      expect(
        find.textContaining('Recovered an interrupted camera photograph'),
        findsOneWidget,
      );
      await tester.scrollUntilVisible(
        find.text('Upload / resume selected files'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      final upload = tester.widget<FilledButton>(
        find.ancestor(
          of: find.text('Upload / resume selected files'),
          matching: find.byWidgetPredicate((w) => w is FilledButton),
        ),
      );
      expect(upload.onPressed, isNull);
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
    await tester.tap(find.text('I checked framing and readability'));
    await tester.pump();
    await tester.runAsync(() async {
      await tester.tap(find.text('Choose files'));
      await Future<void>.delayed(const Duration(milliseconds: 100));
    });
    await tester.pumpAndSettle();
    final checked = tester
        .widget<CheckboxListTile>(find.byType(CheckboxListTile))
        .value;
    await tester.scrollUntilVisible(find.text('chosen.png'), 300);
    expect(find.text('chosen.png'), findsOneWidget);
    expect(checked, isFalse);
    expect(find.text('Measured thumbnail · uncalibrated'), findsOneWidget);
  });
  testWidgets(
    'server preflight requires explicit transmission and leaves quality confirmation unchecked',
    (tester) async {
      SharedPreferences.setMockInitialValues({});
      final repository = PreflightRepository();
      await tester.pumpWidget(
        MaterialApp(
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
      await tester.runAsync(() async {
        await tester.tap(find.text('Choose files'));
        await Future<void>.delayed(const Duration(milliseconds: 100));
      });
      await tester.pumpAndSettle();
      expect(repository.checks, 0);
      expect(repository.uploads, 0);
      await tester.scrollUntilVisible(
        find.text('Send image for server preflight'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Send image for server preflight'));
      await tester.pumpAndSettle();
      expect(repository.checks, 1);
      expect(repository.uploads, 0);
      expect(
        find.textContaining(
          'Changing this image format will not resolve that block',
        ),
        findsOneWidget,
      );
      await tester.scrollUntilVisible(
        find.byType(CheckboxListTile),
        -300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      expect(
        tester.widget<CheckboxListTile>(find.byType(CheckboxListTile)).value,
        isFalse,
      );
    },
  );
}
