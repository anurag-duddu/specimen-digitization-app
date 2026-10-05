// Main's record-status semantics retained in the minimal review composition.

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'widgets/harness.dart';

Specimen _record(
  String state, {
  String id = 'recovery-live',
  String? disposition,
  int revision = 3,
}) => Specimen(<String, dynamic>{
  'specimen_id': id,
  'revision': revision,
  'status': state,
  'disposition': disposition,
});

const _correction = PendingFieldChange(
  fieldKey: 'city',
  displayName: 'City',
  state: 'supported',
  literal: 'Chicago',
);

Widget _strip(
  Specimen specimen, {
  bool saved = false,
  List<PendingFieldChange> pending = const [],
  List<PendingFieldChange> staleChanges = const [],
  String? reconciliationMessage,
}) => Builder(
  builder: (BuildContext context) => MediaQuery(
    data: MediaQuery.of(context).copyWith(supportsAnnounce: true),
    child: WorkbenchStatusStrip(
      specimen: specimen,
      saved: saved,
      blockers: const <ClearanceBlocker>[],
      pending: pending,
      staleChanges: staleChanges,
      reconciliationMessage: reconciliationMessage,
      onGoToBlocker: (ClearanceBlocker _) {},
    ),
  ),
);

List<String> _heard(WidgetTester tester) => tester
    .takeAnnouncements()
    .map((CapturedAccessibilityAnnouncement event) => event.message)
    .toList();

void _testOn(
  TargetPlatform platform,
  String description,
  WidgetTesterCallback body,
) => testWidgets(description, body, variant: TargetPlatformVariant({platform}));

