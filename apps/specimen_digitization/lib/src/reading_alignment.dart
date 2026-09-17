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

class ReadingAlignmentView extends StatelessWidget {
  const ReadingAlignmentView({
    super.key,
    required this.alignment,
    this.leftText,
    this.rightText,
  });
  final Json alignment;
  final String? leftText, rightText;
  Widget _span(BuildContext context, String side, Json span) {
    final UiThemeData ui = context.ui;
    final start = objectOf(span['start']);
    final end = objectOf(span['end']);
    final source = side == 'Left' ? leftText : rightText;
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
            '$side · Line ${start['line']} · UTF-16 [${start['utf16_codeunit']}, ${end['utf16_codeunit']})',
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
