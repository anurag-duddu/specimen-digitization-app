// Controlled UI evidence. No provider, file picker or camera is accessed.
import 'dart:async';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_screen.dart';
import 'package:specimen_digitization/src/screens/intake/intake_import_workspace.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'bulk_intake_test.dart' show BulkFixtureRepository;
import 'capture_screen_test.dart' show FakeCaptureCamera;
import 'golden/golden_harness.dart';

class SourceChoiceRepository extends BulkFixtureRepository {
  SourceChoiceRepository() : super(2);
  final List<String> writes = [];
  final List<String> providerReads = [];

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
    if (method != 'GET') writes.add('$method $path');
    if (path == '/connections') {
      providerReads.add(query?['provider'] ?? '');
      return {'items': <Json>[]};
    }
    if (path == '/sources') return {'items': <Json>[]};
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

Finder sourceButton(String label) => find.widgetWithText(UiButton, label);

Future<void> openSavedSourceChoices(
  WidgetTester tester, {
  required Size size,
  double scale = 1,
  SourceChoiceRepository? repository,
}) async {
  await pumpGoldenApp(
    tester,
    window: size,
    brightness: Brightness.dark,
    textScale: scale,
    location: goldenIntakeLocation,
    repository: repository ?? SourceChoiceRepository(),
  );
  await tester.ensureVisible(sourceButton('Add photos'));
  await tester.tap(sourceButton('Add photos'));
  await tester.pumpAndSettle();
}

class _RecordingController extends BulkIntakeController {
  _RecordingController(SourceChoiceRepository repository)
    : super(
        repository: repository,
        scope: const CollectionScope(
          organizationId: 'org',
          collectionId: 'insects',
          name: 'Insects',
        ),
        userId: 'owner',
      ) {
    loading = false;
    draft = IntakeDraft(repository.draft);
    items = repository.photos.map(IntakeDraftItem.new).toList();
  }

  final List<List<XFile>> additions = [];

  @override
  Future<void> addFiles(
    List<XFile> files, {
    bool camera = false,
    bool sensitive = false,
    String? replacesId,
    Object? captureAttempt,
  }) async => additions.add(files);
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  for (final size in [
    const Size(320, 740),
    const Size(390, 844),
    const Size(768, 1024),
    const Size(1440, 900),
  ]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets('saved source choices fit $size at $scale', (tester) async {
        await openSavedSourceChoices(tester, size: size, scale: scale);
        final primaryLabel = size.width < WindowClass.mediumMin
            ? 'Take photos'
            : 'Choose files';
        final alternative = primaryLabel == 'Take photos'
            ? 'Choose files'
            : 'Take photos';
        expect(
          tester.widget<UiButton>(sourceButton(primaryLabel)).variant,
          UiButtonVariant.primary,
        );
        expect(
          tester.widget<UiButton>(sourceButton(alternative)).variant,
          UiButtonVariant.secondary,
        );
        expect(
          find.byType(
            WindowArrangement.fromSize(
                  size,
                  textScaler: TextScaler.linear(scale),
                ).isStacked
                ? UiSheet
                : UiDialog,
          ),
          findsOneWidget,
        );
        expect(find.widgetWithText(UiListRow, 'Google Drive'), findsNothing);
        final semantics = tester.ensureSemantics();
        await tester.pump();
        try {
          expect(find.bySemanticsLabel('Close add photos'), findsOneWidget);
        } finally {
          semantics.dispose();
        }
        expect(sourceButton('Close').hitTestable(), findsOneWidget);
        for (final label in [primaryLabel, alternative]) {
          final action = sourceButton(label);
          await tester.ensureVisible(action);
          await tester.pumpAndSettle();
          expect(action.hitTestable(), findsOneWidget);
          expect(tester.getSize(action).height, greaterThanOrEqualTo(48));
        }
        await tester.ensureVisible(find.text('Import from a source'));
        await tester.tap(find.text('Import from a source'));
        await tester.pumpAndSettle();
        for (final label in [
          'Google Drive',
          'Dropbox',
          'Storage',
          'Import links',
        ]) {
          final row = find.widgetWithText(UiListRow, label);
          await tester.ensureVisible(row);
          await tester.pumpAndSettle();
          expect(row.hitTestable(), findsOneWidget);
          expect(tester.getSize(row).height, greaterThanOrEqualTo(48));
        }
        expect(find.text('Registered storage'), findsNothing);
        expect(sourceButton('Close').hitTestable(), findsOneWidget);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
      });
    }
  }

