// Finders for the design system's controls.
//
// `find.byTooltip` matches Material's `Tooltip` and nothing else, and
// `find.bySemanticsLabel` needs a semantics handle, so a test that only wants
// to press the reload control had to choose between a dependency on Material
// and a handle it has no other use for. These match the control itself, by the
// name it publishes.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// True when [name] is exactly [label], or matches it where it is a pattern.
bool _names(Pattern label, String name) =>
    label is RegExp ? label.hasMatch(name) : name == label;

/// The icon button whose accessibility name is [label].
Finder uiIconButton(Pattern label) => find.byWidgetPredicate(
  (Widget widget) =>
      widget is UiIconButton && _names(label, widget.semanticsLabel),
  description: 'UiIconButton("$label")',
);

/// Anything pressable whose accessibility name is [label].
///
/// An icon button, a menu trigger, a navigation disc, or a bare `Pressable`
/// such as the control at the end of a banner. Use it where the control's
/// class is not the point of the assertion.
Finder uiControl(Pattern label) => find.byWidgetPredicate(
  (Widget widget) =>
      (widget is Pressable && _names(label, widget.semanticsLabel)) ||
      (widget is UiIconButton && _names(label, widget.semanticsLabel)) ||
      (widget is UiMenuTrigger && _names(label, widget.semanticsLabel)),
  description: 'control named "$label"',
);

/// The menu trigger whose accessibility name is [label].
Finder uiMenuTrigger(Pattern label) => find.byWidgetPredicate(
  (Widget widget) =>
      widget is UiMenuTrigger && _names(label, widget.semanticsLabel),
  description: 'UiMenuTrigger("$label")',
);

/// Whatever carries [message] as its tooltip.
///
/// A navigation disc that draws no label publishes one, as does every icon
/// button, so this is how a test reaches a control the window class decided
/// to draw as a glyph alone.
Finder uiTooltipped(String message) => find.byWidgetPredicate(
  (Widget widget) => widget is UiTooltip && widget.message == message,
  description: 'UiTooltip("$message")',
);

/// The navigation destination named [label], in whichever navigation the
/// window class chose.
///
/// The pill and the collapsed rail draw a glyph and publish the name as a
/// tooltip; the extended rail draws the word under the glyph; the sidebar
/// draws a row titled with it.
Finder uiDestination(String label) => find.byWidgetPredicate(
  (Widget widget) =>
      (widget is UiTooltip && widget.message == label) ||
      (widget is UiListRow && widget.title == label),
  description: 'navigation destination "$label"',
);

/// The button labelled [label].
Finder uiButton(String label) => find.widgetWithText(UiButton, label);
