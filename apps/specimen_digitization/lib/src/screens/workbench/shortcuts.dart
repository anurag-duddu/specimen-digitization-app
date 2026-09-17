/// The workbench keyboard map (screen blueprints, 6.8; responsive 4).
///
/// `Shortcuts` plus `Actions` rather than `CallbackShortcuts`, because an
/// intent has to be able to do nothing when the server does not permit it,
/// and an action that is disabled is not the same as a key that is unbound.
///
/// The digit and letter bindings are unmodified by design, which is only safe
/// because every form in this screen lives in its own route: `EditableText`
/// consumes character keys before they can reach an ancestor `Shortcuts`, and
/// the reason sheet is an overlay entry rather than a descendant of this
/// subtree. Do not wrap a form in this map.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../widgets/widgets.dart';

/// Moves to the next specimen in the queue.
class NextSpecimenIntent extends Intent {
  const NextSpecimenIntent();
}

/// Moves to the previous specimen in the queue.
class PreviousSpecimenIntent extends Intent {
  const PreviousSpecimenIntent();
}

/// Selects the nth label region, one based.
class SelectRegionIntent extends Intent {
  const SelectRegionIntent(this.index);

  /// The region's one based position in the region list.
  final int index;
}

/// Shows one of the evidence segments.
class ShowSegmentIntent extends Intent {
  const ShowSegmentIntent(this.index);

  /// The segment's position in the selector.
  final int index;
}

/// Magnifies the photograph one step.
class ZoomInIntent extends Intent {
  const ZoomInIntent();
}

/// Reduces the magnification one step.
class ZoomOutIntent extends Intent {
  const ZoomOutIntent();
}

/// Returns the view to the whole photograph.
class FitViewIntent extends Intent {
  const FitViewIntent();
}

/// Turns the view a quarter turn.
class RotateViewIntent extends Intent {
  const RotateViewIntent();
}

/// Opens the approval reason sheet.
class ApproveIntent extends Intent {
  const ApproveIntent();
}

/// Opens the coverage reason sheet.
class ConfirmCoverageIntent extends Intent {
  const ConfirmCoverageIntent();
}

/// Lists the shortcuts.
class ShowShortcutsIntent extends Intent {
  const ShowShortcutsIntent();
}

/// One row of the shortcut list, and the binding it documents.
typedef ShortcutEntry = ({String keys, String action});

/// The map, in the order the help sheet prints it.
///
/// `Ctrl` and `Cmd` combinations with `+`, `-`, `0`, `R`, `F`, `W`, `T`, `S`,
/// `P` and `D` are deliberately absent: a browser takes those before the page
/// ever sees them (responsive 4).
const List<ShortcutEntry> workbenchShortcutHelp = <ShortcutEntry>[
  (keys: 'J', action: 'Next specimen'),
  (keys: 'K', action: 'Previous specimen'),
  (keys: '1 to 9', action: 'Select label region'),
  (keys: 'R', action: 'Readings'),
  (keys: 'F', action: 'Fields'),
  (keys: 'H', action: 'History'),
  (keys: 'Plus', action: 'Zoom in'),
  (keys: 'Minus', action: 'Zoom out'),
  (keys: '0', action: 'Fit the whole photograph'),
  (keys: 'Shift and R', action: 'Rotate the view 90 degrees'),
  (keys: 'C', action: 'Confirm label coverage'),
  (keys: 'A', action: 'Approve record'),
  (keys: 'Question mark', action: 'This list'),
];

