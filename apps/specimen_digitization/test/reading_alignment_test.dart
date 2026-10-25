import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/reading_alignment.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

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
        MaterialApp(
          theme: AppTheme.light(),
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
    'a comparison names the two readers it compares, whoever the other readers are',
    (tester) async {
      const start = {'utf16_codeunit': 11, 'line': 1};
      const end = {'utf16_codeunit': 12, 'line': 1};
      const alignment = {
        'status': 'disagreement',
        'alternatives': [
          {
            'operation': 'replace',
            'left': {'start': start, 'end': end, 'text': '2'},
            'right': {'start': start, 'end': end, 'text': '7'},
          },
        ],
      };
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(
            body: ReadingAlignmentView(
              alignment: alignment,
              leftText: 'Chicago 1912',
              rightText: 'Chicago 1917',
              leftName: 'Reader B',
              rightName: 'Reader C',
            ),
          ),
        ),
      );
      expect(find.text('Compared: Reader B and Reader C'), findsOneWidget);
      expect(find.text('Reader B · Line 1 · UTF-16 [11, 12)'), findsOneWidget);
      expect(find.text('Reader C · Line 1 · UTF-16 [11, 12)'), findsOneWidget);
      expect(find.textContaining('Left'), findsNothing);
      expect(find.textContaining('Right'), findsNothing);
    },
  );
  testWidgets(
    'an agreement still says which two readers agree, and a nameless one keeps left and right',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(
            body: ReadingAlignmentView(
              alignment: {'status': 'agreement'},
              leftName: 'Reader A',
              rightName: 'Reader C',
            ),
          ),
        ),
      );
      expect(find.text('Exact retained readings agree'), findsOneWidget);
      expect(find.text('Compared: Reader A and Reader C'), findsOneWidget);

      const start = {'utf16_codeunit': 0, 'line': 1};
      const end = {'utf16_codeunit': 1, 'line': 1};
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(
            body: ReadingAlignmentView(
              alignment: {
                'status': 'disagreement',
                'alternatives': [
                  {
                    'operation': 'replace',
                    'left': {'start': start, 'end': end, 'text': 'a'},
                    'right': {'start': start, 'end': end, 'text': 'b'},
                  },
                ],
              },
            ),
          ),
        ),
      );
      expect(find.textContaining('Compared:'), findsNothing);
      expect(find.text('Left · Line 1 · UTF-16 [0, 1)'), findsOneWidget);
      expect(find.text('Right · Line 1 · UTF-16 [0, 1)'), findsOneWidget);
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
        MaterialApp(
          theme: AppTheme.light(),
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
        MaterialApp(
          theme: AppTheme.light(),
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
