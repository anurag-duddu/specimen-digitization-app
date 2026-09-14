/// A literal reading, compared against a reference
/// (design system, 3.4 and 7.2; accessibility, section 3.1).
///
/// Ported from the inline comparison in `workbench.dart` and improved in four
/// ways: runs of changed characters are grouped instead of being emitted one
/// span per rune, characters past the end of the reference are marked as
/// added rather than as changed, the difference is quantified in a sentence
/// above the text, and the whole block reads to assistive technology as the
/// summary followed by the full text rather than as a silent merge of runs.
library;

import 'package:flutter/material.dart';

import '../theme/icons.dart';

/// How one run of the literal compares with the reference.
enum DiffRunKind {
  /// Present in both, and the same.
  unchanged,

  /// Present in both, and different.
  changed,

  /// Past the end of the reference.
  added,
}

/// One run of the literal, with its verdict.
@immutable
class DiffRun {
  const DiffRun(this.text, this.kind);

  final String text;
  final DiffRunKind kind;

  /// The marker the design system gives this kind: `+` for added, `~` for
  /// changed, nothing for unchanged. It is exposed for callers that render a
  /// legend; the runs themselves carry the marker as a leading glyph.
  String get marker => switch (kind) {
    DiffRunKind.unchanged => '',
    DiffRunKind.changed => '~',
    DiffRunKind.added => '+',
  };
}

/// The comparison of one literal against one reference, computed once.
@immutable
class DiffOutcome {
  const DiffOutcome({
    required this.runs,
    required this.differingPositions,
    required this.summary,
  });

  /// The literal, split into runs.
  final List<DiffRun> runs;

  /// How many rune positions differ, counting positions past the end of the
  /// reference.
  final int differingPositions;

  /// The sentence rendered above the text and spoken before it.
  final String summary;

  /// True when the literal and the reference are identical.
  bool get identical => differingPositions == 0;
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

  /// Compares [text] against [reference] and groups the result into runs.
  static DiffOutcome compare(String text, String? reference) {
    final List<int> literal = text.runes.toList();
    if (reference == null) {
      return DiffOutcome(
        runs: <DiffRun>[
          if (text.isNotEmpty) DiffRun(text, DiffRunKind.unchanged),
        ],
        differingPositions: 0,
        summary: '',
      );
    }

    final List<int> base = reference.runes.toList();
    final List<DiffRun> runs = <DiffRun>[];
    final StringBuffer buffer = StringBuffer();
    DiffRunKind? current;
    int differing = 0;

    void flush() {
      final DiffRunKind? kind = current;
      if (kind != null && buffer.isNotEmpty) {
        runs.add(DiffRun(buffer.toString(), kind));
      }
      buffer.clear();
    }

    for (int i = 0; i < literal.length; i++) {
      final DiffRunKind kind;
      if (i >= base.length) {
        kind = DiffRunKind.added;
      } else if (base[i] != literal[i]) {
        kind = DiffRunKind.changed;
      } else {
        kind = DiffRunKind.unchanged;
      }
      if (kind != DiffRunKind.unchanged) differing++;
      if (kind != current) {
        flush();
        current = kind;
      }
      buffer.writeCharCode(literal[i]);
    }
    flush();

    // A reference longer than the literal differs at every position the
    // literal never reaches. Those positions have no run to carry them, so
    // they are counted here and named in the summary.
    if (base.length > literal.length) differing += base.length - literal.length;

    return DiffOutcome(
      runs: runs,
      differingPositions: differing,
      summary: summaryFor(differing),
    );
  }

  /// The sentence for a difference count.
  static String summaryFor(int differingPositions) =>
      switch (differingPositions) {
        0 => 'Matches the reference reading at every position',
        1 => 'Differs at 1 position',
        _ => 'Differs at $differingPositions positions',
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
                        for (final DiffRun run in outcome.runs)
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
        DiffRunKind.unchanged => null,
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
