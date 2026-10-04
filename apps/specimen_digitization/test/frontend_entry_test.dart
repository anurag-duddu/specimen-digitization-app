import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

void main() {
  testWidgets(
    'a specimen opens at its fields with the full photograph unselected',
    (tester) async {
      useWindow(tester, largeWindow);
      const specimen = Specimen({
        'specimen_id': '92c2aba8-c4e6-4f18-933b-51c62d45d7ea',
        'filename': 'subject_105526321.jpeg',
        'revision': 1,
        'assets': [
          {'width': 1000, 'height': 600, 'pixel_basis': 'original_pixel_edges'},
        ],
        'regions': [
          {
            'region_id': 'label-one',
            'bbox': [0, 0, 100, 100],
          },
        ],
        'fields': [
          {
            'field_key': 'country',
            'display_name': 'Country',
            'required': true,
            'state': 'unknown',
          },
        ],
      });
      await tester.pumpWidget(
        workbenchHost(
          ReviewWorkbench(
            specimen: specimen,
            onChange: (_) async => fail('Opening a record must not save'),
            onRetry: (_) async => fail('Opening a record must not run models'),
            onRefresh: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      final tabs = tester.widget<UiTabs>(uiTabs('Record view'));
      expect(tabs.tabs.map((tab) => tab.label), [
        'Specimen data',
        'Labels',
        'History',
      ]);
      expect(tabs.selected.value, 0);
      expect(find.text('Country'), findsOneWidget);
      expect(find.text('#105526321'), findsOneWidget);
      expect(find.text(specimen.id), findsNothing);
      expect(
        tester
            .widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane))
            .selectedRegionId,
        isNull,
      );

      await tester.tap(uiRecordView('Label review'));
      await tester.pumpAndSettle();
      expect(tabs.selected.value, 1);
      expect(tester.widget<UiSelect<String>>(uiSelect('Label')).value, '');

      await tester.pumpWidget(
        workbenchHost(
          ReviewWorkbench(
            specimen: Specimen({
              ...specimen.data,
              'specimen_id': 'next-record',
              'filename': 'subject_105526324.jpeg',
            }),
            onChange: (_) async => false,
            onRetry: (_) async {},
            onRefresh: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.widget<UiTabs>(uiTabs('Record view')).selected.value, 0);
      expect(find.text('#105526324'), findsOneWidget);
      expect(
        tester
            .widget<WorkbenchSourcePane>(find.byType(WorkbenchSourcePane))
            .selectedRegionId,
        isNull,
      );
      expect(tester.takeException(), isNull);
    },
  );
}
