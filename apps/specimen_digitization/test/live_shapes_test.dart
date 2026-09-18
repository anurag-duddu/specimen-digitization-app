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
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';
import 'package:specimen_digitization/src/workspace.dart';

import 'live_shapes_harness.dart';

/// How many rows the queue builds for a page of a thousand, today.
///
/// Measured on 2026-09-17 at both windows: five at the phone and six at the
/// tablet, which is what each viewport holds plus the sliver list's own cache
/// extent. It was a thousand. Shrink only: see the comment at the assertion
/// that reads it.
const int eagerQueueRows = 6;

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
      final List<String> words = visibleText(tester);

      // Both readers are named on every reading, never one merged answer.
      expect(words.where((String w) => w == 'qwen2.5-vl-72b'), isNotEmpty);
      expect(words.where((String w) => w == 'gemma-3-27b-it'), isNotEmpty);

      // Each disagreement is counted rather than coloured
      // (design/00-north-star.md, "never color alone").
      expect(
        words.where((String w) => w.startsWith('Differs in ')),
        isNotEmpty,
        reason: 'a reading that differs has to say so in words',
      );

      // Twelve disagreements plus the run's own finding, stated as a number
      // the reviewer can act on rather than as a warning glyph.
      expect(
        words.where((String w) => w.contains('block clearance')),
        isNotEmpty,
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
      expect(
        visibleText(tester).where((String w) => w == reading),
        isNotEmpty,
        reason: 'the four hundred character reading is truncated or missing',
      );

      // The ratio the wire measured is shown as measured, because the
      // fixture carries an alignment status the wire actually sends.
      expect(
        visibleText(
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
      // At the phone the segments sit below the first viewport, which is
      // the composition defect 13 section 0 names and A2 is rebuilding. A
      // shape test scrolls to them rather than asserting the arrangement.
      await tester.ensureVisible(find.text('Fields'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Fields'));
      await tester.pumpAndSettle();
      final List<String> words = visibleText(tester);

      // Unknown is a state with a name, not a blank and not a zero
      // (design/00-north-star.md, principle 2).
      expect(words.where((String w) => w == 'Unknown'), isNotEmpty);
      expect(words.where((String w) => w == 'As written: Unknown'), isNotEmpty);

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
      'the queue counts what it loaded and builds only what it shows',
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

        // The count is of what was loaded. The list endpoint answers a page and
        // a cursor and never a total, so a queue claiming one would be claiming
        // authority over records it has never seen.
        // 13 section 4.2 draws it as a numeral with its unit, and the whole
        // sentence stays on the header's live region, which is where a
        // screen reader hears what the page is made of.
        expect(
          visibleText(tester).where((String w) => w == '1000'),
          isNotEmpty,
        );
        expect(
          visibleText(tester).where((String w) => w == 'RECORDS'),
          isNotEmpty,
        );
        expect(
          tester.getSemantics(find.textContaining('need review')).label,
          contains('1000 records loaded'),
        );

        // How many of the thousand rows the queue actually built.
        //
        // A ratchet, the mechanism this repository already uses for its
        // gates: the number may shrink and may never grow. It was a thousand,
        // because the queue built its list with `ListView(children: ...)`,
        // the eager constructor, so every row a collection held was built
        // whether or not it was on screen. Slot A3 rebuilt the screen as the
        // one `CustomScrollView` 13 section 4.2 asks for, with a
        // `SliverList.builder` for the rows, and the number is now what a
        // window shows plus the list's cache extent.
        final int built = tester
            .widgetList<QueueRow>(find.byType(QueueRow))
            .length;
        expect(built, greaterThan(0));
        expect(
          built,
          lessThanOrEqualTo(eagerQueueRows),
          reason:
              'the queue built $built of 1000 rows, up from $eagerQueueRows. '
              'This number may only shrink',
        );

        // It scrolls, and scrolling does not run out of rows.
        await tester.drag(find.byType(QueueRow).first, const Offset(0, -2000));
        await tester.pump();
        expect(find.byType(QueueRow), findsWidgets);
      },
    );
  });
}
