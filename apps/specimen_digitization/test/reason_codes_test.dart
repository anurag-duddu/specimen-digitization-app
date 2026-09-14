// Pass criterion 7.6: a reason chosen from configured codes or recent
// reasons, without typing.
//
// Three sources, and each one says where it came from: a decision vocabulary
// a collection or a profile published, the machine's own reasons this record
// is in the queue, and what this reviewer typed before, kept across sessions
// per user.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/reason_codes.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('configured reason codes', () {
    test('no fixture in this repository publishes one', () {
      // The honest state of the wire today, stated as a test so the row in
      // the verification report cannot quietly go stale: the moment a
      // collection document carries `review_reasons`, this fails and the row
      // is flipped.
      expect(
        configuredReasonCodes(<Json?>[
          const <String, dynamic>{'administrator_contact': 'someone'},
          const <String, dynamic>{'profile_id': 'zoology_insects'},
        ]),
        isEmpty,
      );
    });

    test('a collection document that publishes one is read', () {
      expect(
        configuredReasonCodes(<Json?>[
          const <String, dynamic>{
            preferredConfiguredReasonKey: <String>[
              'Label illegible',
              'Duplicate specimen',
            ],
          },
        ]),
        <String>['Label illegible', 'Duplicate specimen'],
      );
    });

    test('a list of code and label objects reads as the labels', () {
      expect(
        configuredReasonCodes(<Json?>[
          const <String, dynamic>{
            'decision_reasons': <Json>[
              <String, dynamic>{
                'code': 'illegible',
                'label': 'Label illegible',
              },
              <String, dynamic>{'code': 'dupe'},
            ],
          },
        ]),
        <String>['Label illegible', 'dupe'],
      );
    });

    test('the collection wins over the profile', () {
      expect(
        configuredReasonCodes(<Json?>[
          const <String, dynamic>{
            'review_reasons': <String>['From the collection'],
          },
          const <String, dynamic>{
            'review_reasons': <String>['From the profile'],
          },
        ]),
        <String>['From the collection'],
      );
    });

    test('the specimen key of the same name is never read as a vocabulary', () {
      expect(configuredReasonKeys, isNot(contains('reason_codes')));
      expect(
        configuredReasonCodes(<Json?>[
          const <String, dynamic>{
            'reason_codes': <String>['human_approval_required'],
          },
        ]),
        isEmpty,
      );
    });
  });

  group("the record's own reason codes", () {
    test('read as plain words, keeping the field they are about', () {
      expect(
        recordReasonCodes(
          Specimen(const <String, dynamic>{
            'reason_codes': <String>[
              'human_approval_required',
              'mandatory_unresolved:country',
            ],
          }),
        ),
        <String>['Human approval required', 'Mandatory unresolved: country'],
      );
    });

    test('a bare identifier is dropped rather than offered as a reason', () {
      expect(
        recordReasonCodes(
          Specimen(const <String, dynamic>{
            'reason_codes': <String>[
              'unresolved_transcription:7fb0fadb-9e9e-4941-92af-70fd1e197e9d',
            ],
          }),
        ),
        <String>['Unresolved transcription'],
      );
    });

    test('a record with none offers none', () {
      expect(recordReasonCodes(Specimen(const <String, dynamic>{})), isEmpty);
    });
  });

  group('recent reasons across sessions', () {
    test('a reason survives a new store object, which is a restart', () async {
      await const RecentReasonStore('reviewer-1').remember('Label illegible');
      expect(await const RecentReasonStore('reviewer-1').load(), <String>[
        'Label illegible',
      ]);
    });

    test('newest first, and no duplicates', () async {
      const RecentReasonStore store = RecentReasonStore('reviewer-1');
      await store.remember('First');
      await store.remember('Second');
      await store.remember('First');
      expect(await store.load(), <String>['First', 'Second']);
    });

    test('capped at ten', () async {
      const RecentReasonStore store = RecentReasonStore('reviewer-1');
      for (int i = 0; i < 14; i++) {
        await store.remember('Reason $i');
      }
      final List<String> stored = await store.load();
      expect(stored, hasLength(RecentReasonStore.limit));
      expect(stored.first, 'Reason 13');
      expect(stored.last, 'Reason 4');
    });

    test(
      'one reviewer never sees another reviewer on a shared machine',
      () async {
        await const RecentReasonStore('reviewer-1').remember('Mine');
        expect(await const RecentReasonStore('reviewer-2').load(), isEmpty);
      },
    );

    test('unreadable stored text is no reasons, never a crash', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        'review.recent_reasons.reviewer-1': 'not json',
      });
      expect(await const RecentReasonStore('reviewer-1').load(), isEmpty);
    });

    test('the stored shape is a plain JSON list', () async {
      await const RecentReasonStore('reviewer-1').remember('Label illegible');
      final SharedPreferences store = await SharedPreferences.getInstance();
      expect(
        jsonDecode(store.getString('review.recent_reasons.reviewer-1')!),
        <String>['Label illegible'],
      );
    });
  });

  group('the reason sheet', () {
    Future<void> pumpSheet(
      WidgetTester tester, {
      List<String> configured = const <String>[],
      List<String> record = const <String>[],
      List<String> recent = const <String>[],
    }) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(800, 1600);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: ReasonForm(
              title: 'Approve record?',
              action: 'Approve record',
              consequence: 'This is recorded on this version with your name.',
              configuredReasons: configured,
              recordReasons: record,
              recentReasons: recent,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('offers the three groups, configured first', (
      WidgetTester tester,
    ) async {
      await pumpSheet(
        tester,
        configured: const <String>['Label illegible'],
        record: const <String>['Human approval required'],
        recent: const <String>['Nothing on the label'],
      );
      final double configured = tester
          .getTopLeft(find.text(ReasonForm.configuredHeading))
          .dy;
      final double record = tester
          .getTopLeft(find.text(ReasonForm.recordHeading))
          .dy;
      final double recent = tester
          .getTopLeft(find.text(ReasonForm.recentHeading))
          .dy;
      expect(configured, lessThan(record));
      expect(record, lessThan(recent));
    });

    testWidgets('a chip fills the field, so no typing is needed', (
      WidgetTester tester,
    ) async {
      await pumpSheet(tester, configured: const <String>['Label illegible']);
      final Finder confirm = find.widgetWithText(
        FilledButton,
        'Approve record',
      );
      expect(tester.widget<FilledButton>(confirm).onPressed, isNull);
      await tester.tap(find.widgetWithText(ActionChip, 'Label illegible'));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<TextField>(find.widgetWithText(TextField, 'Reason'))
            .controller
            ?.text,
        'Label illegible',
      );
      expect(tester.widget<FilledButton>(confirm).onPressed, isNotNull);
    });

    testWidgets('a group with nothing in it promises nothing', (
      WidgetTester tester,
    ) async {
      await pumpSheet(tester);
      expect(find.text(ReasonForm.configuredHeading), findsNothing);
      expect(find.text(ReasonForm.recordHeading), findsNothing);
      expect(find.text(ReasonForm.recentHeading), findsNothing);
    });
  });
}
