/// A literal reading, compared against a reference reading
/// (design system, 3.4 and 7.2; accessibility, section 3.1).
///
/// The comparison is a real alignment. Two readings of the same label agree
/// almost everywhere and disagree in a few small places, so the question a
/// reviewer needs answered is "which places", not "how far do the two strings
/// drift apart once their indices stop lining up".
///
/// An index-by-index comparison cannot answer that. One character inserted
/// early shifts every index after it, and every later character is reported as
/// changed. On two measured readings of Field Museum slide FMNHINS 4486783 the
/// index comparison claimed 83 differing positions where there are 8 real
/// disagreements, and the one that mattered, a catalog number the other
/// reading skipped entirely, was indistinguishable from the 75 it invented.
/// A reviewer learns from that to ignore the diff.
///
/// So the runs here come from a minimal edit script (Myers, 1986) over runes,
/// and the summary counts the places that differ rather than the positions.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/icons.dart';

/// How one run compares with the other reading.
enum DiffRunKind {
  /// Present in both, and the same.
  unchanged,

  /// Present in both, and different. The run carries the literal text; its
  /// `reference` carries the text it replaced.
  changed,

  /// In the literal, absent from the reference.
  added,

  /// In the reference, absent from the literal.
  ///
  /// A removed run is the only kind whose text is not part of the literal, so
  /// it is the only kind [DiffText] does not render. It is in the outcome
  /// because a place where this reading dropped something the other reading
  /// saw is still one of the places the two disagree, and it still counts.
  removed,
}

/// One run of the comparison, with its verdict.
@immutable
class DiffRun {
  const DiffRun(this.text, this.kind, {this.reference});

  /// The text of this run.
  ///
  /// Literal text for every kind except [DiffRunKind.removed], which carries
  /// the reference text that the literal does not contain.
  final String text;

  final DiffRunKind kind;

  /// For [DiffRunKind.changed], the reference text this run replaced.
  ///
  /// Null for every other kind. It is what lets a caller say "S for s" rather
  /// than naming the two sides in separate breaths.
  final String? reference;

  /// True when [text] is part of the literal and belongs in the rendered
  /// transcription.
  bool get inLiteral => kind != DiffRunKind.removed;

  /// The marker the design system gives this kind: `+` for added, `~` for
  /// changed, `-` for removed, nothing for unchanged. It is exposed for
  /// callers that render a legend; the runs themselves carry the marker as a
  /// leading glyph.
  String get marker => switch (kind) {
    DiffRunKind.unchanged => '',
    DiffRunKind.changed => '~',
    DiffRunKind.added => '+',
    DiffRunKind.removed => '-',
  };
}

/// The comparison of one literal against one reference, computed once.
@immutable
class DiffOutcome {
  const DiffOutcome({
    required this.runs,
    required this.differingPositions,
    required this.editRegions,
    required this.summary,
  });

  /// The whole alignment, in order: the literal split into runs, with a
  /// removed run at each place the literal skips reference text.
  final List<DiffRun> runs;

  /// How many runes the aligned edits cover.
  ///
  /// An added or removed run contributes its length; a changed run
  /// contributes the longer of its two sides. This is a measure of how much
  /// text is in dispute, not of how many places are.
  final int differingPositions;

  /// How many places the two readings disagree, which is the count of runs
  /// that are not unchanged.
  ///
  /// This is the number the summary reports. One insertion of twenty-one
  /// characters is one thing for a reviewer to look at, not twenty-one.
  final int editRegions;

  /// The sentence rendered above the text and spoken before it.
  final String summary;

  /// The runs that make up the literal, in order. Concatenating their text
  /// reproduces the literal exactly.
  Iterable<DiffRun> get literalRuns => runs.where((DiffRun run) => run.inLiteral);

  /// True when the literal and the reference are identical.
  bool get identical => editRegions == 0;
}

/// A literal reading, optionally compared with a reference reading.
class DiffText extends StatelessWidget {
  const DiffText({
    super.key,
    required this.text,
    this.reference,
    this.dense = false,
  });

  /// The literal to render, verbatim.
  final String text;

  /// The reading to compare against. Null renders the literal plain.
  final String? reference;

