import 'package:camera/camera.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';

void main() {
  for (final code in [
    'CameraAccessDenied',
    'CameraAccessDeniedWithoutPrompt',
    'CameraAccessRestricted',
  ]) {
    test('$code is reported as unavailable camera permission', () async {
      final camera = PlatformCaptureCamera(
        cameras: () async => throw CameraException(code, 'Unavailable'),
      );
      await expectLater(
        camera.start(),
        throwsA(
          isA<CaptureCameraUnavailable>().having(
            (failure) => failure.kind,
            'kind',
            CaptureUnavailable.permission,
          ),
        ),
      );
      await camera.dispose();
    });
  }
}
