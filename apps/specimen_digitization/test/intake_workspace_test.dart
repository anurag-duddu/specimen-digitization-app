// Controlled UI/transport evidence. These fixtures are not provider acceptance.
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_import_workspace.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'bulk_intake_test.dart' show BulkFixtureRepository;
import 'golden/golden_harness.dart';

class ImportFixture extends BulkFixtureRepository {
  ImportFixture({this.count = 100, this.connected = true}) : super(0);
  final int count;
  final bool connected;
  int sourceReads = 0;
  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    if (path == '/connections') {
      sourceReads++;
      return {
        'items': connected
            ? [
                {
                  'id': query?['provider'],
                  'provider': query?['provider'],
                  'state': 'connected',
                  'access': query?['provider'] == 'google_drive'
                      ? 'files'
                      : 'folders',
                  'account_id': 'test-owner',
                  'account_label': 'researcher@example.test',
                },
              ]
            : <Json>[],
      };
    }
    if (path.endsWith('/browse')) {
      sourceReads++;
      return {
        'items': [
          for (var i = 0; i < count; i++)
            {
              'id': 'file-$i',
              'filename': 'specimen-${(i + 1).toString().padLeft(3, '0')}.jpg',
              'media_type': 'image/jpeg',
              'supported': true,
              'source': {
                'provider': 'dropbox',
                'connection_id': 'dropbox',
                'object_id': 'file-$i',
                'version': '1',
              },
            },
          {
            'id': 'unavailable',
            'filename': 'restricted-photo.jpg',
            'supported': false,
            'error': {
              'message': 'Ask the owner for access.',
              'action': 'file_access',
            },
          },
        ],
      };
    }
    if (path == '/sources') return {'items': <Json>[]};
    if (path == '/resolve') {
      if ((body?['url'] as String).contains('missing')) {
        throw const ApiFailure(
          'This link has expired. Check the link and try again.',
          code: 'expired_link',
          details: {'action': 'retry'},
        );
      }
      return {
        'items': [
          {
            'id': 'linked-photo',
            'filename': 'specimen-001.jpg',
            'media_type': 'image/jpeg',
            'supported': true,
            'source': {'provider': 'url', 'url': body?['url']},
          },
        ],
      };
    }
    return super.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
      bytes: bytes,
      offset: offset,
    );
  }
}

