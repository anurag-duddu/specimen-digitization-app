// Pass criterion 1.2: a server action shows progress on the control within
// 200 ms of the press, and a result within a second of the server answering.
//
// The verification report marked 1.2 Partial for one reason: the affordances
// were there and nothing measured them. These three tests measure them, on
// the three actions the criterion is about, against the routed application
// rather than a component in isolation, because the progress flag the
// criterion is about lives on `WorkspaceController` and reaches the control
// through the real screen.
//
// How the timing is held honest: the repository is gated on a `Completer`, so
// no wall clock is involved. `tester.pump(const Duration(milliseconds: 200))`
// advances the test clock by exactly the budget and no further; if a control
// needed longer than the budget to show progress, the frame at 200 ms would
// not have it. The same for the second half: the gate is completed, the clock
// is advanced by one second, and the result has to be on screen.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/decision_bar.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';

/// The budget criterion 1.2 gives a control to report that it is working.
const Duration progressBudget = Duration(milliseconds: 200);

/// The budget criterion 1.2 gives the screen to show the result.
const Duration resultBudget = Duration(seconds: 1);

/// A queue that can be held open, page by page and decision by decision.
class GatedRepository extends GoldenQueueRepository {
  GatedRepository(super.records);

  /// Held while the second page is out.
  Completer<void>? pageGate;

  /// Held while a decision is out.
  Completer<void>? reviewGate;

  /// Records loaded so far, so the first page can offer a cursor and the
  /// second can answer with more.
  bool firstPageAnswered = false;

  /// The keys every review call was given, in order.
  final List<String> reviewKeys = <String>[];

  /// Every change the repository was asked to record, in order.
  final List<Json> changes = <Json>[];

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async {
    if (cursor != null && pageGate != null) await pageGate!.future;
    if (cursor != null) {
      return SpecimenPage(<Specimen>[
        Specimen(<String, dynamic>{
          ...records.first.data,
          'specimen_id': 'fixture-page-2',
          'display_name': 'Second page beetle',
        }),
      ]);
    }
    firstPageAnswered = true;
    return SpecimenPage(records, nextCursor: 'page-2');
  }

  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async {
    reviewKeys.add(key);
    changes.add(change);
    if (reviewGate != null) await reviewGate!.future;
    return Specimen(<String, dynamic>{
      ...specimen.data,
      'revision': (specimen.revision) + 1,
    });
  }
}

/// The status strip's version, which is where a landed decision shows.
///
/// `UiStatusStrip` joins its facts onto one line and draws them as one label,
/// so the version is a run inside that label rather than a node of its own
/// (13 section 3.2).
Finder versionLine(int revision) => find.byWidgetPredicate(
  (Widget widget) =>
      widget is Text && (widget.data ?? '').contains('Version $revision'),
);

/// The progress affordance every one of these controls swaps in.
///
/// Matched on the widget rather than on a rendered indicator, because the
/// glyph cross-fades: at the frame the budget lands on, the old glyph may
/// still be painting over the new one, and what the criterion is about is
/// whether the control has been told to report.
Finder get workingIndicator => find.byWidgetPredicate(
  (Widget widget) =>
      (widget is InFlightGlyph && widget.busy) ||
      (widget is UiButton && widget.loading),
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('load more shows progress in 200 ms and rows within a second', (
    WidgetTester tester,
  ) async {
    final GatedRepository repository = GatedRepository(goldenQueue(3));
    repository.pageGate = Completer<void>();
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 1400),
      brightness: Brightness.light,
      location: goldenQueueLocation,
      repository: repository,
    );
    expect(find.text('Load more records'), findsOneWidget);
    expect(workingIndicator, findsNothing);

    await tester.tap(find.text('Load more records'));
    // Exactly the budget, not a settle: a settle would wait for the control
    // however long it took, which is the thing being measured.
    await tester.pump(progressBudget);
    expect(
      workingIndicator,
      findsOneWidget,
      reason: 'the load more control reported nothing 200 ms after the press',
    );
    expect(find.text('Loading more…'), findsOneWidget);

    repository.pageGate!.complete();
    await tester.pump(resultBudget);
    expect(
      find.text('Second page beetle'),
      findsOneWidget,
      reason:
          'the appended rows were not on screen a second after the '
          'server answered',
    );
    expect(workingIndicator, findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a save shows progress in 200 ms and a result within a second', (
    WidgetTester tester,
  ) async {
    final GatedRepository repository = GatedRepository(goldenQueue(1));
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 1400),
      brightness: Brightness.light,
      location: goldenSpecimenLocationOf('fixture-001'),
      repository: repository,
    );

    await tester.tap(find.text('Fields'));
    await tester.pumpAndSettle();
    // Collectors, because it is the field the fixture reports as Unknown:
    // the correction form needs no authority match to keep, which keeps this
    // test about the timing rather than about the form.
    final Finder edit = uiIconButton('Edit as written for Collectors');
    await tester.ensureVisible(edit);
    await tester.tap(edit);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Keep this correction'));
    await tester.pumpAndSettle();
    expect(find.textContaining('1 pending change'), findsWidgets);

    repository.reviewGate = Completer<void>();
    await tester.tap(find.text('Save 1 pending change').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      uiField('Reason'),
      'The label does not carry a country',
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(
        of: find.byType(ReasonForm),
        matching: uiButton('Save 1 pending change'),
      ),
    );

    await tester.pump(progressBudget);
    // The decision bar is the frame's action bar, and a screen publishes into
    // the frame while it is being laid out, so the frame draws what it was
    // asked for in the frame after (13 section 3.4). No clock advances here:
    // the indicator is on screen at 200 ms and this is the paint of it.
    await tester.pump();
    expect(
      workingIndicator,
      findsWidgets,
      reason: 'the save reported nothing 200 ms after the press',
    );

    repository.reviewGate!.complete();
    await tester.pump(resultBudget);
    await tester.pump();
    expect(
      versionLine(18),
      findsOneWidget,
      reason:
          'the new version was not on screen a second after the save landed',
    );
    expect(workingIndicator, findsNothing);
    // The reviewer's own save is not another reviewer's version.
    expect(find.byType(ConflictBanner), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('approve shows progress in 200 ms and a result within a second', (
    WidgetTester tester,
  ) async {
    final GatedRepository repository = GatedRepository(goldenQueue(1));
    repository.reviewGate = Completer<void>();
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 1400),
      brightness: Brightness.light,
      location: goldenSpecimenLocationOf('fixture-001'),
      repository: repository,
    );

    await tester.ensureVisible(
      find.text(WorkbenchDecisionBar.approveLabel).last,
    );
    await tester.tap(find.text(WorkbenchDecisionBar.approveLabel).last);
    await tester.pumpAndSettle();
    await tester.enterText(
      uiField('Reason'),
      'Both readings agree and the label is legible',
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(
        of: find.byType(ReasonForm),
        matching: uiButton(WorkbenchDecisionBar.approveLabel),
      ),
    );

    await tester.pump(progressBudget);
    // As above: the frame draws the chrome one frame after the body asks.
    await tester.pump();
    expect(
      workingIndicator,
      findsWidgets,
      reason: 'approve reported nothing 200 ms after the press',
    );

    repository.reviewGate!.complete();
    await tester.pump(resultBudget);
    await tester.pump();
    expect(
      versionLine(18),
      findsOneWidget,
      reason: 'the new version was not on screen a second after approve landed',
    );
    expect(workingIndicator, findsNothing);
    expect(find.byType(ConflictBanner), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
}
