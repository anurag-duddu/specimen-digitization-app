import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Layout assertions use the real bundled typefaces and Phosphor glyphs.
/// A test font's metrics would not describe the runnable Widgetbook previews.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  await UiFonts.loadForTest(
    (String asset) => rootBundle.load('packages/specimen_ui/$asset'),
  );
  for (final MapEntry<String, String> face in PhosphorFonts.families.entries) {
    final FontLoader loader = FontLoader(PhosphorFonts.prefixed(face.key));
    loader.addFont(rootBundle.load(PhosphorFonts.bundlePath(face.value)));
    await loader.load();
  }
  await testMain();
}
