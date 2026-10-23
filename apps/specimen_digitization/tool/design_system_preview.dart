/// Backend-free native preview using the application's real theme and router.
///
/// Run with `flutter run -t tool/design_system_preview.dart -d <simulator>`.
/// Widgetbook remains the managed catalog; this entry point exercises the same
/// shared components in the existing native application host.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';

void main() {
  if (kReleaseMode) {
    throw UnsupportedError('Design previews require a debug or profile build.');
  }
  runApp(const SpecimenDigitizationApp(initialLocation: AppRoutes.gallery));
}
