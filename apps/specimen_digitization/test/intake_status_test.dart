import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/intake_status.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_entry.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';

ManifestEntry photo(
  UploadState state, {
  Json? summary,
  Object? error,
  IntakeRefusal? refusal,
  bool bytes = true,
}) => ManifestEntry(
  digest: 'a' * 64,
  name: 'photo.jpg',
  state: state,
  specimenId: summary?['specimen_id'] as String?,
  specimen: summary == null ? null : Specimen(summary),
  transferError: error,
  refusal: refusal,
  file: bytes
      ? IntakeFile(
          name: 'photo.jpg',
          bytes: Uint8List.fromList(<int>[1, 2, 3]),
          mimeType: 'image/jpeg',
          sha256: 'a' * 64,
          method: 'camera',
          sensitive: false,
        )
      : null,
);

Json saved(
  String state, {
  String? blocker,
  String? dispatch,
  bool inLine = false,
}) => <String, dynamic>{
  'specimen_id': 'saved-photo',
  'status': state,
  'blocker': blocker,
  'available_actions': <String>['start_processing', 'retry'],
  if (dispatch != null) 'dispatch': <String, dynamic>{'status': dispatch},
  if (inLine) 'intake_progress': <String, dynamic>{'waiting_in_line': true},
};

void checkCopy(IntakeStatus value) {
  expect(value.status.length, lessThanOrEqualTo(14));
  expect(value.status.split(RegExp(r'\s+')).length, lessThanOrEqualTo(2));
  if (value.reason case final String reason) {
    expect(reason.length, lessThanOrEqualTo(55), reason: reason);
    expect(
      reason.split(RegExp(r'\s+')).length,
      lessThanOrEqualTo(8),
      reason: reason,
    );
  }
  final String visible = '${value.status} ${value.reason ?? ''}'.toLowerCase();
  for (final String term in <String>[
    'intake queue',
    'main queue',
    'derivative',
    'offset',
    'classification',
    'checksum',
    'sha-256',
    'preflight',
    'server check',
    'codec',
    'collection profile',
    'runtime',
    'batch',
    'upload handle',
    'not calibrated',
    'failed',
    'invalid',
    'please',
    'sorry',
    'we',
    'photograph',
    'image',
    'picture',
  ]) {
    expect(
      RegExp('\\b${RegExp.escape(term)}\\b').hasMatch(visible),
      isFalse,
      reason: '$term in $visible',
    );
  }
}

