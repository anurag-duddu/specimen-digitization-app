import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workbench.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

const _record = Specimen({
  'specimen_id': 'pending-save-availability',
  'display_name': 'Synthetic review availability record',
  'revision': 3,
  'latest_record_version_id': 'version-3',
  'operational_state': 'completed',
  'disposition': 'needs_human_review',
  'available_actions': ['field', 'coverage'],
  'fields': [
    {
      'field_key': 'country',
      'display_name': 'Country',
      'state': 'unknown',
      'literal_value': null,
    },
  ],
});

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('pending Save explains withdrawn field correction access', (
    tester,
  ) async {
    useWindow(tester, largeWindow);
    final semantics = tester.ensureSemantics();
    final sent = <Json>[];
    var shown = _record;
    late StateSetter rebuild;

    await tester.pumpWidget(
      workbenchHost(
        StatefulBuilder(
          builder: (context, update) {
            rebuild = update;
            return ReviewWorkbench(
              specimen: shown,
              reviewerId: 'synthetic-reviewer',
              onChange: (change) async {
                sent.add(change);
                rebuild(() {
                  shown = Specimen({
                    ...shown.data,
                    'revision': shown.revision + 1,
                    'latest_record_version_id': 'version-${shown.revision + 1}',
                    'fields': [
                      {
                        ...shown.fields.single,
                        'state': change['state'],
                        'literal_value': change['value'],
                      },
                    ],
                  });
                });
                return true;
              },
              onRetry: (_) async {},
              onRefresh: () {},
            );
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Specimen data'));
    await tester.pumpAndSettle();
    await openFieldEditor(tester, 0);
    await pickUiSelect(tester, 'Evidence state', 'Not present');
    await scrollAndTap(tester, uiButton('Keep this correction'));

    const saveLabel = 'Save 1 pending change';
    final originalDraft = tester
        .widget<WorkbenchFields>(find.byType(WorkbenchFields))
        .pending
        .single;
    expect(originalDraft.state, 'not_present');
    expect(controlEnabled(tester, saveLabel), isTrue);

    rebuild(() {
      shown = Specimen({
        ...shown.data,
        'revision': 4,
        'latest_record_version_id': 'version-4',
        'available_actions': ['coverage'],
      });
    });
    await tester.pumpAndSettle();

    expect(
      tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
      [originalDraft],
      reason: 'A permission change must not discard the unsaved correction.',
    );
    expect(controlEnabled(tester, saveLabel), isFalse);
    const reason =
        'The server does not permit field corrections on this version.';
    expect(disabledReasonOf(tester, saveLabel), reason);
    final saveSemantics = tester
        .getSemantics(uiControl(saveLabel))
        .getSemanticsData();
    expect(saveSemantics.hint, reason);
    expect(saveSemantics.hasAction(SemanticsAction.tap), isFalse);
    await scrollAndTap(tester, uiButton(saveLabel));
    expect(find.byType(ReasonForm), findsNothing);
    expect(sent, isEmpty);

    rebuild(() {
      shown = Specimen({
        ...shown.data,
        'revision': 5,
        'latest_record_version_id': 'version-5',
        'available_actions': ['field', 'coverage'],
      });
    });
    await tester.pumpAndSettle();
    expect(controlEnabled(tester, saveLabel), isTrue);
    expect(disabledReasonOf(tester, saveLabel), isNull);
    expect(
      tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
      [originalDraft],
    );
    await scrollAndTap(tester, uiButton(saveLabel));
    await tester.enterText(uiField('Reason'), 'The label has no country.');
    await tester.pumpAndSettle();
    await scrollAndTap(
      tester,
      find.descendant(
        of: find.byType(ReasonForm),
        matching: uiButton(saveLabel),
      ),
    );
    expect(sent, hasLength(1));
    expect(sent.single['kind'], 'field_correction');
    expect(sent.single['state'], 'not_present');
    expect(
      tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
      isEmpty,
    );
    await tester.pumpWidget(const SizedBox());
    semantics.dispose();
  });
}