  for (final size in [const Size(390, 844), const Size(1440, 900)]) {
    testWidgets('all chooser exits retain draft and restore focus at $size', (
      tester,
    ) async {
      final repository = SourceChoiceRepository();
      await pumpGoldenApp(
        tester,
        window: size,
        brightness: Brightness.light,
        location: goldenIntakeLocation,
        repository: repository,
      );
      final original = repository.photos.map(Json.from).toList();
      tester
          .widget<UiPhotoTile>(find.byType(UiPhotoTile).first)
          .onSelected(true);
      await tester.pumpAndSettle();
      for (final exit in ['Close', 'Escape', 'Back', 'Barrier']) {
        final trigger = sourceButton('Add photos');
        await tester.ensureVisible(trigger);
        final triggerFocus = Focus.of(
          tester.element(
            find.descendant(of: trigger, matching: find.text('Add photos')),
          ),
        );
        triggerFocus.requestFocus();
        await tester.pump();
        expect(triggerFocus.hasPrimaryFocus, isTrue);
        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pumpAndSettle();
        expect(sourceButton('Close').hitTestable(), findsOneWidget);
        switch (exit) {
          case 'Close':
            await tester.tap(sourceButton('Close'));
          case 'Escape':
            await tester.sendKeyEvent(LogicalKeyboardKey.escape);
          case 'Back':
            await tester.binding.handlePopRoute();
          case 'Barrier':
            await tester.tapAt(const Offset(2, 2));
        }
        await tester.pumpAndSettle();
        expect(sourceButton('Close'), findsNothing);
        expect(triggerFocus.hasPrimaryFocus, isTrue, reason: exit);
        expect(find.byType(CaptureScreen), findsNothing);
        expect(find.byType(IntakeImportWorkspace), findsNothing);
        expect(repository.photos, original);
        expect(repository.revision, 1);
        expect(repository.writes, isEmpty);
        expect(repository.providerReads, isEmpty);
        expect(repository.submitted, isFalse);
        expect(
          tester
              .widgetList<UiPhotoTile>(find.byType(UiPhotoTile))
              .where((tile) => tile.selected),
          hasLength(1),
        );
        expect(tester.takeException(), isNull);
      }
      await tester.pumpWidget(const SizedBox.shrink());
    });

    for (final source in [
      ('Google Drive', 'google_drive'),
      ('Dropbox', 'dropbox'),
      ('Storage', 'storage'),
      ('Import links', 'url'),
    ]) {
      testWidgets(
        '${source.$1} replaces chooser and preserves draft at $size',
        (tester) async {
          final repository = SourceChoiceRepository();
          await openSavedSourceChoices(
            tester,
            size: size,
            repository: repository,
          );
          await tester.tap(find.text('Import from a source'));
          await tester.pumpAndSettle();
          final row = find.widgetWithText(UiListRow, source.$1);
          await tester.ensureVisible(row);
          await tester.tap(row);
          await tester.pumpAndSettle();
          expect(sourceButton('Close'), findsNothing);
          final workspace = tester.widget<IntakeImportWorkspace>(
            find.byType(IntakeImportWorkspace),
          );
          expect(workspace.provider, source.$2);
          expect(workspace.controller.visible, hasLength(2));
          expect(workspace.controller.draft?.id, 'draft');
          expect(repository.writes, isEmpty);
          await tester.sendKeyEvent(LogicalKeyboardKey.escape);
          await tester.pumpAndSettle();
          expect(find.byType(IntakeImportWorkspace), findsNothing);
          expect(sourceButton('Add photos').hitTestable(), findsOneWidget);
          expect(find.byType(UiPhotoTile), findsNWidgets(2));
          expect(repository.submitted, isFalse);
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox.shrink());
        },
      );
    }
  }

  for (final acquisition in ['Choose files', 'Take photos']) {
    testWidgets('$acquisition closes chooser before existing acquisition', (
      tester,
    ) async {
      final repository = SourceChoiceRepository();
      final controller = _RecordingController(repository);
      addTearDown(controller.dispose);
      final selection = Completer<List<XFile>>();
      var pickerCalls = 0;
      var cameraCalls = 0;
      await pumpGoldenRoute(
        tester,
        window: const Size(390, 844),
        brightness: Brightness.light,
        child: BulkIntakeScreen(
          repository: repository,
          scope: controller.scope,
          userId: controller.userId,
          controller: controller,
          onViewSpecimens: () {},
          pickFiles: () {
            pickerCalls++;
            return selection.future;
          },
          cameraFactory: () async {
            cameraCalls++;
            return FakeCaptureCamera(unavailable: CaptureUnavailable.noCamera);
          },
        ),
      );
      await tester.tap(sourceButton('Add photos'));
      await tester.pumpAndSettle();
      await tester.tap(sourceButton(acquisition));
      await tester.pumpAndSettle();
      expect(sourceButton('Close'), findsNothing);
      if (acquisition == 'Choose files') {
        expect(pickerCalls, 1);
        expect(cameraCalls, 0);
        expect(controller.additions, isEmpty);
        selection.complete([]);
        await tester.pumpAndSettle();
        expect(controller.additions, hasLength(1));
        expect(controller.additions.single, isEmpty);
      } else {
        expect(cameraCalls, 1);
        expect(pickerCalls, 0);
        expect(find.byType(CaptureScreen), findsOneWidget);
        await tester.binding.handlePopRoute();
        await tester.pumpAndSettle();
        expect(find.byType(CaptureScreen), findsNothing);
        expect(controller.additions, isEmpty);
      }
      expect(controller.draft?.id, 'draft');
      expect(controller.visible, hasLength(2));
      expect(repository.writes, isEmpty);
      expect(sourceButton('Add photos').hitTestable(), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
