// The manifest: the eight upload states, the skipped row, the batch progress
// line, the remove control and Stop.
//
// These are component tests over `IntakeManifest`, so a state that is hard to
// reach through the network can still be drawn and checked.

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/capture_quality.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_entry.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';
import 'package:specimen_digitization/src/widgets/not_calibrated_chip.dart';

import 'widgets/harness.dart';

ManifestEntry entryIn(
  UploadState state, {
  String name = 'specimen.png',
  String digest = 'aaaaaaaaaaaaaaaa',
  double progress = 0,
  String? reason,
  bool withFile = true,
}) {
  final ManifestEntry entry = ManifestEntry(
    digest: digest,
    name: name,
    state: state,
    reason: reason,
    progress: progress,
    file: withFile
        ? IntakeFile(
            name: name,
            bytes: Uint8List(8),
            mimeType: 'image/png',
            sha256: digest,
            method: 'files',
            width: 100,
            height: 80,
          )
        : null,
  );
  return entry;
}

Future<void> pumpManifest(
  WidgetTester tester,
  List<ManifestEntry> entries, {
  bool busy = false,
  bool stopping = false,
  VoidCallback? onStop,
  void Function(ManifestEntry)? onRemove,
  Size size = const Size(700, 1600),
}) => pumpComponent(
  tester,
  SizedBox(
    width: size.width,
    height: size.height,
    child: IntakeManifest(
      entries: entries,
      busy: busy,
      stopping: stopping,
      onStop: onStop ?? () {},
      onRemove: onRemove ?? (ManifestEntry _) {},
      onServerCheck: (ManifestEntry _) {},
    ),
  ),
  size: size,
);

