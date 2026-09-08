import 'package:flutter/material.dart';
import 'models.dart';
import 'review_context.dart';

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
  Widget _span(String side, Json span) {
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
          ),
          SelectionArea(
            child: Text(text, style: const TextStyle(fontFamily: 'monospace')),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
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
              : 'Unsupported comparison state',
          style: Theme.of(context).textTheme.titleSmall,
        ),
        for (final reason in alignment['reasons'] as List? ?? [])
          Text(labelOf(reason.toString())),
        if (status == 'disagreement')
          for (final alternative in objects(alignment['alternatives']))
            Card.outlined(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(labelOf(textOf(alternative['operation']))),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _span('Left', objectOf(alternative['left'])),
                        const SizedBox(width: 12),
                        _span('Right', objectOf(alternative['right'])),
                      ],
                    ),
                  ],
                ),
              ),
            ),
        if (status == 'policy_blocked')
          const Text(
            'A comparison limit or incomplete input prevented alignment. This is not agreement; inspect the independent readings and retained raw responses.',
          ),
        EvidenceDetails(
          title: 'Comparison provenance and bounds',
          value: alignment,
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
        'Language: ${labelOf(textOf(metadata['language_state'], 'unknown'))} · Script: ${labelOf(textOf(metadata['script_state'], 'unknown'))}',
      ),
      for (final declaration in objects(metadata['declarations']))
        Text(
          '${declaration['kind']}: ${declaration['value'] ?? 'Unknown'} · ${labelOf(textOf(declaration['method']))}\n${declaration['producer']} · ${declaration['version']}',
        ),
      EvidenceDetails(
        title: 'Declared language, script and heuristic limits',
        value: metadata,
      ),
    ],
  );
}
