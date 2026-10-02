// Actual controls, with no retired-label alias or fabricated confirmation.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/field_row.dart';
import 'package:specimen_digitization/src/widgets/specimen_status.dart';
import 'package:specimen_ui/specimen_ui.dart' hide FieldLayer;

import 'intake_harness.dart';
import 'intake_layout_test.dart' show pumpIntake;
import 'ui_finders.dart';
import 'workbench_harness.dart';

void main() {
  testWidgets(
    'new-file classification is idempotent on the actual intake checkbox',
    (tester) async {
      await pumpIntake(tester, const Size(1000, 1200));
      expect(tester.widget<UiCheckbox>(sensitivityControl).value, isTrue);
      await selectSensitivity(tester, 'Not sensitive');
      await selectSensitivity(tester, 'Not sensitive');
      expect(tester.widget<UiCheckbox>(sensitivityControl).value, isFalse);
      await selectSensitivity(tester, 'Sensitive');
      expect(tester.widget<UiCheckbox>(sensitivityControl).value, isTrue);
      expect(confirmCheckbox, findsNothing);
    },
  );

  testWidgets(
    'unknown classification is refused without changing the actual checkbox',
    (tester) async {
      await pumpIntake(tester, const Size(1000, 1200));
      await expectLater(
        selectSensitivity(tester, 'invented'),
        throwsArgumentError,
      );
      expect(tester.widget<UiCheckbox>(sensitivityControl).value, isTrue);
    },
  );

  testWidgets('select picks a filtered lazy option through its real row', (
    tester,
  ) async {
    var selected = 0;
    await tester.pumpWidget(
      workbenchHost(
        StatefulBuilder(
          builder: (context, setState) => UiSelect<int>(
            label: 'Label',
            value: selected,
            placeholder: 'Choose',
            options: <UiSelectOption<int>>[
              for (var i = 0; i < 12; i++)
                UiSelectOption(value: i, label: 'Label $i'),
            ],
            onChanged: (value) => setState(() => selected = value),
          ),
        ),
      ),
    );
    await pickUiSelect(tester, 'Label', 'Label 11');
    expect(selected, 11);
    expect(tester.widget<UiSelect<int>>(uiSelect('Label')).value, 11);
    expect(find.byType(UiListRow), findsNothing);
  });

  testWidgets('opening a second layer retains an already expanded real field', (
    tester,
  ) async {
    final opened = <FieldLayer>[];
    await tester.pumpWidget(
      workbenchHost(
        FieldRow(
          name: 'Country',
          state: SpecimenStatus.supported,
          required: true,
          asWritten: 'Kenya',
          readAs: 'Kenya',
          standardized: 'KE',
          onEdit: opened.add,
          editSemanticsLabel: (layer) =>
              'Edit ${layer.label.toLowerCase()} for Country',
        ),
      ),
    );
    await openFieldEditor(tester, 0);
    await openFieldEditor(tester, 0, layer: 'read as');
    expect(opened, <FieldLayer>[FieldLayer.asWritten, FieldLayer.readAs]);
    expect(uiIconButton('Edit as written for Country'), findsOneWidget);
    expect(uiIconButton('Edit read as for Country'), findsOneWidget);
  });

  testWidgets(
    'availability reads a genuine overflow declaration and missing controls fail',
    (tester) async {
      await tester.pumpWidget(
        workbenchHost(
          UiMenuTrigger(
            semanticsLabel: 'Commands',
            icon: UiIcons.more,
            items: <UiMenuItem>[
              UiMenuItem(label: 'Allowed', onSelected: () {}),
              const UiMenuItem(
                label: 'Blocked',
                onSelected: null,
                disabledReason: 'Not authorized',
              ),
            ],
          ),
        ),
      );
      expect(controlEnabled(tester, 'Allowed'), isTrue);
      expect(controlEnabled(tester, 'Blocked'), isFalse);
      expect(() => controlEnabled(tester, 'Absent'), throwsStateError);
    },
  );
}
