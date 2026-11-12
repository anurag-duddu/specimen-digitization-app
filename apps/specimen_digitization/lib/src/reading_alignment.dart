import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'models.dart';
import 'review_context.dart';
import 'vocabulary.dart';
import 'widgets/caveat_text.dart';
import 'widgets/evidence_drawer.dart';
import 'widgets/selectable_evidence.dart';

/// Offsets describe the unchanged original text. Never normalize before slicing.
String exactUtf16Span(String source, int start, int end) {
  if (start < 0 || end < start || end > source.length) {
    throw const FormatException('Span outside retained reading');
  }
  bool splitsPair(int offset) =>
      offset > 0 &&
      offset < source.length &&
      source.codeUnitAt(offset) >= 0xdc00 &&
      source.codeUnitAt(offset) <= 0xdfff &&
      source.codeUnitAt(offset - 1) >= 0xd800 &&
      source.codeUnitAt(offset - 1) <= 0xdbff;
  if (splitsPair(start) || splitsPair(end)) {
    throw const FormatException('Span splits a Unicode character');
  }
  return source.substring(start, end);
}

/// The UTF-16 offset of code point [codePoint] of [source].
///
/// A reading unit's `start` and `end` are Python string indices, which count
/// code points (`application/reading_units.py`, `UnitText`); a Dart `String`
/// is indexed by UTF-16 code units, so each character above U+FFFF (an emoji)
/// before the offset moves it by one. A surrogate pair counts as one code
/// point and a lone surrogate as one, as `String.runes` counts them.
int utf16OffsetOfCodePoint(String source, int codePoint) {
  if (codePoint < 0) {
    throw const FormatException('Span outside retained reading');
  }
  int offset = 0;
  for (int seen = 0; seen < codePoint; seen++) {
    if (offset >= source.length) {
      throw const FormatException('Span outside retained reading');
    }
    final int unit = source.codeUnitAt(offset);
    final bool pair =
        unit >= 0xd800 &&
        unit <= 0xdbff &&
        offset + 1 < source.length &&
        source.codeUnitAt(offset + 1) >= 0xdc00 &&
        source.codeUnitAt(offset + 1) <= 0xdfff;
    offset += pair ? 2 : 1;
  }
  return offset;
}

/// The text of [source] from code point [start] to code point [end], sliced
/// by [exactUtf16Span] after converting both offsets.
String exactCodePointSpan(String source, int start, int end) => exactUtf16Span(
  source,
  utf16OffsetOfCodePoint(source, start),
  utf16OffsetOfCodePoint(source, end),
);

/// One comparison between two retained readings of a label.
///
/// A label read by three models has a comparison for each pair, so the two
/// sides carry the readers' names when the caller knows them and fall back to
/// "Left" and "Right" only when it does not.
class ReadingAlignmentView extends StatelessWidget {
  const ReadingAlignmentView({
    super.key,
    required this.alignment,
    this.leftText,
    this.rightText,
    this.leftName,
    this.rightName,
  });
  final Json alignment;
  final String? leftText, rightText;

  /// The readers behind the left and right sides.
  final String? leftName, rightName;
  Widget _span(BuildContext context, String side, Json span) {
    final UiThemeData ui = context.ui;
    final start = objectOf(span['start']);
    final end = objectOf(span['end']);
    final source = side == 'Left' ? leftText : rightText;
    final String who = (side == 'Left' ? leftName : rightName) ?? side;
    var text = textOf(span['text'], '');
    if (source != null) {
      try {
        final exact = exactUtf16Span(
          source,
          start['utf16_codeunit'] as int,
          end['utf16_codeunit'] as int,
        );
        if (exact != text) throw const FormatException('Mismatch');
      } catch (_) {
        text = 'Span does not match the retained reading. Refresh evidence.';
      }
    }
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '$who · Line ${start['line']} · UTF-16 [${start['utf16_codeunit']}, ${end['utf16_codeunit']})',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
          SelectableEvidence(
            child: Text(text, style: ui.type.mono.literalDense),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final status = textOf(alignment['status']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          status == 'policy_blocked'
              ? 'Comparison unavailable'
              : status == 'agreement'
              ? 'Exact retained readings agree'
              : status == 'disagreement'
              ? 'Differences between retained readings'
              : 'Comparison state not recognized',
          style: ui.type.label,
        ),
        if (leftName != null && rightName != null)
          Text(
            'Compared: $leftName and $rightName',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        for (final reason in alignment['reasons'] as List? ?? [])
          Text(vocabularyLabel(reason.toString())),
        if (status == 'disagreement')
          for (final alternative in objects(alignment['alternatives']))
            Padding(
              padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
              child: Surface(
                radius: ui.shape.tile,
                boundary: true,
                padding: EdgeInsetsDirectional.all(ui.space.s3),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      vocabularyLabel(textOf(alternative['operation'])),
                      style: ui.type.label,
                    ),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _span(context, 'Left', objectOf(alternative['left'])),
                        SizedBox(width: ui.space.s3),
                        _span(context, 'Right', objectOf(alternative['right'])),
                      ],
                    ),
                  ],
                ),
              ),
            ),
        if (status == 'policy_blocked')
          const CaveatText(
            label:
                'A comparison limit or incomplete input stopped the alignment.',
            why:
                'This is not agreement. Check the independent readings and the '
                'saved raw responses.',
          ),
        EvidenceDrawer(
          title: 'Comparison provenance and bounds',
          payload: alignment,
        ),
      ],
    );
  }
}

class ReadingMetadataView extends StatelessWidget {
  const ReadingMetadataView({super.key, required this.metadata});
  final Json metadata;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(
        'Language: ${vocabularyLabel(textOf(metadata['language_state'], 'unknown'))} · Script: ${vocabularyLabel(textOf(metadata['script_state'], 'unknown'))}',
        style: context.ui.type.body,
      ),
      for (final declaration in objects(metadata['declarations']))
        Text(
          '${declaration['kind']}: ${declaration['value'] ?? 'Unknown'} · ${vocabularyLabel(textOf(declaration['method']))}\n${declaration['producer']} · ${declaration['version']}',
        ),
      EvidenceDrawer(
        title: 'Declared language, script and heuristic limits',
        payload: metadata,
      ),
    ],
  );
}
