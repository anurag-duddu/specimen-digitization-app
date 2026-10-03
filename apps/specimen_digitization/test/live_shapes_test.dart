// The shapes a live collection produces, on the screens that have to hold
// them (`docs/execution/FRONT_END_REFACTOR.md` section 3I, slot B3, item 2).
//
// Each shape is sent through `ApiSpecimenRepository` first, so the record on
// screen is the one the client's own parse built, and is then measured at the
// phone and at the review desk: nothing overflows, and the words are the ones
// the reviewer is owed rather than a number standing in for an absence.
//
// None of the bytes are real. Every fixture carries the evidence it was
// shaped from in its own `evidence` field; `live_shapes_harness.dart` says
// why that is the honest form here.

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';
import 'package:specimen_digitization/src/widgets/field_row.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'live_shapes_harness.dart';
import 'ui_finders.dart';
import 'workbench_harness.dart' show scrollAndTap;

/// Diff text uses Text.rich; preserve the complete literal when reading the UI.
List<String> renderedText(WidgetTester tester) => tester
    .widgetList<Text>(find.byType(Text))
    .map((text) => text.data ?? text.textSpan?.toPlainText() ?? '')
    .where((value) => value.isNotEmpty)
    .toList();

void main() {
  String recordRoute(Specimen record) =>
      AppRoutes.specimenOf(encodeCollectionKey(liveShapeCollection), record.id);
  final String queueRoute = AppRoutes.queueOf(
    encodeCollectionKey(liveShapeCollection),
  );

  /// Runs [body] at the phone and at the review desk.
  void atEveryWindow(
    String description,
    Future<void> Function(WidgetTester tester, String window, Size size) body,
  ) {
    liveShapeWindows.forEach((String window, Size size) {
      testWidgets('$description at $window', (WidgetTester tester) async {
        collectLayoutErrors();
        await body(tester, window, size);
        expectNoOverflow('$description at $window');
      });
    });
  }

  group('twelve regions, two readers, every region in disagreement', () {
    atEveryWindow('the record screen holds twelve regions', (
      WidgetTester tester,
      String window,
      Size size,
    ) async {
      final Specimen record = await liveShapeRecord(
        liveShapeWire('twelve-regions-two-readers.json'),
      );
      expect(record.regions, hasLength(12));
      expect(record.observations, hasLength(24));
      await pumpLiveShape(
        tester,
        window: size,
        repository: LiveShapeRepository(record),
        location: recordRoute(record),
      );
      await tester.tap(uiRecordView('Label review'));
      await tester.pumpAndSettle();
      await pickUiSelect(tester, 'Label', 'Label 1');
      final List<String> words = renderedText(tester);

      // Both readers are named on every reading, never one merged answer.
      expect(words.where((String w) => w == 'gemma-3-27b-it'), isNotEmpty);
      expect(words.where((String w) => w == 'qwen2.5-vl-72b'), isNotEmpty);

      // Each disagreement is counted rather than coloured
      // (design/00-north-star.md, "never color alone").
      expect(
        words.where((String w) => w.startsWith('Differs in ')),
        isNotEmpty,
        reason: 'a reading that differs has to say so in words',
      );

      // The concise reader name never replaces its producer provenance.
      for (final model in ['gemma-3-27b-it', 'qwen2.5-vl-72b']) {
        await scrollAndTap(
          tester,
          uiIconButton('How this reading was produced, Label 1, $model'),
        );
        expect(find.text(model), findsWidgets);
        await tester.tap(uiButton('Close'));
        await tester.pumpAndSettle();
      }
      await pickUiSelect(tester, 'Label', 'All labels');
      final selector = tester.widget<UiSelect<String>>(uiSelect('Label'));
      expect(selector.options, hasLength(13));
      expect(
        renderedText(
          tester,
        ).where((word) => word == '2 model results · Differences to review'),
        hasLength(12),
      );
    });
  });

  group('a label transcription of four hundred characters', () {
    atEveryWindow('the record screen holds the whole transcription', (
      WidgetTester tester,
      String window,
      Size size,
    ) async {
      final Json document = liveShapeDocument('long-label-transcription.json');
      final Specimen record = await liveShapeRecord(
        document['workspace_response'] as Json,
      );
      final String reading =
          record.observations.first['literal_text'] as String;
      expect(reading, hasLength(400));
      expect(document['character_count'], 400);

      await pumpLiveShape(
        tester,
        window: size,
        repository: LiveShapeRepository(record),
        location: recordRoute(record),
      );

      // The whole reading is on screen, not an ellipsis of it: a
      // transcription is content, and content wraps (11 section 3.3).
      await tester.tap(uiRecordView('Label review'));
      await tester.pumpAndSettle();
      await pickUiSelect(tester, 'Label', 'Label 1');
      expect(
        renderedText(tester).where((String w) => w == reading),
        isNotEmpty,
        reason: 'the four hundred character reading is truncated or missing',
      );

      // The measured comparison remains available in its evidence disclosure.
      await scrollAndTap(tester, find.text('Comparison evidence'));
      expect(
        renderedText(
          tester,
        ).where((String w) => w.contains('Difference fraction: 0.0325')),
        isNotEmpty,
      );
    });
  });

  group('a photograph of six thousand by four thousand pixels', () {
    atEveryWindow('the decode is bounded by the window, not by the original', (
      WidgetTester tester,
      String window,
      Size size,
    ) async {
      final Specimen record = await liveShapeRecord(
        liveShapeWire('large-photograph.json'),
      );
      final Json asset = record.assets.first;
      expect(asset['width'], 6000);
      expect(asset['height'], 4000);

      await pumpLiveShape(
        tester,
        window: size,
        repository: LiveShapeRepository(record),
        location: recordRoute(record),
      );

      final Iterable<Image> images = tester.widgetList<Image>(
        find.byType(Image),
      );
      expect(images, isNotEmpty, reason: 'the photograph is not on screen');
      for (final Image image in images) {
        final ImageProvider<Object> provider = image.image;
        expect(
          provider,
          isA<ResizeImage>(),
          reason:
              'a source photograph decoded at its own size holds '
              '${asset['width']} by ${asset['height']} times four bytes',
        );
        final int? decodeWidth = (provider as ResizeImage).width;
        expect(decodeWidth, isNotNull);
        expect(
          decodeWidth,
          lessThanOrEqualTo(size.width.ceil()),
          reason: 'nothing can be shown wider than the window',
        );
        expect(decodeWidth, lessThan(asset['width'] as int));
      }
    });

    testWidgets('the pipeline really decodes at the bound', (
      WidgetTester tester,
    ) async {
      final Specimen record = await liveShapeRecord(
        liveShapeWire('large-photograph.json'),
      );
      await pumpLiveShape(
        tester,
        window: liveShapeWindows['compact']!,
        repository: LiveShapeRepository(record),
        location: recordRoute(record),
      );
      final ImageProvider<Object> provider = tester
          .widgetList<Image>(find.byType(Image))
          .first
          .image;

      // Not the widget's argument: the pixels the engine actually produced.
      // The checked in photograph is a thousand pixels wide, so a bound of
      // three hundred and ninety has to move it.
      late final ImageInfo decoded;
      await tester.runAsync(() async {
        final Completer<ImageInfo> settled = Completer<ImageInfo>();
        final ImageStream stream = provider.resolve(ImageConfiguration.empty);
        late final ImageStreamListener listener;
        listener = ImageStreamListener((ImageInfo info, bool _) {
          if (!settled.isCompleted) settled.complete(info);
          stream.removeListener(listener);
        });
        stream.addListener(listener);
        decoded = await settled.future;
      });
      addTearDown(decoded.dispose);
      expect(
        decoded.image.width,
        lessThanOrEqualTo(liveShapeWindows['compact']!.width.ceil()),
      );
    });
  });

  group('a record with every measurement missing', () {
    atEveryWindow('every absence keeps its own word', (
      WidgetTester tester,
      String window,
      Size size,
    ) async {
      final Specimen record = await liveShapeRecord(
        liveShapeWire('no-measurements.json'),
      );
      expect(record.disposition, isNull);
      expect(record.data['risk'], isNull);
      expect(
        (record.data['run'] as Json)['usage']['actual_cost_micros'],
        isNull,
      );

      await pumpLiveShape(
        tester,
        window: size,
        repository: LiveShapeRepository(record),
        location: recordRoute(record),
      );
      // Reach the data tab and its progressive field disclosure at either
      // window size before inspecting the rendered abstentions.
      await tester.ensureVisible(find.text('Specimen data'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Specimen data'));
      await tester.pumpAndSettle();
      final row = find.byType(FieldRow).first;
      final disclosure = find.descendant(
        of: row,
        matching: find.byType(UiDisclosure),
      );
      await scrollAndTap(
        tester,
        find
            .descendant(
              of: disclosure,
              matching: find.byWidgetPredicate((widget) => widget is Pressable),
            )
            .first,
      );
      final List<String> words = renderedText(tester);

      // Unknown is a state with a name, not a blank and not a zero
      // (design/00-north-star.md, principle 2).
      expect(words.where((String w) => w == 'Unknown'), isNotEmpty);
      expect(words.where((String w) => w == 'As written'), isNotEmpty);
      expect(
        find.descendant(of: row, matching: find.text('Unknown')),
        findsWidgets,
      );

      // The one thing this screen must never do.
      for (final String word in words) {
        expect(
          word,
          isNot(anyOf('0', '0.0', '0 %', 'None', 'null')),
          reason: 'a missing measurement rendered as a value',
        );
      }
    });
  });

  group('a queue of a thousand rows', () {
    atEveryWindow(
      'the queue retains its loaded page and builds only the viewport cache',
      (WidgetTester tester, String window, Size size) async {
        final Specimen record = await liveShapeRecord(
          liveShapeWire('no-measurements.json'),
        );
        final List<Specimen> rows = liveShapeQueue(1000);
        expect(rows, hasLength(1000));
        await pumpLiveShape(
          tester,
          window: size,
          repository: LiveShapeRepository(record, queue: rows),
          location: queueRoute,
        );

        // The current header is search and review filters. Check the actual
        // loaded page without inventing a server-authoritative total count.
        final controller = WorkspaceScope.read(
          tester.element(find.byType(QueueRow).first),
        );
        expect(controller.items, hasLength(1000));
        expect(
          controller.items.map((item) => item.id),
          rows.map((item) => item.id),
        );

        final rowFinder = find.byType(QueueRow);
        final int built = rowFinder.evaluate().length;
        expect(built, greaterThan(0));
        final list = find.descendant(
          of: find.byKey(const PageStorageKey<String>('queue-list')),
          matching: find.byType(SliverList),
        );
        final RenderSliverList sliver = tester.renderObject<RenderSliverList>(
          list,
        );
        final double minimumHeight = rowFinder
            .evaluate()
            .map((element) => (element.renderObject! as RenderBox).size.height)
            .reduce((a, b) => a < b ? a : b);
        expect(minimumHeight, greaterThan(0));
        final int cacheBound =
            (sliver.constraints.remainingCacheExtent / minimumHeight).ceil() +
            1;
        expect(
          built,
          lessThanOrEqualTo(cacheBound),
          reason:
              'Only the viewport cache plus its partial edge row may be built.',
        );
        expect(built, lessThan(rows.length));

        // It scrolls, and scrolling does not run out of rows.
        await tester.drag(find.byType(QueueRow).first, const Offset(0, -2000));
        await tester.pump();
        expect(find.byType(QueueRow), findsWidgets);
      },
    );
  });
}
