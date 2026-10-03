import 'package:specimen_digitization/src/widgets/field_row.dart';
import 'package:specimen_digitization/src/widgets/selection_bar.dart';
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
      (widget is UiListRow && widget.title == label) ||
      widget.key == ValueKey<String>('mobile-nav-${label.toLowerCase()}') ||
      (widget is Pressable && widget.semanticsLabel == label),
  description: 'navigation destination "$label"',
);

/// A persistent record view tab, by its accessibility name.
Finder uiRecordView(String label) => find.byWidgetPredicate(
  (Widget widget) => widget is Pressable && widget.semanticsLabel == label,
  description: 'record view tab "$label"',
);

/// The button labelled [label].
Finder uiButton(String label) => find.widgetWithText(UiButton, label);

/// The text input whose label is [label].
///
/// A field publishes its label as a property rather than as a child, because
/// the frame draws it beside the box. `UiTextArea` builds a `UiField` with
/// the same label, so this matches the box either way and `enterText` reaches
/// the editor inside it; [uiTextArea] is how a test reaches the area's own
/// widget.
Finder uiField(Pattern label) => find.byWidgetPredicate(
  (Widget widget) => widget is UiField && _names(label, widget.label),
  description: 'field labelled "$label"',
);

/// The multi-line input whose label is [label].
Finder uiTextArea(Pattern label) => find.byWidgetPredicate(
  (Widget widget) => widget is UiTextArea && _names(label, widget.label),
  description: 'UiTextArea("$label")',
);

/// The chip labelled [label].
Finder uiChip(Pattern label) => find.byWidgetPredicate(
  (Widget widget) => widget is UiChip && _names(label, widget.label),
  description: 'UiChip("$label")',
);

/// The select whose label is [label].
Finder uiSelect(Pattern label) => find.byWidgetPredicate(
  (Widget widget) => widget is UiSelect && _names(label, widget.label),
  description: 'UiSelect("$label")',
);

/// The disclosure titled [title].
Finder uiDisclosure(Pattern title) => find.byWidgetPredicate(
  (Widget widget) => widget is UiDisclosure && _names(title, widget.title),
  description: 'UiDisclosure("$title")',
);

/// Opens the supporting label editor after a label has been selected.
Future<void> openLabelCorrection(WidgetTester tester) async {
  final labelView = uiRecordView('Label review');
  if (labelView.evaluate().isNotEmpty) {
    await tester.ensureVisible(labelView);
    await tester.tap(labelView);
    await tester.pumpAndSettle();
  }
  if (uiField('Accepted label text').evaluate().isNotEmpty) return;
  final disclosure = uiDisclosure('Correct label transcription');
  expect(disclosure, findsOneWidget);
  final trigger = find
      .descendant(
        of: disclosure,
        matching: find.byWidgetPredicate(
          (widget) =>
              widget is Pressable &&
              widget.semanticsLabel == 'Correct label transcription',
        ),
      )
      .first;
  await tester.ensureVisible(trigger);
  await tester.tap(trigger);
  await tester.pumpAndSettle();
  expect(uiField('Accepted label text'), findsOneWidget);
}

/// The tab strip whose accessibility name is [label].
Finder uiTabs(String label) => find.byWidgetPredicate(
  (Widget widget) => widget is UiTabs && widget.semanticsLabel == label,
  description: 'UiTabs("$label")',
);

/// The modal pane a `showUiSheet`, `showUiDialog` or `showUiModal` opened.
///
/// The frame is private to the package, so the pane is the last glass surface
/// on screen: the route above the page paints after everything in it.
Finder uiModalPane() => find.byType(GlassSurface).last;

