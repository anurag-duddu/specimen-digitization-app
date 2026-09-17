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

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Where the package's assets sit, relative to the application root, which is
/// where `flutter test` runs.
const String _packageRoot = 'packages/specimen_ui';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  // Loading a font needs a binding, and creating the test binding installs an
  // `HttpOverrides` that answers every request with a mock 400
  // (`flutter_test/src/_binding_io.dart`). That guard exists to stop a widget
  // test reaching the network, and this application has no widget that does:
  // there is no `Image.network` and no `NetworkImage` anywhere in `lib/`.
  // What it would break instead is the suite's real work: the access and
  // protected-HTTP tests bind a loopback server and talk to it, and under the
  // mock every one of them reports "The request did not complete".
  //
  // So the override in place before the binding was created is put back once
  // the faces are loaded. Every test file then sees the HTTP behaviour it saw
  // before this file existed.
  final HttpOverrides? before = HttpOverrides.current;
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
  await _loadPhosphor();

  HttpOverrides.global = before;
  await testMain();
}

/// Loads the Phosphor faces `UiIcons` draws with.
///
/// Nothing on a screen uses them yet; the screens move to `UiIcons` in waves 2
/// and 3. Loading them now means the first screen golden that draws one shows
/// the glyph rather than a box, so the diff that lands with the icon sweep is
/// about the icon rather than about the harness.
///
/// They come out of the asset bundle rather than off disk, because they are a
/// dependency's assets rather than this application's, and they register under
/// the prefixed family name `PhosphorIconData` asks for.
Future<void> _loadPhosphor() async {
  for (final MapEntry<String, String> face in PhosphorFonts.families.entries) {
    final FontLoader loader = FontLoader(PhosphorFonts.prefixed(face.key));
    loader.addFont(rootBundle.load(PhosphorFonts.bundlePath(face.value)));
    await loader.load();
  }
}
