import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets(
    'calendar preserves incoming civil fields and returns UTC days across DST',
    (WidgetTester tester) async {
      // Local inputs deliberately carry a late time. Converting these instants
      // to UTC first can shift the civil day; normalizing y/m/d must not.
      // Execute this regression under both positive and negative TZ offsets.
      for (final (int month, int day) in <(int, int)>[(3, 7), (10, 31)]) {
        DateTime? selected = DateTime(2026, month, day, 23, 45);
        final DateTime first = DateTime(2026, month, day, 8, 30);
        final DateTime last = DateTime(2026, month, day + 2, 21, 15);
        await tester.pumpWidget(
          uiHarness(
            child: StatefulBuilder(
              builder: (BuildContext context, StateSetter setState) => SizedBox(
                width: 640,
                child: UiDatePicker(
                  key: ValueKey<int>(month),
                  label: 'Civil date',
                  value: selected,
                  firstDate: first,
                  lastDate: last,
                  dateLabelBuilder: (DateTime date) =>
                      '${date.year}-${date.month}-${date.day}',
                  onChanged: (DateTime date) => setState(() => selected = date),
                ),
              ),
            ),
          ),
        );
        await tester.tap(find.bySemanticsLabel('2026-$month-$day'));
        await tester.pump();
        expect(selected, DateTime.utc(2026, month, day));
        for (int step = 1; step <= 2; step++) {
          await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
          await tester.pump();
          await tester.sendKeyEvent(LogicalKeyboardKey.enter);
          await tester.pump();
          expect(selected, DateTime.utc(2026, month, day + step));
          expect(selected!.isUtc, isTrue);
          expect(
            selected!.difference(DateTime.utc(2026, month, day)).inHours,
            step * 24,
          );
        }
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
        await tester.pump();
        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pump();
        expect(
          selected,
          DateTime.utc(2026, month, day + 2),
          reason: 'Inclusive civil upper bound',
        );
        await tester.pumpWidget(const SizedBox());
      }
    },
  );

  testWidgets(
    'calendar month stepping retains civil days around leap February',
    (WidgetTester tester) async {
      DateTime? selected = DateTime.utc(2028, 1, 31, 18);
      await tester.pumpWidget(
        uiHarness(
          child: StatefulBuilder(
            builder: (BuildContext context, StateSetter setState) => SizedBox(
              width: 640,
              child: UiDatePicker(
                label: 'Civil date',
                value: selected,
                firstDate: DateTime.utc(2028, 1, 1, 23),
                lastDate: DateTime.utc(2028, 3, 31, 2),
                onChanged: (DateTime date) => setState(() => selected = date),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.bySemanticsLabel('31 January 2028'));
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.pageDown);
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(selected, DateTime.utc(2028, 2, 29));
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(selected, DateTime.utc(2028, 3, 1));
    },
  );

  testWidgets('controlled compact date changes reveal the selected day', (
    tester,
  ) async {
    Widget calendar(int day) => uiHarness(
      child: SizedBox(
        width: 320,
        child: UiDatePicker(
          label: 'Date',
          value: DateTime.utc(2026, 10, day),
          firstDate: DateTime.utc(2026, 10),
          lastDate: DateTime.utc(2026, 10, 31),
          onChanged: (_) {},
        ),
      ),
    );
    await tester.pumpWidget(calendar(1));
    await tester.pump();
    await tester.pumpWidget(calendar(31));
    await tester.pump();
    final viewport = tester.getRect(find.byType(SingleChildScrollView));
    expect(
      viewport.contains(
        tester.getCenter(find.bySemanticsLabel('31 October 2026')),
      ),
      isTrue,
    );
  });

  testWidgets(
    'selected dates retain readable contrast in every interaction state',
    (tester) async {
      double contrast(Color a, Color b) {
        final first = a.computeLuminance();
        final second = b.computeLuminance();
        return (first > second ? first + .05 : second + .05) /
            (first > second ? second + .05 : first + .05);
      }

      for (final mode in Brightness.values) {
        for (final enabled in [false, true]) {
          await tester.pumpWidget(
            uiHarness(
              brightness: mode,
              child: SizedBox(
                width: 640,
                child: UiDatePicker(
                  label: 'Date',
                  value: DateTime.utc(2026, 10, 22),
                  firstDate: DateTime.utc(2026, 10),
                  lastDate: DateTime.utc(2026, 10, 31),
                  onChanged: enabled ? (_) {} : null,
                ),
              ),
            ),
          );
          final selected = find.bySemanticsLabel('22 October 2026');
          final text = tester.widget<Text>(
            find.descendant(of: selected, matching: find.text('22')),
          );
          final fill = tester
              .widgetList<Container>(
                find.descendant(of: selected, matching: find.byType(Container)),
              )
              .map((widget) => widget.decoration)
              .whereType<BoxDecoration>()
              .firstWhere((decoration) => decoration.color != null)
              .color!;
          final ui = mode == Brightness.dark
              ? UiThemeData.dark()
              : UiThemeData.light();
          for (final opacity in [
            0.0,
            ui.color.hoverOpacity,
            ui.color.pressedOpacity,
          ]) {
            // Pressable's overlay covers both the fill and the glyph.
            final layer = ui.brand.secondary.onFill.withValues(
              alpha: enabled ? opacity : 0,
            );
            expect(
              contrast(
                Color.alphaBlend(layer, text.style!.color!),
                Color.alphaBlend(layer, fill),
              ),
              greaterThanOrEqualTo(4.5),
              reason: '$mode enabled=$enabled opacity=$opacity',
            );
          }
        }
      }
    },
  );

  testWidgets('slider pointer drag commits once and follows RTL', (
    WidgetTester tester,
  ) async {
    for (final TextDirection direction in TextDirection.values) {
      double value = 50;
      int commits = 0;
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          child: StatefulBuilder(
            builder: (BuildContext context, StateSetter setState) => SizedBox(
              width: 320,
              child: UiSlider(
                label: 'Zoom',
                value: value,
                min: 0,
                max: 100,
                divisions: 10,
                onChanged: (double next) => setState(() => value = next),
                onChangeEnd: (_) => commits++,
              ),
            ),
          ),
        ),
      );
      final Finder target = find.descendant(
        of: find.byType(UiSlider),
        matching: find.byType(GestureDetector),
      );
      await tester.drag(target, const Offset(150, 0));
      await tester.pump();
      expect(value, direction == TextDirection.ltr ? 100 : 0);
      expect(commits, 1);
    }
  });

  testWidgets(
    'compact calendar reveals selected date and disabled dates never activate',
    (WidgetTester tester) async {
      int changes = 0;
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 320,
            child: UiDatePicker(
              label: 'Date',
              value: DateTime.utc(2026, 10, 22),
              firstDate: DateTime.utc(2026, 10),
              lastDate: DateTime.utc(2026, 10, 31),
              onChanged: (_) => changes++,
            ),
          ),
        ),
      );
      await tester.pump();
      final Finder selected = find.bySemanticsLabel('22 October 2026');
      final Rect viewport = tester.getRect(find.byType(SingleChildScrollView));
      expect(viewport.contains(tester.getCenter(selected)), isTrue);
      await tester.tap(selected);
      expect(changes, 1);
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 320,
            child: UiDatePicker(
              label: 'Date',
              value: DateTime.utc(2026, 10, 22),
              firstDate: DateTime.utc(2026, 10),
              lastDate: DateTime.utc(2026, 10, 31),
              disabledReason: 'Date editing is locked.',
            ),
          ),
        ),
      );
      await tester.tap(selected);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      expect(changes, 1);
      expect(find.text('Date editing is locked.'), findsOneWidget);
    },
  );

  testWidgets('date picker fits phone tablet desktop at double text scale', (
    WidgetTester tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    for (final double width in <double>[390, 768, 1180, 1440]) {
      tester.view.physicalSize = Size(width, 1200);
      await tester.pumpWidget(
        uiHarness(
          size: Size(width, 1200),
          textDirection: TextDirection.rtl,
          textScaler: const TextScaler.linear(2),
          child: SingleChildScrollView(
            child: UiDatePicker(
              label: 'A long acquisition date field label',
              value: DateTime.utc(2026, 10, 22),
              firstDate: DateTime.utc(2026, 9, 15),
              lastDate: DateTime.utc(2026, 12, 15),
              onChanged: (_) {},
            ),
          ),
        ),
      );
      await tester.pump();
      expect(tester.takeException(), isNull, reason: 'width $width');
    }
  });

  testWidgets('file chooser satisfies the shared control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiFileUpload(
        label: 'Photographs',
        files: const <UiUploadFile>[],
        onChooseFiles: () {},
      ),
      semanticsLabel: 'Choose files',
    );
  });

  testWidgets('slider keyboard steps, RTL and bounds stay controlled', (
    WidgetTester tester,
  ) async {
    final FocusNode focus = FocusNode();
    addTearDown(focus.dispose);
    double value = 50;
    final List<double> commits = <double>[];
    for (final TextDirection direction in TextDirection.values) {
      value = 50;
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          child: StatefulBuilder(
            builder: (BuildContext context, StateSetter setState) => SizedBox(
              width: 320,
              child: UiSlider(
                label: 'Zoom',
                value: value,
                min: 0,
                max: 100,
                divisions: 10,
                focusNode: focus,
                onChanged: (double next) => setState(() => value = next),
                onChangeEnd: commits.add,
              ),
            ),
          ),
        ),
      );
      focus.requestFocus();
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pump();
      expect(value, direction == TextDirection.ltr ? 60 : 40);
      await tester.sendKeyEvent(LogicalKeyboardKey.end);
      await tester.pump();
      expect(value, 100);
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump();
      expect(value, 100);
      await tester.sendKeyEvent(LogicalKeyboardKey.home);
      await tester.pump();
      expect(value, 0);
    }
    expect(commits, containsAll(<double>[60, 40, 100, 0]));
  });

  testWidgets('slider exposes semantic adjustment and disabled state', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    double? proposed;
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 300,
          child: UiSlider(
            label: 'Threshold',
            value: .5,
            divisions: 10,
            onChanged: (double value) => proposed = value,
          ),
        ),
      ),
    );
    final SemanticsNode node = tester.getSemantics(
      find.bySemanticsLabel('Threshold').last,
    );
    expect(node.getSemanticsData().hasAction(SemanticsAction.increase), isTrue);
    node.owner!.performAction(node.id, SemanticsAction.increase);
    expect(proposed, closeTo(.6, .001));
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 300,
          child: UiSlider(
            label: 'Threshold',
            value: .5,
            disabledReason: 'Locked',
            errorText: 'Choose an allowed value.',
          ),
        ),
      ),
    );
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Threshold').last)
          .getSemanticsData()
          .hasAction(SemanticsAction.increase),
      isFalse,
    );
    expect(find.text('Choose an allowed value.'), findsOneWidget);
    handle.dispose();
  });

  testWidgets(
    'date picker honors inclusive bounds and keyboard month rollover',
    (WidgetTester tester) async {
      DateTime? selected = DateTime.utc(2026, 10, 31);
      await tester.pumpWidget(
        uiHarness(
          child: StatefulBuilder(
            builder: (BuildContext context, StateSetter setState) => SizedBox(
              width: 480,
              child: UiDatePicker(
                label: 'Acquired',
                value: selected,
                firstDate: DateTime.utc(2026, 10, 30),
                lastDate: DateTime.utc(2026, 11, 2),
                onChanged: (DateTime value) => setState(() => selected = value),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.bySemanticsLabel('31 October 2026'));
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(selected, DateTime.utc(2026, 11, 1));
      await tester.sendKeyEvent(LogicalKeyboardKey.pageDown);
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(selected, DateTime.utc(2026, 11, 2));
      await tester.tap(find.bySemanticsLabel('3 November 2026'));
      await tester.pump();
      expect(selected, DateTime.utc(2026, 11, 2));
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('file actions are controlled and busy chooser cannot reopen', (
    WidgetTester tester,
  ) async {
    int choices = 0;
    UiUploadFile? retried;
    UiUploadFile? removed;
    const UiUploadFile failed = UiUploadFile(
      id: 'failed',
      name: 'photo.jpg',
      statusLabel: 'Failed',
      status: UiFileUploadStatus.error,
      errorText: 'Try the connection again.',
    );
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiFileUpload(
            label: 'Photos',
            files: const <UiUploadFile>[failed],
            onChooseFiles: () => choices++,
            onRetry: (UiUploadFile file) => retried = file,
            onRemove: (UiUploadFile file) => removed = file,
          ),
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Retry photo.jpg'));
    await tester.tap(find.bySemanticsLabel('Remove photo.jpg'));
    expect(retried, same(failed));
    expect(removed, same(failed));
    expect(find.text('photo.jpg'), findsOneWidget);
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiFileUpload(
            label: 'Photos',
            files: const <UiUploadFile>[],
            isChoosing: true,
            onChooseFiles: () => choices++,
          ),
        ),
      ),
    );
    await tester.tap(find.byType(UiButton));
    expect(choices, 0);
  });

  testWidgets('command filtering, disabled skips, activation and Escape', (
    WidgetTester tester,
  ) async {
    String? selected;
    int dismissed = 0;
    final TextEditingController query = TextEditingController();
    addTearDown(query.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 320,
          child: UiCommandMenu(
            searchController: query,
            onDismiss: () => dismissed++,
            commands: <UiCommand>[
              const UiCommand(
                id: 'disabled',
                label: 'Unavailable command',
                disabledReason: 'Select a record.',
              ),
              UiCommand(
                id: 'one',
                label: 'Open queue',
                group: 'Navigate',
                onSelected: () => selected = 'one',
              ),
              UiCommand(
                id: 'two',
                label: 'Keyboard help',
                group: 'Help',
                keywords: const <String>['shortcuts'],
                onSelected: () => selected = 'two',
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(selected, 'one');
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    expect(selected, 'two');
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    expect(dismissed, 1);
    query.text = 'shortcuts';
    await tester.pump();
    expect(find.text('Keyboard help'), findsOneWidget);
    expect(find.text('Open queue'), findsNothing);
    query.text = 'no matching term';
    await tester.pump();
    expect(find.text('No matching commands'), findsOneWidget);
  });

  testWidgets('advanced controls fit 320px, 200% text, both modes and RTL', (
    WidgetTester tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 1000);
    addTearDown(tester.view.reset);
    for (final Brightness brightness in Brightness.values) {
      for (final TextDirection direction in TextDirection.values) {
        final List<Widget> controls = <Widget>[
          UiSlider(
            label: 'Magnification for the specimen photograph',
            value: .5,
            onChanged: (_) {},
            errorText: 'Choose an allowed value.',
          ),
          UiDatePicker(
            label: 'Acquisition date',
            value: DateTime.utc(2026, 10, 22),
            firstDate: DateTime.utc(2026, 10),
            lastDate: DateTime.utc(2026, 11),
            onChanged: (_) {},
          ),
          const UiFileUpload(
            label: 'Specimen photographs',
            files: <UiUploadFile>[
              UiUploadFile(
                id: 'file',
                name: 'Long specimen photograph filename.jpg',
                statusLabel: 'Failed',
                status: UiFileUploadStatus.error,
                errorText: 'The connection was interrupted.',
              ),
            ],
            enabled: false,
            disabledReason: 'Sign in to add photographs.',
          ),
          UiCommandMenu(
            autofocus: false,
            onDismiss: () {},
            commands: <UiCommand>[
              UiCommand(
                id: 'one',
                label: 'Open the specimen review queue',
                description: 'Review specimens that need your attention.',
                onSelected: () {},
              ),
            ],
          ),
        ];
        for (final Widget control in controls) {
          await tester.pumpWidget(
            uiHarness(
              brightness: brightness,
              textDirection: direction,
              textScaler: const TextScaler.linear(2),
              size: const Size(320, 1000),
              child: SingleChildScrollView(child: control),
            ),
          );
          await tester.pump();
          expect(
            tester.takeException(),
            isNull,
            reason: '${control.runtimeType}: $brightness $direction',
          );
        }
      }
    }
  });
}