/// Opens the select labelled [label] and picks the option reading [option].
///
/// A select is a control with a popover, not a form field with a menu on it:
/// pressing it opens the list, and the option is a row inside that list.
Future<void> pickUiSelect(
  WidgetTester tester,
  Pattern label,
  String option,
) async {
  final Finder select = uiSelect(label);
  expect(select, findsOneWidget);
  // UiSelect also contains its field frame/label. Only the actual trigger's
  // Pressable is a hit target; the full widget's centre can be empty space.
  final Finder trigger = find.descendant(
    of: select,
    matching: find.byWidgetPredicate(
      (Widget widget) => widget is Pressable && widget.onPressed != null,
    ),
  );
  expect(trigger, findsOneWidget);
  await tester.ensureVisible(trigger);
  await tester.pumpAndSettle();
  expect(trigger.hitTestable(), findsOneWidget);
  await tester.tap(trigger);
  await tester.pumpAndSettle();
  final Finder filter = find.byWidgetPredicate(
    (Widget widget) =>
        widget is FieldCore && widget.semanticsLabel == 'Filter the options',
  );
  if (filter.evaluate().isNotEmpty) {
    expect(filter, findsOneWidget);
    await tester.enterText(filter, option);
    await tester.pumpAndSettle();
  }
  final Finder row = find.byWidgetPredicate(
    (Widget widget) => widget is UiListRow && widget.title == option,
    description: 'select option "$option"',
  );
  expect(row, findsOneWidget);
  await tester.ensureVisible(row);
  await tester.pumpAndSettle();
  expect(row.hitTestable(), findsOneWidget);
  await tester.tap(row);
  await tester.pumpAndSettle();
}

/// True when the modal on screen is the sheet form rather than the dialog.
///
/// A sheet meets the bottom of the window and fills its width; a dialog
/// floats clear of both (10 section 4.3).
bool modalIsSheet(WidgetTester tester) {
  final Rect pane = tester.getRect(find.byType(GlassSurface).last);
  final Size window = tester.view.physicalSize / tester.view.devicePixelRatio;
  return pane.bottom >= window.height - 1 && pane.left <= 1;
}

/// Expands the requested field when necessary, then opens its real layer editor.
/// A previously expanded row stays open; repeated corrections must not close it.
Future<void> openFieldEditor(
  WidgetTester tester,
  int index, {
  String layer = 'as written',
}) async {
  final Finder row = find.byType(FieldRow).at(index);
  final Finder disclosure = find.descendant(
    of: row,
    matching: find.byType(UiDisclosure),
  );
  final Finder edit = find.descendant(
    of: row,
    matching: uiIconButton(RegExp('^Edit $layer')),
  );
  if (edit.evaluate().isEmpty) {
    expect(disclosure, findsOneWidget);
    await tester.ensureVisible(disclosure);
    await tester.pumpAndSettle();
    final Finder header = find
        .descendant(
          of: disclosure,
          matching: find.byWidgetPredicate(
            (Widget widget) => widget is Pressable && widget.onPressed != null,
          ),
        )
        .first;
    await tester.tap(header);
    await tester.pumpAndSettle();
  }
  expect(edit, findsOneWidget);
  await tester.ensureVisible(edit);
  await tester.pumpAndSettle();
  expect(edit.hitTestable(), findsOneWidget);
  await tester.tap(edit);
  await tester.pumpAndSettle();
}

/// Reveals selection with a row's long press, without leaving a row selected.
Future<void> enterSpecimenSelection(WidgetTester tester) async {
  final row = find.byType(SelectableRow).first;
  await tester.ensureVisible(row);
  await tester.longPress(row);
  await tester.pumpAndSettle();
  await tester.tap(find.descendant(of: row, matching: find.byType(UiCheckbox)));
  await tester.pumpAndSettle();
}

/// Chooses a core specimen view by its accessible radio control.
Future<void> pickSpecimenQueue(WidgetTester tester, String option) async {
  final value = switch (option) {
    'Needs review' || 'Needs a human' => 'needs_human_review',
    'Deferred' => 'deferred',
    'Completed' || 'Cleared' => 'cleared',
    _ => throw ArgumentError.value(
      option,
      'option',
      'Not a core specimen view',
    ),
  };
  final filter = find.byKey(ValueKey<String>('queue-filter-$value'));
  await tester.ensureVisible(filter);
  await tester.tap(filter);
  await tester.pumpAndSettle();
}