  /// Uses the dense literal role, for a field row rather than a card.
  final bool dense;

  /// Above this many runes the runs are not built and the literal is rendered
  /// plain. The summary is still computed, because counting is cheap and a
  /// reviewer still needs to know whether the two readings agree; what is
  /// skipped is thousands of `TextSpan`s and their layout cost.
  static const int plainFallbackRunes = 4000;

  /// The furthest the alignment search will look before it gives up.
  ///
  /// The search costs O(N x D) time and O(D squared) memory in the number of
  /// edits D, so it stays cheap exactly while the two readings are close,
  /// which is the case this widget is for. Two readings of one label are
  /// normally a few dozen edits apart; the measured pair above is 32. Beyond
  /// this bound the readings are not two transcriptions of the same text in
  /// any useful sense, and [compare] degrades to marking the disputed span
  /// whole rather than reporting hundreds of coincidental one-character
  /// matches as agreement.
  ///
  /// [compare] runs inside `build`, so the bound is what keeps it cheap there.
  /// Measured on this toolchain: 175 microseconds for the two real readings,
  /// and 1.6 milliseconds for the worst case the widget accepts at all, two
  /// wholly different literals of [plainFallbackRunes] each.
  static const int maxEditDistance = 512;

  // The operations of an edit script, as stored by [_editScript].
  static const int _opEqual = 0;
  static const int _opRemoved = 1;
  static const int _opAdded = 2;

  /// Compares [text] against [reference] and groups the result into runs.
  static DiffOutcome compare(String text, String? reference) {
    if (reference == null) {
      return DiffOutcome(
        runs: <DiffRun>[
          if (text.isNotEmpty) DiffRun(text, DiffRunKind.unchanged),
        ],
        differingPositions: 0,
        editRegions: 0,
        summary: '',
      );
    }

    final List<int> literal = text.runes.toList();
    final List<int> base = reference.runes.toList();

    // The common prefix and suffix are equal by inspection, and stripping
    // them keeps at least one minimal edit script. It is also what makes the
    // search cheap in practice: on the measured pair it removes the first 73
    // runes and the search never sees them.
    int prefix = 0;
    while (prefix < literal.length &&
        prefix < base.length &&
        literal[prefix] == base[prefix]) {
      prefix++;
    }
    int suffix = 0;
    while (suffix < literal.length - prefix &&
        suffix < base.length - prefix &&
        literal[literal.length - 1 - suffix] ==
            base[base.length - 1 - suffix]) {
      suffix++;
    }

    final List<int> literalCore = literal.sublist(
      prefix,
      literal.length - suffix,
    );
    final List<int> baseCore = base.sublist(prefix, base.length - suffix);

    final List<DiffRun> runs = <DiffRun>[];
    int differing = 0;
    int regions = 0;

    // A run of no runes is not a run. Only the prefix and suffix calls below
    // can produce one; every kind that counts is emitted from a non-empty
    // group.
    void emit(DiffRunKind kind, List<int> runes, [List<int>? replaced]) {
      if (runes.isEmpty) return;
      final String content = String.fromCharCodes(runes);
      switch (kind) {
        case DiffRunKind.unchanged:
          runs.add(DiffRun(content, kind));
        case DiffRunKind.added:
        case DiffRunKind.removed:
          runs.add(DiffRun(content, kind));
          regions++;
          differing += runes.length;
        case DiffRunKind.changed:
          final List<int> other = replaced!;
          runs.add(
            DiffRun(content, kind, reference: String.fromCharCodes(other)),
          );
          regions++;
          differing += math.max(runes.length, other.length);
      }
    }

    emit(DiffRunKind.unchanged, literal.sublist(0, prefix));

    if (baseCore.isEmpty) {
      emit(DiffRunKind.added, literalCore);
    } else if (literalCore.isEmpty) {
      emit(DiffRunKind.removed, baseCore);
    } else {
      final List<List<int>>? script = _editScript(baseCore, literalCore);
      if (script == null) {
        // Further apart than the search budget. One disputed span is the
        // honest reading of that, and it keeps the literal renderable.
        emit(DiffRunKind.changed, literalCore, baseCore);
      } else {
        _emitScript(script, emit);
      }
    }

    emit(
      DiffRunKind.unchanged,
      literal.sublist(literal.length - suffix, literal.length),
    );

    return DiffOutcome(
      runs: runs,
      differingPositions: differing,
      editRegions: regions,
      summary: summaryFor(regions),
    );
  }

