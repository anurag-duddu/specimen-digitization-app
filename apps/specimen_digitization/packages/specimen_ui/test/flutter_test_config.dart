/// Loads the bundled faces before any test in this package runs.
///
/// Without this a golden renders in the platform sans, which is exactly the v1
/// defect 10 section 7 names. The faces are registered under the prefixed
/// family names Flutter resolves a package font under, because that is what
/// `UiType` asks for.
library;

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'font_loading.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  await UiFonts.loadForTest(loadPackageFont);
  await testMain();
}
