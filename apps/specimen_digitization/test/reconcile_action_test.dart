// An administrator reconciles an unknown outcome from the Processing panel.
//
// The server offers `reconcile` in `available_actions` only to an
// administrator, and only when the blocked step reads (it never repeats an
// effect that writes). The panel draws the action only then, next to the
// explanation of the unknown outcome, behind a reason sheet that says what
// happened, what reconciling does and what it costs.

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

const String unknown = 'external_outcome_unknown';
const String reconcile = ProcessingDetail.reconcileAction;

Specimen specimenWith({
  List<String> actions = const <String>['pause', 'cancel', 'reconcile'],
  String blocker = unknown,
  DateTime? lease,
}) => Specimen(<String, dynamic>{
  'specimen_id': 'reconcile-001',
  'revision': 7,
  'available_actions': actions,
  'run': <String, dynamic>{
    'blocker': blocker,
    'lease_until': lease?.toUtc().toIso8601String(),
  },
});

Widget panel(
  Specimen specimen, {
  bool canOperate = true,
  bool busy = false,
  Future<void> Function(Json)? onAction,
}) => OperationalPanel(
  specimen: specimen,
  canOperate: canOperate,
  busy: busy,
  onAction: onAction ?? (Json _) async {},
);

/// [child] at [scale] times the text size, on a window [width] wide.
Future<void> pumpScaled(
  WidgetTester tester,
  Widget child, {
  required double width,
  double scale = 2.0,
}) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = Size(width, 900);
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      builder: (BuildContext context, Widget? home) => MediaQuery(
        data: MediaQuery.of(
          context,
        ).copyWith(textScaler: TextScaler.linear(scale)),
        child: home!,
      ),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    ),
  );
  await tester.pumpAndSettle();
}

/// Fails when any text under [scope] is ellipsized or drawn past the window.
void expectNothingCutOff(WidgetTester tester, Finder scope, double width) {
  final Finder paragraphs = find.descendant(
    of: scope,
    matching: find.byType(RichText),
  );
  expect(paragraphs, findsWidgets);
  for (final Element element in paragraphs.evaluate()) {
    final RenderParagraph paragraph = element.renderObject! as RenderParagraph;
    final String text = paragraph.text.toPlainText();
    expect(
      paragraph.didExceedMaxLines,
      isFalse,
      reason: '"$text" is ellipsized',
    );
    final Rect box = MatrixUtils.transformRect(
      paragraph.getTransformTo(null),
      Offset.zero & paragraph.size,
    );
    expect(
      box.left,
      greaterThanOrEqualTo(-0.5),
      reason: '"$text" starts off screen',
    );
    expect(
      box.right,
      lessThanOrEqualTo(width + 0.5),
      reason: '"$text" ends off screen',
    );
  }
}

