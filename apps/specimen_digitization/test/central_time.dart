/// US Central time, the zone the goldens were rendered in, for the suite's
/// pin of `wallTime` (`flutter_test_config.dart`; coordinator ruling for S6,
/// 2026-09-24).
///
/// The daylight-saving rule in force since 2007: CDT from the second Sunday
/// of March at 02:00 CST to the first Sunday of November at 02:00 CDT, and
/// CST otherwise.
library;

import 'package:specimen_digitization/src/wall_time.dart';

/// [instant] as a clock in Chicago shows it.
WallTime centralWallTime(DateTime instant) {
  final DateTime utc = instant.toUtc();
  // 02:00 CST is 08:00 UTC, and 02:00 CDT is 07:00 UTC.
  final DateTime daylightFrom = _sunday(
    utc.year,
    DateTime.march,
    2,
  ).add(const Duration(hours: 8));
  final DateTime daylightUntil = _sunday(
    utc.year,
    DateTime.november,
    1,
  ).add(const Duration(hours: 7));
  final bool daylight =
      !utc.isBefore(daylightFrom) && utc.isBefore(daylightUntil);
  final DateTime wall = utc.subtract(Duration(hours: daylight ? 5 : 6));
  return (
    year: wall.year,
    month: wall.month,
    day: wall.day,
    hour: wall.hour,
    minute: wall.minute,
    zone: daylight ? 'CDT' : 'CST',
  );
}

/// The [nth] Sunday of [month] in [year], at midnight UTC.
DateTime _sunday(int year, int month, int nth) {
  final DateTime first = DateTime.utc(year, month);
  final int toSunday = (DateTime.sunday - first.weekday) % 7;
  return DateTime.utc(year, month, 1 + toSunday + 7 * (nth - 1));
}

/// A synthetic zone whose clocks jump over midnight, as Havana's, Santiago's
/// and the Azores' do on their daylight-saving day: UTC-5 until [jump], then
/// UTC-4, so the day [jump] falls on has no 00:00 (#197 and #202 reviews).
WallTime Function(DateTime instant) skipsMidnightAt(DateTime jump) =>
    (DateTime instant) {
      final DateTime utc = instant.toUtc();
      final bool after = !utc.isBefore(jump);
      final DateTime wall = utc.add(Duration(hours: after ? -4 : -5));
      return (
        year: wall.year,
        month: wall.month,
        day: wall.day,
        hour: wall.hour,
        minute: wall.minute,
        zone: after ? 'SDT' : 'SST',
      );
    };
