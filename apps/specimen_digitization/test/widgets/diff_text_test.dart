// The diff: a real alignment, a quantified summary, marked runs, and one
// spoken order.

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/diff_text.dart';

import 'harness.dart';

/// Two real readings of Field Museum slide FMNHINS 4486783
/// (`subject_105526322.jpeg`), captured 2026-09-14 from the two configured
/// routes.
///
/// `handwriting-qwen` (Qwen/Qwen3-VL-30B-A3B-Instruct, novita) is the first
/// reading in the region, so it is the reference. `handwriting-muse`
/// (meta-models/Muse-Glimmer-30B, deepinfra) is the literal the card renders.
///
/// They are here verbatim because the bug this file guards against only shows
/// on text of this shape: seven one-character disagreements spread through the
/// label, and one long insertion at the end. Synthetic strings do not reproduce
/// it.
const String qwenReading =
    'CNHM. E Slope Mt.\n'
    'McKinley, Davao Prov.\n'
    'Mindanao, P.I.\n'
    "6-Sept-1946, Elev. 6400'\n"
    'H. Hoogstraal leg.\n'
    'shrubs, mostly forest\n'
    'wings 4 head\n'
    'sp. 30 ♀';

/// The second reading. It reads the sideways annotation and the barcode
/// catalog number that the first reading skipped, which is the one
/// disagreement on this slide that a reviewer has to act on:
/// `fmnh_ins_number` is mandatory and this record flags it unresolved.
const String museReading =
    'CNHM. E Slope Mt.\n'
    'McKinley, Davao Prov.\n'
    'Mindanao, P.I.\n'
    '6-Sept-1946, Elev.6400\n'
    'H. Hoogstraal leg.\n'
    'Shrubs, mostly Forest\n'
    'Wings 4 head\n'
    'Sp.30 ♀\n'
    'p-959-81-16\n'
    'FMNH\n'
    '448';

/// What the second reading saw and the first did not.
const String skippedCatalogNumber = '\np-959-81-16\nFMNH\n448';

/// The runs of [outcome] that carry literal text, in order.
Iterable<DiffRun> literalRunsOf(DiffOutcome outcome) =>
    outcome.runs.where((DiffRun run) => run.kind != DiffRunKind.removed);

/// Every run of [outcome] that is not `unchanged`, in order.
List<DiffRun> editsOf(DiffOutcome outcome) => outcome.runs
    .where((DiffRun run) => run.kind != DiffRunKind.unchanged)
    .toList();

/// The length of the longest common subsequence of [a] and [b], by table.
///
/// Deliberately the textbook quadratic version and deliberately not the
/// algorithm under test: it is the independent answer the alignment is checked
/// against.
int longestCommonSubsequence(String a, String b) {
  final List<int> left = a.runes.toList();
  final List<int> right = b.runes.toList();
  List<int> previous = List<int>.filled(right.length + 1, 0);
  for (int i = 1; i <= left.length; i++) {
    final List<int> row = List<int>.filled(right.length + 1, 0);
    for (int j = 1; j <= right.length; j++) {
      row[j] = left[i - 1] == right[j - 1]
          ? previous[j - 1] + 1
          : math.max(previous[j], row[j - 1]);
    }
    previous = row;
  }
  return previous[right.length];
}

