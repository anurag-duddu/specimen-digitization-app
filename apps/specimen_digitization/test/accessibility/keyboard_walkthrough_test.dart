// The keyboard-only review, end to end (accessibility, section 4.2, "Keyboard
// only script, Chrome"; north star, "Speed of review"; pass criterion 7.1).
//
// One reviewer, one keyboard, no pointer: find a record in the queue, open it,
// move between the three evidence panels, jump to a label region, start an
// approval, back out of it, move to the next record, and return to the queue
// with the browser's own back button.
//
// Every step is one `sendKeyEvent`, and every assertion is about what is on
// screen afterwards, so a binding that exists but reaches nothing fails here
// rather than passing because the key was accepted.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/screens/queue/workbench_screen.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// A desktop browser window: the one the keyboard script is written for.
const Size keyboardWindow = Size(1180, 820);

/// The current location, as the address bar would show it.
String locationOf(WidgetTester tester) => GoRouter.of(
  tester.element(find.byType(Navigator).first),
).routerDelegate.currentConfiguration.uri.toString();

/// The browser's back button, as the platform delivers it.
Future<void> browserBack(WidgetTester tester) async {
  await tester.binding.defaultBinaryMessenger.handlePlatformMessage(
    'flutter/navigation',
    const JSONMethodCodec().encodeMethodCall(const MethodCall('popRoute')),
    (_) {},
  );
  await tester.pumpAndSettle();
}