Future<void> openWorkspace(
  WidgetTester tester,
  ImportFixture repo, {
  Size size = const Size(1440, 900),
  Brightness brightness = Brightness.light,
  double scale = 1,
  String source = 'Dropbox',
}) async {
  await pumpGoldenApp(
    tester,
    window: size,
    brightness: brightness,
    textScale: scale,
    location: goldenIntakeLocation,
    repository: repo,
  );
  await tester.ensureVisible(find.widgetWithText(UiButton, source));
  await tester.tap(find.widgetWithText(UiButton, source));
  await tester.pumpAndSettle();
  expect(find.byType(IntakeImportWorkspace), findsOneWidget);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  for (final size in [const Size(390, 844), const Size(1440, 900)]) {
    for (final state in [
      'drive-connect',
      'drive-connected',
      'storage-empty',
      'links-partial',
    ]) {
      testWidgets('integration state $state $size', (tester) async {
        await openWorkspace(
          tester,
          ImportFixture(connected: state != 'drive-connect'),
          size: size,
          source: state.startsWith('drive')
              ? 'Google Drive'
              : state == 'storage-empty'
              ? 'Storage'
              : 'Import links',
        );
        if (state == 'links-partial') {
          await tester.enterText(
            find.descendant(
              of: find.widgetWithText(UiField, 'Photo or folder links'),
              matching: find.byType(EditableText),
            ),
            'https://images.example/photo.jpg\nhttps://images.example/missing.jpg',
          );
          await tester.tap(find.widgetWithText(UiButton, 'Review links'));
          await tester.pumpAndSettle();
          expect(find.text('Add 1 photo').hitTestable(), findsOneWidget);
        } else if (state == 'drive-connect') {
          expect(
            find.text('Connect Google Drive').hitTestable(),
            findsOneWidget,
          );
        } else if (state == 'drive-connected') {
          expect(find.text('Choose photos').hitTestable(), findsOneWidget);
        } else {
          expect(find.textContaining('No storage locations'), findsOneWidget);
        }
        expect(tester.takeException(), isNull);
        await expectGoldenFinder(
          tester,
          find.byType(MaterialApp),
          'intake-import-$state-${size.width.toInt()}',
        );
      });
    }
  }
  for (final size in [
    const Size(390, 844),
    const Size(768, 1024),
    const Size(1440, 900),
  ]) {
    for (final brightness in [Brightness.light, Brightness.dark]) {
      testWidgets('cloud import full shell $size ${brightness.name}', (
        tester,
      ) async {
        await openWorkspace(
          tester,
          ImportFixture(),
          size: size,
          brightness: brightness,
        );
        await tester.tap(
          find.widgetWithText(UiButton, 'Select visible photos'),
        );
        await tester.pumpAndSettle();
        expect(find.text('Add 100 photos').hitTestable(), findsOneWidget);
        expect(find.byType(UiCheckbox).evaluate().length, lessThan(30));
        expect(tester.takeException(), isNull);
        await expectGoldenFinder(
          tester,
          find.byType(MaterialApp),
          'intake-import-${size.width.toInt()}-${brightness.name}',
        );
      });
    }
  }
  testWidgets('500 selection is virtualized and terminal source reads stop', (
    tester,
  ) async {
    final repo = ImportFixture(count: 500);
    await openWorkspace(tester, repo);
    await tester.tap(find.widgetWithText(UiButton, 'Select visible photos'));
    await tester.pumpAndSettle();
    expect(find.text('Add 500 photos').hitTestable(), findsOneWidget);
    expect(find.byType(UiCheckbox).evaluate().length, lessThan(30));
    final reads = repo.sourceReads;
    await tester.pump(const Duration(seconds: 60));
    expect(repo.sourceReads, reads);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets(
    'filter selection preserves hidden choices and reopening restores them',
    (tester) async {
      final repo = ImportFixture(count: 10);
      await openWorkspace(tester, repo);
      final filter = find.descendant(
        of: find.widgetWithText(UiField, 'Filter loaded files'),
        matching: find.byType(EditableText),
      );
      await tester.enterText(filter, '001');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(UiButton, 'Select visible photos'));
      await tester.pumpAndSettle();
      expect(find.text('Add 1 photo'), findsOneWidget);
      await tester.enterText(filter, '002');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(UiButton, 'Select visible photos'));
      await tester.pumpAndSettle();
      expect(find.text('Add 2 photos'), findsOneWidget);
      await tester.tap(
        find.byWidgetPredicate(
          (w) => w is UiIconButton && w.semanticsLabel == 'Close photo sources',
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(UiButton, 'Dropbox'));
      await tester.pumpAndSettle();
      expect(find.text('Add 2 photos'), findsOneWidget);
      await tester.enterText(filter, '');
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<UiCheckbox>(
              find.widgetWithText(UiCheckbox, 'specimen-001.jpg'),
            )
            .value,
        isTrue,
      );
      expect(
        tester
            .widget<UiCheckbox>(
              find.widgetWithText(UiCheckbox, 'specimen-002.jpg'),
            )
            .value,
        isTrue,
      );
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets('phone 200 percent text keeps selection and close reachable', (
    tester,
  ) async {
    await openWorkspace(
      tester,
      ImportFixture(count: 10),
      size: const Size(390, 844),
      scale: 2,
    );
    final select = find.widgetWithText(UiButton, 'Select visible photos');
    await tester.ensureVisible(select);
    await tester.pumpAndSettle();
    await tester.tap(select);
    await tester.pumpAndSettle();
    expect(find.text('Add 10 photos').hitTestable(), findsOneWidget);
    expect(
      find
          .byWidgetPredicate(
            (w) =>
                w is UiIconButton && w.semanticsLabel == 'Close photo sources',
          )
          .hitTestable(),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
    await expectGoldenFinder(
      tester,
      find.byType(MaterialApp),
      'intake-import-390-text2',
    );
  });
}
