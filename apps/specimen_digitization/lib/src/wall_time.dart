/// Wall-clock time: the one place the app reads a time zone.
///
/// A screen prints an instant through [wallTime]. In the app that reads the
/// host's zone, so a reviewer sees their own clock. The test suite pins it
/// with [debugWallTimeOverride], the way `debugDefaultTargetPlatformOverride`
/// pins the platform, so no golden depends on the zone of the machine that
/// renders it (coordinator ruling for S6, 2026-09-24). A release build
/// ignores the override.
///
/// `test/wall_time_test.dart` fails when other code in `lib` converts to the
/// host zone, asks its name or offset, builds an instant from the host's
/// wall-clock fields or from an epoch without `isUtc`, reads a wall-clock
/// field of `DateTime.now()`, or touches the override. A parse of text
/// without a zone is not checked: the server's instants carry one.
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
/// zone in full ("Central Daylight Time"), so a name of several words is
/// shortened to its initials, and the one full name whose letters are not
/// its initials keeps its own: UTC. An abbreviation or an offset is kept.
@visibleForTesting
String zoneAbbreviation(String name) {
  if (!name.contains(' ')) return name;
  if (name == 'Coordinated Universal Time') return 'UTC';
  return <String>[
    for (final String word in name.split(' '))
      if (word.isNotEmpty) word[0].toUpperCase(),
  ].join();
}
