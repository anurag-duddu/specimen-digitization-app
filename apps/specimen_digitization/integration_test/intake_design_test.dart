// Native execution of the shipped Intake screen with in-memory inputs.
// Pickers, authentication, camera hardware and processing are not exercised.
import 'dart:ui' as ui;

import 'package:file_selector/file_selector.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart' show MaterialApp;
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/intake_photo.dart';
import 'package:specimen_digitization/src/widgets/upload_item.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../test/verification/ingestion_repository_fixture.dart';

class _NativeRepository extends PreviewRepository {
  Uint8List? sentBytes;

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) {
    sentBytes = file.bytes;
    return super.upload(scope, session, file, progress);
  }
}

Future<Uint8List> _photo() async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(
    const Rect.fromLTWH(0, 0, 1000, 520),
    Paint()..color = const Color(0xFFF6F1E1),
  );
  final paragraph = ui.ParagraphBuilder(ui.ParagraphStyle(fontSize: 36))
    ..pushStyle(ui.TextStyle(color: const Color(0xFF1B1A16)))
    ..addText(
      'SYNTHETIC TEST PHOTO\nNot museum data\n\nChicago 1912\nTeaching garden',
    );
  final label = paragraph.build()
    ..layout(const ui.ParagraphConstraints(width: 900));
  canvas.drawParagraph(label, const Offset(40, 30));
  final image = await recorder.endRecording().toImage(1000, 520);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  for (final dark in <bool>[false, true]) {
    testWidgets('native intake selection, preview and sending, dark=$dark', (
      tester,
    ) async {
      final bytes = await _photo();
      final repository = _NativeRepository();
      await tester.pumpWidget(
        MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: dark ? AppTheme.dark() : AppTheme.light(),
          home: UiScaffold(
            body: SafeArea(
              child: IntakeScreen(
                repository: repository,
                scope: previewScope,
                userId: 'synthetic-design-${dark ? 'dark' : 'light'}',
                onComplete: () {},
                pickImages: (_) async => [
                  XFile.fromData(
                    bytes,
                    path: 'synthetic-photo.png',
                    name: 'synthetic-photo.png',
                    mimeType: 'image/png',
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('intake-choose-files')));
      for (var attempt = 0; attempt < 100; attempt++) {
        await tester.pump(const Duration(milliseconds: 100));
        if (find.byType(IntakePhoto).evaluate().isNotEmpty) break;
      }
      await tester.pumpAndSettle();
      final photo = find.byType(IntakePhoto);
      expect(photo, findsOneWidget);
      expect(tester.widget<IntakePhoto>(photo).bytes, isNotNull);
      expect(find.text('Waiting to upload'), findsOneWidget);
      expect(photo.hitTestable(), findsOneWidget);
      final size = tester.view.physicalSize / tester.view.devicePixelRatio;
      expect(tester.getRect(photo).bottom, lessThan(size.height));
      final kind = size.width < 600 ? 'phone' : 'tablet';
      final mode = dark ? 'dark' : 'light';
      if (defaultTargetPlatform == TargetPlatform.android) {
        await binding.convertFlutterSurfaceToImage();
        await tester.pumpAndSettle();
      }
      await binding.takeScreenshot('intake-native-$kind-$mode');
      await tester.tap(photo);
      await tester.pumpAndSettle();
      expect(find.text('Photo preview'), findsOneWidget);
      final close = find.byWidgetPredicate(
        (widget) => widget is UiButton && widget.label == 'Close preview',
      );
      await tester.ensureVisible(close);
      await tester.tap(close);
      await tester.pumpAndSettle();
      expect(find.text('Photo preview'), findsNothing);
      final progress = find.text('Progress details');
      await tester.ensureVisible(progress);
      await tester.tap(progress);
      await tester.pumpAndSettle();
      expect(find.text('Upload: Waiting'), findsOneWidget);
      final send = find.byKey(const ValueKey('intake-upload'));
      await tester.ensureVisible(send);
      await tester.tap(send);
      for (var attempt = 0; attempt < 100; attempt++) {
        await tester.pump(const Duration(milliseconds: 100));
        final entry = tester
            .widget<IntakeManifest>(find.byType(IntakeManifest))
            .entries
            .single;
        if (entry.state == UploadState.accepted ||
            entry.state == UploadState.failed) {
          break;
        }
      }
      await tester.pumpAndSettle();
      final entry = tester
          .widget<IntakeManifest>(find.byType(IntakeManifest))
          .entries
          .single;
      expect(entry.state, UploadState.accepted, reason: entry.reason);
      expect(repository.sentBytes, bytes);
      expect(entry.file, isNull);
      expect(find.text('Waiting to start'), findsOneWidget);
      expect(find.text('In main Queue'), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpAndSettle();
    });
  }
}
