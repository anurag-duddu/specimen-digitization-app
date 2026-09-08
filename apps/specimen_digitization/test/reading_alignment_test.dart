import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/reading_alignment.dart';

void main() {
  test(
    'raw UTF16 half-open spans preserve astral combining and CRLF boundaries',
    () {
      const text = '😀a\r\nb';
      expect(exactUtf16Span(text, 5, 6), 'b');
      expect(exactUtf16Span(text, 0, 2), '😀');
      expect(exactUtf16Span('a\u0301\r\n٢', 0, 2), 'a\u0301');
      expect(() => exactUtf16Span(text, 1, 2), throwsFormatException);
      expect(() => exactUtf16Span(text, 0, 1), throwsFormatException);
      expect(() => exactUtf16Span(text, 0, 99), throwsFormatException);
    },
  );
  testWidgets(
    'blocked long or truncated comparisons never display agreement or invented differences',
    (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: ReadingAlignmentView(
              alignment: {
                'status': 'policy_blocked',
                'reasons': ['alignment_budget_exceeded'],
                'comparison_sha256': null,
                'alternatives': [
                  {'operation': 'invented'},
                ],
              },
            ),
          ),
        ),
      );
      expect(find.text('Comparison unavailable'), findsOneWidget);
      expect(find.text('alignment budget exceeded'), findsOneWidget);
      expect(find.text('Exact retained readings agree'), findsNothing);
      expect(find.text('invented'), findsNothing);
    },
  );
  testWidgets(
    'serialized multilingual span distinguishes UTF16 bytes and codepoints in unchanged source',
    (tester) async {
      // Display projection from align_readings at immutable backend 026d0b9.
      // Hashes are not part of this presentation test; authenticated wire tests
      // separately cover retained raw digest validation.
      const left = 'Málaga a\u0301 😀\r\n日本語 العربية ٢';
      const right = 'Málaga a\u0301 😀\r\n日本語 العربية ٣';
      const start = {
        'codepoint': 25,
        'utf8_byte': 43,
        'utf16_codeunit': 26,
        'line': 2,
        'column_codepoint': 12,
      };
      const end = {
        'codepoint': 26,
        'utf8_byte': 45,
        'utf16_codeunit': 27,
        'line': 2,
        'column_codepoint': 13,
      };
      const alignment = {
        'status': 'disagreement',
        'alternatives': [
          {
            'operation': 'replace',
            'left': {'start': start, 'end': end, 'text': '٢'},
            'right': {'start': start, 'end': end, 'text': '٣'},
            'contains_numeral': true,
          },
        ],
      };
      expect(exactUtf16Span(left, 26, 27), '٢');
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: ReadingAlignmentView(
              alignment: alignment,
              leftText: left,
              rightText: right,
            ),
          ),
        ),
      );
      expect(find.text('٢'), findsOneWidget);
      expect(find.text('٣'), findsOneWidget);
      expect(find.textContaining('UTF-16 [26, 27)'), findsNWidgets(2));
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: ReadingAlignmentView(
              alignment: alignment,
              leftText: right,
              rightText: right,
            ),
          ),
        ),
      );
      expect(
        find.text(
          'Span does not match the retained reading. Refresh evidence.',
        ),
        findsOneWidget,
      );
      expect(find.text('٢'), findsNothing);
    },
  );
}
