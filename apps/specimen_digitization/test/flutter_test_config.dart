/// Loads Geist and Geist Mono before any test in the application runs.
///
/// Every screen golden renders in the product typeface because of this file.
/// The v1 goldens rendered in the platform sans, because the faces were never
/// bundled; a golden of the wrong typeface is evidence of nothing.
///
/// The faces are read out of the `specimen_ui` package directory rather than
/// through `rootBundle`, because a test binding has no asset manifest for a
/// dependency's fonts.
library;

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Where the package's assets sit, relative to the application root, which is
/// where `flutter test` runs.
const String _packageRoot = 'packages/specimen_ui';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  await UiFonts.loadForTest((String asset) async {
    final File file = File('$_packageRoot/$asset');
    if (!file.existsSync()) {
      throw StateError(
        'the font asset ${file.path} is missing. Every golden would render in '
        'the platform sans.',
      );
    }
    return ByteData.sublistView(await file.readAsBytes());
  });
  await testMain();
}
