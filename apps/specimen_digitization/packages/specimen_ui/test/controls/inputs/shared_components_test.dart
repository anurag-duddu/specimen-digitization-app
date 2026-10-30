import 'dart:ui' show CheckedState;
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets(
    'verification paste distributes all six digits and completes once',
    (tester) async {
      var code = '';
      final completed = <String>[];
      await tester.pumpWidget(
        uiHarness(
          child: StatefulBuilder(
            builder: (_, setState) => UiVerificationCode(
              label: 'Email code',
              value: code,
              onChanged: (value) => setState(() => code = value),
              onCompleted: completed.add,
            ),
          ),
        ),
      );
      await tester.enterText(find.byType(EditableText).first, '12x345678');
      await tester.pump();
      expect(code, '123456');
      expect(completed, ['123456']);
      expect(
        tester
            .widgetList<EditableText>(find.byType(EditableText))
            .map((e) => e.controller.text),
        ['1', '2', '3', '4', '5', '6'],
      );
      expect(
        tester
            .widget<EditableText>(find.byType(EditableText).first)
            .autofillHints,
        contains(AutofillHints.oneTimeCode),
      );
      await tester.enterText(find.byType(EditableText).last, '6');
      await tester.pump();
      expect(completed, ['123456']);
      await tester.enterText(find.byType(EditableText).last, '');
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.backspace);
      await tester.pump();
      expect(
        tester
            .widget<EditableText>(find.byType(EditableText).at(4))
            .focusNode
            .hasFocus,
        isTrue,
      );
    },
  );

  testWidgets(
    'four digit verification fits large RTL text and disabled editor',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(320, 600));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 600),
          textDirection: TextDirection.rtl,
          textScaler: const TextScaler.linear(2),
          child: const UiVerificationCode(
            label: 'Verification',
            value: '1234',
            length: 4,
            errorText: 'Request a new code.',
          ),
        ),
      );
      expect(tester.takeException(), isNull);
      for (final field in tester.widgetList<UiField>(find.byType(UiField))) {
        expect(field.enabled, isFalse);
      }
      final first = tester.getTopLeft(find.byType(EditableText).first);
      final last = tester.getTopLeft(find.byType(EditableText).last);
      expect(first.dx, lessThan(last.dx));
    },
  );

  testWidgets(
    'tag entry rejects blanks and duplicates and removes with empty Backspace',
    (tester) async {
      List<String> values = ['Museum'];
      await tester.pumpWidget(
        uiHarness(
          child: StatefulBuilder(
            builder: (_, setState) => UiTagField(
              label: 'Tags',
              values: values,
              onChanged: (v) => setState(() => values = v),
            ),
          ),
        ),
      );
      await tester.enterText(find.byType(EditableText), ' Museum ');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pump();
      expect(values, ['Museum']);
      await tester.enterText(find.byType(EditableText), 'Birds');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pump();
      expect(values, ['Museum', 'Birds']);
      await tester.tap(find.byType(EditableText));
      await tester.sendKeyEvent(LogicalKeyboardKey.backspace);
      await tester.pump();
      expect(values, ['Museum']);
    },
  );

  testWidgets(
    'phone country remains explicit and native number remains verbatim',
    (tester) async {
      final controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        uiHarness(
          child: UiPhoneField(
            label: 'Phone',
            controller: controller,
            countries: const [
              UiPhoneCountry(
                code: 'US',
                name: 'United States',
                dialingCode: '+1',
              ),
            ],
            onCountryChanged: (_) {},
          ),
        ),
      );
      expect(find.text('Choose country'), findsOneWidget);
      await tester.enterText(find.byType(EditableText), '+44 (0)20 1234 ext 5');
      expect(controller.text, '+44 (0)20 1234 ext 5');
      expect(
        tester.widget<EditableText>(find.byType(EditableText)).keyboardType,
        TextInputType.phone,
      );
    },
  );

  testWidgets('checkbox support is one mixed node and retains 48 dp target', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: UiCheckbox(
          label: 'All records',
          supporting: 'Includes verified records',
          value: null,
          size: UiSelectionControlSize.small,
          shape: UiCheckboxShape.circle,
          onChanged: (_) {},
        ),
      ),
    );
    final finder = find.bySemanticsLabel(
      'All records. Includes verified records',
    );
    expect(finder, findsOneWidget);
    expect(
      tester.getSemantics(finder).getSemanticsData().flagsCollection.isChecked,
      CheckedState.mixed,
    );
    expect(tester.getSize(finder).height, greaterThanOrEqualTo(48));
    semantics.dispose();
  });

  testWidgets(
    'rich inverse tooltip reveals supporting text without an extra action',
    (tester) async {
      await tester.pumpWidget(
        uiHarness(
          child: const UiTooltip(
            message: 'Collection identifier',
            supportingText:
                'Use the original identifier printed on the specimen label.',
            emphasis: UiTooltipEmphasis.inverse,
            child: Text('Identifier help'),
          ),
        ),
      );
      await tester.longPress(find.text('Identifier help'));
      await tester.pumpAndSettle();
      expect(
        find.text('Use the original identifier printed on the specimen label.'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'upload fill uses reported progress and leaves recovery host-owned',
    (tester) async {
      var removed = '';
      await tester.pumpWidget(
        uiHarness(
          child: UiFileUpload(
            label: 'Images',
            progressStyle: UiFileUploadProgressStyle.fill,
            files: const [
              UiUploadFile(
                id: '1',
                name: 'sample.tiff',
                statusLabel: 'Transferring',
                status: UiFileUploadStatus.uploading,
                progress: .35,
              ),
            ],
            onRemove: (file) => removed = file.id,
          ),
        ),
      );
      expect(find.text('35%'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('Remove sample.tiff'));
      expect(removed, '1');
    },
  );
  testWidgets('action retains complete control contract at every density', (
    tester,
  ) async {
    await expectControlContract(
      tester,
      (_) => UiActionButton(label: 'Review', onPressed: () {}),
      semanticsLabel: 'Review',
    );
  });

  testWidgets('busy and disabled actions never activate', (tester) async {
    var calls = 0;
    await tester.pumpWidget(
      uiHarness(
        disableAnimations: true,
        child: UiActionButton(
          label: 'Save',
          busy: true,
          onPressed: () => calls++,
        ),
      ),
    );
    await tester.tap(find.byType(UiActionButton));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    expect(calls, 0);
  });

  testWidgets('joined command arrow navigation does not activate commands', (
    tester,
  ) async {
    final calls = <String>[];
    await tester.pumpWidget(
      uiHarness(
        child: UiButtonGroup(
          label: 'History',
          items: [
            UiButtonGroupItem(
              label: 'Undo',
              onPressed: () => calls.add('undo'),
            ),
            UiButtonGroupItem(
              label: 'Redo',
              onPressed: () => calls.add('redo'),
            ),
          ],
        ),
      ),
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(calls, isEmpty);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    expect(calls, ['redo']);
  });

  testWidgets('radio cards skip unavailable options and select with arrows', (
    tester,
  ) async {
    Set<int> selected = {1};
    await tester.pumpWidget(
      uiHarness(
        child: StatefulBuilder(
          builder: (_, setState) => SizedBox(
            width: 320,
            child: UiSelectionCards<int>(
              label: 'Method',
              mode: UiSelectionMode.single,
              selected: selected,
              options: const [
                UiSelectionCardOption(value: 1, label: 'Manual'),
                UiSelectionCardOption(
                  value: 2,
                  label: 'Unavailable',
                  enabled: false,
                ),
                UiSelectionCardOption(value: 3, label: 'Assisted'),
              ],
              onChanged: (value) => setState(() => selected = value),
            ),
          ),
        ),
      ),
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pump();
    expect(selected, {3});
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pump();
    expect(selected, {1});
  });

  testWidgets('range slider thumbs clamp at each other and follow RTL arrows', (
    tester,
  ) async {
    var values = const UiRangeValues(20, 40);
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        child: StatefulBuilder(
          builder: (_, setState) => SizedBox(
            width: 320,
            child: UiRangeSlider(
              label: 'Range',
              min: 0,
              max: 100,
              divisions: 10,
              values: values,
              onChanged: (value) => setState(() => values = value),
            ),
          ),
        ),
      ),
    );
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(values, const UiRangeValues(10, 40));
    await tester.sendKeyEvent(LogicalKeyboardKey.end);
    await tester.pump();
    expect(values, const UiRangeValues(40, 40));
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pump();
    expect(values, const UiRangeValues(40, 40));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.home);
    await tester.pump();
    expect(values, const UiRangeValues(40, 40));
    await tester.sendKeyEvent(LogicalKeyboardKey.end);
    await tester.pump();
    expect(values, const UiRangeValues(40, 100));
  });

  testWidgets('disabled range exposes no adjustment actions', (tester) async {
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 300,
          child: UiRangeSlider(
            label: 'Bounds',
            values: const UiRangeValues(.2, .8),
            disabledReason: 'Read only',
          ),
        ),
      ),
    );
    for (final label in ['Bounds, Minimum', 'Bounds, Maximum']) {
      final data = tester
          .getSemantics(find.bySemanticsLabel(label))
          .getSemanticsData();
      expect(data.hasAction(SemanticsAction.increase), isFalse);
      expect(data.hint, 'Read only');
    }
    semantics.dispose();
  });

  testWidgets(
    'multi combobox filters, preserves selection and closes with Escape',
    (tester) async {
      final semantics = tester.ensureSemantics();
      Set<String> selected = {'a'};
      await tester.pumpWidget(
        uiHarness(
          child: StatefulBuilder(
            builder: (_, setState) => SizedBox(
              width: 320,
              child: UiCombobox<String>(
                label: 'Collectors',
                selected: selected,
                multiple: true,
                options: const [
                  UiComboboxOption(value: 'a', label: 'Alice', group: 'Museum'),
                  UiComboboxOption(value: 'b', label: 'Beth', group: 'Museum'),
                  UiComboboxOption(value: 'c', label: 'Carol', enabled: false),
                ],
                onChanged: (value) => setState(() => selected = value),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.bySemanticsLabel('Collectors'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(EditableText), 'Beth');
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(selected, {'a', 'b'});
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
      expect(find.byType(EditableText), findsNothing);
      expect(selected, {'a', 'b'});
      semantics.dispose();
    },
  );

  testWidgets(
    'date range commits only a complete UTC draft and rejects disabled preset',
    (tester) async {
      final semantics = tester.ensureSemantics();
      final received = <UiDateRange>[];
      await tester.pumpWidget(
        uiHarness(
          size: const Size(800, 1000),
          child: SingleChildScrollView(
            child: SizedBox(
              width: 640,
              child: UiDateRangePicker(
                label: 'Collected dates',
                value: null,
                showActions: true,
                firstDate: DateTime.utc(2028, 2, 1),
                lastDate: DateTime.utc(2028, 3, 31),
                presets: [
                  UiDateRangePreset(
                    label: 'Unavailable dates',
                    range: UiDateRange(
                      DateTime.utc(2027),
                      DateTime.utc(2027, 2),
                    ),
                  ),
                ],
                onChanged: received.add,
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.bySemanticsLabel('20 February 2028'));
      await tester.pump();
      await tester.tap(find.bySemanticsLabel('10 February 2028'));
      await tester.pump();
      expect(received, isEmpty);
      await tester.ensureVisible(find.text('Apply dates'));
      await tester.tap(find.text('Apply dates'));
      await tester.pump();
      expect(
        received.single,
        UiDateRange(DateTime.utc(2028, 2, 10), DateTime.utc(2028, 2, 20)),
      );
      expect(received.single.start.isUtc, isTrue);
      final unavailable = tester
          .getSemantics(find.bySemanticsLabel('Unavailable dates'))
          .getSemanticsData();
      expect(unavailable.hasAction(SemanticsAction.tap), isFalse);
      semantics.dispose();
    },
  );

  testWidgets(
    'avatar overflow announces every member and keeps add action separate',
    (tester) async {
      final semantics = tester.ensureSemantics();
      var added = 0;
      await tester.pumpWidget(
        uiHarness(
          textScaler: const TextScaler.linear(2),
          child: SizedBox(
            width: 180,
            child: UiAvatarGroup(
              label: 'Reviewers',
              maxVisible: 3,
              people: List.generate(
                8,
                (i) => UiAvatarPerson(name: 'Reviewer $i'),
              ),
              onAdd: () => added++,
            ),
          ),
        ),
      );
      expect(tester.takeException(), isNull);
      expect(
        find.bySemanticsLabel(RegExp('Reviewers.*Reviewer 7')),
        findsOneWidget,
      );
      await tester.tap(find.bySemanticsLabel('Add person'));
      expect(added, 1);
      semantics.dispose();
    },
  );

  testWidgets(
    'progress displays exact decreases while loader freezes under reduced motion',
    (tester) async {
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(
        uiHarness(
          disableAnimations: true,
          child: const Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              UiProgressDisplay(
                label: 'Storage',
                value: .24,
                form: UiProgressDisplayForm.halfCircle,
                labelPosition: UiProgressLabelPosition.center,
              ),
              UiLoadingIndicator(
                label: 'Reading',
                style: UiLoadingIndicatorStyle.dots,
              ),
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester
            .getSemantics(find.bySemanticsLabel('Storage'))
            .getSemanticsData()
            .value,
        '24%',
      );
      expect(tester.binding.hasScheduledFrame, isFalse);
      semantics.dispose();
    },
  );

  testWidgets('rich shared controls fit 320 wide RTL with 200 percent text', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(320, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      uiHarness(
        size: const Size(320, 900),
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        disableAnimations: true,
        child: SingleChildScrollView(
          child: SizedBox(
            width: 320,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                UiButtonGroup(
                  label: 'Commands',
                  items: [
                    UiButtonGroupItem(
                      label: 'Previous record',
                      onPressed: () {},
                    ),
                    UiButtonGroupItem(label: 'Next record', onPressed: () {}),
                  ],
                ),
                UiActionButton(
                  label: 'Save selected records',
                  onPressed: () {},
                ),
                UiSelectionCards<int>(
                  label: 'Review mode',
                  selected: const {1},
                  options: const [
                    UiSelectionCardOption(
                      value: 1,
                      label: 'Assisted transcription',
                      supporting:
                          'Keep the complete original evidence available for review.',
                      leading: UiAvatar(name: 'Reviewer'),
                    ),
                  ],
                  onChanged: (_) {},
                ),
                UiRangeSlider(
                  label: 'Image resolution',
                  values: const UiRangeValues(.2, .8),
                  errorText:
                      'Choose limits that include your complete collection.',
                  onChanged: (_) {},
                ),
                UiTag(
                  label: 'Invertebrate collections',
                  count: 120,
                  onRemove: () {},
                ),
                const UiAvatarLabel(
                  name: 'Museum collections reviewer',
                  supporting: 'Research and collections department',
                  status: UiAvatarStatus.online,
                ),
                const UiProgressDisplay(
                  label: 'Collection coverage',
                  value: .4,
                  form: UiProgressDisplayForm.halfCircle,
                  labelPosition: UiProgressLabelPosition.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