void main() {
  group('who sees the action', () {
    testWidgets('an administrator sees it beside the explanation', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(scrollingHost(panel(specimenWith())));
      final Finder explanation = find.textContaining('Its result is unknown');
      expect(explanation, findsOneWidget);
      expect(uiButton(reconcile), findsOneWidget);
      expect(controlEnabled(tester, reconcile), isTrue);
      // Under the explanation and its caveat, above the other run actions.
      final double explained = tester.getBottomLeft(explanation).dy;
      final double reconciling = tester.getTopLeft(uiButton(reconcile)).dy;
      expect(reconciling, greaterThan(explained));
      expect(
        reconciling,
        lessThan(tester.getTopLeft(uiButton('Pause processing')).dy),
      );
    });

    testWidgets('it is hidden when the server does not offer it', (
      WidgetTester tester,
    ) async {
      // What an operator, reviewer or manager is sent, and what an
      // administrator is sent when the blocked step writes.
      await tester.pumpWidget(
        scrollingHost(
          panel(specimenWith(actions: const <String>['pause', 'cancel'])),
        ),
      );
      expect(find.textContaining('Its result is unknown'), findsOneWidget);
      expect(uiButton(reconcile), findsNothing);
      expect(uiButton('Pause processing'), findsOneWidget);
    });

    testWidgets('it is hidden from a reader who cannot operate runs', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        scrollingHost(panel(specimenWith(), canOperate: false)),
      );
      expect(find.textContaining('Its result is unknown'), findsOneWidget);
      expect(uiButton(reconcile), findsNothing);
    });

    testWidgets('it is drawn only for an unknown outcome', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        scrollingHost(
          panel(
            specimenWith(blocker: 'stage_failed_inspect_private_worker_logs'),
          ),
        ),
      );
      expect(uiButton(reconcile), findsNothing);
    });
  });

  group('when it cannot be used yet', () {
    testWidgets(
      'it is disabled with the reason while the service holds the run',
      (WidgetTester tester) async {
        await tester.pumpWidget(
          scrollingHost(
            panel(
              specimenWith(lease: DateTime.now().add(const Duration(hours: 1))),
            ),
          ),
        );
        expect(controlEnabled(tester, reconcile), isFalse);
        expect(
          disabledReasonOf(tester, reconcile),
          contains('processing service'),
        );
        expect(
          find.text(
            'Reconcile, resume and new run are unavailable until then.',
          ),
          findsOneWidget,
        );
      },
    );

    testWidgets('it is disabled with the reason while a save is in flight', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(scrollingHost(panel(specimenWith(), busy: true)));
      expect(controlEnabled(tester, reconcile), isFalse);
      expect(disabledReasonOf(tester, reconcile), contains('save'));
    });
  });

  group('the reason sheet', () {
    Future<Finder> open(WidgetTester tester, List<Json> sent) async {
      await tester.pumpWidget(
        scrollingHost(
          panel(
            specimenWith(),
            onAction: (Json change) async {
              sent.add(change);
            },
          ),
        ),
      );
      await tester.tap(uiButton(reconcile));
      await tester.pumpAndSettle();
      return find.byType(ReasonForm);
    }

    testWidgets('says what happened, what reconciling does and what it costs', (
      WidgetTester tester,
    ) async {
      await open(tester, <Json>[]);
      expect(find.text(ProcessingDetail.reconcileTitle), findsOneWidget);
      expect(find.text(ProcessingDetail.reconcileConsequence), findsOneWidget);
      expect(find.text(ProcessingDetail.reconcileRetained), findsOneWidget);
      expect(
        ProcessingDetail.reconcileConsequence,
        allOf(
          contains('may have run'),
          contains('runs that step again'),
          contains('few cents'),
        ),
      );
      expect(
        ProcessingDetail.reconcileRetained,
        contains('nothing is written twice'),
      );
    });

    testWidgets('will not send without a reason, then sends the action once', (
      WidgetTester tester,
    ) async {
      final List<Json> sent = <Json>[];
      final Finder form = await open(tester, sent);
      final Finder confirm = find.descendant(
        of: form,
        matching: uiButton(reconcile),
      );
      expect(tester.widget<UiButton>(confirm).onPressed, isNull);
      expect(
        tester.widget<UiButton>(confirm).disabledReason,
        ReasonForm.reasonRequiredHint,
      );
      await tester.tap(confirm);
      await tester.pumpAndSettle();
      expect(sent, isEmpty);

      await tester.enterText(uiField('Reason'), '   ');
      await tester.pumpAndSettle();
      expect(tester.widget<UiButton>(confirm).onPressed, isNull);

      await tester.enterText(uiField('Reason'), 'Reader dropped; read again');
      await tester.pumpAndSettle();
      await tester.tap(confirm);
      await tester.pumpAndSettle();
      expect(sent, <Json>[
        <String, dynamic>{
          'kind': 'run_action',
          'action': 'reconcile',
          'reason': 'Reader dropped; read again',
        },
      ]);
      expect(find.byType(ReasonForm), findsNothing);
    });

    testWidgets('sends nothing when the administrator backs out', (
      WidgetTester tester,
    ) async {
      final List<Json> sent = <Json>[];
      await open(tester, sent);
      await tester.tap(uiButton(ReasonForm.cancelLabel));
      await tester.pumpAndSettle();
      expect(sent, isEmpty);
      expect(find.byType(ReasonForm), findsNothing);
    });
  });

  group('the result is announced once', () {
    Specimen record() => Specimen(<String, dynamic>{
      'specimen_id': 'reconcile-001',
      'display_name': 'Synthetic reconcile record',
      'revision': 7,
      'disposition': 'needs_human_review',
      'available_actions': const <String>['pause', 'cancel', 'reconcile'],
      'run': const <String, dynamic>{
        'blocker': unknown,
        'stage': 'processing_blocked',
      },
    });

    Future<List<String>> reconcileThroughTheWorkbench(
      WidgetTester tester, {
      required bool saved,
      required List<Json> sent,
    }) async {
      useWindow(tester, largeWindow);
      final SemanticsHandle semantics = tester.ensureSemantics();
      final List<String> announced = <String>[];
      tester.binding.defaultBinaryMessenger.setMockDecodedMessageHandler<
        dynamic
      >(SystemChannels.accessibility, (dynamic message) async {
        final Map<Object?, Object?> event = message as Map<Object?, Object?>;
        if (event['type'] != 'announce') return;
        final Map<Object?, Object?> data =
            event['data']! as Map<Object?, Object?>;
        announced.add('${data['message']}');
      });
      addTearDown(
        () => tester.binding.defaultBinaryMessenger
            .setMockDecodedMessageHandler<dynamic>(
              SystemChannels.accessibility,
              null,
            ),
      );
      await tester.pumpWidget(
        workbenchHost(
          ReviewWorkbench(
            specimen: record(),
            onChange: (Json change) async {
              sent.add(change);
              return saved;
            },
            onRetry: (String _) async {},
            onRefresh: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      // The run's internals sit in the record's closed review details.
      await tester.tap(find.text('Specimen data'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Review details'));
      await tester.pumpAndSettle();
      final Finder processing = find.text(ProcessingDisclosure.title);
      await tester.ensureVisible(processing);
      await tester.pumpAndSettle();
      await tester.tap(processing);
      await tester.pumpAndSettle();
      await tester.ensureVisible(uiButton(reconcile));
      await tester.pumpAndSettle();
      await tester.tap(uiButton(reconcile));
      await tester.pumpAndSettle();
      await tester.enterText(uiField('Reason'), 'Reader dropped; read again');
      await tester.pumpAndSettle();
      await tester.tap(
        find.descendant(
          of: find.byType(ReasonForm),
          matching: uiButton(reconcile),
        ),
      );
      await tester.pumpAndSettle();
      semantics.dispose();
      return announced;
    }

    testWidgets('a saved reconcile says so once', (WidgetTester tester) async {
      final List<Json> sent = <Json>[];
      final List<String> announced = await reconcileThroughTheWorkbench(
        tester,
        saved: true,
        sent: sent,
      );
      expect(sent.single['action'], 'reconcile');
      expect(
        announced.where((String m) => m == ProcessingDetail.reconcileSaved),
        hasLength(1),
      );
    });

    testWidgets('a reconcile the server refused is not announced as saved', (
      WidgetTester tester,
    ) async {
      final List<Json> sent = <Json>[];
      final List<String> announced = await reconcileThroughTheWorkbench(
        tester,
        saved: false,
        sent: sent,
      );
      expect(sent, hasLength(1));
      expect(announced, isNot(contains(ProcessingDetail.reconcileSaved)));
    });
  });

  group('at 200 percent text', () {
    for (final double width in <double>[390, 320]) {
      testWidgets('nothing is cut off at $width wide', (
        WidgetTester tester,
      ) async {
        await pumpScaled(tester, panel(specimenWith()), width: width);
        expect(uiButton(reconcile), findsOneWidget);
        expectNothingCutOff(tester, find.byType(OperationalPanel), width);
        expect(tester.takeException(), isNull);
        // The control keeps the 48 dp target at any text size.
        expect(
          tester.getSize(uiButton(reconcile)).height,
          greaterThanOrEqualTo(48),
        );
      });

      testWidgets('the reason sheet fits $width wide', (
        WidgetTester tester,
      ) async {
        await pumpScaled(tester, panel(specimenWith()), width: width);
        await tester.tap(uiButton(reconcile));
        await tester.pumpAndSettle();
        final Finder form = find.byType(ReasonForm);
        expect(form, findsOneWidget);
        expect(
          find.text(ProcessingDetail.reconcileConsequence),
          findsOneWidget,
        );
        expectNothingCutOff(tester, form, width);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('the action has a name a screen reader can read', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle semantics = tester.ensureSemantics();
      await pumpScaled(tester, panel(specimenWith()), width: 390);
      expect(find.bySemanticsLabel(reconcile), findsWidgets);
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      semantics.dispose();
    });
  });
}
