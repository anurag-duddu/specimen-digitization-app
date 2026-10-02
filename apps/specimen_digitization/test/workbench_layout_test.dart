// The qualified workbench uses one page on narrow constraints and a dominant
// canvas beside one inspector when readable columns and height permit it.
// History stays in the shared tab strip; decisions remain reachable locally.
// Policy, blocker navigation, reading semantics, keyboard and conflict controls
// below the layout group retain their behavior with actual control interactions.

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
import 'reading_region_comparison_test.dart' show selectLabel;
import 'ui_finders.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/screens/workbench/decision_bar.dart';

/// The actual source overlay action, scoped by region identity.
Finder regionOverlay(int index) => find.byWidgetPredicate(
  (Widget widget) => widget is RegionOverlay && widget.index == index,
  description: 'saved label overlay $index',
);

Finder regionOverlayControl(int index) => find.descendant(
  of: regionOverlay(index),
  matching: find.byWidgetPredicate(
    (Widget widget) =>
        widget is Pressable && widget.semanticsLabel == 'Label $index',
  ),
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
    test('readable local columns choose stacked or two-pane review', () {
      expect(WorkbenchRegime.fromWidth(599), WorkbenchRegime.stacked);
      expect(WorkbenchRegime.fromWidth(767), WorkbenchRegime.stacked);
      expect(WorkbenchRegime.fromWidth(768), WorkbenchRegime.twoPane);
      expect(WorkbenchRegime.fromWidth(840), WorkbenchRegime.twoPane);
      expect(WorkbenchRegime.fromWidth(1200), WorkbenchRegime.twoPane);
      for (final regime in WorkbenchRegime.values) {
        expect(WorkbenchSegment.forRegime(regime), WorkbenchSegment.values);
      }
    });

    test(
      'height and enlarged text can return a wide allocation to one scroll',
      () {
        expect(
          WorkbenchRegime.fromConstraints(
            const BoxConstraints(maxWidth: 1000, maxHeight: 600),
          ),
          WorkbenchRegime.twoPane,
        );
        expect(
          WorkbenchRegime.fromConstraints(
            const BoxConstraints(maxWidth: 1000, maxHeight: 200),
          ),
          WorkbenchRegime.stacked,
        );
        expect(
          WorkbenchRegime.fromConstraints(
            const BoxConstraints(maxWidth: 1000, maxHeight: 600),
            textScaler: const TextScaler.linear(2),
          ),
          WorkbenchRegime.stacked,
        );
      },
    );

    testWidgets('compact photograph leaves with the page instead of pinning', (
      tester,
    ) async {
      useWindow(tester, compactWindow);
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      expect(find.text('History'), findsOneWidget);
      expect(find.byType(AuditHistoryPanel), findsNothing);
      final Finder photo = find.byType(InteractiveViewer);
      final Rect before = tester.getRect(photo);
      expect(before.height, greaterThanOrEqualTo(sourceImageMinHeight));
      expect(before.width, lessThanOrEqualTo(compactWindow.width));
      await tester.drag(find.byKey(evidenceScrollKey), const Offset(0, -200));
      await tester.pumpAndSettle();
      expect(tester.getTopLeft(photo).dy, lessThan(before.top));
      expect(find.byType(InteractiveViewer), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('landscape puts the photograph beside one review inspector', (
      tester,
    ) async {
      useWindow(tester, expandedWindow);
      await tester.pumpWidget(host(record()));
      await tester.pumpAndSettle();
      final Rect source = tester.getRect(find.byType(InteractiveViewer));
      final Rect inspector = tester.getRect(
        find.byKey(const ValueKey<String>('review-inspector')),
      );
      expect(source.right, lessThanOrEqualTo(inspector.left));
      expect(source.width, greaterThan(0));
      expect(inspector.width, greaterThan(0));
      expect(find.text('History'), findsOneWidget);
      expect(find.byType(AuditHistoryPanel), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets(
      'wide History stays a tab and restores Labels without moving source',
      (tester) async {
        useWindow(tester, largeWindow);
        await tester.pumpWidget(host(record()));
        await tester.pumpAndSettle();
        final Finder tabs = find.byKey(
          const ValueKey<String>('review-context-tabs'),
        );
        final Finder historyTab = find.descendant(
          of: tabs,
          matching: find.text('History'),
        );
        final Finder labelsTab = find.descendant(
          of: tabs,
          matching: find.text('Labels'),
        );
        expect(historyTab, findsOneWidget);
        expect(find.byType(AuditHistoryPanel), findsNothing);
        final Rect source = tester.getRect(find.byType(InteractiveViewer));
        await tester.tap(historyTab);
        await tester.pumpAndSettle();
        expect(find.byType(AuditHistoryPanel), findsOneWidget);
        expect(tester.getRect(find.byType(InteractiveViewer)), source);
        await tester.tap(labelsTab);
        await tester.pumpAndSettle();
        expect(find.byType(AuditHistoryPanel), findsNothing);
        expect(
          find.byType(AuditHistoryPanel, skipOffstage: false),
          findsOneWidget,
          reason:
              'visited history is retained without exposing hidden controls',
        );
        expect(tester.getRect(find.byType(InteractiveViewer)), source);
        expect(tester.takeException(), isNull);
      },
    );

    testWidgets(
      'wide inspector scrolls evidence while keeping its decision reachable',
      (tester) async {
        useWindow(tester, largeWindow);
        final crowded = record(
          extraFindings: List<Json>.generate(
            20,
            (index) => <String, dynamic>{
              'field_key': 'country',
              'message': 'Synthetic retained finding $index',
              'severity': 'hard',
              'rule_id': 'synthetic-$index',
            },
          ),
        );
        await tester.pumpWidget(host(crowded));
        await tester.pumpAndSettle();
        final Finder bar = find.byType(WorkbenchDecisionBar);
        final Rect before = tester.getRect(bar);
        await tester.tap(find.text('Specimen data'));
        await tester.pumpAndSettle();
        await tester.drag(find.byKey(evidenceScrollKey), const Offset(0, -250));
        await tester.pumpAndSettle();
        expect(tester.getRect(bar), before);
        expect(bar.hitTestable(), findsOneWidget);
        expect(controlEnabled(tester, 'Confirm label coverage'), isTrue);
        expect(tester.takeException(), isNull);
      },
    );

    test('the segments stick only at default type at every window class', () {
      for (final WindowClass window in WindowClass.values) {
        expect(segmentsStick(TextScaler.noScaling, window), isTrue);
        expect(segmentsStick(const TextScaler.linear(1.3), window), isFalse);
        expect(segmentsStick(const TextScaler.linear(2.0), window), isFalse);
      }
    });

    testWidgets(
      'compact decisions stay below the page and clear its viewport',
      (tester) async {
        useWindow(tester, compactWindow);
        await tester.pumpWidget(host(record()));
        await tester.pumpAndSettle();
        final Finder bar = find.byType(WorkbenchDecisionBar);
        final Rect before = tester.getRect(bar);
        final Rect scroll = tester.getRect(find.byKey(evidenceScrollKey));
        expect(scroll.bottom, lessThanOrEqualTo(before.top));
        expect(before.bottom, lessThanOrEqualTo(compactWindow.height));
        expect(before.bottom, greaterThan(compactWindow.height - 48));
        await tester.drag(find.byKey(evidenceScrollKey), const Offset(0, -200));
        await tester.pumpAndSettle();
        expect(tester.getRect(bar), before);
        expect(bar.hitTestable(), findsOneWidget);
        expect(controlEnabled(tester, 'Confirm label coverage'), isTrue);
        expect(tester.takeException(), isNull);
      },
    );

    testWidgets(
      'wide decisions belong to the inspector and leave the top bar free',
      (tester) async {
        for (final window in <Size>[
          mediumWindow,
          expandedWindow,
          largeWindow,
        ]) {
          useWindow(tester, window);
          await tester.pumpWidget(host(record()));
          await tester.pumpAndSettle();
          final Finder bar = find.byType(WorkbenchDecisionBar);
          final Rect decision = tester.getRect(bar);
          final Rect inspector = tester.getRect(
            find.byKey(const ValueKey<String>('review-inspector')),
          );
          final Rect top = tester.getRect(find.byType(UiTopBar));
          expect(decision.left, greaterThanOrEqualTo(inspector.left));
          expect(decision.right, lessThanOrEqualTo(inspector.right));
          expect(decision.top, greaterThanOrEqualTo(top.bottom));
          expect(decision.bottom, lessThanOrEqualTo(inspector.bottom));
          expect(
            find.ancestor(of: bar, matching: find.byType(UiTopBar)),
            findsNothing,
          );
          expect(find.text('layout-001'), findsOneWidget);
          expect(controlEnabled(tester, 'Confirm label coverage'), isTrue);
          expect(
            UiScaffold.of(
              tester.element(find.byType(ReviewWorkbench)),
            ).bottomInset,
            0,
            reason: 'the frame reserves no duplicate action-bar region',
          );
          expect(tester.takeException(), isNull);
        }
      },
    );
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

    testWidgets(
      'a blocked field exposes its finding beside its correction control',
      (tester) async {
        useWindow(tester, largeWindow);
        await tester.pumpWidget(host(record()));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Specimen data'));
        await tester.pumpAndSettle();
        final Finder finding = find.text('A supported country is required');
        await tester.ensureVisible(finding);
        await tester.pumpAndSettle();
        expect(finding, findsOneWidget);
        expect(find.text('Required'), findsOneWidget);
        expect(find.text('Country'), findsOneWidget);
        final Finder disclosure = find.descendant(
          of: find.byType(FieldRow).first,
          matching: find.byType(UiDisclosure),
        );
        final Finder header = find.descendant(
          of: disclosure,
          matching: find.byWidgetPredicate(
            (Widget widget) => widget is Pressable && widget.onPressed != null,
          ),
        );
        expect(header, findsOneWidget);
        await tester.ensureVisible(header);
        await tester.tap(header);
        await tester.pumpAndSettle();
        final Finder edit = uiIconButton('Edit as written for Country');
        expect(edit, findsOneWidget);
        expect(tester.widget<UiIconButton>(edit).onPressed, isNotNull);
        // Check the genuine correction control while its route is visible.
        // Opening its dialog puts that underlying route offstage.
        await scrollAndTap(tester, edit);
        expect(find.text('Correct Country'), findsOneWidget);
        expect(uiSelect('Evidence state'), findsOneWidget);
        expect(find.text('Keep this correction'), findsOneWidget);
        expect(tester.takeException(), isNull);
      },
    );
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
    testWidgets(
      'the label selector and source overlay carry the same saved selection',
      (tester) async {
        useWindow(tester, largeWindow);
        final semantics = tester.ensureSemantics();
        try {
          await tester.pumpWidget(host(record()));
          await tester.pumpAndSettle();
          final UiSelect<String> selector = tester.widget<UiSelect<String>>(
            uiSelect('Label'),
          );
          expect(
            selector.options.map((option) => option.label),
            containsAll(<String>['Label 1', 'Label 2']),
          );
          for (final int index in <int>[1, 2]) {
            expect(regionOverlay(index), findsOneWidget);
            expect(regionOverlayControl(index), findsOneWidget);
            expect(find.bySemanticsLabel('Label $index'), findsWidgets);
          }
          await selectLabel(tester, 2);
          expect(
            tester.widget<UiSelect<String>>(uiSelect('Label')).value,
            'r2',
          );
          expect(
            tester.widget<RegionOverlay>(regionOverlay(2)).selected,
            isTrue,
          );
          expect(
            tester.widget<RegionOverlay>(regionOverlay(1)).selected,
            isFalse,
          );
          expect(
            tester
                .getSemantics(regionOverlayControl(2))
                .getSemanticsData()
                .flagsCollection
                .isSelected,
            Tristate.isTrue,
          );
          expect(tester.takeException(), isNull);
        } finally {
          semantics.dispose();
        }
      },
    );

    testWidgets(
      'a digit selects the same saved label in selector and photograph',
      (tester) async {
        useWindow(tester, largeWindow);
        await tester.pumpWidget(host(record()));
        await tester.pumpAndSettle();
        final Finder canvas = find.byKey(
          const ValueKey<String>('source-photo-viewport'),
        );
        await tester.ensureVisible(canvas);
        await tester.pumpAndSettle();
        expect(canvas.hitTestable(), findsOneWidget);
        await tester.tap(canvas);
        await tester.pumpAndSettle();
        await tester.sendKeyEvent(LogicalKeyboardKey.digit2);
        await tester.pumpAndSettle();
        expect(tester.widget<UiSelect<String>>(uiSelect('Label')).value, 'r2');
        expect(tester.widget<RegionOverlay>(regionOverlay(2)).selected, isTrue);
        expect(
          tester.widget<RegionOverlay>(regionOverlay(1)).selected,
          isFalse,
        );
      },
    );

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
        find.text('A newer version (22) is available. Refresh and compare.'),
        findsOneWidget,
      );
      expect(find.text('Refresh and compare'), findsOneWidget);
    });
  });
}
