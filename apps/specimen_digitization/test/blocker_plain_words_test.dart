// A run that stopped, said in plain words wherever a person reads it.
//
// The server blocks a run with a machine code. After its automatic retries
// run out the code is `retry_budget_exhausted:<cause>`, and a run stopped by a
// limit carries a code with "budget" in it that is a step limit, a request
// limit, a time limit or a cost limit. The processing panel, the workbench
// issue list, the queue row, the history and the filter menu each used to
// print that code, or its words with the underscores taken out. None of them
// may now: each shows a name and a sentence for the exact code, and a code
// this client has no words for gets a generic sentence rather than itself
// (UX writing guidelines 4.9: never expose a raw code in primary text).

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/audit_history.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/reason_codes.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/search_filters.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'widgets/harness.dart' show pumpComponent;
import 'workbench_harness.dart';

/// One blocker and the words a person reads for it.
///
/// [what] has no closing full stop, as in a list. [caveat] marks a stop the
/// panel sets in two parts, the sentence and then the instruction, with a
/// "Why" behind it; every other stop is one passage of two sentences.
/// [money] is true for a limit on money, the only kind that may say "cost".
typedef Case = ({
  String code,
  String label,
  String what,
  String next,
  bool caveat,
  bool money,
});

const String retryLater = 'Retry later, or ask an administrator.';
const String reviewLimit = 'An administrator must review the approved limit.';

Case stop(
  String code,
  String label,
  String what, {
  String next = reviewLimit,
  bool caveat = false,
  bool money = false,
}) => (
  code: code,
  label: label,
  what: what,
  next: next,
  caveat: caveat,
  money: money,
);

/// A run whose retries ran out, by the cause that stopped it.
final List<Case> retryCauses = <Case>[
  stop(
    'retry_budget_exhausted:lookup_operational_failure',
    'Retries stopped, source not reachable',
    // The wording PR #298 gave this cause, kept word for word.
    'An approved source could not be reached after repeated attempts',
    next: retryLater,
  ),
  stop(
    'retry_budget_exhausted:field_research_timeout',
    'Retries stopped, ran out of time',
    'Field research ran out of time after repeated attempts',
    next: retryLater,
  ),
  stop(
    'retry_budget_exhausted:field_research_model_error',
    'Retries stopped, no usable model answer',
    'The model gave no usable answer after repeated attempts',
    next: retryLater,
  ),
];

final Case unknownCause = stop(
  'retry_budget_exhausted:some_future_cause',
  'Automatic retries stopped',
  'Processing stopped after repeated attempts',
  next: retryLater,
);

final Case unknownCode = stop(
  'some_future_blocker',
  'Needs an operator check',
  'Processing needs an operator check before it can continue',
  next: 'Ask an administrator to review it.',
);

/// The limits the run carries, each named for what it limits. Only the two
/// limits on money say "cost" or "spending".
final List<Case> runLimits = <Case>[
  stop(
    'step_budget_exhausted',
    'Step limit reached',
    'The run reached its limit on processing steps',
  ),
  stop(
    'external_call_budget_exhausted',
    'External request limit reached',
    'The run reached its limit on external requests',
  ),
  stop(
    'token_budget_exhausted',
    'Model unit limit reached',
    'The run reached its limit on model units',
  ),
  stop(
    'active_time_budget_exhausted',
    'Active time limit reached',
    'The run reached its limit on active processing time',
  ),
  stop(
    'evidence_harness_blocked:elapsed_budget_exhausted',
    'Evidence check time limit reached',
    'An evidence check reached its time limit',
  ),
];

final List<Case> moneyLimits = <Case>[
  stop(
    'cost_budget_exhausted',
    'Cost limit reached',
    'Processing stopped at a cost limit',
    next:
        'An administrator must review the approved limit or the provider '
        'configuration.',
    caveat: true,
    money: true,
  ),
  stop(
    'program_allowance_exhausted',
    'Spending allowance reached',
    "Processing stopped at the program's spending allowance",
    next: 'An administrator must review the allowance.',
    caveat: true,
    money: true,
  ),
  stop(
    'pilot_launch_budget_exhausted',
    'Pilot cost limit reached',
    "The pilot's cost limit would be crossed",
    money: true,
  ),
  stop(
    'pilot_cohort_reading_budget_insufficient',
    'Reading cost limit too low',
    'The cost limit does not cover the planned readings',
    money: true,
  ),
];

