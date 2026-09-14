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
          compactWindow.height * sourcePaneMinViewportFraction * 0.6,
        ),
      );

      // It does not scroll with the evidence: scrolling the evidence pane
      // leaves the photograph where it was.
      final before = tester.getTopLeft(find.byType(InteractiveViewer));
      await tester.drag(
        find.byType(SegmentedButton<WorkbenchSegment>),
        const Offset(0, -200),
      );
      await tester.pumpAndSettle();
      expect(tester.getTopLeft(find.byType(InteractiveViewer)), before);

      // The photograph can be collapsed and brought back.
      await tester.tap(find.byTooltip('Collapse the photograph'));
      await tester.pumpAndSettle();
      expect(find.byType(InteractiveViewer), findsNothing);
      await tester.tap(find.byTooltip('Show the photograph'));
      await tester.pumpAndSettle();
      expect(find.byType(InteractiveViewer), findsOneWidget);
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
          of: find.byType(SegmentedButton<WorkbenchSegment>),
          matching: find.text('History'),
        ),
        findsNothing,
      );
      expect(
        tester.getSize(find.byType(AuditHistoryPanel)).width,
        closeTo(historyPaneWidth, 1),
      );
    });

    testWidgets('the decision bar is pinned at every regime', (tester) async {
      for (final window in [compactWindow, expandedWindow, largeWindow]) {
        useWindow(tester, window);
        await tester.pumpWidget(host(record()));
        await tester.pumpAndSettle();
        final bar = tester.getRect(
          find
              .ancestor(
                of: find.text('Approve record'),
                matching: find.byType(SafeArea),
              )
              .first,
        );
        expect(
          bar.bottom,
          closeTo(window.height, 32),
          reason: 'the decision bar sits at the foot of the pane at $window',
        );
        // It is below the evidence, which is the thing that scrolls.
        expect(
          bar.top,
          greaterThanOrEqualTo(
            tester.getRect(scrollableIn(find.byType(ReviewWorkbench))).bottom -
                1,
          ),
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
      expect(blockersSummary(0), 'Nothing outstanding. Approval is available.');
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
        'Differs at 1 position',
      );
      expect(
        DiffText.compare('Chicago 1917', 'Chicago 1912').differingPositions,
        1,
      );
      expect(DiffText.summaryFor(3), 'Differs at 3 positions');
    });

    testWidgets('the summary is on screen and spoken with the reading', (
      tester,
    ) async {
      useWindow(tester, largeWindow);
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      expect(find.text('Differs at 1 position'), findsOneWidget);
      expect(
        find.bySemanticsLabel(RegExp('Differs at 1 position')),
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
        expect(find.widgetWithText(ChoiceChip, name), findsOneWidget);
        expect(find.bySemanticsLabel(name), findsWidgets);
      }
      await tester.tap(find.widgetWithText(ChoiceChip, 'Label 2'));
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
      expect(
        tester
            .widget<ChoiceChip>(find.widgetWithText(ChoiceChip, 'Label 2'))
            .selected,
        isTrue,
      );
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
      expect(find.byTooltip('Next specimen'), findsOneWidget);
      expect(find.byTooltip('Previous specimen'), findsOneWidget);

      // Without the callbacks there is no control and no shortcut, because a
      // control that does nothing is worse than no control.
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      expect(find.byTooltip('Next specimen'), findsNothing);
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