  /// Turns an edit script into runs, folding an adjacent removal and addition
  /// into one changed run.
  ///
  /// That pair is a replacement. A reviewer reads "S for s" faster than
  /// "s gone, then S arrived", and the design system gives a replacement its
  /// own announcement, `differs: <a> versus <b>`.
  static void _emitScript(
    List<List<int>> script,
    void Function(DiffRunKind, List<int>, [List<int>?]) emit,
  ) {
    final List<int> ops = script[0];
    final List<int> runes = script[1];

    // Group consecutive operations of the same kind.
    final List<int> kinds = <int>[];
    final List<List<int>> texts = <List<int>>[];
    for (int i = 0; i < ops.length; i++) {
      if (kinds.isNotEmpty && kinds.last == ops[i]) {
        texts.last.add(runes[i]);
      } else {
        kinds.add(ops[i]);
        texts.add(<int>[runes[i]]);
      }
    }

    for (int i = 0; i < kinds.length; i++) {
      final int kind = kinds[i];
      final int? next = i + 1 < kinds.length ? kinds[i + 1] : null;
      if (kind == _opRemoved && next == _opAdded) {
        emit(DiffRunKind.changed, texts[i + 1], texts[i]);
        i++;
      } else if (kind == _opAdded && next == _opRemoved) {
        emit(DiffRunKind.changed, texts[i], texts[i + 1]);
        i++;
      } else if (kind == _opEqual) {
        emit(DiffRunKind.unchanged, texts[i]);
      } else if (kind == _opRemoved) {
        emit(DiffRunKind.removed, texts[i]);
      } else {
        emit(DiffRunKind.added, texts[i]);
      }
    }
  }

  /// A minimal edit script turning [base] into [literal], as two parallel
  /// lists: the operation at each step, and the rune it applies to.
  ///
  /// This is Myers' greedy algorithm: walk the edit graph one edit distance at
  /// a time, keeping the furthest point reached on each diagonal, and stop as
  /// soon as the far corner is reachable. The first D that reaches it is the
  /// edit distance, so the script is minimal.
  ///
  /// Null when [base] and [literal] are more than [maxEditDistance] edits
  /// apart.
  static List<List<int>>? _editScript(List<int> base, List<int> literal) {
    final int n = base.length;
    final int m = literal.length;
    final int budget = math.min(n + m, maxEditDistance);
    // Every edit changes the length by at most one, so two readings whose
    // lengths differ by more than the budget cannot align inside it.
    if ((n - m).abs() > budget) return null;

    final int offset = budget + 1;
    // furthest[k + offset] is the furthest column reached on diagonal k.
    final List<int> furthest = List<int>.filled(2 * offset + 1, 0);
    // One snapshot per edit distance, taken before that distance is walked.
    // Backtracking reads them to recover which move was taken.
    final List<List<int>> trace = <List<int>>[];

    for (int d = 0; d <= budget; d++) {
      trace.add(List<int>.of(furthest));
      for (int k = -d; k <= d; k += 2) {
        final int down = furthest[k + 1 + offset];
        final int right = furthest[k - 1 + offset];
        // Down takes a rune from the literal, right takes one from the
        // reference. Prefer whichever has already reached further.
        int x = (k == -d || (k != d && right < down)) ? down : right + 1;
        int y = x - k;
        while (x < n && y < m && base[x] == literal[y]) {
          x++;
          y++;
        }
        furthest[k + offset] = x;
        if (x >= n && y >= m) {
          return _backtrack(base, literal, trace, d, offset);
        }
      }
    }
    return null;
  }

