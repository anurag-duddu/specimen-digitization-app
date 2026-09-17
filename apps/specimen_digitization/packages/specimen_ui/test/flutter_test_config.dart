/// Loads the bundled faces before any test in this package runs.
///
/// Without this a golden renders in the platform sans, which is exactly the v1
/// defect 10 section 7 names. The faces are registered under the prefixed
/// family names Flutter resolves a package font under, because that is what
/// `UiType` asks for.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'font_loading.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  await UiFonts.loadForTest(loadPackageFont);
  await loadPhosphorFonts();
  goldenFileComparator = PlatformGatedGoldenComparator(goldenFileComparator);
  await testMain();
}

/// Compares goldens on macOS and only renders them elsewhere.
///
/// Every golden in this package is generated on macOS, and Linux rasterises
/// the same fonts one to eleven percent differently, so a pixel comparison on
/// the CI runner fails on every file for no reason a reviewer can act on. The
/// application's screen goldens carry the same rule (`goldensCompare` in its
/// golden harness). Off macOS the golden is still rendered, so every layout,
/// overflow and semantics assertion in the same test has run; only the pixel
/// comparison is set aside, and `--update-goldens` refuses, so no golden is
/// ever written by a platform that did not draw the rest of the set.
///
/// `SPECIMEN_UI_GOLDENS=skip` in the environment forces the off macOS path,
/// which is how the path is exercised on a Mac.
class PlatformGatedGoldenComparator extends GoldenFileComparator {
  /// Wraps the comparator the test runner installed for the current file.
  PlatformGatedGoldenComparator(this.base);

  /// The runner's own comparator, which knows the test file's directory.
  final GoldenFileComparator base;

  static bool _noted = false;

  /// True where the pixels are meaningful.
  static bool get compares =>
      Platform.isMacOS && Platform.environment['SPECIMEN_UI_GOLDENS'] != 'skip';

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    if (compares) return base.compare(imageBytes, golden);
    if (!_noted) {
      _noted = true;
      debugPrint(
        'specimen_ui goldens are compared on macOS only; rendered and not '
        'compared on ${Platform.operatingSystem}.',
      );
    }
    return true;
  }

  @override
  Future<void> update(Uri golden, Uint8List imageBytes) {
    if (!compares) {
      throw StateError(
        'specimen_ui goldens are generated on macOS; refusing to write '
        '$golden from ${Platform.operatingSystem}.',
      );
    }
    return base.update(golden, imageBytes);
  }

  @override
  Uri getTestUri(Uri key, int? version) => base.getTestUri(key, version);
}