void main() {
  group('compare', () {
    test('no reference means no comparison', () {
      final DiffOutcome outcome = DiffText.compare('Chicago 1912', null);
      expect(outcome.differingPositions, 0);
      expect(outcome.editRegions, 0);
      expect(outcome.summary, isEmpty);
      expect(outcome.runs.single.kind, DiffRunKind.unchanged);
    });

    test('an identical reading differs nowhere', () {
      final DiffOutcome outcome = DiffText.compare('Chicago', 'Chicago');
      expect(outcome.identical, isTrue);
      expect(outcome.editRegions, 0);
      expect(outcome.summary, 'Matches the reference reading');
    });

    test('counts differing positions and groups them into runs', () {
      final DiffOutcome outcome = DiffText.compare(
        'Chicago 1913',
        'Chicago 1912',
      );
      expect(outcome.differingPositions, 1);
      expect(outcome.editRegions, 1);
      expect(outcome.summary, 'Differs in 1 place');
      expect(outcome.runs, hasLength(2));
      expect(outcome.runs.first.kind, DiffRunKind.unchanged);
      expect(outcome.runs.last.kind, DiffRunKind.changed);
      expect(outcome.runs.last.text, '3');
      expect(outcome.runs.last.reference, '2');
    });

    test('three changed characters make one run, not three spans', () {
      final DiffOutcome outcome = DiffText.compare('Chixxxo', 'Chicago');
      expect(outcome.differingPositions, 3);
      expect(outcome.editRegions, 1);
      expect(outcome.summary, 'Differs in 1 place');
      expect(
        outcome.runs.where((DiffRun run) => run.kind == DiffRunKind.changed),
        hasLength(1),
      );
    });

    test('characters past the reference are added, not changed', () {
      final DiffOutcome outcome = DiffText.compare('Chicago IL', 'Chicago');
      final DiffRun last = outcome.runs.last;
      expect(last.kind, DiffRunKind.added);
      expect(last.text, ' IL');
      expect(last.marker, '+');
      expect(outcome.differingPositions, 3);
      expect(outcome.editRegions, 1);
    });

    test('a reference longer than the literal still counts the difference', () {
      final DiffOutcome outcome = DiffText.compare('Chi', 'Chicago');
      expect(outcome.differingPositions, 4);
      expect(outcome.editRegions, 1);
    });

    test('the summary is singular at one place', () {
      expect(DiffText.summaryFor(1), 'Differs in 1 place');
      expect(DiffText.summaryFor(2), 'Differs in 2 places');
      expect(DiffText.summaryFor(0), 'Matches the reference reading');
    });
  });

  // The regression this file exists for. A strict index-by-index comparison
  // reports 83 differing positions on the pair below, because one inserted
  // character shifts every index after it. Every assertion here is a measured
  // number, not a chosen one.
  group('alignment', () {
    test('an insertion does not shift the rest of the reading', () {
      // The literal has a space the reference lacks. Everything after it is
      // identical, and a real alignment says so.
      final DiffOutcome outcome = DiffText.compare(
        'Chicago 1912',
        'Chicago1912',
      );
      expect(outcome.editRegions, 1);
      expect(outcome.differingPositions, 1);
      expect(editsOf(outcome).single.kind, DiffRunKind.added);
      expect(editsOf(outcome).single.text, ' ');
    });

    test('text absent from the literal is one removed run', () {
      final DiffOutcome outcome = DiffText.compare(
        'Chicago 1912',
        'Chicago, IL 1912',
      );
      expect(outcome.editRegions, 1);
      expect(outcome.differingPositions, 4);
      final DiffRun removed = editsOf(outcome).single;
      expect(removed.kind, DiffRunKind.removed);
      expect(removed.text, ', IL');
      expect(removed.marker, '-');
    });

    test('two real readings differ in 8 places, not 83 positions', () {
      final DiffOutcome outcome = DiffText.compare(museReading, qwenReading);
      expect(qwenReading.runes.length, 142);
      expect(museReading.runes.length, 160);
      expect(outcome.editRegions, 8);
      expect(outcome.differingPositions, 28);
      expect(outcome.summary, 'Differs in 8 places');
    });

    test('the 8 places are the disagreements a reviewer would name', () {
      final DiffOutcome outcome = DiffText.compare(museReading, qwenReading);
      final List<DiffRun> edits = editsOf(outcome);
      expect(
        edits.map((DiffRun run) => (run.kind, run.reference, run.text)),
        <(DiffRunKind, String?, String)>[
          // Elev. 6400 -> Elev.6400
          (DiffRunKind.removed, null, ' '),
          // 6400' -> 6400
          (DiffRunKind.removed, null, "'"),
          (DiffRunKind.changed, 's', 'S'), // shrubs -> Shrubs
          (DiffRunKind.changed, 'f', 'F'), // forest -> Forest
          (DiffRunKind.changed, 'w', 'W'), // wings -> Wings
          (DiffRunKind.changed, 's', 'S'), // sp. -> Sp.
          // sp. 30 -> Sp.30
          (DiffRunKind.removed, null, ' '),
          (DiffRunKind.added, null, skippedCatalogNumber),
        ],
      );
    });

    test('the catalog number the first reading skipped is one added run', () {
      // 21 of the 28 differing characters are this single legitimate
      // insertion. Burying it inside a claimed 83-position difference is what
      // teaches a reviewer to ignore the diff.
      final DiffOutcome outcome = DiffText.compare(museReading, qwenReading);
      final List<DiffRun> added = outcome.runs
          .where((DiffRun run) => run.kind == DiffRunKind.added)
          .toList();
      expect(added, hasLength(1));
      expect(added.single.text, skippedCatalogNumber);
      expect(added.single.text.runes.length, 21);
    });

    test('the literal runs still spell the literal, exactly', () {
      // A removed run carries reference text that is not in the literal. It
      // must never reach the rendered string, or a reviewer copying a
      // transcription would get characters the model never produced.
      for (final (String literal, String reference) in <(String, String)>[
        (museReading, qwenReading),
        (qwenReading, museReading),
        ('Chi', 'Chicago'),
        ('Chicago, IL 1912', 'Chicago 1912'),
        ('', 'Chicago'),
      ]) {
        final DiffOutcome outcome = DiffText.compare(literal, reference);
        expect(
          literalRunsOf(outcome).map((DiffRun run) => run.text).join(),
          literal,
          reason: 'the rendered runs must reconstruct the literal verbatim',
        );
      }
    });

    test('the comparison is symmetric in the places it finds', () {
      // Swapping the two readings turns the insertion into a removal and the
      // case changes around, but the number of places does not move.
      final DiffOutcome forward = DiffText.compare(museReading, qwenReading);
      final DiffOutcome backward = DiffText.compare(qwenReading, museReading);
      expect(forward.editRegions, backward.editRegions);
      expect(forward.differingPositions, backward.differingPositions);
      expect(
        editsOf(backward).map((DiffRun run) => run.kind),
        contains(DiffRunKind.removed),
        reason: 'the reading that skipped the barcode is missing that text',
      );
    });

    test('an empty literal is one removed run, not a silent match', () {
      final DiffOutcome outcome = DiffText.compare('', 'Chicago');
      expect(outcome.identical, isFalse);
      expect(outcome.editRegions, 1);
      expect(outcome.differingPositions, 7);
      expect(editsOf(outcome).single.kind, DiffRunKind.removed);
    });

    test('a multi-rune character is aligned as one character', () {
      // The astral pair is one rune and must be replaced as one, not split
      // across its two UTF-16 code units.
      final DiffOutcome outcome = DiffText.compare(
        'α🙂\nuncertain?',
        'α🙃\nuncertain?',
      );
      expect(outcome.editRegions, 1);
      expect(outcome.differingPositions, 1);
      final DiffRun changed = editsOf(outcome).single;
      expect(changed.kind, DiffRunKind.changed);
      expect(changed.text, '🙂');
      expect(changed.reference, '🙃');
    });

    test('the alignment is minimal, and both sides reconstruct', () {
      // The hand-picked cases above cannot show that a script is the shortest
      // one. This can: a minimal script leaves exactly the longest common
      // subsequence unchanged, so the unchanged runes are the LCS length,
      // computed here by a direct table that has no code in common with the
      // widget. Seeded, so a failure is reproducible from the seed alone.
      final math.Random random = math.Random(20260914);
      const String alphabet = 'abc \n';
      String word(int length) => String.fromCharCodes(<int>[
        for (int i = 0; i < length; i++)
          alphabet.codeUnitAt(random.nextInt(alphabet.length)),
      ]);

      for (int trial = 0; trial < 400; trial++) {
        final String literal = word(random.nextInt(18));
        final String reference = word(random.nextInt(18));
        final DiffOutcome outcome = DiffText.compare(literal, reference);

        expect(
          literalRunsOf(outcome).map((DiffRun run) => run.text).join(),
          literal,
          reason: 'literal side, trial $trial: $literal / $reference',
        );
        expect(
          outcome.runs
              .map(
                (DiffRun run) => switch (run.kind) {
                  DiffRunKind.unchanged || DiffRunKind.removed => run.text,
                  DiffRunKind.changed => run.reference!,
                  DiffRunKind.added => '',
                },
              )
              .join(),
          reference,
          reason: 'reference side, trial $trial: $literal / $reference',
        );
        expect(
          outcome.editRegions,
          editsOf(outcome).length,
          reason: 'trial $trial: $literal / $reference',
        );
        expect(
          outcome.runs
              .where((DiffRun run) => run.kind == DiffRunKind.unchanged)
              .fold<int>(0, (int n, DiffRun run) => n + run.text.runes.length),
          longestCommonSubsequence(literal, reference),
          reason: 'not a minimal script, trial $trial: $literal / $reference',
        );
      }
    });

    test('readings too different to align degrade to one marked span', () {
      // Beyond the search budget the honest answer is one disputed span, not
      // a scattering of coincidental matches.
      final String literal = 'a' * (DiffText.maxEditDistance * 2);
      final String reference = 'b' * (DiffText.maxEditDistance * 2);
      final DiffOutcome outcome = DiffText.compare(literal, reference);
      expect(outcome.editRegions, 1);
      expect(outcome.differingPositions, literal.length);
      expect(editsOf(outcome).single.kind, DiffRunKind.changed);
      expect(literalRunsOf(outcome).map((DiffRun r) => r.text).join(), literal);
    });
  });

  testWidgets('the summary is rendered above the literal', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const DiffText(text: 'Chicago 1913', reference: 'Chicago 1912'),
    );
    expect(find.text('Differs in 1 place'), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('Differs in 1 place')).dy,
      lessThan(tester.getTopLeft(find.byType(SelectionArea)).dy),
    );
  });

  testWidgets('the block speaks the summary and then the full text', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(
      tester,
      const DiffText(text: 'Chixxxo', reference: 'Chicago'),
    );
    expect(
      find.bySemanticsLabel('Differs in 1 place. Full text: Chixxxo'),
      findsOneWidget,
    );
    // The visible summary is not read a second time.
    expect(find.bySemanticsLabel('Differs in 1 place'), findsNothing);
    handle.dispose();
  });

  testWidgets('the rendered text is the literal, never the reference', (
    WidgetTester tester,
  ) async {
    // A removed run has no place in the rendered literal. This is the widget
    // half of the run invariant above.
    await pumpComponent(
      tester,
      const DiffText(text: 'Chicago 1912', reference: 'Chicago, IL 1912'),
    );
    final Text body = tester.widget<Text>(
      find.descendant(
        of: find.byType(SelectionArea),
        matching: find.byType(Text),
      ),
    );
    expect(body.textSpan!.toPlainText(), 'Chicago 1912');
    expect(find.text('Differs in 1 place'), findsOneWidget);
  });

  testWidgets('a literal above the fallback is rendered plain', (
    WidgetTester tester,
  ) async {
    final String long = 'a' * (DiffText.plainFallbackRunes + 1);
    await pumpComponent(
      tester,
      SizedBox(
        width: 600,
        child: SingleChildScrollView(
          child: DiffText(text: long, reference: 'b$long'),
        ),
      ),
    );
    expect(
      find.textContaining('Too long to mark position by position'),
      findsOneWidget,
    );
    final Text body = tester.widget<Text>(
      find.descendant(
        of: find.byType(SelectionArea),
        matching: find.byType(Text),
      ),
    );
    expect(body.textSpan, isNull, reason: 'plain text, not a run of spans');
  });

  testWidgets('a literal below the fallback is rendered as runs', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const DiffText(text: 'Chixxxo', reference: 'Chicago'),
    );
    final Text body = tester.widget<Text>(
      find.descendant(
        of: find.byType(SelectionArea),
        matching: find.byType(Text),
      ),
    );
    expect(body.textSpan, isNotNull);
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        const DiffText(text: 'Chicago 1913', reference: 'Chicago 1912'),
        theme: theme,
      );
      await expectAccessible(tester);
    }
  });

  testWidgets('the real pair renders its 8 places in both themes', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        const SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: DiffText(text: museReading, reference: qwenReading),
          ),
        ),
        theme: theme,
      );
      expect(find.text('Differs in 8 places'), findsOneWidget);
      final Text body = tester.widget<Text>(
        find.descendant(
          of: find.byType(SelectionArea),
          matching: find.byType(Text),
        ),
      );
      expect(body.textSpan!.toPlainText(), museReading);
      await expectAccessible(tester);
    }
  });
}
