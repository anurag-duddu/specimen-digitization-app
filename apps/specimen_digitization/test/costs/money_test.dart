// Money on screen (`lib/src/money.dart`): dollars and cents from micro-dollars,
// and the other way for a typed monthly limit.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/money.dart';

void main() {
  group('formatMicros', () {
    test('writes dollars with cents', () {
      expect(formatMicros(1000000), r'$1.00');
      expect(formatMicros(12345678), r'$12.35');
      expect(formatMicros(50000000), r'$50.00');
      expect(formatMicros(450000), r'$0.45');
    });

    test('separates thousands', () {
      expect(formatMicros(999990000), r'$999.99');
      expect(formatMicros(1000000000), r'$1,000.00');
      expect(formatMicros(1234567890), r'$1,234.57');
      expect(formatMicros(12345678900000), r'$12,345,678.90');
      expect(formatMicros(1000000000000), r'$1,000,000.00');
    });

    test('rounds half up to the cent', () {
      expect(formatMicros(14999), r'$0.01');
      expect(formatMicros(15000), r'$0.02');
      expect(formatMicros(999999999), r'$1,000.00');
    });

    test('says an amount under one cent in words, never as zero', () {
      expect(formatMicros(1), underOneCent);
      expect(formatMicros(9999), underOneCent);
      expect(formatMicros(10000), r'$0.01');
      expect(underOneCent, 'Under one cent');
    });

    test('writes a measured zero as dollars and cents', () {
      // Zero is a recorded nothing. A slice the meter recorded nothing for is
      // said in words by the screen, which decides that before it gets here.
      expect(formatMicros(0), r'$0.00');
    });

    test('keeps a sign on an amount below zero', () {
      expect(formatMicros(-1200000), r'-$1.20');
    });

    test('never writes the unit the meter counts in', () {
      for (final int micros in <int>[0, 1, 12345678, 1234567890]) {
        expect(formatMicros(micros).toLowerCase(), isNot(contains('micro')));
      }
    });
  });

  group('formatCount', () {
    test('separates a count over 999', () {
      expect(formatCount(7), '7');
      expect(formatCount(999), '999');
      expect(formatCount(1000), '1,000');
      expect(formatCount(1234567), '1,234,567');
    });
  });

  group('parseLimitInput', () {
    int? micros(String text) => parseLimitInput(text).micros;
    LimitInputProblem? problem(String text) => parseLimitInput(text).problem;

    test('reads dollars and cents', () {
      expect(micros('25'), 25000000);
      expect(micros('25.5'), 25500000);
      expect(micros('25.50'), 25500000);
      expect(micros('0.01'), 10000);
      expect(micros('.5'), 500000);
      expect(micros('25.'), 25000000);
    });

    test('ignores spaces, a dollar sign and thousands commas', () {
      expect(micros(r' $1,250.00 '), 1250000000);
      expect(micros('1,250'), 1250000000);
      expect(micros('007'), 7000000);
    });

    test('reads back what the field was filled with', () {
      for (final int amount in <int>[10000, 5000000, 1234560000, 7000000]) {
        expect(micros(limitFieldText(amount)), amount, reason: '$amount');
      }
      expect(limitFieldText(5000000), '5.00');
      expect(limitFieldText(1234560000), '1234.56');
    });

    test('refuses an empty field', () {
      expect(problem(''), LimitInputProblem.empty);
      expect(problem('   '), LimitInputProblem.empty);
      expect(problem(r'$'), LimitInputProblem.empty);
    });

    test('refuses what is not an amount', () {
      for (final String text in <String>[
        'abc',
        '1.2.3',
        '-5',
        '5e3',
        '.',
        '5 5x',
      ]) {
        expect(problem(text), LimitInputProblem.notAnAmount, reason: text);
      }
    });

    test('refuses a third decimal place rather than rounding it', () {
      expect(problem('25.123'), LimitInputProblem.tooPrecise);
      expect(problem('0.001'), LimitInputProblem.tooPrecise);
    });

    test('refuses zero, which is not a limit', () {
      expect(problem('0'), LimitInputProblem.notAboveZero);
      expect(problem('0.00'), LimitInputProblem.notAboveZero);
    });

    test('refuses more than a million dollars', () {
      expect(micros('1000000'), 1000000000000);
      expect(problem('1000000.01'), LimitInputProblem.tooLarge);
      expect(problem('99999999999'), LimitInputProblem.tooLarge);
    });

    test('sets exactly one of the amount and the reason', () {
      for (final String text in <String>['5', '', 'x', '0', '1.234']) {
        final LimitInput input = parseLimitInput(text);
        expect(input.micros == null, input.problem != null, reason: text);
      }
    });
  });
}
