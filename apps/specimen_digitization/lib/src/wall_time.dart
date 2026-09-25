/// Wall-clock time: the one place the app reads a time zone.
///
/// A screen prints an instant through [wallTime]. In the app that reads the
/// host's zone, so a reviewer sees their own clock. The test suite pins it
/// with [debugWallTimeOverride], the way `debugDefaultTargetPlatformOverride`
/// pins the platform, so no golden depends on the zone of the machine that
/// renders it (coordinator ruling for S6, 2026-09-24). A test fails if any
/// other code in `lib` reads the host's zone.
library;

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

/// Reads instants in place of the host's zone when set. The test harness
/// sets it; the app never does.
WallTime Function(DateTime instant)? debugWallTimeOverride;

/// [instant] as the reviewer's wall clock shows it.
WallTime wallTime(DateTime instant) =>
    (debugWallTimeOverride ?? hostWallTime)(instant);

/// [instant] in the host's zone.
WallTime hostWallTime(DateTime instant) {
  final DateTime local = instant.toLocal();
  return (
    year: local.year,
    month: local.month,
    day: local.day,
    hour: local.hour,
    minute: local.minute,
    zone: local.timeZoneName,
  );
}