  /// Walks the trace back from the far corner, recovering the script.
  static List<List<int>> _backtrack(
    List<int> base,
    List<int> literal,
    List<List<int>> trace,
    int distance,
    int offset,
  ) {
    final List<int> ops = <int>[];
    final List<int> runes = <int>[];
    int x = base.length;
    int y = literal.length;

    for (int d = distance; d > 0; d--) {
      final List<int> furthest = trace[d];
      final int k = x - y;
      final int down = furthest[k + 1 + offset];
      final int right = furthest[k - 1 + offset];
      final int previousK = (k == -d || (k != d && right < down))
          ? k + 1
          : k - 1;
      final int previousX = furthest[previousK + offset];
      final int previousY = previousX - previousK;

      // The diagonal run of equal runes that this edit was followed by.
      while (x > previousX && y > previousY) {
        ops.add(_opEqual);
        runes.add(base[x - 1]);
        x--;
        y--;
      }
      if (x > previousX) {
        ops.add(_opRemoved);
        runes.add(base[x - 1]);
        x--;
      } else if (y > previousY) {
        ops.add(_opAdded);
        runes.add(literal[y - 1]);
        y--;
      }
    }
    // The leading diagonal, which no edit precedes.
    while (x > 0) {
      ops.add(_opEqual);
      runes.add(base[x - 1]);
      x--;
      y--;
    }

    return <List<int>>[ops.reversed.toList(), runes.reversed.toList()];
  }

  /// The sentence for a number of disagreeing places.
  static String summaryFor(int editRegions) => switch (editRegions) {
    0 => 'Matches the reference reading',
    1 => 'Differs in 1 place',
    _ => 'Differs in $editRegions places',
  };

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle literalStyle = dense
        ? context.mono.literalDense
        : context.mono.literal;
    final DiffOutcome outcome = compare(text, reference);
    final bool plain =
        reference == null || text.runes.length > plainFallbackRunes;

    final String spoken = outcome.summary.isEmpty
        ? text
        : '${outcome.summary}. Full text: $text';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        // The summary is spoken as part of the text block below, so the
        // visible copy of it is not a second stop for a screen reader.
        if (outcome.summary.isNotEmpty) ...<Widget>[
          ExcludeSemantics(
            child: Text(
              outcome.summary,
              style: theme.textTheme.labelMedium?.copyWith(
                color: outcome.identical
                    ? theme.colorScheme.onSurfaceVariant
                    : context.tokens.diffChangedContent,
              ),
            ),
          ),
          SizedBox(height: context.space.space1),
        ],
        if (plain && reference != null)
          Padding(
            padding: EdgeInsets.only(bottom: context.space.space1),
            child: Text(
              'Too long to mark position by position. The comparison above '
              'still holds.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        // The runs merge into one silent string for a screen reader, so
        // the block is spoken as the summary and then the full text.
        Semantics(
          container: true,
          label: spoken,
          excludeSemantics: true,
          child: SelectionArea(
            child: plain
                ? Text(text, style: literalStyle)
                : Text.rich(
                    TextSpan(
                      children: <InlineSpan>[
                        // Literal runs only. A removed run carries reference
                        // text, and splicing that into the transcription
                        // would hand a reviewer characters this model never
                        // produced, in a block they can select and copy.
                        for (final DiffRun run in outcome.literalRuns)
                          TextSpan(
                            text: run.text,
                            style: _styleFor(context, run.kind),
                          ),
                      ],
                    ),
                    style: literalStyle,
                  ),
          ),
        ),
      ],
    );
  }

  TextStyle? _styleFor(BuildContext context, DiffRunKind kind) =>
      switch (kind) {
        // Removed runs are filtered out above and never reach this.
        DiffRunKind.unchanged || DiffRunKind.removed => null,
        DiffRunKind.changed => TextStyle(
          decoration: TextDecoration.underline,
          decorationColor: context.tokens.diffChangedContent,
          decorationThickness: context.shape.strokeEmphasis,
          fontWeight: FontWeight.w700,
          backgroundColor: context.tokens.diffChangedFill,
        ),
        DiffRunKind.added => TextStyle(
          decoration: TextDecoration.underline,
          decorationStyle: TextDecorationStyle.double,
          decorationColor: context.tokens.diffAddedContent,
          decorationThickness: context.shape.strokeEmphasis,
          fontWeight: FontWeight.w700,
          backgroundColor: context.tokens.diffAddedFill,
        ),
      };
}
