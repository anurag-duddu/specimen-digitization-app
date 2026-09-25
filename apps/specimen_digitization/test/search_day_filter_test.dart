// A typed day is the reviewer's own day (coordinator ruling for S6,
// 2026-09-25, applying design/01 H2.1: "display local dates, and convert to
// UTC in the request"). Its midnight on the reviewer's clock goes to the API
// in UTC, and the queue's chip shows it back as a day. The suite's clock is
// pinned to US Central time (`flutter_test_config.dart`).

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/search_filters.dart';
import 'package:specimen_digitization/src/wall_time.dart';

import 'central_time.dart';
import 'widgets/harness.dart';

void main() {
  test("a typed day starts at the reviewer's midnight, in UTC on the wire", () {
    expect(typedDayStart('2026-09-08'), DateTime.utc(2026, 9, 8, 5));
    expect(typedDayStart('2026-01-08'), DateTime.utc(2026, 1, 8, 6));
  });

  test('a record at 23:30 on the 7th is outside "on or after the 8th"', () {
    final DateTime bound = typedDayStart('2026-09-08')!;
    // 23:30 CDT on 7 September, and 00:30 CDT on the 8th.
    final DateTime lateOnThe7th = DateTime.utc(2026, 9, 8, 4, 30);
    final DateTime earlyOnThe8th = DateTime.utc(2026, 9, 8, 5, 30);
    expect(lateOnThe7th.isBefore(bound), isTrue);
    expect(earlyOnThe8th.isBefore(bound), isFalse);
  });

  test('what is not a day is no day', () {
    for (final String typed in <String>['2026-02-30', '8 Sep', '2026-9-8']) {
      expect(typedDayStart(typed), isNull, reason: typed);
    }
  });

  test('a stored bound reads back as the day that was typed', () {
    expect(
      typedDayOf(typedDayStart('2026-09-08')!.toIso8601String()),
      '2026-09-08',
    );
    expect(typedDayOf(null), '');
  });

  test('a stored bound shows on its chip as a day, never as an instant', () {
    final String stored = typedDayStart('2026-09-08')!.toIso8601String();
    expect(searchValueLabel('created_from', stored), '8 Sep 2026');
    expect(searchValueLabel('created_before', stored), '8 Sep 2026');
    expect(searchValueLabel('batch_id', 'batch-7'), 'batch-7');
  });

  test('a day whose midnight the clocks skip still reads as that day', () {
    // Where the clocks jump over midnight (Havana, Santiago, the Azores),
    // the stored bound is the jump, and it reads back and shows as the day
    // that was typed, never the day before (#202 review).
    final DateTime jump = DateTime.utc(2026, 9, 8, 5);
    debugWallTimeOverride = skipsMidnightAt(jump);
    addTearDown(() => debugWallTimeOverride = centralWallTime);
    final String stored = typedDayStart('2026-09-08')!.toIso8601String();
    expect(stored, jump.toIso8601String());
    expect(typedDayOf(stored), '2026-09-08');
    expect(searchValueLabel('created_from', stored), '8 Sep 2026');
  });

  testWidgets('the sheet sends the typed day as its midnight', (
    WidgetTester tester,
  ) async {
    final GlobalKey<SearchFiltersState> form = GlobalKey<SearchFiltersState>();
    await pumpComponent(
      tester,
      SingleChildScrollView(
        child: SearchFilters(key: form, initial: const <String, String>{}),
      ),
      size: const Size(800, 3000),
    );
    await tester.enterText(
      find.descendant(
        of: find.widgetWithText(UiField, 'Created on or after'),
        matching: find.byType(EditableText),
      ),
      '2026-09-08',
    );
    await tester.pump();
    expect(
      form.currentState!.submit()!['created_from'],
      DateTime.utc(2026, 9, 8, 5).toIso8601String(),
    );
  });
}
