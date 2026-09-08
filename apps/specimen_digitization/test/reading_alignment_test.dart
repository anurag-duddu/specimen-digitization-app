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
}