/// A limit that could not be checked, because its settings or totals were
/// not available. These are not limits on money being reached.
final List<Case> settingsUnavailable = <Case>[
  stop(
    'approved_cost_budget_unavailable',
    'Cost settings not available',
    'The approved cost settings for this run are not available',
    next: 'An administrator must review the cost settings.',
  ),
  stop(
    'research_budget_state_unavailable',
    'Saved cost totals not readable',
    'The saved cost totals for this record could not be read',
    next: 'An operator must check them before processing continues.',
  ),
  stop(
    'program_allowance_ledger_unavailable',
    'Allowance totals not readable',
    "The program's spending totals could not be read",
    next: 'An operator must check them before processing continues.',
  ),
  stop(
    'program_allowance_unavailable',
    'Spending allowance not set up',
    "The program's spending allowance is not set up for this collection",
    next: 'An administrator must review the allowance settings.',
  ),
  stop(
    'pilot_run_budget_not_approved',
    'Run limits do not fit the pilot',
    "The run's approved limits do not fit the pilot launch",
    next: 'An administrator must review them.',
  ),
  stop(
    'pilot_stage_cost_reservations_mismatch',
    'Stage cost settings differ',
    "The run's stage cost settings differ from the pilot launch",
    next: 'An administrator must review them.',
  ),
  stop(
    'pilot_cohort_reader_cost_unknown',
    'Reading cost not set',
    'The cost of a reading step is not set',
    next: 'An administrator must review the cost settings.',
  ),
];

final List<Case> limitFamilies = <Case>[
  ...runLimits,
  ...moneyLimits,
  ...settingsUnavailable,
];

final List<Case> everyCase = <Case>[
  ...retryCauses,
  unknownCause,
  unknownCode,
  ...limitFamilies,
];

/// Every piece of text on screen, as the person reads it.
List<String> visibleText(WidgetTester tester) => <String>[
  for (final RichText text in tester.widgetList<RichText>(
    find.byType(RichText),
  ))
    text.text.toPlainText(),
];

/// Fails when any text on screen is a machine code, or carries one, or
/// carries it with the underscores taken out (which is how the screens used to
/// print it).
void expectNoCodeOnScreen(WidgetTester tester, String code) {
  final List<String> spoken = <String>[
    'retry_budget_exhausted',
    for (final String part in code.split(':')) part,
  ];
  for (final String text in visibleText(tester)) {
    for (final String part in spoken) {
      expect(text, isNot(contains(part)), reason: text);
      expect(
        text.toLowerCase(),
        isNot(contains(part.replaceAll('_', ' '))),
        reason: text,
      );
    }
    expect(
      RegExp(r'[A-Za-z]+_[A-Za-z_]+').hasMatch(text),
      isFalse,
      reason: 'an underscore code is on screen: "$text"',
    );
  }
}