/// Presses one key and settles.
Future<void> press(WidgetTester tester, LogicalKeyboardKey key) async {
  await tester.sendKeyEvent(key);
  await tester.pumpAndSettle();
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('a reviewer opens a record and works it without a pointer', (
    WidgetTester tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: keyboardWindow,
      brightness: Brightness.light,
      location: goldenQueueLocation,
      // A photograph whose display transform is known, so the label regions
      // are drawn and a digit can select one.
      repository: GoldenRepository.verified(),
    );
    expect(find.byType(QueuePane), findsOneWidget);

    // Slash puts the caret in the search field, and nothing else moves.
    await press(tester, LogicalKeyboardKey.slash);
    expect(
      FocusManager.instance.primaryFocus?.debugLabel,
      'Queue search',
      reason: 'slash focuses the queue search field',
    );

    // Tab leaves the field, which is how a reviewer gets the arrow keys back:
    // while the caret is in the search box the list deliberately ignores them.
    await press(tester, LogicalKeyboardKey.tab);
    expect(
      FocusManager.instance.primaryFocus?.debugLabel,
      isNot('Queue search'),
      reason: 'tab moves on from the search field',
    );

    // The arrow keys move the selection without opening anything.
    await press(tester, LogicalKeyboardKey.arrowDown);
    expect(locationOf(tester), endsWith('/queue'));
    final QueueRow selected = tester.widget<QueueRow>(
      find.byType(QueueRow).first,
    );
    expect(
      selected.selected,
      isTrue,
      reason: 'the arrow key moved the cursor onto the first row',
    );

    // Enter opens the selected record, and the record has its own address.
    await press(tester, LogicalKeyboardKey.enter);
    expect(find.byType(WorkbenchScreen), findsOneWidget);
    expect(locationOf(tester), endsWith('/queue/$goldenSpecimenId'));

    // F, H and R move between the three evidence panels.
    await press(tester, LogicalKeyboardKey.keyF);
    expect(find.text('Record fields'), findsOneWidget);
    await press(tester, LogicalKeyboardKey.keyH);
    expect(find.text('Current decision history'), findsOneWidget);
    await press(tester, LogicalKeyboardKey.keyR);
    expect(find.text('Record fields'), findsNothing);

    // 1 selects the first label region, on the photograph and in the strip.
    await press(tester, LogicalKeyboardKey.digit1);
    final Iterable<RegionOverlay> overlays = tester.widgetList<RegionOverlay>(
      find.byType(RegionOverlay),
    );
    expect(overlays, isNotEmpty, reason: 'the regions are drawn at all');
    expect(
      overlays.where((RegionOverlay o) => o.selected).length,
      1,
      reason: 'exactly one region is current after pressing 1',
    );

    // A starts the approval, with its reason field and its consequences.
    await press(tester, LogicalKeyboardKey.keyA);
    expect(find.byType(ReasonForm), findsOneWidget);
    expect(uiField('Reason'), findsOneWidget);

    // Escape backs out of it. Nothing was typed, so nothing is lost and the
    // sheet closes without asking.
    await press(tester, LogicalKeyboardKey.escape);
    expect(find.byType(ReasonForm), findsNothing);
    expect(find.byType(WorkbenchScreen), findsOneWidget);

    // The browser's back button returns to the queue rather than leaving the
    // app (pass criterion 3.1).
    await browserBack(tester);
    expect(find.byType(WorkbenchScreen), findsNothing);
    expect(find.byType(QueuePane), findsOneWidget);
    expect(locationOf(tester), endsWith('/queue'));

    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('J and K move to the next and the previous record', (
    WidgetTester tester,
  ) async {
    // Finding V-2. The keys were bound, listed in the help sheet, and wired
    // to a callback the record screen never supplied, so a reviewer who read
    // the shortcut list and pressed J got nothing. They move along the loaded
    // queue now, and the decision bar's own controls do the same thing.
    await pumpGoldenApp(
      tester,
      window: keyboardWindow,
      brightness: Brightness.light,
      location: goldenSpecimenLocation,
      repository: GoldenQueueRepository(goldenQueue(3)),
    );
    expect(find.byType(WorkbenchScreen), findsOneWidget);
    final String opened = locationOf(tester);
    expect(opened, endsWith('/fixture-001'));

    await press(tester, LogicalKeyboardKey.keyJ);
    expect(
      locationOf(tester),
      endsWith('/fixture-002'),
      reason: 'J opens the next record in the queue',
    );

    await press(tester, LogicalKeyboardKey.keyK);
    expect(
      locationOf(tester),
      opened,
      reason: 'K returns to the record it came from',
    );

    // The queue does not wrap. At the head the previous control is drawn
    // disabled with the reason on its hint and its tooltip, so the end of the
    // queue says why rather than moving nowhere (13 section 3.3, polish 3;
    // pass criterion 5.6, finding V-2).
    final UiIconButton previous = tester.widget<UiIconButton>(
      uiIconButton('Previous specimen'),
    );
    expect(previous.onPressed, isNull);
    expect(previous.disabledReason, 'This is the first record in the queue.');
    await press(tester, LogicalKeyboardKey.keyK);
    expect(locationOf(tester), opened, reason: 'K at the head wraps nowhere');

    // The reviewer's position is on the decision bar (pass criterion 6.5).
    expect(find.text('1 of 3'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the decision bar moves between records without the keyboard', (
    WidgetTester tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: keyboardWindow,
      brightness: Brightness.light,
      location: goldenSpecimenLocation,
      repository: GoldenQueueRepository(goldenQueue(3)),
    );
    await tester.tap(uiIconButton('Next specimen'));
    await tester.pumpAndSettle();
    expect(locationOf(tester), endsWith('/fixture-002'));
    expect(find.text('2 of 3'), findsOneWidget);

    await tester.tap(uiIconButton('Previous specimen'));
    await tester.pumpAndSettle();
    expect(locationOf(tester), endsWith('/fixture-001'));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the shortcut list is one key away and names every binding', (
    WidgetTester tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: keyboardWindow,
      brightness: Brightness.light,
      location: goldenSpecimenLocation,
    );
    await tester.sendKeyDownEvent(LogicalKeyboardKey.shift);
    await press(tester, LogicalKeyboardKey.slash);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.shift);
    await tester.pumpAndSettle();
    expect(find.text('Keyboard shortcuts'), findsOneWidget);
    // The bindings a reviewer needs to move without a pointer are all listed.
    for (final String action in <String>[
      'Next specimen',
      'Previous specimen',
      'Select label region',
      'Readings',
      'Fields',
      'History',
      'Approve record',
    ]) {
      // `findsWidgets` rather than one: the record behind the sheet carries
      // the same three words on its own evidence selector.
      expect(find.text(action), findsWidgets, reason: '$action is listed');
    }
    await press(tester, LogicalKeyboardKey.escape);
    expect(find.text('Keyboard shortcuts'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
}
