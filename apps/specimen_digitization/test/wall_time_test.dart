// Wall-clock time is read in one place, and the suite pins that place to US
// Central time, the zone the goldens were rendered in. So no golden and no
// test depends on the zone of the machine that runs it (coordinator ruling
// for S6, 2026-09-24, after this machine's zone moved to America/New_York
// and six History goldens failed with no code change).

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/wall_time.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';

import 'central_time.dart';

/// A read of the host's zone: converting to it, asking its name or offset,
/// or building an instant from the host's wall-clock fields.
final RegExp _hostZone = RegExp(
  r'\.toLocal\(\)|\.timeZoneName\b|\.timeZoneOffset\b|\bDateTime\(',
);

void main() {
  group('the suite pins Central time', () {
    test('an instant prints in CDT on any machine', () {
      expect(
        absoluteWallTime(DateTime.utc(2026, 9, 13, 19, 32)),
        '13 Sep 2026, 14:32 CDT',
      );
      expect(
        absoluteTime(DateTime.utc(2026, 9, 13, 19, 32).toLocal()),
        '13 Sep 2026, 14:32 CDT',
        reason: 'an instant in the host zone reads on the pinned clock',
      );
    });

    test("an instant in UTC prints on the reviewer's clock too", () {
      // design/01 H1.9: a reviewer never converts zones in their head
      // (coordinator ruling for S6, 2026-09-24).
      expect(
        absoluteTime(DateTime.utc(2026, 9, 14, 10, 22)),
        '14 Sep 2026, 05:22 CDT',
      );
    });

    test('the pin is the harness default, not a per-test choice', () {
      expect(debugWallTimeOverride, same(centralWallTime));
    });
  });

  group('Central time follows the daylight-saving rule', () {
    test('CDT starts at 02:00 CST on the second Sunday of March', () {
      expect(centralWallTime(DateTime.utc(2026, 3, 8, 7, 59)), (
        year: 2026,
        month: 3,
        day: 8,
        hour: 1,
        minute: 59,
        zone: 'CST',
      ));
      expect(centralWallTime(DateTime.utc(2026, 3, 8, 8)), (
        year: 2026,
        month: 3,
        day: 8,
        hour: 3,
        minute: 0,
        zone: 'CDT',
      ));
    });

    test('CST returns at 02:00 CDT on the first Sunday of November', () {
      expect(centralWallTime(DateTime.utc(2026, 11, 1, 6, 59)), (
        year: 2026,
        month: 11,
        day: 1,
        hour: 1,
        minute: 59,
        zone: 'CDT',
      ));
      expect(centralWallTime(DateTime.utc(2026, 11, 1, 7)), (
        year: 2026,
        month: 11,
        day: 1,
        hour: 1,
        minute: 0,
        zone: 'CST',
      ));
    });

    test('an instant in the host zone reads as its UTC twin does', () {
      final DateTime utc = DateTime.utc(2026, 9, 8, 5, 1);
      expect(centralWallTime(utc.toLocal()), centralWallTime(utc));
    });
  });

  group('the app reads a zone through one seam', () {
    tearDown(() => debugWallTimeOverride = centralWallTime);

    test('the wall-clock form prints what the seam reads', () {
      debugWallTimeOverride = (DateTime _) =>
          (year: 2001, month: 2, day: 3, hour: 4, minute: 5, zone: 'ZZZ');
      expect(absoluteWallTime(DateTime.utc(2026)), '3 Feb 2001, 04:05 ZZZ');
    });

    test('unpinned, the seam reads the host zone', () {
      debugWallTimeOverride = null;
      final DateTime instant = DateTime.utc(2026, 9, 8, 5, 1);
      final DateTime local = instant.toLocal();
      expect(wallTime(instant), (
        year: local.year,
        month: local.month,
        day: local.day,
        hour: local.hour,
        minute: local.minute,
        zone: local.timeZoneName,
      ));
    });

    test('nothing else in lib reads the host zone', () {
      final List<String> leaks = <String>[
        for (final String root in <String>['lib', 'packages/specimen_ui/lib'])
          if (Directory(root).existsSync())
            for (final FileSystemEntity entity in Directory(
              root,
            ).listSync(recursive: true))
              if (entity is File &&
                  entity.path.endsWith('.dart') &&
                  !entity.path.endsWith('lib/src/wall_time.dart'))
                for (final (int index, String line)
                    in entity.readAsLinesSync().indexed)
                  if (_hostZone.hasMatch(line))
                    '${entity.path}:${index + 1}: ${line.trim()}',
      ];
      expect(
        leaks,
        isEmpty,
        reason:
            'Read wall-clock time through wallTime() in '
            'lib/src/wall_time.dart, and build instants with DateTime.utc, '
            'so no screen and no golden depends on the host zone.',
      );
    });
  });
}
