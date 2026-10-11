import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/capture/capture_camera.dart';

import '../test/verification/capture_app.dart' as capture_app;

Future<void> _pumpUntil(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 30),
}) async {
  final int attempts = timeout.inMilliseconds ~/ 250;
  for (int attempt = 0; attempt < attempts; attempt++) {
    await tester.pump(const Duration(milliseconds: 250));
    if (finder.evaluate().isNotEmpty) return;
  }
  fail('Timed out waiting for the expected integration-test control.');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('installed app reaches the native camera path', (
    WidgetTester tester,
  ) async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await capture_app.main();
    await _pumpUntil(
      tester,
      find.byKey(const ValueKey<String>('intake-take-photograph')),
    );
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('intake-take-photograph')),
    );

    if (defaultTargetPlatform == TargetPlatform.iOS) {
      // Apple simulators do not expose camera hardware. Reaching this product
      // explanation proves that the installed app invoked the native camera
      // plugin and handled its real simulator result without crashing.
      await _pumpUntil(tester, find.text('Use device camera'));
      expect(find.text(CaptureUnavailable.noCamera.message), findsOneWidget);
      expect(find.text('Cancel'), findsOneWidget);
      return;
    }

    // Android emulators expose a virtual camera. Permission is granted by the
    // device harness before this test so the widget runner can remain inside
    // the application while exercising actual plugin capture.
    await _pumpUntil(
      tester,
      find.byKey(const ValueKey<String>('capture-shutter')),
    );
    await tester.tap(find.byKey(const ValueKey<String>('capture-shutter')));
    await _pumpUntil(
      tester,
      find.byKey(const ValueKey<String>('capture-send')),
    );
    expect(
      find.byKey(const ValueKey<String>('capture-rotate')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey<String>('capture-crop')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey<String>('capture-send')));
    await _pumpUntil(
      tester,
      find.byKey(const ValueKey<String>('capture-shutter')),
    );
    await tester.tap(find.byKey(const ValueKey<String>('capture-auto-ingest')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey<String>('capture-shutter')));
    await _pumpUntil(tester, find.text('2 photographs in this batch'));

    await tester.tap(find.text('Done'));
    await _pumpUntil(tester, find.text('Intake queue'));
    await _pumpUntil(tester, find.text('Uploaded'));
    expect(find.text('Uploaded'), findsNWidgets(2));
  });
}
