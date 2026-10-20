import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/capture/capture_screen.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/screens/intake/intake_status.dart';
import 'package:specimen_digitization/src/screens/intake/intake_transfer_session.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';

import 'capture_screen_test.dart' show FakeCaptureCamera;
import 'intake_layout_test.dart' show scope;
import 'intake_manifest_test.dart' show entryIn;
import 'widget_test.dart' show TestRepository;
import 'widgets/harness.dart';

final banned = RegExp(
  r'\b(Intake queue|main Queue|derivative|server offset|offset|classification|checksum|SHA-256|preflight|server check|codec|collection profile|runtime|batch|upload handle|Not calibrated|failed|invalid|please|sorry|we)\b',
  caseSensitive: false,
);

void expectPrimaryCopy(Finder root) {
  for (final element
      in find.descendant(of: root, matching: find.byType(Text)).evaluate()) {
    final text = element.widget as Text;
    final copy = text.data ?? text.textSpan!.toPlainText();
    expect(banned.hasMatch(copy), isFalse, reason: 'Primary text: $copy');
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  for (final state in UploadState.values) {
    testWidgets(
      'primary Intake and camera copy for $state excludes technical terms',
      (tester) async {
        final repo = TestRepository();
        await pumpComponent(
          tester,
          IntakeScreen(
            repository: repo,
            scope: scope,
            userId: 'copy',
            onComplete: () {},
          ),
        );
        final session = intakeTransferSession(repo, scope, 'copy');
        final entry = entryIn(state);
        session.entries.add(entry);
        session.changed();
        await tester.pumpAndSettle();
        expectPrimaryCopy(find.byType(IntakeScreen));
        await tester.pumpWidget(const SizedBox.shrink());
        forgetIntakeTransfers(repo, 'copy');
        await pumpComponent(
          tester,
          CaptureScreen(
            camera: () async => FakeCaptureCamera(),
            onCaptured: (_) {},
            statusLabel: intakeBatchSummary([entry]),
          ),
          size: const Size(390, 844),
        );
        expectPrimaryCopy(find.byType(CaptureScreen));
        await tester.pumpWidget(const SizedBox.shrink());
      },
    );
  }
}
