import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_controller.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_thread_card.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'research_fixture.dart';

Future<void> pumpResearchCard(
  WidgetTester tester,
  ResearchThreadCard card, {
  double width = 640,
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
            textScaler: TextScaler.linear(scale),
            disableAnimations: true,
          ),
          child: Scaffold(
            body: SingleChildScrollView(
              child: Padding(padding: const EdgeInsets.all(8), child: card),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

ResearchThreadCard readyCard({
  ResearchFieldThread? field,
  VoidCallback? onRetry,
  ValueChanged<ResearchReviewCandidate>? onSelectCandidate,
  bool fieldCentered = false,
  bool paused = false,
  bool unknown = false,
  bool readOnly = false,
  bool historical = false,
  int? canonicalRevision,
  int? reviewSavedRevision,
  ResearchNetworkState state = ResearchNetworkState.ready,
}) => ResearchThreadCard(
  scope: trustedResearchScope(),
  recordRevision: 100,
  fieldKey: 'taxon',
  fieldLabel: 'Taxon',
  field: field ?? fixtureThread().field('taxon'),
  historical: historical,
  canonicalRevision: canonicalRevision,
  reviewSavedRevision: reviewSavedRevision,
  networkState: state,
  paused: paused,
  hasUnknownState: unknown,
  readOnly: readOnly,
  onRetry: onRetry,
  onSelectCandidate: onSelectCandidate,
  fieldCentered: fieldCentered,
  onRefresh: () {},
);

void main() {
  testWidgets('selectable possibility returns its verified source candidate', (
    tester,
  ) async {
    final json = researchFixture('failed-thread');
    final taxon = fixtureField(json, 'taxon');
    taxon['work_state'] = 'waiting_human';
    taxon['checkpoint']['resolution']['work_state'] = 'waiting_human';
    taxon['actions'] = ['review_proposal'];
    taxon['review'] = {
      'question_reason': 'semantic_ambiguity',
      'reason': 'Two source possibilities remain.',
      'question': {
        'field_key': 'taxon',
        'question': 'Which retained source candidate is supported?',
        'reason': 'semantic_ambiguity',
        'coverage': [
          {
            'source_id': 'gbif',
            'field_key': 'taxon',
            'state': 'exhausted',
            'source_version': 'test-v1',
            'qualification_digest': 'a' * 64,
            'exact_join_attempted': true,
            'query_digest': 'b' * 64,
            'receipt_ids': ['coverage-receipt'],
            'candidate_count': 1,
            'coverage_limit': 'bounded test scope',
            'reason': 'Search completed within the fixture scope',
          },
        ],
        'evidence_ids': ['source-evidence'],
      },
      'evidence': [
        {
          'evidence_id': 'source-evidence',
          'source_id': 'geolocate',
          'kind': 'lookup',
          'outcome': 'ambiguous',
        },
      ],
      'candidates': [
        {
          'label': 'Mindanao',
          'source_id': 'geolocate',
          'selection_id': 'b' * 64,
          'selection_value': 'Philippines',
          'evidence_id': 'source-evidence',
        },
      ],
      'evidence_not_shown': 0,
      'candidates_not_shown': 0,
    };
    taxon['checkpoint']['resolution']['question'] = taxon['review'].remove(
      'question',
    );
    final field = ResearchThread.fromJson(
      json,
      expectedScope: trustedResearchScope(),
    ).field('taxon')!;
    ResearchReviewCandidate? selected;
    await pumpResearchCard(
      tester,
      readyCard(
        field: field,
        fieldCentered: true,
        onSelectCandidate: (candidate) => selected = candidate,
      ),
    );
    await tester.tap(find.text('Research'));
    await tester.pumpAndSettle();
    expect(find.text('Mindanao'), findsOneWidget);
    expect(find.text('Proposed field value'), findsOneWidget);
    expect(find.text('Philippines'), findsOneWidget);
    await tester.tap(find.text('Use this possibility'));
    await tester.pump();
    expect(selected?.selectionId, 'b' * 64);
    expect(selected?.label, 'Mindanao');
    expect(selected?.selectionValue, 'Philippines');
  });

  testWidgets('historical report shows its saved revisions and disables choice', (
    tester,
  ) async {
    final json = researchFixture('failed-thread')
      ..['historical'] = true
      ..['canonical_revision'] = 41
      ..['review_saved_revision'] = 42;
    final taxon = fixtureField(json, 'taxon');
    taxon['work_state'] = 'waiting_human';
    taxon['checkpoint']['resolution']['work_state'] = 'waiting_human';
    taxon['actions'] = ['review_proposal'];
    taxon['review'] = {
      'question_reason': 'semantic_ambiguity',
      'reason': 'Two source possibilities remain.',
      'evidence': [],
      'candidates': [
        {
          'label': 'Mindanao',
          'source_id': 'geolocate',
          'selection_id': 'c' * 64,
          'selection_value': 'Philippines',
        },
      ],
      'evidence_not_shown': 0,
      'candidates_not_shown': 0,
    };
    final resolution = taxon['checkpoint']['resolution'] as Map;
    resolution['question'] = {
      'field_key': 'taxon',
      'question': 'Which retained source candidate is supported?',
      'reason': 'semantic_ambiguity',
      'coverage': [
        {
          'source_id': 'gbif',
          'field_key': 'taxon',
          'state': 'exhausted',
          'source_version': 'test-v1',
          'qualification_digest': 'a' * 64,
          'exact_join_attempted': true,
          'query_digest': 'b' * 64,
          'receipt_ids': ['coverage-receipt'],
          'candidate_count': 1,
          'coverage_limit': 'bounded test scope',
          'reason': 'Search completed within the fixture scope',
        },
      ],
    };
    final thread = ResearchThread.fromJson(
      json,
      expectedScope: trustedResearchScope(),
    );
    var selections = 0;
    await pumpResearchCard(
      tester,
      readyCard(
        field: thread.field('taxon'),
        fieldCentered: true,
        historical: thread.historical,
        canonicalRevision: thread.canonicalRevision,
        reviewSavedRevision: thread.reviewSavedRevision,
        onSelectCandidate: (_) => selections++,
      ),
    );
    expect(find.textContaining('Historical report ·'), findsOneWidget);
    await tester.tap(find.text('Research'));
    await tester.pumpAndSettle();
    expect(
      find.textContaining('record revision 41; review saved at revision 42'),
      findsOneWidget,
    );
    final button = tester.widget<UiButton>(
      find.widgetWithText(UiButton, 'Use this possibility'),
    );
    expect(button.onPressed, isNull);
    expect(
      button.disabledReason,
      'This field is read-only or the research result is no longer actionable.',
    );
    expect(selections, 0);
  });

  testWidgets('collapsed disclosure is lazy and touch reveal requests once', (
    tester,
  ) async {
    var reads = 0;
    await pumpResearchCard(
      tester,
      ResearchThreadCard(
        scope: trustedResearchScope(),
        recordRevision: 100,
        fieldKey: 'taxon',
        fieldLabel: 'Taxon',
        onLoad: () => reads++,
      ),
    );
    expect(reads, 0);
    expect(find.text('As written'), findsNothing);
    await tester.tap(find.text('Research'));
    await tester.pump();
    expect(reads, 1);
    expect(find.byType(SingleChildScrollView), findsOneWidget);
    expect(find.byType(UiDisclosure), findsOneWidget);
    expect(find.byType(Surface), findsWidgets);
  });

  testWidgets('keyboard disclosure reveal and advertised retry work', (
    tester,
  ) async {
    var retries = 0;
    await pumpResearchCard(tester, readyCard(onRetry: () => retries++));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(find.text('As written'), findsOneWidget);
    await tester.tap(find.text('Retry field'));
    await tester.pump();
    expect(retries, 1);
  });

  for (final disabled in [
    'paused',
    'unknown',
    'historical',
    'busy',
    'blocked',
  ]) {
    testWidgets('disabled retry cannot activate: $disabled', (tester) async {
      var retries = 0;
      var field = fixtureThread().field('taxon')!;
      if (disabled == 'blocked') {
        final json = researchFixture('failed-thread');
        fixtureField(json, 'taxon')['blocker_code'] = 'research_retry_blocked';
        field = ResearchThread.fromJson(
          json,
          expectedScope: trustedResearchScope(),
        ).field('taxon')!;
      }
      await pumpResearchCard(
        tester,
        readyCard(
          field: field,
          onRetry: () => retries++,
          paused: disabled == 'paused',
          unknown: disabled == 'unknown',
          readOnly: disabled == 'historical',
          state: disabled == 'busy'
              ? ResearchNetworkState.submitting
              : ResearchNetworkState.ready,
        ),
      );
      await tester.tap(find.text('Research'));
      await tester.pump();
      final button = tester.widget<UiButton>(
        find.widgetWithText(
          UiButton,
          disabled == 'busy' ? 'Queuing retry' : 'Retry field',
        ),
      );
      expect(button.onPressed, isNull);
      if (disabled == 'blocked') {
        expect(find.textContaining('Retry blocked.'), findsOneWidget);
        expect(button.disabledReason, 'Retry is blocked for this field.');
      }
      expect(retries, 0);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets(
    'prerequisite, question and policy exception remain visible without new actions',
    (tester) async {
      final json = researchFixture('failed-thread');
      final raw = fixtureField(json, 'taxon');
      raw['work_state'] = 'waiting_human';
      raw['actions'] = ['supply_information', 'review_proposal'];
      final resolution = raw['checkpoint']['resolution'] as Map;
      resolution['work_state'] = 'waiting_human';
      resolution['source_coverage'] = [
        {
          'source_id': 'labels',
          'field_key': 'taxon',
          'state': 'exhausted',
          'source_version': 'v1',
          'coverage_limit': 'Current label only',
          'qualification_digest': 'a' * 64,
          'exact_join_attempted': true,
          'exact_join_proven': true,
          'query_digest': 'b' * 64,
          'receipt_ids': ['synthetic-label-search-receipt'],
          'candidate_count': 0,
          'reason': 'No additional supported value',
        },
      ];
      resolution['question'] = {
        'field_key': 'taxon',
        'question': 'Which reading is correct?',
        'reason': 'semantic_ambiguity',
        'coverage': resolution['source_coverage'],
      };
      resolution['exception'] = {
        'field_key': 'taxon',
        'dependency': 'qualified source',
        'policy_version': 'v1',
        'reason': 'Source unavailable',
        'reevaluate_when': 'Source becomes available',
      };
      final field = ResearchThread.fromJson(
        json,
        expectedScope: trustedResearchScope(),
      ).field('taxon');
      await pumpResearchCard(tester, readyCard(field: field));
      await tester.tap(find.text('Research'));
      await tester.pump();
      expect(find.text('Which reading is correct?'), findsOneWidget);
      expect(find.textContaining('Current label only'), findsOneWidget);
      expect(find.textContaining('Policy exception:'), findsOneWidget);
      expect(
        find.textContaining('not available in this view yet'),
        findsNWidgets(2),
      );
      expect(find.widgetWithText(UiButton, 'Supply information'), findsNothing);
      expect(find.widgetWithText(UiButton, 'Review proposal'), findsNothing);
    },
  );

  testWidgets(
    'retains all three value layers and evidence without a review mutation',
    (tester) async {
      final json = researchFixture('failed-thread');
      final country = fixtureField(json, 'country');
      final value = <String, dynamic>{
        ...country['value'] as Map<String, dynamic>,
        'literal': 'Written layer',
        'parsed': 'Interpreted layer',
        'normalized': 'Standardized layer',
      };
      country['value'] = value;
      country['checkpoint']['resolution']['value'] = value;
      final field = ResearchThread.fromJson(
        json,
        expectedScope: trustedResearchScope(),
      ).field('country');
      await pumpResearchCard(
        tester,
        ResearchThreadCard(
          scope: trustedResearchScope(),
          recordRevision: 100,
          fieldKey: 'country',
          fieldLabel: 'Country',
          field: field,
          networkState: ResearchNetworkState.ready,
          onRefresh: () {},
        ),
      );
      await tester.tap(find.text('Research'));
      await tester.pump();
      for (final text in [
        'Written layer',
        'Interpreted layer',
        'Standardized layer',
      ]) {
        expect(find.text(text), findsOneWidget);
      }
      expect(find.text('1 evidence reference'), findsOneWidget);
      expect(find.text('Approve'), findsNothing);
    },
  );

  testWidgets('loading, denial and wrong field binding hide value layers', (
    tester,
  ) async {
    for (final state in [
      ResearchNetworkState.loading,
      ResearchNetworkState.error,
      ResearchNetworkState.denied,
    ]) {
      await pumpResearchCard(tester, readyCard(state: state));
      await tester.tap(find.text('Research'));
      await tester.pump();
      expect(find.text('As written'), findsNothing);
      expect(tester.takeException(), isNull);
    }
    await pumpResearchCard(
      tester,
      readyCard(field: fixtureThread().field('country')),
    );
    await tester.tap(find.text('Research'));
    await tester.pump();
    expect(find.text('Synthetic country'), findsNothing);
    expect(find.textContaining('could not be verified'), findsWidgets);
  });

  for (final width in [320.0, 768.0]) {
    for (final scale in [1.0, 2.0]) {
      for (final dark in [false, true]) {
        testWidgets('fits width ${width.toString()} scale '
            '${scale.toString()}${dark ? ' dark' : ' light'}', (tester) async {
          await pumpResearchCard(
            tester,
            readyCard(onRetry: () {}),
            width: width,
            scale: scale,
            dark: dark,
          );
          await tester.tap(find.text('Research'));
          await tester.pump();
          expect(tester.takeException(), isNull);
          expect(find.byType(SingleChildScrollView), findsOneWidget);
          final semantics = tester.ensureSemantics();
          try {
            await expectLater(
              tester,
              meetsGuideline(androidTapTargetGuideline),
            );
            await expectLater(
              tester,
              meetsGuideline(labeledTapTargetGuideline),
            );
          } finally {
            semantics.dispose();
          }
        });
      }
    }
  }

  for (final source in <String, String>{
    'global_names_verifier': 'Global Names Verifier',
    'catalogue_of_life': 'Catalogue of Life',
    'gbif': 'GBIF',
    'bugguide': 'BugGuide',
    'mapcarta': 'Mapcarta',
    'geolocate': 'GEOLocate',
    'field_museum_ipt': 'Field Museum IPT',
    'field_museum_emudata': 'Field Museum EMu data',
    'unknown_registry_source': 'Research source',
    // Retired 2026-10-03 (owner G-geo-1); a stored row reads generically.
    'google_maps': 'Research source',
  }.entries) {
    testWidgets(
      'displays approved source name and scope without raw provenance codes: '
      '${source.key}',
      (tester) async {
        final json = researchFixture('failed-thread');
        final raw = fixtureField(json, 'taxon');
        raw['work_state'] = 'waiting_source';
        raw['actions'] = [];
        raw['blocker_code'] = 'source_prerequisite';
        raw['checkpoint']['resolution']['work_state'] = 'waiting_source';
        raw['checkpoint']['resolution']['source_coverage'] = [
          {
            'source_id': source.key,
            'field_key': 'taxon',
            'state': 'unqualified',
            'source_version': 'v1',
            'coverage_limit': 'Current input and collection only',
            'reason': 'scope_join_not_proven',
          },
        ];
        final field = ResearchThread.fromJson(
          json,
          expectedScope: trustedResearchScope(),
        ).field('taxon')!;
        await pumpResearchCard(tester, readyCard(field: field));
        await tester.tap(find.text('Research'));
        await tester.pump();
        expect(find.textContaining('${source.value}:'), findsOneWidget);
        expect(
          find.textContaining('Source needs qualification before use.'),
          findsOneWidget,
        );
        expect(
          find.textContaining('Scope: Current input and collection only'),
          findsOneWidget,
        );
        expect(find.textContaining(source.key), findsNothing);
        expect(find.textContaining('scope_join_not_proven'), findsNothing);
        expect(find.textContaining('unqualified'), findsNothing);
        expect(
          field.checkpoint!.resolution.sourceCoverage.single.sourceId,
          source.key,
        );
        expect(
          field.checkpoint!.resolution.sourceCoverage.single.reason,
          'scope_join_not_proven',
        );
        expect(
          find.widgetWithText(UiButton, 'Supply information'),
          findsNothing,
        );
        expect(find.widgetWithText(UiButton, 'Review proposal'), findsNothing);
        expect(find.widgetWithText(UiButton, 'Retry field'), findsNothing);
      },
    );
  }

  for (final state in <String, String>{
    'not_attempted': 'Search has not started.',
    'unqualified': 'Source needs qualification before use.',
    'inaccessible': 'Source is unavailable.',
    'schema_only':
        'Source structure is available; records have not been searched.',
    'failed': 'Search could not be completed.',
    'searched': 'Search completed.',
    'exhausted': 'Search completed within the recorded scope.',
  }.entries) {
    testWidgets(
      'describes scoped source state without inventing absence: ${state.key}',
      (tester) async {
        final json = researchFixture('failed-thread');
        final raw = fixtureField(json, 'taxon');
        raw['work_state'] = 'waiting_source';
        raw['actions'] = [];
        raw['checkpoint']['resolution']['work_state'] = 'waiting_source';
        raw['checkpoint']['resolution']['source_coverage'] = [
          {
            'source_id': 'gbif',
            'field_key': 'taxon',
            'state': state.key,
            'source_version': 'v1',
            'coverage_limit': 'Typed name query only',
            if (state.key == 'exhausted') 'qualification_digest': 'a' * 64,
            if (state.key == 'exhausted') 'exact_join_attempted': true,
            if (state.key == 'exhausted') 'exact_join_proven': true,
            if (state.key == 'exhausted') 'query_digest': 'b' * 64,
            if (state.key == 'exhausted')
              'receipt_ids': ['synthetic-name-query-receipt'],
            if (state.key == 'exhausted') 'candidate_count': 0,
            'reason': 'transport_or_policy_code',
          },
        ];
        final field = ResearchThread.fromJson(
          json,
          expectedScope: trustedResearchScope(),
        ).field('taxon');
        await pumpResearchCard(tester, readyCard(field: field));
        await tester.tap(find.text('Research'));
        await tester.pump();
        expect(find.textContaining(state.value), findsOneWidget);
        expect(
          find.textContaining('Scope: Typed name query only'),
          findsOneWidget,
        );
        expect(find.textContaining('transport_or_policy_code'), findsNothing);
        expect(find.textContaining('No supported value'), findsNothing);
        expect(find.text('Which reading is correct?'), findsNothing);
        expect(
          find.widgetWithText(UiButton, 'Supply information'),
          findsNothing,
        );
        expect(find.widgetWithText(UiButton, 'Review proposal'), findsNothing);
      },
    );
  }

  for (final width in [320.0, 640.0]) {
    for (final state in [
      ResearchNetworkState.error,
      ResearchNetworkState.denied,
    ]) {
      testWidgets('network state has accurate disabled explanations at width '
          '${width.toString()}: ${state.name}', (tester) async {
        await pumpResearchCard(
          tester,
          readyCard(state: state),
          width: width,
          scale: 2,
        );
        await tester.tap(find.text('Research'));
        await tester.pump();
        expect(find.widgetWithText(UiButton, 'Retry field'), findsNothing);
        expect(find.widgetWithText(UiButton, 'Retry'), findsNothing);
        expect(find.text('As written'), findsNothing);
        final refresh = tester
            .widgetList<UiButton>(find.byType(UiButton))
            .singleWhere((button) => button.label.startsWith('Refresh'));
        if (state == ResearchNetworkState.denied) {
          expect(refresh.onPressed, isNull);
          expect(refresh.disabledReason, 'Research access is unavailable.');
          expect(
            find.textContaining(
              'Research access is unavailable for this collection.',
            ),
            findsOneWidget,
          );
        } else {
          expect(refresh.onPressed, isNotNull);
          expect(refresh.disabledReason, isNull);
          expect(
            find.textContaining('Refresh before retrying this field.'),
            findsOneWidget,
          );
        }
      });
    }
  }

  testWidgets('record change recreates the disclosure collapsed', (
    tester,
  ) async {
    await pumpResearchCard(tester, readyCard(onRetry: () {}));
    await tester.tap(find.text('Research'));
    await tester.pump();
    expect(find.text('As written'), findsOneWidget);
    await pumpResearchCard(
      tester,
      ResearchThreadCard(
        scope: trustedResearchScope(),
        recordRevision: 101,
        fieldKey: 'taxon',
        fieldLabel: 'Taxon',
        field: fixtureThread().field('taxon'),
        networkState: ResearchNetworkState.ready,
      ),
    );
    expect(find.text('As written'), findsNothing);
  });
}
