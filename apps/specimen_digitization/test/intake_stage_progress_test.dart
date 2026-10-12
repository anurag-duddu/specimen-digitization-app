import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_entry.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/screens/intake/stage_progress.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';
import 'package:specimen_ui/specimen_ui.dart';

ManifestEntry processing({
  String step = 'transcribe',
  String status = 'running',
  UploadState state = UploadState.processing,
  List<String> completed = const <String>['segment'],
  String? retryAt,
  bool legacy = false,
}) => ManifestEntry(
  digest: 'photo',
  name: 'photo.jpg',
  state: state,
  specimenId: 'photo',
  specimen: Specimen(<String, dynamic>{
    'stage': legacy ? step : status,
    'status': status,
    if (!legacy)
      'intake_progress': <String, dynamic>{
        'next_step': step,
        'completed_stages': completed,
        'next_retry_at': retryAt,
      },
  }),
);

Future<void> pumpRow(
  WidgetTester tester,
  ManifestEntry entry, {
  bool reduced = true,
  double width = 390,
  double scale = 1,
  bool dark = false,
}) async {
  tester.view.physicalSize = Size(width, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: dark ? AppTheme.dark() : AppTheme.light(),
      home: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(context).copyWith(
            disableAnimations: reduced,
            textScaler: TextScaler.linear(scale),
          ),
          child: Scaffold(
            body: SingleChildScrollView(
              child: IntakeManifestRow(
                entry: entry,
                busy: false,
                onRemove: () {},
                onServerCheck: () {},
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  for (final (step, label) in <(String, String)>[
    ('pin_dependencies', 'Preparing photo'),
    ('segment', 'Finding labels'),
    ('transcribe', 'Reading the label'),
    ('first_pass', 'Comparing readings'),
    ('adjudicate', 'Comparing readings'),
    ('parse', 'Organising fields'),
    ('plan', 'Checking fields'),
    ('field_research', 'Checking fields'),
    ('lookup', 'Checking fields'),
    ('validate', 'Checking fields'),
    ('finalize', 'Finishing the record'),
    ('finalized', 'Moving to main Queue'),
  ]) {
    testWidgets('$step has one active segment with no invented percentage', (
      tester,
    ) async {
      await pumpRow(tester, processing(step: step));
      expect(find.text(label), findsOneWidget);
      final indicators = tester.widgetList<UiProgress>(find.byType(UiProgress));
      expect(indicators, hasLength(1));
      expect(indicators.single.value, isNull);
      expect(
        find.byWidgetPredicate(
          (w) =>
              w is Container &&
              w.key is ValueKey<String> &&
              (w.key! as ValueKey<String>).value.startsWith('stage-'),
        ),
        findsNWidgets(8),
      );
    });
  }

  testWidgets('waiting does not roll or certify a stage', (tester) async {
    await pumpRow(
      tester,
      processing(step: 'pin_dependencies', status: 'pending', completed: []),
    );
    expect(find.text('Waiting to start'), findsOneWidget);
    expect(find.byType(UiProgress), findsNothing);
    expect(find.byKey(const ValueKey('stage-segment-waiting')), findsOneWidget);
    expect(find.byKey(const ValueKey('stage-upload-done')), findsOneWidget);
  });

  testWidgets('retry shows local scheduled time and stops rolling', (
    tester,
  ) async {
    await pumpRow(
      tester,
      processing(status: 'retry_scheduled', retryAt: '2026-10-12T19:20:00Z'),
    );
    expect(find.text('Retrying at 14:20'), findsOneWidget);
    expect(find.byKey(const ValueKey('stage-read-retrying')), findsOneWidget);
    expect(find.byType(UiProgress), findsNothing);
    await pumpRow(
      tester,
      processing(status: 'retry_scheduled', retryAt: 'not-a-date'),
    );
    expect(find.text('Retry scheduled'), findsOneWidget);
  });

  for (final status in ['processing_blocked', 'paused', 'cancelled']) {
    testWidgets('$status keeps completed work and names attention', (
      tester,
    ) async {
      await pumpRow(
        tester,
        processing(status: status, state: UploadState.processingBlocked),
      );
      expect(find.text('Needs attention'), findsOneWidget);
      expect(find.byKey(const ValueKey('stage-segment-done')), findsOneWidget);
      expect(
        find.byKey(const ValueKey('stage-read-attention')),
        findsOneWidget,
      );
      expect(find.byType(UiProgress), findsNothing);
    });
  }

  testWidgets('Queue handoff does not manufacture unrecorded completion', (
    tester,
  ) async {
    await pumpRow(
      tester,
      processing(state: UploadState.inMainQueue, completed: []),
    );
    expect(find.text('In main Queue'), findsOneWidget);
    expect(find.byKey(const ValueKey('stage-queue-done')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('stage-research-unknown')),
      findsOneWidget,
    );
    await pumpRow(
      tester,
      processing(
        state: UploadState.inMainQueue,
        completed: [
          'segment',
          'read',
          'compare',
          'extract',
          'research',
          'finalize',
        ],
      ),
    );
    for (final stage in IntakeStage.values) {
      expect(find.byKey(ValueKey('stage-${stage.name}-done')), findsOneWidget);
    }
  });

  testWidgets('old and unknown server stages remain honest', (tester) async {
    await pumpRow(tester, processing(step: 'transcribe', legacy: true));
    expect(find.text('Reading the label'), findsOneWidget);
    expect(find.byKey(const ValueKey('stage-segment-done')), findsNothing);
    await pumpRow(tester, processing(step: 'future_stage', legacy: true));
    expect(find.text('Checking processing status'), findsOneWidget);
    expect(find.byType(UiProgress), findsNothing);
  });

  testWidgets('only upload exposes real byte progress, silently', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    addTearDown(semantics.dispose);
    final entry = ManifestEntry(
      digest: 'photo',
      name: 'photo.jpg',
      state: UploadState.uploading,
      progress: .42,
    );
    await pumpRow(tester, entry);
    expect(tester.widget<UiProgress>(find.byType(UiProgress)).value, .42);
    final upload = tester.getSemantics(
      find.bySemanticsLabel('Upload: in progress'),
    );
    expect(upload.value, '42 percent uploaded');
    expect(upload.getSemanticsData().flagsCollection.isLiveRegion, isFalse);
    final status = tester.getSemantics(
      find.byKey(const ValueKey('intake-stage-status')),
    );
    final statusId = status.id;
    expect(status.label, 'Uploading photo');
    entry.progress = .73;
    await pumpRow(tester, entry);
    final changed = tester.getSemantics(
      find.byKey(const ValueKey('intake-stage-status')),
    );
    expect(changed.id, statusId);
    expect(changed.label, 'Uploading photo');
    expect(changed.value, isEmpty);
  });

  testWidgets(
    'status semantics change once, never on a tick or identical poll',
    (tester) async {
      final semantics = tester.ensureSemantics();
      addTearDown(semantics.dispose);
      await pumpRow(tester, processing(), reduced: false);
      final finder = find.byKey(const ValueKey('intake-stage-status'));
      final before = tester.getSemantics(finder);
      final id = before.id;
      expect(before.getSemanticsData().flagsCollection.isLiveRegion, isTrue);
      await tester.pump(const Duration(milliseconds: 250));
      expect(tester.getSemantics(finder).label, 'Reading the label');
      await pumpRow(tester, processing(), reduced: false);
      expect(tester.getSemantics(finder).id, id);
      expect(tester.getSemantics(finder).label, 'Reading the label');
      await pumpRow(tester, processing(step: 'first_pass'), reduced: false);
      expect(tester.getSemantics(finder).id, id);
      expect(tester.getSemantics(finder).label, 'Comparing readings');
      expect(
        find.bySemanticsLabel('Read labels: not recorded'),
        findsOneWidget,
      );
    },
  );

  testWidgets('rolling progress moves, then freezes when motion is disabled', (
    tester,
  ) async {
    await pumpRow(tester, processing(), reduced: false);
    final indicator = find.byType(UiProgress);
    Finder moving() => find.descendant(
      of: indicator,
      matching: find.byType(FractionallySizedBox),
    );
    final start = tester.widget<FractionallySizedBox>(moving()).alignment;
    await tester.pump(const Duration(milliseconds: 250));
    expect(
      tester.widget<FractionallySizedBox>(moving()).alignment,
      isNot(start),
    );
    await pumpRow(tester, processing());
    await tester.pumpAndSettle();
    final frozen = tester.widget<FractionallySizedBox>(moving()).alignment;
    await tester.pump(const Duration(seconds: 2));
    expect(tester.widget<FractionallySizedBox>(moving()).alignment, frozen);
    expect(tester.binding.hasScheduledFrame, isFalse);
  });

  for (final width in [320.0, 390.0, 768.0, 1440.0]) {
    for (final dark in [false, true]) {
      testWidgets('row fits $width at double text, dark=$dark', (tester) async {
        await pumpRow(
          tester,
          processing(
            status: 'retry_scheduled',
            retryAt: '2026-10-12T19:20:00Z',
          ),
          width: width,
          scale: 2,
          dark: dark,
        );
        expect(tester.takeException(), isNull);
        final track = tester.getRect(find.byType(IntakeStageProgress));
        final first = tester.getRect(
          find.byKey(const ValueKey('stage-upload-done')),
        );
        final last = tester.getRect(
          find.byKey(const ValueKey('stage-queue-waiting')),
        );
        expect(first.left, greaterThanOrEqualTo(track.left));
        expect(last.right, lessThanOrEqualTo(width));
        expect(first.width, closeTo(last.width, .01));
        final semantics = tester.ensureSemantics();
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
        semantics.dispose();
      });
    }
  }
}