/// The bindings themselves.
Map<ShortcutActivator, Intent>
workbenchShortcuts() => <ShortcutActivator, Intent>{
  const SingleActivator(LogicalKeyboardKey.keyJ): const NextSpecimenIntent(),
  const SingleActivator(LogicalKeyboardKey.keyK):
      const PreviousSpecimenIntent(),
  const SingleActivator(LogicalKeyboardKey.bracketRight):
      const NextSpecimenIntent(),
  const SingleActivator(LogicalKeyboardKey.bracketLeft):
      const PreviousSpecimenIntent(),
  for (final (int i, LogicalKeyboardKey key) in _digits.indexed)
    SingleActivator(key): SelectRegionIntent(i + 1),
  const SingleActivator(LogicalKeyboardKey.keyR): const ShowSegmentIntent(0),
  const SingleActivator(LogicalKeyboardKey.keyF): const ShowSegmentIntent(1),
  const SingleActivator(LogicalKeyboardKey.keyH): const ShowSegmentIntent(2),
  const SingleActivator(LogicalKeyboardKey.keyR, shift: true):
      const RotateViewIntent(),
  const SingleActivator(LogicalKeyboardKey.equal): const ZoomInIntent(),
  const SingleActivator(LogicalKeyboardKey.add): const ZoomInIntent(),
  const SingleActivator(LogicalKeyboardKey.minus): const ZoomOutIntent(),
  const SingleActivator(LogicalKeyboardKey.digit0): const FitViewIntent(),
  const SingleActivator(LogicalKeyboardKey.keyA): const ApproveIntent(),
  const SingleActivator(LogicalKeyboardKey.keyC): const ConfirmCoverageIntent(),
  const SingleActivator(LogicalKeyboardKey.slash, shift: true):
      const ShowShortcutsIntent(),
};

const List<LogicalKeyboardKey> _digits = <LogicalKeyboardKey>[
  LogicalKeyboardKey.digit1,
  LogicalKeyboardKey.digit2,
  LogicalKeyboardKey.digit3,
  LogicalKeyboardKey.digit4,
  LogicalKeyboardKey.digit5,
  LogicalKeyboardKey.digit6,
  LogicalKeyboardKey.digit7,
  LogicalKeyboardKey.digit8,
  LogicalKeyboardKey.digit9,
];

/// Shows the shortcut list.
Future<void> showShortcutSheet(BuildContext context) => showAdaptiveModal<void>(
  context,
  title: shortcutSheetTitle,
  body: (BuildContext formContext) => const _ShortcutList(),
  primaryAction: (BuildContext formContext) => UiButton(
    label: shortcutSheetClose,
    autofocus: true,
    onPressed: () => Navigator.of(formContext).pop(),
  ),
);

/// The sheet's own title.
const String shortcutSheetTitle = 'Keyboard shortcuts';

/// The way out of it.
const String shortcutSheetClose = 'Close the shortcut list';

/// The map, one row per binding, each key drawn as a cap.
class _ShortcutList extends StatelessWidget {
  const _ShortcutList();

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          for (final ShortcutEntry entry in workbenchShortcutHelp)
            MergeSemantics(
              child: Padding(
                padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s1),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    // The caps take the width their own labels need at this
                    // text scale, rather than a column measured by eye: at
                    // 200 percent "Shift" alone is wider than the column
                    // this row used to reserve (11 section 2.2).
                    _Caps(keys: entry.keys),
                    SizedBox(width: ui.space.s3),
                    Expanded(child: Text(entry.action, style: ui.type.body)),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// One binding, drawn as the keys it is pressed with.
///
/// The help table is written in words, because a screen reader reads the
/// words and a caption has to say "Question mark" rather than "?". The caps
/// print the key and keep the word on the semantics node, which is what
/// `UiKeyCap.semanticsLabel` is for.
class _Caps extends StatelessWidget {
  const _Caps({required this.keys});

  final String keys;

  /// The word a shortcut is written with, and the key a cap prints.
  static const Map<String, String> printed = <String, String>{
    'Plus': '+',
    'Minus': '-',
    'Question mark': '?',
  };

  /// The words that join two caps rather than naming one.
  static const List<String> joiners = <String>[' and ', ' to '];

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final List<Widget> parts = <Widget>[];
    for (final String joiner in joiners) {
      if (!keys.contains(joiner)) continue;
      final List<String> sides = keys.split(joiner);
      for (final (int i, String side) in sides.indexed) {
        if (i > 0) {
          parts
            ..add(SizedBox(width: ui.space.s1))
            ..add(
              Text(
                joiner.trim(),
                style: ui.type.labelSmall.copyWith(
                  color: ui.color.inkSecondary,
                ),
              ),
            )
            ..add(SizedBox(width: ui.space.s1));
        }
        parts.add(_cap(side));
      }
      return Row(mainAxisSize: MainAxisSize.min, children: parts);
    }
    return _cap(keys);
  }

  Widget _cap(String word) => UiKeyCap(
    label: printed[word] ?? word,
    semanticsLabel: printed.containsKey(word) ? word : null,
  );
}
