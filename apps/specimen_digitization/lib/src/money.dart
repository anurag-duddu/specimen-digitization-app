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

/// What an amount below zero and over minus one cent reads as: the same
/// reasoning, in the credit's words.
const String creditUnderOneCent = 'Credit under one cent';

/// The word that says an amount is taken off, written after the dollars:
/// `$0.30 credit`.
const String creditWord = 'credit';

/// The most a monthly limit may be, in micro-dollars: the service's own bound,
/// 2^53 - 1, which is also the largest integer the web build keeps exact.
const int maxLimitMicros = 9007199254740991;

/// The most a monthly limit may be, in cents.
const int maxLimitCents = maxLimitMicros ~/ microsPerCent;

/// [micros] as US dollars with thousands separators and cents, such as
/// `$1,234.56`.
///
/// Rounds half up to the cent. An amount above zero and under one cent reads
/// [underOneCent]; zero reads `$0.00`, which is a measured nothing and not an
/// absent figure (the caller says "No costs recorded" for the latter).
///
/// An amount below zero is a credit, because every sum the meter reports is
/// signed: Google's free allowance is recorded as a negative row, and a
/// residual can come out below the charges it is measured against. It is
/// written in words after its dollars, `$0.30 credit`, and never with a minus
/// sign or a dash, which a reader takes for a hyphen in a sentence or for a
/// missing figure (02 section 6, rule 1).
String formatMicros(int micros) {
  if (micros < 0) {
    final int credit = -micros;
    return credit < microsPerCent
        ? creditUnderOneCent
        : '${formatMicros(credit)} $creditWord';
  }
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

  /// The amount is above [maxLimitCents].
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
/// the one that was typed. Zero is an amount: the service takes a limit from
/// 0 up to [maxLimitMicros], and removing a limit is its own action.
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
  // Checked before it is read, so a long run of digits is never parsed into a
  // number the web build cannot hold exactly.
  if (trimmed.length > (maxLimitCents ~/ _centsPerDollar).toString().length) {
    return _refused(LimitInputProblem.tooLarge);
  }
  final int dollars = trimmed.isEmpty ? 0 : int.parse(trimmed);
  final int cents =
      dollars * _centsPerDollar +
      (fraction.isEmpty ? 0 : int.parse(fraction.padRight(2, '0')));
  if (cents > maxLimitCents) return _refused(LimitInputProblem.tooLarge);
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
