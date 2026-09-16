/// Reads a font asset off disk for a test.
///
/// `rootBundle` in a test binding resolves the application's asset manifest,
/// which does not exist when the package is tested on its own, so the files
/// are read from the package directory instead. The path is relative to the
/// package root, which is where `flutter test` runs.
library;

import 'dart:io';
import 'dart:typed_data';

/// The bytes of [asset], a path relative to the package root.
Future<ByteData> loadPackageFont(String asset) async {
  final File file = File(asset);
  if (!file.existsSync()) {
    throw StateError(
      'the font asset $asset is missing. Goldens would render in the platform '
      'sans, which is the v1 defect 10 section 7 names.',
    );
  }
  return ByteData.sublistView(await file.readAsBytes());
}
