// Wall-clock time is read in one place, and the suite pins that place to US
// Central time, the zone the goldens were rendered in. So no golden and no
// test depends on the zone of the machine that runs it (coordinator ruling
// for S6, 2026-09-24, 23:11Z, after the host zone moved away from Central
// and six History goldens failed with no code change).

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/workbench/moments.dart';
import 'package:specimen_digitization/src/wall_time.dart';
import 'package:specimen_digitization/src/widgets/queue_row.dart';

import 'central_time.dart';

/// What the guard checks, line by line: converting to the host zone, asking
/// its name or offset, building an instant from the host's wall-clock
/// fields (`DateTime(`, `DateTime.new(`) or from an epoch without `isUtc`,
/// reading a wall-clock field of `DateTime.now()`, and touching the seam's
/// own override or host reader.
///
/// What it cannot see, because it reads one line at a time and knows no
/// types (#182 and #197 reviews):
/// - a `now` held in a variable and read later (`now.hour`), or a chained
///   read such as `DateTime.now().add(d).day`;
/// - `copyWith` on a local instant;
/// - `toString` or `toIso8601String` of a local instant, which prints the
///   host's wall clock;
/// - a tear-off, such as `.map(DateTime.new)` or `toLocal` passed uncalled;
/// - an expression split across lines, or a read through another package;
/// - a parse of text without a zone (the server's instants carry one);
/// - code outside the two roots.
/// It also rejects two correct UTC epoch calls: one split across lines,
/// whose `isUtc: true` sits on a later line, and one on one line whose
/// argument has parentheses, since the look-ahead stops at the first `)`.
final RegExp _hostZone = RegExp(
  r'\.toLocal\(\)|\.timeZoneName\b|\.timeZoneOffset\b|\bDateTime(\.new)?\('
  r'|from(Milli|Micro)secondsSinceEpoch\((?![^)]*isUtc:\s*true)'
  r'|DateTime\.now\(\)\.(year|month|day|hour|minute|second|millisecond'
  r'|microsecond|weekday)\b'
  r'|\bdebugWallTimeOverride\b|\bhostWallTime\b',
);

/// Where the guard looks. A root that goes missing fails the guard rather
/// than passing it by scanning nothing.
const List<String> _roots = <String>['lib', 'packages/specimen_ui/lib'];

/// The one file allowed to read the host zone, by its exact path.
const String _seam = 'lib/src/wall_time.dart';

void main() {
  group('the suite pins Central time', () {
    test('an instant prints in CDT on any machine', () {
      expect(
        absoluteTime(DateTime.utc(2026, 9, 13, 19, 32)),
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

    test('History cites an instant in CDT, which CI checks too', () {
      // Goldens compare on macOS only; this runs everywhere (#181 review).
      expect(citedInstant('2026-09-07T10:00:00Z'), '7 Sep 2026, 05:00 CDT');
    });
  });

  group("a browser's zone name reads as design/02 writes it", () {
    // A browser names the zone in full, "Central Daylight Time" (#181
    // review); 02 section 4.14 writes "CDT". Initials mislead outside
    // en-US (#182 review), so only names in a table are shortened.
    test('a US zone, UTC, GMT or BST is shortened as design/02 writes it', () {
      for (final (String name, String short) in <(String, String)>[
        ('Central Daylight Time', 'CDT'),
        ('Eastern Standard Time', 'EST'),
        ('Alaska Daylight Time', 'AKDT'),
        ('Hawaii-Aleutian Standard Time', 'HST'),
        ('Coordinated Universal Time', 'UTC'),
        ('Greenwich Mean Time', 'GMT'),
        ('British Summer Time', 'BST'),
      ]) {
        expect(zoneAbbreviation(name), short, reason: name);
      }
    });

    test('any other name is kept as given, never guessed from initials', () {
      for (final String name in <String>[
        // Initials would say CEST, Pakistan's would say PST.
        'Central European Standard Time',
        'Pakistan Standard Time',
        // A browser in Spanish.
        'hora de verano central',
        'CDT',
        'GMT+05:30',
      ]) {
        expect(zoneAbbreviation(name), name, reason: name);
      }
    });
  });

  group("a reviewer's day starts at their midnight (design/01 H2.1)", () {
    test('a day starts at midnight on the pinned clock', () {
      expect(wallDayStart(2026, 9, 8), DateTime.utc(2026, 9, 8, 5));
      expect(wallDayStart(2026, 1, 8), DateTime.utc(2026, 1, 8, 6));
    });

    test('the days daylight saving starts and ends begin at midnight', () {
      // The clocks change at 02:00, so both midnights keep the old offset.
      expect(wallDayStart(2026, 3, 8), DateTime.utc(2026, 3, 8, 6));
      expect(wallDayStart(2026, 11, 1), DateTime.utc(2026, 11, 1, 5));
    });

    test('a day whose midnight the clocks skip starts at the jump', () {
      // Havana, Santiago and the Azores go from 23:59 to 01:00 on their
      // daylight-saving day, so that day has no midnight (#197 review).
      // Here a synthetic zone at UTC-5 moves to UTC-4 at what would have
      // been 00:00 on 8 September.
      final DateTime jump = DateTime.utc(2026, 9, 8, 5);
      debugWallTimeOverride = skipsMidnightAt(jump);
      addTearDown(() => debugWallTimeOverride = centralWallTime);
      expect(wallDayStart(2026, 9, 8), jump);
      final WallTime wall = wallTime(wallDayStart(2026, 9, 8));
      expect(
        (wall.day, wall.hour),
        (8, 1),
        reason: "the day's first moment, never 23:00 on the 7th",
      );
    });

    test('the day start reads back as that day at midnight', () {
      final WallTime wall = wallTime(wallDayStart(2026, 9, 8));
      expect(
        (wall.year, wall.month, wall.day, wall.hour, wall.minute),
        (2026, 9, 8, 0, 0),
      );
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

    test('absoluteTime prints what the seam reads', () {
      debugWallTimeOverride = (DateTime _) =>
          (year: 2001, month: 2, day: 3, hour: 4, minute: 5, zone: 'ZZZ');
      expect(absoluteTime(DateTime.utc(2026)), '3 Feb 2001, 04:05 ZZZ');
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
        zone: zoneAbbreviation(local.timeZoneName),
      ));
    });

    test('nothing else in lib reads the host zone', () {
      for (final String root in _roots) {
        expect(Directory(root).existsSync(), isTrue, reason: '$root is gone');
      }
      final List<String> leaks = <String>[
        for (final String root in _roots)
          for (final FileSystemEntity entity in Directory(
            root,
          ).listSync(recursive: true))
            if (entity is File &&
                entity.path.endsWith('.dart') &&
                entity.path != _seam)
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
