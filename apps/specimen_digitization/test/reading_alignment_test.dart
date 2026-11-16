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

  // A reading unit's offsets are Python string indices: code points
  // (WP 1.6, docs/execution/units/PLAN.md).
  test('a unit after an emoji converts its code points to UTF-16', () {
    for (final (
          String reading,
          int start,
          int end,
          String unit,
          int from,
          int to,
        )
        in <(String, int, int, String, int, int)>[
          // Nothing above U+FFFF: the two offsets agree.
          ('Elev.6400', 0, 9, 'Elev.6400', 0, 9),
          // One emoji before the unit moves both offsets by one.
          ('🦋 Chicago 1912', 2, 9, 'Chicago', 3, 10),
          // Two emoji before it move them by two.
          ('🦋🐞 Chicago', 3, 10, 'Chicago', 5, 12),
          // An emoji before the unit and one inside it.
          ('🐞Sp.30 🐞 x', 1, 8, 'Sp.30 🐞', 2, 10),
          // The first and last characters above U+FFFF: U+10000 is the pair
          // D800 DC00 and U+10FFFF the pair DBFF DFFF, each one code point.
          ('\u{10000} x', 2, 3, 'x', 3, 4),
          ('\u{10000} x', 0, 1, '\u{10000}', 0, 2),
          ('\u{10FFFF} x', 2, 3, 'x', 3, 4),
          ('\u{10FFFF} x', 0, 1, '\u{10FFFF}', 0, 2),
          // Next to the surrogates, U+D7FF and U+E000 are one code unit each,
          // as is U+FFFF.
          ('\u{D7FF}\u{E000}\u{FFFF} x', 4, 5, 'x', 4, 5),
          // The unit is the emoji.
          ('Sp.30 ♀ 🐞', 8, 9, '🐞', 8, 10),
          // A combining accent is a code point of its own, and in the BMP.
          ('Me\u0301xico 🦋', 0, 7, 'Me\u0301xico', 0, 7),
          // An empty unit at the end of the reading.
          ('🦋 x', 3, 3, '', 4, 4),
        ]) {
      expect(utf16OffsetOfCodePoint(reading, start), from, reason: reading);
      expect(utf16OffsetOfCodePoint(reading, end), to, reason: reading);
      expect(exactCodePointSpan(reading, start, end), unit, reason: reading);
      if (from != start && unit.isNotEmpty) {
        // Sliced as UTF-16 without the conversion, the offsets miss the unit.
        expect(
          reading.substring(start, end.clamp(start, reading.length)),
          isNot(unit),
          reason: reading,
        );
      }
    }
    for (final (int start, int end) in <(int, int)>[(-1, 2), (2, 5), (3, 2)]) {
      expect(
        () => exactCodePointSpan('🦋 x', start, end),
        throwsFormatException,
        reason: '[$start, $end)',
      );
    }
  });

  test('every code-point span of a mixed reading is its runes', () {
    for (final String reading in <String>[
      '',
      'Elev.6400',
      '😀a\r\nb',
      'a\u0301\r\n٢ 🦋🐞 Sp.30 ♀',
      '\u{10000}a\u{10FFFF}b\u{D7FF}\u{E000}\u{FFFF}',
      // A lone surrogate is one code point, as `runes` counts it.
      'x\uD800y\uDC00z🐞',
      'z\uD800',
    ]) {
      final List<int> runes = reading.runes.toList();
      for (int start = 0; start <= runes.length; start++) {
        expect(
          utf16OffsetOfCodePoint(reading, start),
          String.fromCharCodes(runes.take(start)).length,
          reason: '$reading at $start',
        );
        for (int end = start; end <= runes.length; end++) {
          expect(
            exactCodePointSpan(reading, start, end),
            String.fromCharCodes(runes.sublist(start, end)),
            reason: '$reading [$start, $end)',
          );
        }
      }
      expect(
        () => utf16OffsetOfCodePoint(reading, runes.length + 1),
        throwsFormatException,
      );
    }
  });
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
