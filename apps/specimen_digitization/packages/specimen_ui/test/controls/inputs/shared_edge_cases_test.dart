import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets('tooltip keyboard reveal and Escape preserve the control focus', (
    tester,
  ) async {
    final focus = FocusNode();
    addTearDown(focus.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: UiTooltip(
          message: 'Record identifier',
          supportingText: 'Use the number on the label.',
          child: UiActionButton(
            label: 'Identifier help',
            focusNode: focus,
            onPressed: () {},
          ),
        ),
      ),
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    expect(find.text('Use the number on the label.'), findsOneWidget);
    expect(focus.hasFocus, isTrue);
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.text('Use the number on the label.'), findsNothing);
    expect(focus.hasFocus, isTrue);
  });

  testWidgets(
    'verification keeps cells coherent after middle deletion and host reset',
    (tester) async {
      String value = '123456';
      final completed = <String>[];
      late StateSetter update;
      await tester.pumpWidget(
        uiHarness(
          child: StatefulBuilder(
            builder: (_, setState) {
              update = setState;
              return UiVerificationCode(
                label: 'Code',
                value: value,
                onChanged: (next) => setState(() => value = next),
                onCompleted: completed.add,
              );
            },
          ),
        ),
      );
      await tester.enterText(find.byType(EditableText).at(2), '');
      await tester.pump();
      expect(value, '12456');
      expect(
        tester
            .widgetList<EditableText>(find.byType(EditableText))
            .map((e) => e.controller.text)
            .toList(),
        ['1', '2', '4', '5', '6', ''],
      );
      update(() => value = '');
      await tester.pump();
      await tester.enterText(find.byType(EditableText).first, '123456');
      await tester.pump();
      expect(completed, ['123456']);
      update(() => value = '');
      await tester.pump();
      await tester.enterText(find.byType(EditableText).first, '123456');
      await tester.pump();
      expect(completed, ['123456', '123456']);
    },
  );

  testWidgets(
    'calendar distinguishes host-reported today and activity from selection',
    (tester) async {
      await tester.pumpWidget(
        uiHarness(
          size: const Size(800, 900),
          child: UiDatePicker(
            label: 'Calendar',
            value: DateTime.utc(2026, 10, 12),
            firstDate: DateTime.utc(2026, 10, 1),
            lastDate: DateTime.utc(2026, 10, 31),
            currentDate: DateTime.utc(2026, 10, 22),
            markedDates: {DateTime.utc(2026, 10, 22)},
            onChanged: (_) {},
          ),
        ),
      );
      expect(
        find.bySemanticsLabel('22 October 2026, today, activity available'),
        findsOneWidget,
      );
      expect(find.bySemanticsLabel('12 October 2026'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('closable badge exposes an independent named action', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    var removed = false;
    await tester.pumpWidget(
      uiHarness(
        child: UiStatusBadge(
          label: 'Featured',
          leading: const UiIcon(UiIcons.check),
          onRemove: () => removed = true,
        ),
      ),
    );
    expect(find.bySemanticsLabel('Featured'), findsOneWidget);
    final remove = find.bySemanticsLabel('Remove Featured');
    expect(remove, findsOneWidget);
    await tester.tap(remove);
    expect(removed, isTrue);
    semantics.dispose();
  });

  testWidgets(
    'typed date endpoints validate actual calendar dates, order and bounds before Apply',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(800, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final received = <UiDateRange>[];
      await tester.pumpWidget(
        uiHarness(
          size: const Size(800, 1200),
          child: SingleChildScrollView(
            child: UiDateRangePicker(
              label: 'Range',
              value: null,
              firstDate: DateTime.utc(2028, 2, 1),
              lastDate: DateTime.utc(2028, 3, 31),
              showActions: true,
              onChanged: received.add,
            ),
          ),
        ),
      );
      await tester.enterText(find.byType(EditableText).first, '2028-02-30');
      await tester.enterText(find.byType(EditableText).last, '2028-03-03');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pump();
      expect(
        find.text('Enter a valid date in YYYY-MM-DD format.'),
        findsOneWidget,
      );
      expect(received, isEmpty);
      expect(
        tester
            .widget<UiButton>(find.widgetWithText(UiButton, 'Apply dates'))
            .onPressed,
        isNull,
      );
      await tester.enterText(find.byType(EditableText).first, '2028-03-10');
      await tester.pump();
      expect(
        find.text('The end date must be on or after the start date.'),
        findsOneWidget,
      );
      await tester.enterText(find.byType(EditableText).last, '2028-04-01');
      await tester.pump();
      expect(
        find.text('Choose a date from 2028-02-01 to 2028-03-31.'),
        findsOneWidget,
      );
      await tester.enterText(find.byType(EditableText).first, '2028-02-29');
      await tester.enterText(find.byType(EditableText).last, '2028-03-03');
      await tester.pump();
      expect(received, isEmpty);
      await tester.ensureVisible(find.text('Apply dates'));
      await tester.tap(find.text('Apply dates'));
      expect(received, [
        UiDateRange(DateTime.utc(2028, 2, 29), DateTime.utc(2028, 3, 3)),
      ]);
    },
  );

  testWidgets('calendar and cancel synchronize the typed endpoint draft', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(800, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final accepted = UiDateRange(
      DateTime.utc(2026, 10, 2),
      DateTime.utc(2026, 10, 4),
    );
    await tester.pumpWidget(
      uiHarness(
        size: const Size(800, 1200),
        child: SingleChildScrollView(
          child: UiDateRangePicker(
            label: 'Dates',
            value: accepted,
            firstDate: DateTime.utc(2026, 10, 1),
            lastDate: DateTime.utc(2026, 10, 31),
            showActions: true,
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('10 October 2026'));
    await tester.pump();
    expect(
      tester
          .widget<EditableText>(find.byType(EditableText).first)
          .controller
          .text,
      '2026-10-10',
    );
    expect(
      tester
          .widget<EditableText>(find.byType(EditableText).last)
          .controller
          .text,
      '',
    );
    await tester.tap(find.bySemanticsLabel('15 October 2026'));
    await tester.pump();
    expect(
      tester
          .widget<EditableText>(find.byType(EditableText).last)
          .controller
          .text,
      '2026-10-15',
    );
    await tester.ensureVisible(find.text('Cancel'));
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    expect(
      tester
          .widget<EditableText>(find.byType(EditableText).first)
          .controller
          .text,
      '2026-10-02',
    );
    expect(
      tester
          .widget<EditableText>(find.byType(EditableText).last)
          .controller
          .text,
      '2026-10-04',
    );
  });

  testWidgets(
    'immediate typed dates issue one proposal, not another on submit',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(800, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final received = <UiDateRange>[];
      await tester.pumpWidget(
        uiHarness(
          size: const Size(800, 1200),
          child: SingleChildScrollView(
            child: UiDateRangePicker(
              label: 'Dates',
              value: null,
              firstDate: DateTime.utc(2026, 10, 1),
              lastDate: DateTime.utc(2026, 10, 31),
              onChanged: received.add,
            ),
          ),
        ),
      );
      await tester.enterText(find.byType(EditableText).first, '2026-10-10');
      await tester.enterText(find.byType(EditableText).last, '2026-10-20');
      await tester.pump();
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pump();
      expect(received, [
        UiDateRange(DateTime.utc(2026, 10, 10), DateTime.utc(2026, 10, 20)),
      ]);
    },
  );

  testWidgets(
    'adaptive date field commits typed endpoints at narrow 200 percent text',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(320, 800));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      UiDateRange? accepted;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 800),
          textDirection: TextDirection.rtl,
          textScaler: const TextScaler.linear(2),
          child: StatefulBuilder(
            builder: (_, setState) => UiDateRangeField(
              label: 'Collected dates',
              value: accepted,
              firstDate: DateTime.utc(2026, 10, 1),
              lastDate: DateTime.utc(2026, 10, 31),
              onChanged: (value) => setState(() => accepted = value),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Collected dates'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(EditableText).first, '2026-10-10');
      await tester.enterText(find.byType(EditableText).last, '2026-10-20');
      await tester.pump();
      await tester.ensureVisible(find.text('Apply dates'));
      await tester.tap(find.text('Apply dates'));
      await tester.pumpAndSettle();
      expect(
        accepted,
        UiDateRange(DateTime.utc(2026, 10, 10), DateTime.utc(2026, 10, 20)),
      );
      expect(find.byType(EditableText), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'provider and store actions preserve names, target and unavailable behavior',
    (tester) async {
      final semantics = tester.ensureSemantics();
      var calls = 0;
      await tester.pumpWidget(
        uiHarness(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              UiProviderButton(
                label: 'Continue with institution',
                mark: const Text('I'),
                iconOnly: true,
                onPressed: () => calls++,
              ),
              const UiStoreBadge(
                storeName: 'Museum store',
                caption: 'Download',
                mark: Text('M'),
                disabledReason: 'Not available on this platform.',
              ),
            ],
          ),
        ),
      );
      final provider = find.bySemanticsLabel('Continue with institution');
      expect(tester.getSize(provider).height, greaterThanOrEqualTo(48));
      await tester.tap(provider);
      expect(calls, 1);
      await tester.tap(find.byType(UiStoreBadge));
      expect(calls, 1);
      semantics.dispose();
    },
  );

  for (final position in UiRangeLabelPosition.values) {
    testWidgets(
      'range labels ${position.name} fit coincident limits at 320 RTL 200 percent text',
      (tester) async {
        await tester.binding.setSurfaceSize(const Size(320, 600));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        await tester.pumpWidget(
          uiHarness(
            size: const Size(320, 600),
            textDirection: TextDirection.rtl,
            textScaler: const TextScaler.linear(2),
            child: UiRangeSlider(
              label: 'Range',
              min: 0,
              max: 100,
              values: const UiRangeValues(100, 100),
              labelPosition: position,
              valueLabel: (value) => '${value.round()}%',
              onChanged: (_) {},
            ),
          ),
        );
        expect(tester.takeException(), isNull);
        if (position == UiRangeLabelPosition.floating ||
            position == UiRangeLabelPosition.floatingBelow) {
          expect(find.text('100% to 100%'), findsOneWidget);
        }
      },
    );
  }

  testWidgets(
    'combobox becoming unavailable closes the open overlay and blocks selection',
    (tester) async {
      var enabled = true;
      var changes = 0;
      late StateSetter update;
      await tester.pumpWidget(
        uiHarness(
          child: StatefulBuilder(
            builder: (_, setState) {
              update = setState;
              return UiCombobox<int>(
                label: 'Collector',
                options: const [UiComboboxOption(value: 1, label: 'Avery')],
                selected: const {},
                onChanged: enabled ? (_) => changes++ : null,
              );
            },
          ),
        ),
      );
      await tester.tap(find.bySemanticsLabel('Collector'));
      await tester.pumpAndSettle();
      expect(find.byType(EditableText), findsOneWidget);
      update(() => enabled = false);
      await tester.pumpAndSettle();
      expect(find.byType(EditableText), findsNothing);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      expect(changes, 0);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'a disabled combobox option cannot be chosen with pointer or arrows',
    (tester) async {
      final results = <Set<int>>[];
      await tester.pumpWidget(
        uiHarness(
          child: UiCombobox<int>(
            label: 'Collector',
            selected: const {},
            options: const [
              UiComboboxOption(
                value: 1,
                label: 'Archived',
                enabled: false,
                disabledReason: 'Archived account.',
              ),
              UiComboboxOption(value: 2, label: 'Available'),
            ],
            onChanged: results.add,
          ),
        ),
      );
      await tester.tap(find.bySemanticsLabel('Collector'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Archived'));
      await tester.pump();
      expect(results, isEmpty);
      await tester.tap(find.byType(EditableText));
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(results, [
        {2},
      ]);
    },
  );

  testWidgets('date cancel restores accepted range without invoking change', (
    tester,
  ) async {
    final accepted = UiDateRange(
      DateTime.utc(2026, 10, 2),
      DateTime.utc(2026, 10, 4),
    );
    var changes = 0;
    var cancellations = 0;
    await tester.pumpWidget(
      uiHarness(
        size: const Size(800, 1000),
        child: SingleChildScrollView(
          child: UiDateRangePicker(
            label: 'Dates',
            value: accepted,
            firstDate: DateTime.utc(2026, 10, 1),
            lastDate: DateTime.utc(2026, 10, 31),
            showActions: true,
            onChanged: (_) => changes++,
            onCancel: () => cancellations++,
          ),
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('10 October 2026'));
    await tester.pump();
    await tester.ensureVisible(find.text('Cancel'));
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    expect(find.text('2026-10-02 to 2026-10-04'), findsOneWidget);
    expect(changes, 0);
    expect(cancellations, 1);
  });

  testWidgets('tag checkbox and remove actions are independent', (
    tester,
  ) async {
    var selected = false;
    var removed = 0;
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (_, setState) => UiTag(
            label: 'Collection',
            count: 8,
            selected: selected,
            onSelected: (value) => setState(() => selected = value),
            onRemove: () => removed++,
          ),
        ),
      ),
    );
    await tester.tap(find.byType(UiCheckbox));
    await tester.pump();
    expect(selected, isTrue);
    expect(removed, 0);
    await tester.tap(find.bySemanticsLabel('Remove Collection'));
    expect(removed, 1);
    expect(selected, isTrue);
  });

  testWidgets('formatting sends only the activated host command', (
    tester,
  ) async {
    final commands = <UiTextFormat>[];
    await tester.pumpWidget(
      uiHarness(
        child: UiTextToolbar(
          onCommand: commands.add,
          active: const {UiTextFormat.bold},
        ),
      ),
    );
    await tester.tap(find.text('Italic'));
    expect(commands, [UiTextFormat.italic]);
    await tester.pumpWidget(
      uiHarness(child: const UiTextToolbar(onCommand: null)),
    );
    await tester.tap(find.text('Bold'));
    expect(commands, [UiTextFormat.italic]);
  });
}
