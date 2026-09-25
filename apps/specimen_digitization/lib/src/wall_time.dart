/// Wall-clock time: the one place the app reads a time zone.
///
/// A screen prints an instant through [wallTime]. In the app that reads the
/// host's zone, so a reviewer sees their own clock. The test suite pins it
/// with [debugWallTimeOverride], the way `debugDefaultTargetPlatformOverride`
/// pins the platform, so no golden depends on the zone of the machine that
/// renders it (coordinator ruling for S6, 2026-09-24, 23:10:57Z). A release
/// build ignores the override.
///
/// `test/wall_time_test.dart` fails when other code in `lib` converts to the
/// host zone, asks its name or offset, builds an instant from the host's
/// wall-clock fields or from an epoch without `isUtc`, reads a wall-clock
/// field of `DateTime.now()`, or touches the override. It reads one line at
/// a time and knows no types, so it cannot see a `now` held in a variable
/// and read later, a chained read such as `DateTime.now().add(d).day`,
/// `copyWith` or `toString`/`toIso8601String` on a local instant, a tear-off
/// such as `.map(DateTime.new)`, an expression split across lines, a read
/// through another package, a parse of text without a zone (the server's
/// instants carry one), or code outside `lib` and
/// `packages/specimen_ui/lib`. It also rejects two correct UTC epoch calls:
/// one whose `isUtc: true` sits on a later line, and one whose argument has
/// parentheses, since its look-ahead stops at the first `)`.
library;

import 'package:flutter/foundation.dart';

/// An instant as a wall clock shows it: the fields a screen prints, and the
/// zone's abbreviation.
typedef WallTime = ({
  int year,
  int month,
  int day,
  int hour,
  int minute,
  String zone,
});

/// Reads instants in place of the host's zone when set, in a debug build
/// only. The test harness sets it; the app never does.
WallTime Function(DateTime instant)? debugWallTimeOverride;

/// [instant] as the reviewer's wall clock shows it.
WallTime wallTime(DateTime instant) =>
    ((kDebugMode ? debugWallTimeOverride : null) ?? _hostWallTime)(instant);

/// [instant] in the host's zone.
WallTime _hostWallTime(DateTime instant) {
  final DateTime local = instant.toLocal();
  return (
    year: local.year,
    month: local.month,
    day: local.day,
    hour: local.hour,
    minute: local.minute,
    zone: zoneAbbreviation(local.timeZoneName),
  );
}

/// A zone's name as 02 section 4.14 writes it: "CDT". A browser names the
/// zone in full ("Central Daylight Time"). Only the names in this table are
/// shortened, because initials mislead elsewhere: "Central European Standard
/// Time" is not CEST, Pakistan's is not PST, and a browser in Spanish names
/// the zone in Spanish (#182 review). Any other name is kept as given.
@visibleForTesting
String zoneAbbreviation(String name) => _shortZones[name] ?? name;

/// The US zones, UTC, GMT and BST, by the full names browsers give them.
const Map<String, String> _shortZones = <String, String>{
  'Eastern Standard Time': 'EST',
  'Eastern Daylight Time': 'EDT',
  'Central Standard Time': 'CST',
  'Central Daylight Time': 'CDT',
  'Mountain Standard Time': 'MST',
  'Mountain Daylight Time': 'MDT',
  'Pacific Standard Time': 'PST',
  'Pacific Daylight Time': 'PDT',
  'Alaska Standard Time': 'AKST',
  'Alaska Daylight Time': 'AKDT',
  'Hawaii-Aleutian Standard Time': 'HST',
  'Hawaii-Aleutian Daylight Time': 'HDT',
  'Coordinated Universal Time': 'UTC',
  'Greenwich Mean Time': 'GMT',
  'British Summer Time': 'BST',
};

/// The instant a day begins on the reviewer's wall clock, in UTC, for a
/// filter the reviewer typed as a day (design/01 H2.1; coordinator ruling
/// for S6, 2026-09-25, 01:26:02Z): its midnight, or, where the clocks jump
/// over midnight on a daylight-saving day (Havana, Santiago, the Azores), the
/// jump, the day's first moment. Where the clocks repeat midnight, it is the
/// first midnight west of UTC, which is every such day in 2024-2030 (Havana
/// each November, the Azores each October: 21 in the #202 review's sweep),
/// and the second east of UTC, which no zone does in 2024-2030. Found through
/// [wallTime], so the suite's pinned clock answers it as well as the host's.
DateTime wallDayStart(int year, int month, int day) {
  final DateTime midnight = DateTime.utc(year, month, day);
  // Moves [instant] by how far its wall clock reads from the midnight.
  DateTime towardMidnight(DateTime instant) {
    final WallTime wall = wallTime(instant);
    final DateTime seen = DateTime.utc(
      wall.year,
      wall.month,
      wall.day,
      wall.hour,
      wall.minute,
    );
    return instant.subtract(seen.difference(midnight));
  }

  // The first step finds the offset at a first guess; the second corrects
  // for an offset that changed between the guess and the midnight.
  final DateTime first = towardMidnight(midnight);
  final DateTime second = towardMidnight(first);
  final WallTime reached = wallTime(second);
  // West of UTC, a day with no midnight sends the second step back to the
  // day before, and the first step's instant is then the jump itself; east
  // of UTC, the second step lands on the jump.
  return (reached.year, reached.month, reached.day) == (year, month, day)
      ? second
      : first;
}