void main() {
  group('the eight upload states each draw their own chip', () {
    for (final UploadState state in UploadState.values) {
      testWidgets('${state.name} renders as "${state.label}"', (
        WidgetTester tester,
      ) async {
        await pumpManifest(tester, <ManifestEntry>[
          entryIn(state, reason: 'A stated reason.', progress: 0.5),
        ]);
        expect(find.text(state.label), findsOneWidget);
        expect(find.text('A stated reason.'), findsOneWidget);
      });
    }
  });

  testWidgets('uploading draws a determinate ring at the reported fraction', (
    WidgetTester tester,
  ) async {
    await pumpManifest(tester, <ManifestEntry>[
      entryIn(UploadState.uploading, progress: 0.42),
    ]);
    final UiProgress ring = tester.widget<UiProgress>(find.byType(UiProgress));
    expect(ring.value, closeTo(0.42, 0.0001));
  });

  testWidgets('no other state draws a ring', (WidgetTester tester) async {
    for (final UploadState state in UploadState.values.where(
      (UploadState s) => s != UploadState.uploading,
    )) {
      await pumpManifest(tester, <ManifestEntry>[
        entryIn(state, progress: 0.42),
      ]);
      expect(
        find.byType(UiProgress),
        findsNothing,
        reason: '${state.name} must not claim a measured fraction',
      );
    }
  });

  testWidgets('a rejected file is a skipped row carrying its own reason', (
    WidgetTester tester,
  ) async {
    await pumpManifest(tester, <ManifestEntry>[
      ManifestEntry.skipped(
        digest: 'size:huge.tif:99',
        name: 'huge.tif',
        why: 'This file is over 25 MB.',
      ),
    ]);
    expect(find.text('huge.tif'), findsOneWidget);
    expect(find.text('Skipped'), findsOneWidget);
    expect(find.text('This file is over 25 MB.'), findsOneWidget);
    // The reason belongs to the file, not to a screen level banner.
    expect(
      find.descendant(
        of: find.byType(IntakeManifestRow),
        matching: find.text('This file is over 25 MB.'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('the remove control is live until the server takes the file', (
    WidgetTester tester,
  ) async {
    final List<ManifestEntry> removed = <ManifestEntry>[];
    final ManifestEntry ready = entryIn(
      UploadState.ready,
      name: 'ready.png',
      digest: 'bbbbbbbbbbbbbbbb',
    );
    final ManifestEntry accepted = entryIn(
      UploadState.accepted,
      name: 'done.png',
      digest: 'cccccccccccccccc',
    );
    await pumpManifest(tester, <ManifestEntry>[
      ready,
      accepted,
    ], onRemove: removed.add);
    final Finder controls = find.widgetWithIcon(IconButton, Icons.close);
    expect(controls, findsNothing, reason: 'the library uses Material Symbols');

    final List<IconButton> buttons = tester
        .widgetList<IconButton>(find.byType(IconButton))
        .toList();
    expect(buttons.length, 2);
    expect(buttons.first.onPressed, isNotNull);
    expect(buttons.last.onPressed, isNull);
    await tester.tap(find.byType(IconButton).first);
    await tester.pumpAndSettle();
    expect(removed, <ManifestEntry>[ready]);
  });

  testWidgets('Stop is offered only while a batch is running', (
    WidgetTester tester,
  ) async {
    var stops = 0;
    await pumpManifest(tester, <ManifestEntry>[entryIn(UploadState.ready)]);
    expect(find.text('Stop'), findsNothing);

    await pumpManifest(
      tester,
      <ManifestEntry>[entryIn(UploadState.uploading)],
      busy: true,
      onStop: () => stops++,
    );
    await tester.tap(find.text('Stop'));
    await tester.pumpAndSettle();
    expect(stops, 1);

    await pumpManifest(
      tester,
      <ManifestEntry>[entryIn(UploadState.uploading)],
      busy: true,
      stopping: true,
    );
    expect(find.text('Stopping'), findsOneWidget);
    expect(
      find.text('Stopping. The file already sending finishes first.'),
      findsOneWidget,
    );
  });

  testWidgets('an empty manifest says so rather than showing nothing', (
    WidgetTester tester,
  ) async {
    await pumpManifest(tester, <ManifestEntry>[]);
    expect(find.text('No files selected yet'), findsOneWidget);
    expect(
      find.text('Nothing here yet. Photographs appear as you add them.'),
      findsOneWidget,
    );
  });

  testWidgets('local measurements are three labelled values and a caveat', (
    WidgetTester tester,
  ) async {
    final ManifestEntry entry = entryIn(UploadState.ready);
    entry.quality = CaptureQuality.measure(
      Uint8List.fromList(
        <int>[0, 255, 0, 255].expand((int v) => <int>[v, v, v, 255]).toList(),
      ),
      2,
      2,
    );
    await pumpManifest(tester, <ManifestEntry>[entry]);
    for (final String label in CaptureQualitySummary.labels) {
      expect(find.text(label), findsOneWidget);
    }
    expect(find.text(NotCalibratedChip.label), findsOneWidget);
  });

  group('the batch progress line', () {
    test('reads "8 of 12 accepted, 1 skipped"', () {
      final List<ManifestEntry> entries = <ManifestEntry>[
        for (int i = 0; i < 8; i++)
          entryIn(UploadState.accepted, digest: 'a$i'),
        for (int i = 0; i < 3; i++) entryIn(UploadState.ready, digest: 'r$i'),
        entryIn(UploadState.skipped, digest: 's0'),
      ];
      expect(batchProgressLine(entries), '8 of 12 accepted, 1 skipped');
    });

    test('names duplicates, interruptions and failures when they exist', () {
      expect(
        batchProgressLine(<ManifestEntry>[
          entryIn(UploadState.accepted, digest: 'a'),
          entryIn(UploadState.duplicate, digest: 'b'),
          entryIn(UploadState.interrupted, digest: 'c'),
          entryIn(UploadState.failed, digest: 'd'),
        ]),
        '1 of 4 accepted, 1 already in collection, 1 interrupted, 1 failed',
      );
    });

    test('a zero count is left out', () {
      expect(
        batchProgressLine(<ManifestEntry>[
          entryIn(UploadState.accepted, digest: 'a'),
        ]),
        '1 of 1 accepted',
      );
    });

    test('an empty batch says so', () {
      expect(batchProgressLine(<ManifestEntry>[]), 'No files selected yet');
    });
  });

  group('progress is monotonic', () {
    test('a resumed upload reporting a lower offset never runs backwards', () {
      final ManifestEntry entry = entryIn(UploadState.uploading);
      entry.observeProgress(0.4);
      entry.observeProgress(0.9);
      entry.observeProgress(0.2);
      expect(entry.progress, closeTo(0.9, 0.0001));
    });

    test('an out of range fraction is clamped, never trusted', () {
      final ManifestEntry entry = entryIn(UploadState.uploading);
      entry.observeProgress(4);
      expect(entry.progress, 1);
      entry.observeProgress(double.nan);
      expect(entry.progress, 1);
    });
  });

  test('a round trip in flight shows as Checking without losing its state', () {
    final ManifestEntry entry = entryIn(UploadState.interrupted);
    expect(entry.displayState, UploadState.interrupted);
    entry.checking = true;
    expect(entry.displayState, UploadState.checking);
    expect(entry.state, UploadState.interrupted);
  });

  testWidgets('every manifest control is reachable and big enough to hit', (
    WidgetTester tester,
  ) async {
    await pumpManifest(tester, <ManifestEntry>[
      entryIn(UploadState.ready, digest: 'r1', name: 'ready.png'),
      ManifestEntry.skipped(
        digest: 's1',
        name: 'skipped.png',
        why: 'This file is empty, so there is nothing to upload.',
      ),
    ], busy: true);
    await expectAccessible(tester);
  });
}
