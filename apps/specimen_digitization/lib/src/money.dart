/// Money on screen: US dollars from the cost meter's integer micro-dollars.
///
/// The meter counts in millionths of a dollar so that a call costing a
/// fraction of a cent still adds up. A reviewer reads dollars and cents, so
/// this file is the one place that converts, in both directions, and "micros"
/// never reaches a screen.
library;

/// Micro-dollars in one US dollar.
const int microsPerDollar = 1000000;

/// Micro-dollars in one cent.
const int microsPerCent = 10000;

const int _centsPerDollar = 100;

/// What an amount above zero and under one cent reads as.
///
/// A cent is the smallest amount the screen can write as digits. Rounding a
/// real cost to `$0.00` would read as no cost at all, and rounding it up to
/// `$0.01` would claim more than was spent, so it is said in words.
const String underOneCent = 'Under one cent';

/// The most a monthly limit may be, in dollars.
///
/// A guard on what a person types, not a rule of the service: the web build
/// keeps integers exact only below 2^53, and a limit above a million dollars
/// is a mistyped one for a collection of this size.
const int maxLimitDollars = 1000000;

/// [micros] as US dollars with thousands separators and cents, such as
/// `$1,234.56`.
///
/// Rounds half up to the cent. An amount above zero and under one cent reads
/// [underOneCent]; zero reads `$0.00`, which is a measured nothing and not an
/// absent figure (the caller says "No costs recorded" for the latter).
String formatMicros(int micros) {
  if (micros < 0) return '-${formatMicros(-micros)}';
  if (micros > 0 && micros < microsPerCent) return underOneCent;
  final int cents = (micros + microsPerCent ~/ 2) ~/ microsPerCent;
  final int dollars = cents ~/ _centsPerDollar;
  final String remainder = (cents % _centsPerDollar).toString().padLeft(2, '0');
  return '\$${_grouped(dollars)}.$remainder';
}

/// A count with a comma between each group of three digits: `1,234`.
///
/// Every count over 999 carries its separators (02 section 4.14).
String formatCount(int count) => _grouped(count);

/// [value] with a comma between each group of three digits, from the right.
String _grouped(int value) {
  final String digits = value.toString();
  final StringBuffer out = StringBuffer();
  for (int index = 0; index < digits.length; index++) {
    if (index > 0 && (digits.length - index) % 3 == 0) out.write(',');
    out.write(digits[index]);
  }
  return out.toString();
}

/// Why a typed monthly limit cannot be used.
enum LimitInputProblem {
  /// Nothing was typed.
  empty,

  /// The text is not an amount of dollars.
  notAnAmount,

  /// More than two decimal places.
  tooPrecise,

  /// The amount is zero, which is not a limit.
  notAboveZero,

  /// The amount is above [maxLimitDollars].
  tooLarge,
}

/// What reading a typed limit produced: micro-dollars, or the reason not.
///
/// Exactly one of the two is set.
typedef LimitInput = ({int? micros, LimitInputProblem? problem});

/// Reads [text] as an amount of US dollars: `25`, `25.5`, `$1,250.00`.
///
/// Spaces, a leading dollar sign and thousands commas are ignored. Cents are
/// the finest unit a person can set, so a third decimal place is refused
/// rather than rounded: a limit that quietly changed by a digit would not be
/// the one that was typed.
LimitInput parseLimitInput(String text) {
  final String cleaned = text
      .replaceAll(RegExp(r'\s'), '')
      .replaceFirst(r'$', '')
      .replaceAll(',', '');
  if (cleaned.isEmpty) return _refused(LimitInputProblem.empty);
  final RegExpMatch? match = RegExp(r'^(\d*)(?:\.(\d*))?$').firstMatch(cleaned);
  if (match == null) return _refused(LimitInputProblem.notAnAmount);
  final String whole = match.group(1) ?? '';
  final String fraction = match.group(2) ?? '';
  if (whole.isEmpty && fraction.isEmpty) {
    return _refused(LimitInputProblem.notAnAmount);
  }
  if (fraction.length > 2) return _refused(LimitInputProblem.tooPrecise);
  final String trimmed = whole.replaceFirst(RegExp(r'^0+'), '');
  if (trimmed.length > maxLimitDollars.toString().length) {
    return _refused(LimitInputProblem.tooLarge);
  }
  final int dollars = trimmed.isEmpty ? 0 : int.parse(trimmed);
  final int cents =
      dollars * _centsPerDollar +
      (fraction.isEmpty ? 0 : int.parse(fraction.padRight(2, '0')));
  if (cents == 0) return _refused(LimitInputProblem.notAboveZero);
  if (cents > maxLimitDollars * _centsPerDollar) {
    return _refused(LimitInputProblem.tooLarge);
  }
  return (micros: cents * microsPerCent, problem: null);
}

LimitInput _refused(LimitInputProblem problem) =>
    (micros: null, problem: problem);

/// [micros] as the text a limit field starts with: `25.00`, no sign and no
/// separators, so it parses back to the same amount.
String limitFieldText(int micros) {
  final int cents = (micros + microsPerCent ~/ 2) ~/ microsPerCent;
  final String remainder = (cents % _centsPerDollar).toString().padLeft(2, '0');
  return '${cents ~/ _centsPerDollar}.$remainder';
}