void main() {
  group('the processing panel', () {
    Future<void> show(WidgetTester tester, String blocker) async {
      await tester.pumpWidget(
        scrollingHost(
          OperationalPanel(
            specimen: Specimen(<String, dynamic>{
              'specimen_id': 's',
              'available_actions': <String>['reprocess'],
              'run': <String, dynamic>{
                'blocker': blocker,
                'dead_letter': blocker.startsWith('retry_budget_exhausted:'),
                'attempts': <String, dynamic>{'field_research': 3},
              },
            }),
            canOperate: true,
            busy: false,
            onAction: (_) async {},
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    for (final Case cause in everyCase) {
      testWidgets('${cause.code} says "${cause.label}", never the code', (
        WidgetTester tester,
      ) async {
        await show(tester, cause.code);
        expect(find.text('Blocked: ${cause.label}'), findsOneWidget);
        if (cause.caveat) {
          expect(find.text('${cause.what}.'), findsOneWidget);
          expect(find.text(cause.next), findsOneWidget);
        } else {
          expect(find.text('${cause.what}. ${cause.next}'), findsOneWidget);
        }
        expectNoCodeOnScreen(tester, cause.code);
        expect(tester.takeException(), isNull);
      });
    }

    for (final Case limit in runLimits) {
      testWidgets('${limit.code} is no cost limit, and says nothing of cost', (
        WidgetTester tester,
      ) async {
        await show(tester, limit.code);
        for (final String text in visibleText(tester)) {
          expect(text.toLowerCase(), isNot(contains('cost')), reason: text);
          expect(text.toLowerCase(), isNot(contains('spending')), reason: text);
        }
      });
    }

    testWidgets('a blocker the client names keeps its own words', (
      WidgetTester tester,
    ) async {
      await show(tester, 'external_outcome_unknown');
      expect(find.text('Blocked: Last request may have run'), findsOneWidget);
      expect(
        find.text(
          'The last external request may have run. Its result is unknown.',
        ),
        findsOneWidget,
      );
      expect(
        find.text('${unknownCode.what}. ${unknownCode.next}'),
        findsNothing,
      );
      expectNoCodeOnScreen(tester, 'external_outcome_unknown');
    });

    testWidgets('a word in the code decides nothing: an unlisted budget or '
        'cost code reads generically', (WidgetTester tester) async {
      for (final String code in <String>[
        'some_future_budget_exhausted',
        'some_future_cost_check',
      ]) {
        await show(tester, code);
        expect(find.text('Blocked: Needs an operator check'), findsOneWidget);
        expect(find.textContaining('cost limit'), findsNothing);
        expectNoCodeOnScreen(tester, code);
      }
    });
  });

  group('the workbench issue list', () {
    Specimen record(String blocker) => Specimen(<String, dynamic>{
      'specimen_id': 'plain-words-001',
      'display_name': 'Synthetic record',
      'revision': 2,
      'disposition': 'needs_human_review',
      'available_actions': const <String>['reprocess'],
      'reason_codes': <String>[blocker],
      'fields': const <Json>[
        <String, dynamic>{
          'field_key': 'country',
          'display_name': 'Country',
          'state': 'unknown',
        },
      ],
      'run': <String, dynamic>{
        'blocker': blocker,
        'dead_letter': blocker.startsWith('retry_budget_exhausted:'),
      },
    });

    Future<void> pumpWorkbench(WidgetTester tester, String blocker) async {
      useWindow(tester, largeWindow);
      await tester.pumpWidget(
        workbenchHost(
          ReviewWorkbench(
            specimen: record(blocker),
            onChange: (_) async => false,
            onRetry: (_) async {},
            onRefresh: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    Future<void> openRequirements(WidgetTester tester, String blocker) async {
      await pumpWorkbench(tester, blocker);
      await tester.ensureVisible(find.text('Record review requirements'));
      await tester.tap(find.text('Record review requirements'));
      await tester.pumpAndSettle();
    }

    // One of each family: a run limit, each kind of money limit, a limit that
    // could not be checked, the evidence check's time and the pilot's.
    final List<Case> listed = <Case>[
      ...retryCauses,
      unknownCause,
      runLimits.first,
      runLimits.last,
      moneyLimits.first,
      moneyLimits[1],
      moneyLimits[2],
      settingsUnavailable[1],
      settingsUnavailable[3],
      settingsUnavailable[4],
    ];
    for (final Case cause in listed) {
      testWidgets('${cause.code} is listed as its cause and a next step', (
        WidgetTester tester,
      ) async {
        await openRequirements(tester, cause.code);
        expect(find.text(cause.what), findsOneWidget);
        expect(find.text(cause.next), findsOneWidget);
        // The list names the record's one block once, not once per source of
        // the same code.
        expect(
          find.text('A specimen check needs review before approval'),
          findsNothing,
        );
        expectNoCodeOnScreen(tester, cause.code);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('the code stays in the technical details, two taps down', (
      WidgetTester tester,
    ) async {
      final String code = retryCauses.first.code;
      await pumpWorkbench(tester, code);
      expect(find.textContaining('retry_budget_exhausted'), findsNothing);
      for (final String title in <String>[
        'Review details',
        'Technical review details',
      ]) {
        await tester.ensureVisible(find.text(title));
        await tester.tap(find.text(title));
        await tester.pumpAndSettle();
      }
      expect(find.textContaining(code), findsOneWidget);
    });

    testWidgets('an unknown code is listed in the generic sentence', (
      WidgetTester tester,
    ) async {
      await openRequirements(tester, unknownCode.code);
      expect(find.text(unknownCode.what), findsOneWidget);
      expectNoCodeOnScreen(tester, unknownCode.code);
    });

    testWidgets('an unlisted budget code is listed generically, not as a '
        'limit', (WidgetTester tester) async {
      await openRequirements(tester, 'some_future_budget_exhausted');
      expect(find.text(unknownCode.what), findsOneWidget);
      expect(find.textContaining('limit'), findsNothing);
    });
  });

  group('the queue row', () {
    for (final Case cause in everyCase) {
      test('${cause.code} reads "${cause.label}"', () {
        final String reason = queueReason(
          Specimen(<String, dynamic>{
            'specimen_id': 's',
            'blocker': cause.code,
            'reason_codes': <String>[cause.code],
          }),
        );
        expect(reason, cause.label);
      });
    }
  });

  group('the history', () {
    Future<void> showChange(
      WidgetTester tester, {
      required Object? before,
      required Object? after,
    }) async {
      const Specimen current = Specimen(<String, dynamic>{
        'specimen_id': 's',
        'revision': 3,
      });
      await tester.pumpWidget(
        scrollingHost(
          AuditHistoryPanel(
            specimen: current,
            embedded: true,
            loadPage: (int after, int through) async => HistoryPage(
              items: <Json>[
                for (int revision = after + 1; revision <= through; revision++)
                  <String, dynamic>{
                    'revision': revision,
                    'action': 'review_field',
                    'actor': 'Reviewer',
                    'created_at': '2026-09-27T10:00:00Z',
                  },
              ],
              throughRevision: through,
            ),
            loadRevision: (int revision, String? runId, String? digest) async =>
                Specimen(<String, dynamic>{
                  'specimen_id': 's',
                  'revision': revision,
                  'audit_events': <Json>[
                    <String, dynamic>{
                      'action': 'legacy',
                      'before': <String, dynamic>{'blocker': before},
                      'after': <String, dynamic>{'blocker': after},
                    },
                  ],
                }),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Saved versions'));
      await tester.tap(find.text('Saved versions'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Version 2'));
      await tester.tap(find.text('Version 2'));
      await tester.pumpAndSettle();
    }

    testWidgets('a changed blocker reads in plain words', (
      WidgetTester tester,
    ) async {
      await showChange(
        tester,
        before: retryCauses.first.code,
        after: unknownCode.code,
      );
      expect(
        find.text(
          'Processing blocker: ${retryCauses.first.label} → '
          '${unknownCode.label}',
        ),
        findsWidgets,
      );
      expectNoCodeOnScreen(tester, retryCauses.first.code);
      expectNoCodeOnScreen(tester, unknownCode.code);
    });

    testWidgets('a limit reads as the limit it is', (
      WidgetTester tester,
    ) async {
      await showChange(
        tester,
        before: 'step_budget_exhausted',
        after: 'cost_budget_exhausted',
      );
      expect(
        find.text(
          'Processing blocker: Step limit reached → Cost limit reached',
        ),
        findsWidgets,
      );
    });

    for (final Object? absent in <Object?>[null, '']) {
      testWidgets('a blocker that is ${absent == null ? 'null' : 'empty'} '
          'reads "Not recorded"', (WidgetTester tester) async {
        await showChange(tester, before: retryCauses.first.code, after: absent);
        expect(
          find.text(
            'Processing blocker: ${retryCauses.first.label} → Not recorded',
          ),
          findsWidgets,
        );
      });
    }
  });

  group('the reason sheet', () {
    test('a run whose retries ran out is offered as its cause', () {
      final List<Case> codes = <Case>[...retryCauses, unknownCause];
      final List<String> reasons = recordReasonCodes(
        Specimen(<String, dynamic>{
          'specimen_id': 's',
          'reason_codes': <String>[for (final Case cause in codes) cause.code],
        }),
      );
      expect(reasons, <String>[for (final Case cause in codes) cause.label]);
    });

    test('a limit is offered as the limit it is', () {
      final List<String> reasons = recordReasonCodes(
        const Specimen(<String, dynamic>{
          'specimen_id': 's',
          'reason_codes': <String>[
            'step_budget_exhausted',
            'cost_budget_exhausted',
          ],
        }),
      );
      expect(reasons, <String>['Step limit reached', 'Cost limit reached']);
    });
  });

  group('the filter form', () {
    Future<List<String>> menuFor(
      WidgetTester tester,
      List<String> codes,
    ) async {
      await pumpComponent(
        tester,
        Builder(
          builder: (BuildContext context) => UiButton(
            label: 'Open',
            onPressed: () => SearchFilters.show(
              context,
              initial: const <String, String>{},
              configuration: <String, dynamic>{'blockers': codes},
            ),
          ),
        ),
        size: const Size(1000, 900),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      // The menu draws only the rows that fit, so the entries are read from
      // the select itself, and the first rows are checked on screen.
      final UiSelect<String> select = tester.widget<UiSelect<String>>(
        uiSelect('Blocker'),
      );
      final List<String> labels = <String>[
        for (final UiSelectOption<String> option in select.options)
          option.label,
      ];
      await tester.tap(
        find.descendant(
          of: uiSelect('Blocker'),
          matching: find.byWidgetPredicate(
            (Widget widget) => widget is Pressable && widget.onPressed != null,
          ),
        ),
      );
      await tester.pumpAndSettle();
      final List<String> drawn = <String>[
        for (final UiListRow row in tester.widgetList<UiListRow>(
          find.byType(UiListRow),
        ))
          row.title,
      ];
      expect(drawn, isNotEmpty);
      expect(labels.take(drawn.length), drawn);
      return labels;
    }

    testWidgets('lists each blocker by name, never by code', (
      WidgetTester tester,
    ) async {
      final List<String> titles = await menuFor(tester, <String>[
        for (final Case cause in everyCase) cause.code,
      ]);
      for (final Case cause in everyCase) {
        if (cause.code == unknownCode.code) continue;
        expect(titles, contains(cause.label), reason: cause.code);
        expectNoCodeOnScreen(tester, cause.code);
      }
      expect(titles, contains(unknownCode.label));
    });

    testWidgets('never lists two different blockers under one name', (
      WidgetTester tester,
    ) async {
      final List<String> codes = <String>[
        'step_budget_exhausted',
        'external_call_budget_exhausted',
        'token_budget_exhausted',
        'active_time_budget_exhausted',
        'cost_budget_exhausted',
        'program_allowance_exhausted',
        'some_future_blocker',
        'another_future_blocker',
        'retry_budget_exhausted:one_future_cause',
        'retry_budget_exhausted:another_future_cause',
      ];
      final List<String> titles = await menuFor(tester, codes);
      expect(titles.toSet(), hasLength(titles.length), reason: '$titles');
      // Anything the client has no name for keeps its place, numbered, so a
      // person can still tell the choices apart without reading a code.
      expect(titles, contains('${unknownCode.label} (1)'));
      expect(titles, contains('${unknownCode.label} (2)'));
      expect(titles, contains('${unknownCause.label} (1)'));
      expect(titles, contains('${unknownCause.label} (2)'));
      expect(titles, contains('Step limit reached'));
      expect(titles, contains('Cost limit reached'));
    });
  });
}