void main() {
  final List<Object?> haptics = <Object?>[];

  setUp(() {
    haptics.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (
          MethodCall call,
        ) async {
          if (call.method == 'HapticFeedback.vibrate') {
            haptics.add(call.arguments);
          }
          return null;
        });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null);
  });

  for (final TargetPlatform platform in <TargetPlatform>[
    TargetPlatform.android,
    TargetPlatform.iOS,
  ]) {
    for (final (String form, Size size) in <(String, Size)>[
      ('phone', const Size(390, 844)),
      ('tablet', const Size(768, 1024)),
    ]) {
      _testOn(
        platform,
        '${platform.name} $form: autonomous state changes announce once '
        'without save feedback',
        (WidgetTester tester) async {
          await pumpComponent(
            tester,
            _strip(_record('running')),
            size: size,
            platform: platform,
          );
          expect(_heard(tester), isEmpty);

          for (final (String wire, String spoken) in <(String, String)>[
            ('paused', 'Run: paused'),
            ('retry_scheduled', 'Run: retry scheduled'),
            ('cancelled', 'Run: cancelled'),
            ('processing_blocked', 'Run: processing blocked'),
          ]) {
            // A server's blank disposition still means no queue. It must
            // never turn an operational update into a saved decision.
            await pumpComponent(
              tester,
              _strip(_record(wire, disposition: '  ')),
              size: size,
              platform: platform,
            );
            expect(_heard(tester), <String>[spoken]);
            expect(find.text('Saved'), findsNothing);
            expect(find.byType(StatusChip), findsNothing);
            expect(haptics, isEmpty);

            await pumpComponent(
              tester,
              _strip(_record(wire, revision: 4)),
              size: size,
              platform: platform,
            );
            expect(_heard(tester), isEmpty, reason: 'no repeat on polling');
            expect(find.text('Saved'), findsNothing);
            expect(haptics, isEmpty);
          }

          await pumpComponent(
            tester,
            _strip(_record('completed', disposition: 'needs_human_review')),
            size: size,
            platform: platform,
          );
          expect(_heard(tester), <String>['Queue: needs review']);
          expect(find.text('Saved'), findsNothing);
          expect(haptics, isEmpty);

          await pumpComponent(
            tester,
            _strip(_record('paused', id: 'another-record')),
            size: size,
            platform: platform,
          );
          expect(_heard(tester), isEmpty, reason: 'opening is not a change');
          expect(find.text('Saved'), findsNothing);
          expect(haptics, isEmpty);
          expect(tester.takeException(), isNull);
        },
      );
    }

    _testOn(
      platform,
      '${platform.name}: a valid decision settles once and restore clears it',
      (WidgetTester tester) async {
        await pumpComponent(
          tester,
          _strip(_record('completed', disposition: 'needs_human_review')),
          platform: platform,
        );
        expect(_heard(tester), isEmpty);
        expect(find.text('Saved'), findsNothing);

        await pumpComponent(
          tester,
          _strip(
            _record('completed', disposition: 'cleared', revision: 4),
            saved: true,
          ),
          platform: platform,
        );
        expect(_heard(tester), <String>['Saved. Queue: cleared']);
        expect(find.text('Saved'), findsOneWidget);
        expect(haptics, <Object?>['HapticFeedbackType.mediumImpact']);

        // Canonical whitespace does not make a second decision.
        await pumpComponent(
          tester,
          _strip(
            _record('completed', disposition: ' cleared ', revision: 4),
            saved: true,
          ),
          platform: platform,
        );
        expect(_heard(tester), isEmpty);
        expect(haptics, hasLength(1));

        await pumpComponent(
          tester,
          _strip(_record('paused', revision: 5)),
          platform: platform,
        );
        expect(_heard(tester), <String>['Run: paused']);
        expect(find.text('Saved'), findsNothing);
        expect(haptics, hasLength(1));
      },
    );

    _testOn(
      platform,
      '${platform.name}: acknowledged same-disposition save cues once per version',
      (tester) async {
        final record = _record('completed', disposition: 'needs_human_review');
        await pumpComponent(tester, _strip(record), platform: platform);
        expect(_heard(tester), isEmpty);
        await pumpComponent(
          tester,
          _strip(record, saved: true),
          platform: platform,
        );
        expect(_heard(tester), <String>['Saved. Queue: needs review']);
        expect(find.text('Saved'), findsOneWidget);
        expect(haptics, <Object?>['HapticFeedbackType.mediumImpact']);
        await pumpComponent(
          tester,
          _strip(record, saved: true),
          platform: platform,
        );
        expect(_heard(tester), isEmpty, reason: 'polling repeats no ACK cue');
        expect(haptics, hasLength(1));
        await pumpComponent(
          tester,
          _strip(record, pending: const [_correction]),
          platform: platform,
        );
        expect(_heard(tester), isEmpty);
        expect(find.text('Saved'), findsNothing);
        await pumpComponent(
          tester,
          _strip(record, saved: true),
          platform: platform,
        );
        expect(_heard(tester), isEmpty, reason: 'discard is not another save');
        expect(haptics, hasLength(1));
        await pumpComponent(
          tester,
          _strip(
            _record(
              'completed',
              disposition: 'needs_human_review',
              revision: 4,
            ),
            saved: true,
          ),
          platform: platform,
        );
        expect(_heard(tester), <String>['Saved. Queue: needs review']);
        expect(haptics, hasLength(2));
        await pumpComponent(
          tester,
          _strip(
            _record('completed', id: 'new-record', disposition: 'cleared'),
          ),
          platform: platform,
        );
        expect(_heard(tester), isEmpty);
        expect(find.text('Saved'), findsNothing);
        expect(haptics, hasLength(2));
      },
    );

    for (final recovery in ['pending', 'stale', 'reconciliation']) {
      _testOn(
        platform,
        '${platform.name}: $recovery suppresses save announcements and haptics',
        (tester) async {
          final record = _record(
            'completed',
            disposition: 'needs_human_review',
          );
          await pumpComponent(tester, _strip(record), platform: platform);
          expect(_heard(tester), isEmpty);
          await pumpComponent(
            tester,
            _strip(
              record,
              saved: true,
              pending: recovery == 'pending' ? const [_correction] : const [],
              staleChanges: recovery == 'stale'
                  ? const [_correction]
                  : const [],
              reconciliationMessage: recovery == 'reconciliation'
                  ? 'Refresh and compare this save.'
                  : null,
            ),
            platform: platform,
          );
          expect(_heard(tester), isEmpty);
          expect(find.text('Saved'), findsNothing);
          expect(haptics, isEmpty);
          await pumpComponent(
            tester,
            _strip(record, saved: true),
            platform: platform,
          );
          expect(_heard(tester), isEmpty, reason: 'recovery is not a new ACK');
          expect(haptics, isEmpty);
        },
      );
    }
  }

  _testOn(
    TargetPlatform.android,
    'invalid dispositions never confirm a saved decision',
    (WidgetTester tester) async {
      await pumpComponent(tester, _strip(_record('running')));
      expect(_heard(tester), isEmpty);
      await pumpComponent(
        tester,
        _strip(_record('running', disposition: 'paused')),
      );
      expect(_heard(tester), <String>['Queue: state unknown']);
      expect(find.text('Saved'), findsNothing);
      expect(haptics, isEmpty);

      await pumpComponent(
        tester,
        _strip(_record('running', disposition: 'supported')),
      );
      expect(_heard(tester), isEmpty);
      expect(find.text('Saved'), findsNothing);
      expect(haptics, isEmpty);
    },
  );

  _testOn(
    TargetPlatform.android,
    'idle review feedback does not restore duplicate status facts',
    (WidgetTester tester) async {
      await pumpComponent(
        tester,
        _strip(_record('completed', disposition: 'needs_human_review')),
      );
      final UiStatusStrip strip = tester.widget<UiStatusStrip>(
        find.byType(UiStatusStrip),
      );
      expect(strip.disposition, isNull);
      expect(strip.provenance, isEmpty);
      expect(strip.blockers, isNull);
      expect(find.byType(StatusChip), findsNothing);
      expect(find.byType(TermText), findsNothing);
      expect(find.text('Saved'), findsNothing);
    },
  );
}
