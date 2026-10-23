import 'package:file_selector/file_selector.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_screen.dart';

import 'bulk_intake_test.dart' show BulkFixtureRepository;
import 'capture_screen_test.dart' show FakeCaptureCamera;
import 'widgets/harness.dart';

class ReplacementController extends BulkIntakeController {
  ReplacementController()
    : super(
        repository: BulkFixtureRepository(1),
        scope: const CollectionScope(
          organizationId: 'org',
          collectionId: 'collection',
          name: 'Collection',
        ),
        userId: 'owner',
      ) {
    items = [
      const IntakeDraftItem({
        'id': 'original',
        'filename': 'original.png',
        'state': 'ready',
        'photo_sensitive': true,
      }),
    ];
  }

  List<XFile> replacements = [];
  String? replacedId;
  bool? replacementSensitive;

  @override
  Future<void> addFiles(
    List<XFile> files, {
    bool camera = false,
    bool sensitive = false,
    String? replacesId,
    Object? captureAttempt,
  }) async {
    replacements = files;
    replacedId = replacesId;
    replacementSensitive = sensitive;
  }
}

void main() {
  for (final cancel in [false, true]) {
    testWidgets(
      'retake camera fallback ${cancel ? 'cancellation keeps original' : 'selects one replacement with identity and sensitivity'}',
      (tester) async {
        final controller = ReplacementController();
        addTearDown(controller.dispose);
        var pickerCalls = 0;
        var closed = false;
        final replacement = XFile('replacement.png');
        await pumpComponent(
          tester,
          BulkPhotoInspector(
            controller: controller,
            initialId: 'original',
            cameraFactory: () async =>
                FakeCaptureCamera(unavailable: CaptureUnavailable.noCamera),
            pickReplacementFile: () async {
              pickerCalls++;
              return cancel ? null : replacement;
            },
            onClose: () => closed = true,
          ),
          size: const Size(800, 900),
        );
        await tester.tap(find.text('Retake photo'));
        await tester.pumpAndSettle();
        expect(find.text('No camera found.'), findsOneWidget);
        await tester.tap(find.text('Choose files'));
        await tester.pumpAndSettle();
        expect(pickerCalls, 1);
        expect(closed, !cancel);
        expect(controller.items.single.id, 'original');
        if (cancel) {
          expect(controller.replacements, isEmpty);
          expect(controller.replacedId, isNull);
        } else {
          expect(controller.replacements, [replacement]);
          expect(controller.replacedId, 'original');
          expect(controller.replacementSensitive, isTrue);
        }
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
      },
    );
  }
}
