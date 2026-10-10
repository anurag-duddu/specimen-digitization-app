// A run that stopped, said in plain words wherever a person reads it.
//
// The server blocks a run with a machine code. After its automatic retries
// run out the code is `retry_budget_exhausted:<cause>`. The processing panel,
// the workbench issue list, the queue row, the history and the filter menu
// each used to print that code, or its words with the underscores taken out.
// None of them may now: each shows a sentence or a short name for the cause,
// and a code this client has no words for gets a generic sentence rather than
// itself (UX writing guidelines 4.9: never expose a raw code in primary text).

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
typedef Case = ({String code, String label, String sentence});

const String retryLater = 'Retry later, or ask an administrator.';

const List<Case> knownCauses = <Case>[
  (
    code: 'retry_budget_exhausted:lookup_operational_failure',
    label: 'Approved source not reachable',
    // The wording PR #298 gave this cause, kept word for word.
    sentence:
        'An approved source could not be reached after repeated attempts. '
        '$retryLater',
  ),
  (
    code: 'retry_budget_exhausted:field_research_timeout',
    label: 'Field research ran out of time',
    sentence:
        'Field research ran out of time after repeated attempts. $retryLater',
  ),
  (
    code: 'retry_budget_exhausted:field_research_model_error',
    label: 'No usable model answer',
    sentence:
        'The model gave no usable answer after repeated attempts. $retryLater',
  ),
];

const Case unknownCause = (
  code: 'retry_budget_exhausted:some_future_cause',
  label: 'Automatic retries stopped',
  sentence: 'Processing stopped after repeated attempts. $retryLater',
);

const Case unknownCode = (
  code: 'some_future_blocker',
  label: 'Needs an operator check',
  sentence:
      'Processing needs an operator check before it can continue. '
      'Ask an administrator to review it.',
);

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

    for (final Case cause in <Case>[
      ...knownCauses,
      unknownCause,
      unknownCode,
    ]) {
      testWidgets('${cause.code} says "${cause.label}", never the code', (
        WidgetTester tester,
      ) async {
        await show(tester, cause.code);
        expect(find.text('Blocked: ${cause.label}'), findsOneWidget);
        expect(find.text(cause.sentence), findsOneWidget);
        expectNoCodeOnScreen(tester, cause.code);
        expect(tester.takeException(), isNull);
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
      expect(find.text(unknownCode.sentence), findsNothing);
      expectNoCodeOnScreen(tester, 'external_outcome_unknown');
    });

    testWidgets('a cost limit still says so, and says no more', (
      WidgetTester tester,
    ) async {
      await show(tester, 'cost_budget_exhausted');
      expect(find.text('Blocked: Cost limit reached'), findsOneWidget);
      expect(find.text('Processing stopped at a cost limit.'), findsOneWidget);
      expect(find.text(unknownCode.sentence), findsNothing);
      expectNoCodeOnScreen(tester, 'cost_budget_exhausted');
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

    for (final Case cause in <Case>[...knownCauses, unknownCause]) {
      testWidgets('${cause.code} is listed as its cause and a next step', (
        WidgetTester tester,
      ) async {
        await openRequirements(tester, cause.code);
        final List<String> sentence = cause.sentence.split('. ');
        expect(find.text(sentence.first), findsOneWidget);
        expect(find.text(sentence.last), findsOneWidget);
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
      final String code = knownCauses.first.code;
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
      expect(
        find.text('Processing needs an operator check before it can continue'),
        findsOneWidget,
      );
      expectNoCodeOnScreen(tester, unknownCode.code);
    });
  });

  group('the queue row', () {
    for (final Case cause in <Case>[
      ...knownCauses,
      unknownCause,
      unknownCode,
    ]) {
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
    testWidgets('a changed blocker reads in plain words', (
      WidgetTester tester,
    ) async {
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
                      'before': <String, dynamic>{
                        'blocker': knownCauses.first.code,
                      },
                      'after': <String, dynamic>{'blocker': unknownCode.code},
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
      expect(
        find.text(
          'Processing blocker: ${knownCauses.first.label} → '
          '${unknownCode.label}',
        ),
        findsWidgets,
      );
      expectNoCodeOnScreen(tester, knownCauses.first.code);
      expectNoCodeOnScreen(tester, unknownCode.code);
    });
  });

  group('the reason sheet', () {
    test('a run whose retries ran out is offered as its cause', () {
      final List<String> reasons = recordReasonCodes(
        Specimen(<String, dynamic>{
          'specimen_id': 's',
          'reason_codes': <String>[
            for (final Case cause in <Case>[...knownCauses, unknownCause])
              cause.code,
          ],
        }),
      );
      expect(reasons, <String>[
        for (final Case cause in <Case>[...knownCauses, unknownCause])
          cause.label,
      ]);
    });
  });

  group('the filter form', () {
    testWidgets('lists each blocker by name, never by code', (
      WidgetTester tester,
    ) async {
      final List<Case> blockers = <Case>[
        ...knownCauses,
        unknownCause,
        unknownCode,
      ];
      await pumpComponent(
        tester,
        Builder(
          builder: (BuildContext context) => UiButton(
            label: 'Open',
            onPressed: () => SearchFilters.show(
              context,
              initial: const <String, String>{},
              configuration: <String, dynamic>{
                'blockers': <String>[for (final Case b in blockers) b.code],
              },
            ),
          ),
        ),
        size: const Size(1000, 900),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.descendant(
          of: uiSelect('Blocker'),
          matching: find.byWidgetPredicate(
            (Widget widget) => widget is Pressable && widget.onPressed != null,
          ),
        ),
      );
      await tester.pumpAndSettle();
      for (final Case blocker in blockers) {
        expect(
          find.byWidgetPredicate(
            (Widget widget) =>
                widget is UiListRow && widget.title == blocker.label,
          ),
          findsOneWidget,
          reason: blocker.code,
        );
        expectNoCodeOnScreen(tester, blocker.code);
      }
    });
  });
}
