/// Instants, in words a reviewer can act on (audit pass criterion 1.6).
///
/// No machine format reaches the screen. Anything inside a day reads as a
/// relative phrase; anything older or further out reads as the citable
/// absolute form. An instant the server did not send reads as not recorded,
/// never as an epoch and never as a blank.
library;

import '../../models.dart';
import '../../widgets/widgets.dart';

/// The hours inside which an instant is phrased relatively.
const int relativeWindowHours = 24;

/// One wire instant, rendered for a reviewer.
String relativeInstant(Object? value) {
  final DateTime? parsed = DateTime.tryParse(textOf(value, ''));
  if (parsed == null) return 'Not recorded';
  final Duration delta = parsed.difference(DateTime.now());
  final Duration size = delta.abs();
  if (size.inHours >= relativeWindowHours) return absoluteTime(parsed);
  final String span = size.inMinutes < 1
      ? 'less than a minute'
      : size.inHours < 1
      ? '${size.inMinutes} min'
      : '${size.inHours} h';
  return delta.isNegative ? '$span ago' : 'in $span';
}

/// The same instant with its absolute form attached, for a timeline entry
/// where the relative phrase alone is not citable.
String citedInstant(Object? value) {
  final DateTime? parsed = DateTime.tryParse(textOf(value, ''));
  if (parsed == null) return 'Not recorded';
  final Duration size = parsed.difference(DateTime.now()).abs();
  if (size.inHours >= relativeWindowHours) return absoluteTime(parsed);
  return '${relativeInstant(value)} (${absoluteTime(parsed)})';
}
