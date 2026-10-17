import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_screen.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'capture_screen_test.dart'
    show FakeCaptureCamera, waitForCameraCondition;
import 'golden/golden_harness.dart';
import 'widgets/harness.dart';

/// Deterministic transport fixture. Provider and physical-device acceptance
/// are deliberately outside these UI tests.
class BulkFixtureRepository extends GoldenRepository
    implements BulkIntakeRepository {
  BulkFixtureRepository(int count, {this.state = 'ready'})
    : photos = List.generate(
        count,
        (i) => <String, dynamic>{
          'id': 'photo-$i',
          'filename': 'specimen-${i + 1}.png',
          'state': state,
          'photo_sensitive': false,
          'included': true,
          'removed': false,
          'revision': 1,
          if (state == 'needs_attention')
            'error': {'message': 'Choose the original photo again.'},
        },
      );
  final String state;
  final List<Json> photos;
  bool submitted = false;
  int revision = 1, previewCalls = 0;
  List<String> submittedIds = [];
  Json get draft => {
    'id': 'draft',
    'revision': revision,
    'state': submitted ? 'submitted' : 'draft',
    'name': 'Photo batch',
    'created_at': '2026-10-17',
  };
  Json get batch => {
    'id': 'submission',
    'total': submittedIds.length,
    'counts': {'sent': submittedIds.length},
    'entries': submittedIds.map((id) => {'id': id}).toList(),
  };
  @override
  Future<Uint8List> intakePreview(
    CollectionScope scope,
    String itemId, {
    bool full = false,
  }) async {
    previewCalls++;
    return goldenPreviewBytes;
  }

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
    Json page(List<Json> rows) {
      final after = int.tryParse(query?['after'] ?? '0') ?? 0;
      final end = (after + 100).clamp(0, rows.length);
      return {
        'items': rows.sublist(after, end),
        'next_cursor': end < rows.length ? end : null,
      };
    }

    if (path == '/capabilities') {
      return {'version': 1, 'worker_configured': true};
    }
    if (path == '/drafts') {
      return {
        'items': photos.isEmpty ? <Json>[] : [draft],
        'next_cursor': null,
      };
    }
    if (path == '/submissions') {
      return {
        'items': submitted ? [batch] : <Json>[],
        'next_cursor': null,
      };
    }
    if (path == '/drafts/draft') return draft;
    if (path == '/drafts/draft/items') return page(photos);
    if (path == '/drafts/draft/edit') {
      for (final photo in photos.where(
        (p) => (body!['item_ids'] as List).contains(p['id']),
      )) {
        switch (body!['action']) {
          case 'remove':
            photo['removed'] = true;
          case 'restore':
            photo['removed'] = false;
          case 'exclude':
            photo['included'] = false;
          case 'include':
            photo['included'] = true;
          case 'sensitive':
            photo['photo_sensitive'] = body['value'];
        }
      }
      revision++;
      return draft;
    }
    if (path == '/drafts/draft/submit') {
      submitted = true;
      submittedIds = List<String>.from(body!['item_ids'] as List);
      return batch;
    }
    if (path == '/submissions/submission') return batch;
    if (path == '/submissions/submission/items') {
      return page(
        submittedIds
            .map(
              (id) => <String, dynamic>{
                'item_id': id,
                'filename': '$id.png',
                'state': 'sent',
              },
            )
            .toList(),
      );
    }
    throw StateError('Unexpected intake request $method $path');
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  for (final size in [
    const Size(390, 844),
    const Size(768, 1024),
    const Size(1440, 900),
  ]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets('bulk review full shell $size text $scale', (tester) async {
        final repo = BulkFixtureRepository(100);
        await pumpGoldenApp(
          tester,
          window: size,
          brightness: Brightness.light,
          textScale: scale,
          location: goldenIntakeLocation,
          repository: repo,
        );
        expect(find.byType(BulkIntakeScreen), findsOneWidget);
        expect(find.text('Submit 100 photos').hitTestable(), findsOneWidget);
        expect(tester.takeException(), isNull);
        await settleImages(tester);
        await expectGoldenFinder(
          tester,
          find.byType(MaterialApp),
          'bulk-intake-${size.width.toInt()}x${size.height.toInt()}-text$scale',
        );
        await tester.pumpWidget(const SizedBox.shrink());
      });
    }
  }
  for (final state in [
    'empty',
    'waiting',
    'needs_attention',
    'inspector',
    'submitted',
  ]) {
    for (final size in [const Size(390, 844), const Size(1440, 900)]) {
      testWidgets('$state full shell at $size with 200% text', (tester) async {
        final repo = BulkFixtureRepository(
          state == 'empty' ? 0 : 20,
          state: ['waiting', 'needs_attention'].contains(state)
              ? state
              : 'ready',
        );
        await pumpGoldenApp(
          tester,
          window: size,
          brightness: Brightness.dark,
          textScale: 2,
          location: goldenIntakeLocation,
          repository: repo,
        );
        if (state == 'inspector') {
          tester.widget<UiPhotoTile>(find.byType(UiPhotoTile).first).onOpen();
          await tester.pumpAndSettle();
        }
        if (state == 'submitted') {
          await tester.tap(find.text('Submit 20 photos'));
          await tester.pumpAndSettle();
        }
        expect(tester.takeException(), isNull);
        await settleImages(tester);
        await expectGoldenFinder(
          tester,
          find.byType(MaterialApp),
          'bulk-intake-$state-${size.width.toInt()}-dark-text2',
        );
        await tester.pumpWidget(const SizedBox.shrink());
      });
    }
  }
  testWidgets(
    '500 thumbnails are virtualized and selection never changes inclusion',
    (tester) async {
      final repo = BulkFixtureRepository(500);
      await pumpGoldenApp(
        tester,
        window: const Size(1440, 900),
        brightness: Brightness.light,
        location: goldenIntakeLocation,
        repository: repo,
      );
      expect(find.text('Submit 500 photos'), findsOneWidget);
      expect(find.byType(UiPhotoTile).evaluate().length, lessThan(100));
      final screen = tester.state(find.byType(BulkIntakeScreen));
      expect(screen.mounted, isTrue);
      final first = find.byType(UiPhotoTile).first;
      final tile = tester.widget<UiPhotoTile>(first);
      tile.onSelected(true);
      await tester.pumpAndSettle();
      expect(find.text('1 selected for editing'), findsOneWidget);
      expect(find.text('Submit 500 photos'), findsOneWidget);
      await tester.tap(find.text('Remove selected'));
      await tester.pumpAndSettle();
      expect(find.text('Submit 499 photos'), findsOneWidget);
      await tester.tap(find.text('Undo removal'));
      await tester.pumpAndSettle();
      expect(find.text('Submit 500 photos'), findsOneWidget);
      expect(repo.submitted, isFalse);
      await tester.tap(find.text('Submit 500 photos'));
      await tester.pumpAndSettle();
      expect(repo.submittedIds.length, 500);
      expect(
        find.text('500 of 500 finished · 500 sent to pipeline'),
        findsOneWidget,
      );
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
  testWidgets(
    'thirty captures remain in viewfinder and wait for retention only',
    (tester) async {
      var count = 0;
      final gate = Completer<void>();
      await pumpComponent(
        tester,
        CaptureScreen(
          camera: () async => FakeCaptureCamera(),
          bulkDraft: true,
          onCapturedDurably: (_) async {
            count++;
            if (count == 1) await gate.future;
          },
        ),
        size: const Size(390, 844),
      );
      await tester.tap(find.byKey(const ValueKey('capture-shutter')));
      await tester.pump();
      await waitForCameraCondition(tester, () => count == 1);
      expect(find.text('Use photo'), findsNothing);
      gate.complete();
      await tester.pumpAndSettle();
      for (var n = 1; n < 30; n++) {
        await tester.tap(find.byKey(const ValueKey('capture-shutter')));
        await tester.pump();
        await waitForCameraCondition(tester, () => count == n + 1);
        await tester.pumpAndSettle();
      }
      expect(find.text('Review 30'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
