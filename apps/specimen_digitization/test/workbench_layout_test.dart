// The workbench at each of the three layout regimes, and the behaviour the
// blueprint names for each: a pinned photograph, a decision bar that never
// scrolls, a blockers list that leads to the control that resolves it, and a
// keyboard a reviewer can work the whole record from.
//
// Layout is asserted from the window width, never from a platform.

import 'dart:io';

import 'package:flutter/material.dart';
import 'dart:ui' show Tristate;

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/audit_history.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workbench.dart';

import 'workbench_harness.dart';
import 'ui_finders.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/screens/workbench/decision_bar.dart';

/// The source pane's region chip named [name].
///
/// The pane draws its region list as a `UiCapsuleToggle`, whose one control
/// per option is a `Pressable` in the toggle role, so the chip is reached by
/// the name it publishes rather than by a Material type
/// (the source pane slot proved this form in `test/source_geometry_test.dart`).
Finder regionChip(String name) => find.byWidgetPredicate(
  (Widget widget) =>
      widget is Pressable &&
      widget.role == PressableRole.toggle &&
      widget.semanticsLabel == name,
  description: 'region chip "$name"',
);

void main() {
  final bytes = File(
    'test/fixtures/synthetic-wide-label.png',
  ).readAsBytesSync();

  Specimen record({List<Json> extraFindings = const <Json>[]}) => Specimen({
    'specimen_id': 'layout-001',
    'display_name': 'Synthetic layout record',
    'revision': 4,
    'disposition': 'needs_human_review',
    'available_actions': const ['field', 'transcription', 'coverage'],
    'assets': [
      {'width': 1000, 'height': 520, 'preview_bytes': bytes},
    ],
    'regions': const [
      {
        'region_id': 'r1',
        'bbox': [100, 52, 400, 212],
      },
      {
        'region_id': 'r2',
        'bbox': [420, 52, 700, 212],
      },
    ],
    'observations': const [
      {
        'id': 'o1',
        'model_id': 'Reader A',
        'provider': 'synthetic',
        'region_id': 'r1',
        'literal_text': 'Chicago 1912',
      },
      {
        'id': 'o2',
        'model_id': 'Reader B',
        'provider': 'synthetic',
        'region_id': 'r1',
        'literal_text': 'Chicago 1917',
      },
    ],
    'fields': const [
      {
        'field_key': 'country',
        'display_name': 'Country',
        'required': true,
        'state': 'unknown',
        'literal_value': null,
      },
    ],
    'validation_findings': <Json>[
      const {
        'field_key': 'country',
        'message': 'A supported country is required',
        'severity': 'hard',
        'rule_id': 'country.required',
      },
      ...extraFindings,
    ],
  });

  Widget host(
    Specimen specimen, {
    VoidCallback? onNext,
    VoidCallback? onPrevious,
  }) => workbenchHost(
    ReviewWorkbench(
      specimen: specimen,
      onChange: (_) async => false,
      onRetry: (_) async {},
      onRefresh: () {},
      onNext: onNext,
      onPrevious: onPrevious,
    ),
  );

  group('layout regimes', () {
    test('the regime comes from the width alone', () {
      expect(WorkbenchRegime.fromWidth(599), WorkbenchRegime.stacked);
      expect(WorkbenchRegime.fromWidth(839), WorkbenchRegime.stacked);
      expect(WorkbenchRegime.fromWidth(840), WorkbenchRegime.twoPane);
      expect(WorkbenchRegime.fromWidth(1199), WorkbenchRegime.twoPane);
      expect(WorkbenchRegime.fromWidth(1200), WorkbenchRegime.threePane);
      expect(
        WorkbenchSegment.forRegime(WorkbenchRegime.twoPane),
        WorkbenchSegment.values,
      );
      expect(
        WorkbenchSegment.forRegime(WorkbenchRegime.threePane),
        <WorkbenchSegment>[WorkbenchSegment.readings, WorkbenchSegment.fields],
      );
    });

    testWidgets('below 840 the photograph is a pinned header', (tester) async {
      useWindow(tester, compactWindow);
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();

      // History is a segment at this width, not a pane.
      expect(find.text('History'), findsOneWidget);
      expect(find.byType(AuditHistoryPanel), findsNothing);

      // The photograph keeps at least the blueprint's share of the viewport.
      final pane = tester.getSize(find.byType(InteractiveViewer));
      expect(
        pane.height,
        greaterThanOrEqualTo(
          compactWindow.height * sourceHeaderMinFraction * 0.6,
        ),
      );

      // It does not scroll away with the evidence: the header gives height
      // back to its floor and stays there (13 section 3.1).
      final before = tester.getTopLeft(find.byType(InteractiveViewer));
      await tester.drag(find.byKey(evidenceScrollKey), const Offset(0, -200));
      await tester.pumpAndSettle();
      expect(tester.getTopLeft(find.byType(InteractiveViewer)), before);
      expect(find.byType(InteractiveViewer), findsOneWidget);
      expect(
        tester.getSize(find.byType(InteractiveViewer)).height,
        greaterThan(0),
      );
    });

    testWidgets('840 to 1199 is two panes with History as a segment', (
      tester,
    ) async {
      useWindow(tester, expandedWindow);
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      expect(find.text('History'), findsOneWidget);
      expect(find.byType(AuditHistoryPanel), findsNothing);
      // The photograph and the evidence share the width.
      final source = tester.getRect(find.byType(InteractiveViewer));
      expect(source.right, lessThan(expandedWindow.width * 0.6));
    });

    testWidgets('1200 and above gives History a pane of its own', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      expect(find.byType(AuditHistoryPanel), findsOneWidget);
      // History has left the selector.
      expect(
        find.descendant(
          of: uiTabs(evidenceTabsLabel),
          matching: find.text('History'),
        ),
        findsNothing,
      );
      expect(
        tester.getSize(find.byType(AuditHistoryPanel)).width,
        closeTo(historyPaneWidth, 1),
      );
    });

    test('the decision sits in the top bar from expanded up', () {
      // 13 section 4.1, the expanded and large table: at 200 percent text
      // the bar, the one line band and an action bar are 184.85 dp against
      // the 164 an 820 dp window allows, so those classes give the action bar
      // up and the decision moves into the bar the record already publishes.
      expect(decisionInTopBar(WindowClass.compact), isFalse);
      expect(decisionInTopBar(WindowClass.medium), isFalse);
      for (final WindowClass window in WindowClass.values) {
        expect(
          decisionInTopBar(window),
          window.isAtLeast(WindowClass.expanded),
          reason: '$window',
        );
      }
    });

    test('the segments stick at default type at every window class', () {
      // A2's rule by text size, and the window weighed as 22d5110 asked: the
      // classes that used to spend their budget on the action bar hold the
      // segments once the decision is in the bar (148 of the 180 a 900 dp
      // window allows at 1440 by 900 in the stacked regime).
      for (final WindowClass window in WindowClass.values) {
        expect(segmentsStick(TextScaler.noScaling, window), isTrue);
        expect(segmentsStick(const TextScaler.linear(1.3), window), isFalse);
        expect(segmentsStick(const TextScaler.linear(2.0), window), isFalse);
      }
    });

    testWidgets(
      'the decision bar is the frame action bar at compact and medium',
      (tester) async {
        for (final window in [compactWindow, mediumWindow]) {
          useWindow(tester, window);
          await tester.pumpWidget(host(record()));
          await tester.pumpAndSettle();
          // 13 section 3.3: the bar sits in `UiScaffold.actionBar`, which the
          // screen fills through the frame's own slot, so the shell owns the
          // bottom of the window and the chrome budget with it.
          final bar = tester.getRect(find.byType(WorkbenchDecisionBar));
          expect(
            bar.bottom,
            closeTo(window.height, 32),
            reason:
                'the decision bar is not at the foot of the window at '
                '$window',
          );
          expect(
            find.ancestor(
              of: find.byType(WorkbenchDecisionBar),
              matching: find.byWidgetPredicate(
                (Widget widget) =>
                    widget is PinnedChrome &&
                    widget.region == UiPinnedRegion.actionBar,
              ),
            ),
            findsOneWidget,
            reason: 'the frame does not count the bar as its action bar',
          );
          // The evidence ends clear of it, which is what the frame's own
          // bottom inset buys (10 section 4.4).
          expect(
            UiScaffold.of(
              tester.element(find.byType(ReviewWorkbench)),
            ).bottomInset,
            greaterThanOrEqualTo(bar.height),
          );
        }
      },
    );

    testWidgets('from expanded up the decision bar is in the top bar', (
      tester,
    ) async {
      for (final window in [expandedWindow, largeWindow]) {
        useWindow(tester, window);
        await tester.pumpWidget(host(record()));
        await tester.pumpAndSettle();
        // 13 section 4.1, the expanded and large table. The same widget as
        // below medium, inside the bar the record publishes, so the frame
        // counts it as the top bar and floats nothing over the evidence.
        final Rect bar = tester.getRect(find.byType(WorkbenchDecisionBar));
        final Rect top = tester.getRect(find.byType(UiTopBar));
        expect(
          bar.top,
          greaterThanOrEqualTo(top.top - 0.5),
          reason: 'the decision bar is not inside the top bar at $window',
        );
        expect(bar.bottom, lessThanOrEqualTo(top.bottom + 0.5));
        expect(
          find.ancestor(
            of: find.byType(WorkbenchDecisionBar),
            matching: find.byWidgetPredicate(
              (Widget widget) =>
                  widget is PinnedChrome &&
                  widget.region == UiPinnedRegion.topBar,
            ),
          ),
          findsOneWidget,
          reason: 'the frame does not count the bar as its top bar',
        );
        expect(
          find.byWidgetPredicate(
            (Widget widget) =>
                widget is PinnedChrome &&
                widget.region == UiPinnedRegion.actionBar,
          ),
          findsNothing,
          reason: 'the action bar was not given back at $window',
        );
        // The identifier keeps its own width beside the decision: the name
        // is never cut, the decision degrades by its own ladder.
        expect(find.text('layout-001'), findsOneWidget);
        expect(
          tester.getRect(find.text('layout-001')).right,
          lessThanOrEqualTo(bar.left + 0.5),
        );
        // Both decisions are reachable from the bar at this width.
        expect(controlEnabled(tester, 'Confirm label coverage'), isTrue);
        expect(
          UiScaffold.of(
            tester.element(find.byType(ReviewWorkbench)),
          ).bottomInset,
          0,
          reason: 'the frame floats nothing inside a record at $window',
        );
      }
    });
  });

  group('the blockers summary', () {
    test('one list is assembled from every place a gate lives', () {
      final blockers = blockersFor(
        Specimen({
          ...record().data,
          'reason_codes': const ['coverage_unconfirmed'],
          'transcriptions': const [
            {'region_id': 'r1', 'resolved': false},
          ],
          'run': const {'blocker': 'external_outcome_unknown'},
        }),
      );
      expect(blockers, hasLength(4));
      expect(blockers.map((b) => b.segment).toSet(), {
        WorkbenchSegment.readings,
        WorkbenchSegment.fields,
      });
      // A record with nothing outstanding carries no summary at all: a
      // control that opens an empty list is a control that does nothing, and
      // the decision bar's enabled approval already says it (13 section 3.2).
      expect(blockersSummary(1), '1 thing blocks clearance');
      expect(blockersSummary(4), '4 things block clearance');
    });

    testWidgets('each entry moves to the control that resolves it', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      expect(find.text('1 thing blocks clearance'), findsOneWidget);
      await tester.tap(find.text('1 thing blocks clearance'));
      await tester.pumpAndSettle();
      expect(find.text('A supported country is required'), findsWidgets);
      await tester.tap(find.text('Go to').first);
      await tester.pumpAndSettle();
      // The fields segment is now showing, with the field on screen.
      expect(find.text('Country (required)'), findsOneWidget);
    });
  });

  group('the reading diff', () {
    test('the summary is quantified, not a symbol', () {
      expect(
        DiffText.compare('Chicago 1917', 'Chicago 1912').summary,
        'Differs in 1 place',
      );
      expect(
        DiffText.compare('Chicago 1917', 'Chicago 1912').differingPositions,
        1,
      );
      expect(DiffText.summaryFor(3), 'Differs in 3 places');
    });

    testWidgets('the summary is on screen and spoken with the reading', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      expect(find.text('Differs in 1 place'), findsOneWidget);
      expect(
        find.bySemanticsLabel(RegExp('Differs in 1 place')),
        findsOneWidget,
      );
      semantics.dispose();
    });
  });

  group('region selection', () {
    testWidgets('the chip and the overlay carry the same name and state', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      for (final name in ['Label 1', 'Label 2']) {
        expect(regionChip(name), findsOneWidget);
        expect(find.bySemanticsLabel(name), findsWidgets);
      }
      await tester.tap(regionChip('Label 2'));
      await tester.pumpAndSettle();
      expect(
        tester
            .getSemantics(find.bySemanticsLabel('Label 2').first)
            .getSemanticsData()
            .flagsCollection
            .isSelected,
        Tristate.isTrue,
      );
      semantics.dispose();
    });

    testWidgets('a digit selects the nth region from the keyboard', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.digit2);
      await tester.pumpAndSettle();
      expect(tester.widget<Pressable>(regionChip('Label 2')).selected, isTrue);
    });

    testWidgets('J and K move between specimens only when the host offers it', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      var next = 0;
      var previous = 0;
      await tester.pumpWidget(
        host(record(), onNext: () => next++, onPrevious: () => previous++),
      );
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.keyJ);
      await tester.sendKeyEvent(LogicalKeyboardKey.keyK);
      await tester.pumpAndSettle();
      expect(next, 1);
      expect(previous, 1);
      expect(uiIconButton('Next specimen'), findsOneWidget);
      expect(uiIconButton('Previous specimen'), findsOneWidget);

      // Without the callbacks the control is drawn disabled with the reason
      // on it, the way every other control in the system carries a
      // `disabledReason` (13 section 3.3, polish 3), and the key says the
      // same sentence aloud rather than doing nothing at all (pass criterion
      // 5.6, finding V-2).
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      final UiIconButton nextControl = tester.widget<UiIconButton>(
        uiIconButton('Next specimen'),
      );
      expect(nextControl.onPressed, isNull);
      expect(nextControl.disabledReason, notInQueueMessage);
      expect(
        tester
            .widget<UiIconButton>(uiIconButton('Previous specimen'))
            .disabledReason,
        notInQueueMessage,
      );
      final semantics = tester.ensureSemantics();
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
      await tester.sendKeyEvent(LogicalKeyboardKey.keyJ);
      await tester.pumpAndSettle();
      expect(announced, contains(notInQueueMessage));
      semantics.dispose();
    });

    testWidgets('the shortcut list is one keystroke away', (tester) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      await tester.sendKeyDownEvent(LogicalKeyboardKey.shift);
      await tester.sendKeyEvent(LogicalKeyboardKey.slash);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.shift);
      await tester.pumpAndSettle();
      expect(find.text('Keyboard shortcuts'), findsOneWidget);
      expect(find.text('Next specimen'), findsOneWidget);
    });
  });

  group('pending changes', () {
    test('a change that moved under the reviewer is dropped, not applied', () {
      const pending = PendingFieldChange(
        fieldKey: 'country',
        displayName: 'Country',
        state: 'supported',
        literal: 'United States',
        baseLiteral: 'Unites States',
      );
      final split = reapply(
        <PendingFieldChange>[pending],
        Specimen({
          ...record().data,
          'fields': const [
            {
              'field_key': 'country',
              'display_name': 'Country',
              'state': 'supported',
              'literal_value': 'United States of America',
            },
          ],
        }),
      );
      expect(split.keep, isEmpty);
      expect(split.stale, hasLength(1));
    });

    test('a change whose field is untouched survives a new version', () {
      const pending = PendingFieldChange(
        fieldKey: 'country',
        displayName: 'Country',
        state: 'unknown',
      );
      final split = reapply(<PendingFieldChange>[pending], record());
      expect(split.keep, hasLength(1));
      expect(split.stale, isEmpty);
    });

    test('the chip says how many, in words', () {
      expect(pendingChangesLabel(1), '1 pending change');
      expect(pendingChangesLabel(3), '3 pending changes');
    });
  });

  group('conflict', () {
    testWidgets('a version that arrives from elsewhere raises a banner', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      expect(find.byType(ConflictBanner), findsNothing);
      await tester.pumpWidget(
        host(Specimen({...record().data, 'revision': 22})),
      );
      await tester.pumpAndSettle();
      expect(find.byType(ConflictBanner), findsOneWidget);
      expect(
        find.text(
          'Version 22 was saved by another reviewer. Refresh and '
          'compare.',
        ),
        findsOneWidget,
      );
      expect(find.text('Refresh and compare'), findsOneWidget);
    });
  });
}