void main() {
  test('all eleven UploadState values have one intake mapping', () {
    final Map<UploadState, (String, IntakeTone, IntakeAction?)> expected = {
      UploadState.ready: ('Ready', IntakeTone.neutral, IntakeAction.menu),
      UploadState.checking: ('Sending', IntakeTone.processing, null),
      UploadState.uploading: ('Sending', IntakeTone.processing, null),
      UploadState.accepted: ('Saved', IntakeTone.neutral, IntakeAction.dismiss),
      UploadState.processing: ('Starting', IntakeTone.processing, null),
      UploadState.inMainQueue: ('Sent', IntakeTone.none, null),
      UploadState.processingBlocked: (
        'Held',
        IntakeTone.neutral,
        IntakeAction.dismiss,
      ),
      UploadState.duplicate: ('Duplicate', IntakeTone.none, null),
      UploadState.interrupted: (
        'Unfinished',
        IntakeTone.neutral,
        IntakeAction.chooseFile,
      ),
      UploadState.skipped: ('Not added', IntakeTone.error, IntakeAction.remove),
      UploadState.failed: ('Not sent', IntakeTone.error, IntakeAction.remove),
    };
    expect(expected.keys.toSet(), UploadState.values.toSet());
    for (final MapEntry<UploadState, (String, IntakeTone, IntakeAction?)> row
        in expected.entries) {
      final ManifestEntry entry = photo(
        row.key,
        bytes: false,
        summary: switch (row.key) {
          UploadState.processing => saved('pending'),
          UploadState.processingBlocked => saved(
            'processing_blocked',
            blocker: 'sensitive_record_not_processed',
          ),
          _ => null,
        },
      );
      final IntakeStatus value = intakeStatus(entry);
      expect(
        (value.status, value.tone, value.action),
        row.value,
        reason: row.key.name,
      );
      checkCopy(value);
    }
  });

  for (final String status in <String>[
    'running',
    'retry_scheduled',
    'paused',
    'cancelled',
    'completed',
  ]) {
    test('$status is Sent without a disposition or stage inference', () {
      final IntakeStatus value = intakeStatus(
        photo(UploadState.processing, summary: saved(status)),
      );
      expect(
        (value.status, value.reason, value.action, value.tone),
        ('Sent', null, null, IntakeTone.none),
      );
      expect(value.leavesIntake, isTrue);
      checkCopy(value);
    });
  }

  test('any set disposition and a pending photo in line are Sent', () {
    for (final Json summary in <Json>[
      {...saved('pending'), 'disposition': 'needs_human_review'},
      {...saved('pending'), 'disposition': 'future_outcome'},
      saved('pending', inLine: true),
    ]) {
      expect(
        intakeStatus(photo(UploadState.processing, summary: summary)).status,
        'Sent',
      );
    }
  });

  test(
    'pending and unknown summaries stay Starting without invented progress',
    () {
      for (final Json summary in <Json>[
        saved('pending'),
        saved('future_state'),
        {
          'specimen_id': 'saved-photo',
          'stage': 'running',
          'active_run_id': 'run',
          'revision': 20,
        },
      ]) {
        final IntakeStatus value = intakeStatus(
          photo(UploadState.processing, summary: summary),
        );
        expect(
          (value.status, value.reason, value.action),
          ('Starting', null, null),
        );
        checkCopy(value);
      }
    },
  );

  for (final (String, String, String, IntakeAction?, IntakeTone) row
      in <(String, String, String, IntakeAction?, IntakeTone)>[
        (
          'sensitive_record_not_processed',
          'Held',
          'Sensitive. Saved, not read.',
          IntakeAction.dismiss,
          IntakeTone.neutral,
        ),
        (
          'collection_processing_unconfigured',
          'Not started',
          'Not set up for processing. Ask an admin.',
          IntakeAction.dismiss,
          IntakeTone.operational,
        ),
        (
          'program_allowance_unavailable',
          'Not started',
          'Not set up for processing. Ask an admin.',
          IntakeAction.dismiss,
          IntakeTone.operational,
        ),
      ]) {
    test('${row.$1} is a hand-off refusal with one action', () {
      final IntakeStatus value = intakeStatus(
        photo(
          UploadState.processingBlocked,
          summary: saved('processing_blocked', blocker: row.$1),
        ),
      );
      expect(
        (value.status, value.reason, value.action, value.tone),
        (row.$2, row.$3, row.$4, row.$5),
      );
      checkCopy(value);
    });
  }

  test(
    'every other pipeline blocker is Sent including unknown future blockers',
    () {
      for (final String? blocker in <String?>[
        null,
        'external_outcome_unknown',
        'model_output_invalid',
        'cost_budget_exhausted',
        'future_blocker',
      ]) {
        final IntakeStatus value = intakeStatus(
          photo(
            UploadState.processingBlocked,
            summary: saved('processing_blocked', blocker: blocker),
          ),
        );
        expect(
          (value.status, value.reason, value.action),
          ('Sent', null, null),
        );
      }
    },
  );

  test('only a failed or unconfigured dispatch is Not started', () {
    for (final (String?, String, IntakeAction?) row
        in <(String?, String, IntakeAction?)>[
          (null, 'Starting', null),
          ('requested', 'Starting', null),
          ('unknown', 'Starting', null),
          ('failed', 'Not started', IntakeAction.start),
          ('unconfigured', 'Not started', IntakeAction.dismiss),
        ]) {
      final IntakeStatus value = intakeStatus(
        photo(
          UploadState.processing,
          summary: saved('pending', dispatch: row.$1),
        ),
      );
      expect((value.status, value.action), (row.$2, row.$3));
      checkCopy(value);
    }
    final Json denied = saved('pending', dispatch: 'failed')
      ..['available_actions'] = <String>[];
    expect(
      intakeStatus(photo(UploadState.processing, summary: denied)).action,
      isNull,
    );
    expect(
      intakeStatus(
        photo(
          UploadState.processing,
          summary: saved('pending', dispatch: 'failed', inLine: true),
        ),
      ).status,
      'Sent',
    );
  });

  test('completion without specimen_id is Saved regardless of the status', () {
    for (final String state in <String>[
      'pending',
      'running',
      'completed',
      'processing_blocked',
    ]) {
      final Json summary = saved(state)..remove('specimen_id');
      final IntakeStatus value = intakeStatus(
        photo(UploadState.accepted, summary: summary),
      );
      expect(
        (value.status, value.reason, value.action),
        ('Saved', 'Saved. Start not confirmed.', IntakeAction.dismiss),
      );
    }
  });

  test('server duplicate and an explicit summary override are honored', () {
    final ManifestEntry entry = photo(
      UploadState.processing,
      summary: saved('pending'),
    );
    expect(
      intakeStatus(entry, summary: Specimen(saved('running'))).status,
      'Sent',
    );
    expect(
      intakeStatus(
        entry,
        summary: Specimen({...saved('pending'), 'upload_state': 'duplicate'}),
      ).status,
      'Duplicate',
    );
  });

  test(
    'transfer failure catalogue keeps operational faults out of error tone',
    () {
      for (final ApiFailure error in <ApiFailure>[
        const ApiFailure('private detail', code: 'network'),
        const ApiFailure('private detail', code: 'timeout'),
        for (final int status in <int>[408, 429, 500, 503, 599])
          ApiFailure('private detail', status: status),
      ]) {
        for (final UploadState state in <UploadState>[
          UploadState.failed,
          UploadState.interrupted,
        ]) {
          final IntakeStatus value = intakeStatus(photo(state, error: error));
          expect(
            (value.status, value.reason, value.action, value.tone),
            (
              'Retrying',
              'Connection lost. Retrying.',
              IntakeAction.retryNow,
              IntakeTone.operational,
            ),
          );
          checkCopy(value);
        }
      }
      for (final (ApiFailure, String, IntakeAction, IntakeTone) row
          in <(ApiFailure, String, IntakeAction, IntakeTone)>[
            (
              const ApiFailure('image_codec_unavailable', status: 503),
              'Format not supported yet. Photo kept.',
              IntakeAction.retry,
              IntakeTone.operational,
            ),
            (
              const ApiFailure(
                'detail',
                code: 'image_codec_unsupported',
                status: 422,
              ),
              'Format not supported yet. Photo kept.',
              IntakeAction.retry,
              IntakeTone.operational,
            ),
            (
              const ApiFailure('detail', code: 'intake_sensitivity_mismatch'),
              'Saved earlier with another setting. Photo kept.',
              IntakeAction.dismiss,
              IntakeTone.operational,
            ),
            for (final int status in <int>[400, 404, 409, 413, 415, 422])
              (
                ApiFailure('private detail', status: status),
                'Photo could not be used. Retake it.',
                IntakeAction.remove,
                IntakeTone.error,
              ),
          ]) {
        final IntakeStatus value = intakeStatus(
          photo(UploadState.failed, error: row.$1),
        );
        expect(
          (value.reason, value.action, value.tone),
          (row.$2, row.$3, row.$4),
        );
        checkCopy(value);
      }
      for (final int status in <int>[401, 403]) {
        final IntakeStatus value = intakeStatus(
          photo(
            UploadState.failed,
            error: ApiFailure('private detail', status: status),
          ),
        );
        expect(
          (value.status, value.reason, value.tone),
          ('Ready', null, IntakeTone.neutral),
        );
      }
    },
  );

  test(
    'local refusal catalogue uses the exact words and one Remove action',
    () {
      const Map<IntakeRefusal, String> reasons = {
        IntakeRefusal.empty: 'Empty file. Choose another.',
        IntakeRefusal.tooLarge: 'Over 25 MB. Choose a smaller photo.',
        IntakeRefusal.format: 'Use JPEG, PNG, HEIC, TIFF or DNG.',
        IntakeRefusal.resolution: 'Over 40 megapixels. Choose a smaller photo.',
        IntakeRefusal.unreadable: 'Could not read this photo. Choose it again.',
      };
      for (final row in reasons.entries) {
        final IntakeStatus value = intakeStatus(
          photo(UploadState.skipped, refusal: row.key),
        );
        expect(
          (value.status, value.reason, value.action, value.tone),
          ('Not added', row.value, IntakeAction.remove, IntakeTone.error),
        );
        checkCopy(value);
      }
    },
  );

  test('stopped and restored photos use their exact short reason', () {
    final ManifestEntry ready = photo(UploadState.ready)
      ..reason = intakeStoppedReason;
    expect(intakeStatus(ready).reason, 'Stopped. Send to continue.');
    final ManifestEntry restored = ManifestEntry.restored(
      digest: 'a' * 64,
      handle: {'upload_id': 'saved'},
    );
    expect(restored.label, 'Unfinished photo');
    expect(intakeStatus(restored).reason, 'Choose this photo again.');
    checkCopy(intakeStatus(restored));
    expect(intakeSignedOutReason, 'Signed out. Sign in to keep sending.');
    expect(intakeRestoreError, 'Earlier photos could not be restored.');
  });

  test(
    'summary has required order, omits zeros and meets the example budget',
    () {
      final List<ManifestEntry> entries = [
        for (var i = 0; i < 12; i++) photo(UploadState.inMainQueue),
        for (var i = 0; i < 3; i++) photo(UploadState.uploading),
        for (var i = 0; i < 2; i++) photo(UploadState.failed),
      ];
      expect(intakeBatchSummary(entries), '2 to fix · 3 sending · 12 sent');
      expect(
        intakeBatchSummary(entries).split(RegExp(r'\s+')).length,
        lessThanOrEqualTo(10),
      );
      expect(intakeBatchSummary([]), 'No photos');
      expect(
        intakeBatchSummary([], sent: 12, duplicates: 2),
        '12 sent · 2 duplicate',
      );
      expect(
        intakeBatchSummary([
          photo(
            UploadState.processingBlocked,
            summary: saved(
              'processing_blocked',
              blocker: 'sensitive_record_not_processed',
            ),
          ),
        ]),
        '1 held',
      );
    },
  );

  test('dense summary preserves all six counts rather than hiding outcomes', () {
    // All six prescribed labels need 13 words (18 with standalone separators).
    // This cannot meet the simultaneous ten-word requirement without omissions.
    final List<ManifestEntry> entries = [
      photo(UploadState.duplicate),
      photo(UploadState.inMainQueue),
      photo(UploadState.processing, summary: saved('pending')),
      photo(UploadState.ready),
      photo(
        UploadState.processingBlocked,
        summary: saved(
          'processing_blocked',
          blocker: 'sensitive_record_not_processed',
        ),
      ),
      photo(UploadState.failed),
    ];
    expect(
      intakeBatchSummary(entries),
      '1 to fix · 1 held · 1 ready · 1 sending · 1 sent · 1 duplicate',
    );
    expect(intakeBatchSummary(entries), isNot(contains('Intake queue')));
  });
  test(
    'departure text counts sent photos and duplicates without conflating them',
    () {
      expect(intakeDepartureLine(1), '1 photo sent');
      expect(intakeDepartureLine(3), '3 photos sent');
      expect(intakeDepartureLine(0, duplicates: 1), '1 duplicate');
      expect(
        intakeDepartureLine(2, duplicates: 1),
        '2 photos sent · 1 duplicate',
      );
      expect(intakeDepartureLine(0), '');
    },
  );
  test(
    'pending start follows the offered action even with a retained blocker',
    () {
      final Json summary = saved('pending', blocker: 'previous_hold');
      expect(intakeStartOffered(Specimen(summary)), isTrue);
      expect(
        intakeStatus(photo(UploadState.processing, summary: summary)).status,
        'Starting',
      );
    },
  );
}
