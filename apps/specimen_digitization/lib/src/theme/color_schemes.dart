/// The two Material 3 `ColorScheme`s, derived from the design system.
///
/// Nothing is generated from a seed any more. `UiThemeData.toColorScheme()`
/// maps the v2 roles in 09 section 3.1 onto the Material slots the
/// infrastructure widgets read, and the mapping lives in the package beside
/// the roles it maps.
library;

import 'package:flutter/material.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The light scheme.
ColorScheme lightColorScheme() => UiThemeData.light().toColorScheme();

/// The dark scheme.
ColorScheme darkColorScheme() => UiThemeData.dark().toColorScheme();
