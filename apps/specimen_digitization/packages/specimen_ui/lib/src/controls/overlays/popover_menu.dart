/// The overflow menu (10 section 4.3, `UiPopoverMenu`).
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/popover.dart';
import '../../primitives/pressable.dart';

/// One command in a [UiPopoverMenu].
///
/// A value rather than a widget, because a menu owns its own layout: the
/// glyph column, the label column and the shortcut column line up across every
/// item, which they cannot do if each item paints itself.
@immutable
class UiMenuItem {
  /// Binds [label] to [onSelected].
  ///
  /// [onSelected] null disables the item, and [disabledReason] then says why
  /// in the reviewer's words (03 section 3.6).
  const UiMenuItem({
    required this.label,
    required this.onSelected,
    this.icon,
    this.shortcut,
    this.destructive = false,
    this.disabledReason,
  });

  /// The visible label. Verb first, two to four words (02 section 4.3).
  final String label;

  /// What choosing the item does. Null disables it.
  final VoidCallback? onSelected;

  /// The glyph at the start of the row. Drawn at 20.
  final IconSpec? icon;

  /// The keyboard shortcut, set in `mono.identifier` at the end of the row.
  final String? shortcut;

  /// True for an item that supersedes or discards work.
  ///
  /// Tints the label and the glyph with `status.blocked.content`. Colour is
  /// never the only signal: a destructive item still reads as a verb that says
  /// what it does (02 section 4.4).
  final bool destructive;

  /// Why the item cannot be chosen.
  final String? disabledReason;

  /// True when the item responds to input.
  bool get enabled => onSelected != null;
}

/// The resolved paint of one menu.
@immutable
class UiPopoverMenuStyle {
  /// Binds every token a menu draws with.
  const UiPopoverMenuStyle({
    required this.radius,
    required this.itemRadius,
    required this.panePadding,
    required this.itemPadding,
    required this.itemHeight,
    required this.minWidth,
    required this.maxWidth,
    required this.gap,
    required this.label,
    required this.shortcut,
    required this.foreground,
    required this.shortcutColor,
  });

  /// The pane's corner radius: `radius.tile`.
  final double radius;

  /// An item's corner radius, nested inside the pane.
  final double itemRadius;

  /// Padding inside the pane, around the item column.
  final EdgeInsetsGeometry panePadding;

  /// Padding inside one item.
  final EdgeInsetsGeometry itemPadding;

  /// An item's height, from density.
  final double itemHeight;

  /// The narrowest a menu may be.
  final double minWidth;

  /// The widest a menu may be before its labels wrap.
  final double maxWidth;

  /// The gap between a glyph and its label.
  final double gap;

  /// The label's type role.
  final TextStyle label;

  /// The shortcut's type role.
  final TextStyle shortcut;

  /// The label and glyph colour, by state.
  final WidgetStateProperty<Color> foreground;

  /// The shortcut's colour. Quieter than the label: it is a reminder, not the
  /// command.
  final Color shortcutColor;

  /// The style a menu draws with in [ui], with a [destructive] item tinted.
  static UiPopoverMenuStyle resolve(
    UiThemeData ui, {
    bool destructive = false,
  }) {
    Color text(Set<WidgetState> states) {
      if (states.contains(WidgetState.disabled)) {
        return ui.color.disabledContent;
      }
      return destructive ? ui.color.status.blocked.content : ui.color.ink;
    }

    return UiPopoverMenuStyle(
      radius: ui.shape.tile,
      itemRadius: ui.shape.nested(ui.shape.tile, ui.space.s2),
      panePadding: EdgeInsetsDirectional.all(ui.space.s2),
      itemPadding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s3),
      itemHeight: ui.density.rowHeight,
      minWidth: minPaneWidth,
      maxWidth: maxPaneWidth,
      gap: ui.space.s3,
      label: ui.type.label,
      shortcut: ui.type.mono.identifier,
      foreground: WidgetStateProperty.resolveWith(text),
      shortcutColor: ui.color.inkTertiary,
    );
  }

  /// The narrowest a menu is drawn, so a two word command does not produce a
  /// pane the reviewer has to aim at.
  static const double minPaneWidth = 200;

  /// The widest a menu is drawn. A label longer than this wraps rather than
  /// pushing the pane across the window.
  static const double maxPaneWidth = 320;
}

/// A menu of commands anchored to a trigger.
///
/// Retires `MenuAnchor`, `PopupMenuButton` and `showMenu`. Submenus are not
/// supported: a menu that needs a second level is a screen.
///
/// [child] is the trigger and [controller] opens and closes the menu, so a
/// caller that already has a control of its own keeps it. [UiMenuTrigger] is
/// the convenience for a caller that does not.
class UiPopoverMenu extends StatefulWidget {
  /// Anchors [items] to [child], under [controller].
  const UiPopoverMenu({
    super.key,
    required this.controller,
    required this.items,
    required this.child,
    this.semanticsLabel,
    this.placement = PopoverPlacement.auto,
    this.style,
  });

  /// Opens and closes the menu.
  final PopoverController controller;

  /// The commands, in the order they are read.
  final List<UiMenuItem> items;

  /// What the menu itself is called, for a screen reader.
  ///
  /// Optional, and normally left null: the pane's role already announces it as
  /// a menu and its items are visible text, so a label repeating the trigger's
  /// would be read twice. Set it where a window has more than one menu open
  /// at different times and the reviewer has to tell them apart.
  final String? semanticsLabel;

  /// The trigger. Focus returns here when the menu closes.
  final Widget child;

  /// Where the menu sits relative to the trigger.
  final PopoverPlacement placement;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiPopoverMenuStyle? style;

  @override
  State<UiPopoverMenu> createState() => _UiPopoverMenuState();
}

class _UiPopoverMenuState extends State<UiPopoverMenu> {
  List<FocusNode> _nodes = <FocusNode>[];

  @override
  void initState() {
    super.initState();
    _syncNodes();
  }

  @override
  void didUpdateWidget(UiPopoverMenu oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.items.length != widget.items.length) _syncNodes();
  }

  @override
  void dispose() {
    _disposeNodes();
    super.dispose();
  }

  void _disposeNodes() {
    for (final FocusNode node in _nodes) {
      node.dispose();
    }
  }

  void _syncNodes() {
    _disposeNodes();
    _nodes = <FocusNode>[
      for (int i = 0; i < widget.items.length; i++)
        FocusNode(debugLabel: 'UiMenuItem $i'),
    ];
  }

  /// The index the reviewer is on, or minus one before they move.
  int get _focused => _nodes.indexWhere((FocusNode node) => node.hasFocus);

  /// Moves focus by [step], skipping disabled items and wrapping at the ends.
  ///
  /// Wrapping is the WAI-ARIA menu pattern: Down on the last item returns to
  /// the first, so a reviewer holding Down never lands outside the menu.
  void _move(int step) {
    if (_nodes.isEmpty) return;
    final int start = _focused;
    int index = start < 0 ? (step > 0 ? -1 : 0) : start;
    for (int tried = 0; tried < _nodes.length; tried++) {
      index = (index + step) % _nodes.length;
      if (index < 0) index += _nodes.length;
      if (widget.items[index].enabled) {
        _nodes[index].requestFocus();
        return;
      }
    }
  }

  void _choose(UiMenuItem item) {
    widget.controller.close();
    item.onSelected?.call();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiPopoverMenuStyle style =
        widget.style ?? UiPopoverMenuStyle.resolve(ui);
    final UiPopoverMenuStyle destructive = UiPopoverMenuStyle.resolve(
      ui,
      destructive: true,
    );
    final int first = widget.items.indexWhere((UiMenuItem item) => item.enabled);
    return Popover(
      controller: widget.controller,
      placement: widget.placement,
      radius: style.radius,
      overlayBuilder: (BuildContext context) => Shortcuts(
        shortcuts: const <ShortcutActivator, Intent>{
          SingleActivator(LogicalKeyboardKey.arrowDown): _MenuMoveIntent(1),
          SingleActivator(LogicalKeyboardKey.arrowUp): _MenuMoveIntent(-1),
        },
        child: Actions(
          actions: <Type, Action<Intent>>{
            _MenuMoveIntent: CallbackAction<_MenuMoveIntent>(
              onInvoke: (_MenuMoveIntent intent) {
                _move(intent.step);
                return null;
              },
            ),
          },
          child: Semantics(
            container: true,
            explicitChildNodes: true,
            role: SemanticsRole.menu,
            label: widget.semanticsLabel,
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minWidth: style.minWidth,
                maxWidth: style.maxWidth,
              ),
              child: Padding(
                padding: style.panePadding,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    for (int i = 0; i < widget.items.length; i++)
                      _MenuItem(
                        item: widget.items[i],
                        style: widget.items[i].destructive
                            ? destructive
                            : style,
                        focusNode: _nodes[i],
                        autofocus: i == first,
                        onChosen: () => _choose(widget.items[i]),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
      child: widget.child,
    );
  }
}

/// A trigger that opens a [UiPopoverMenu].
///
/// The convenience for the common case: a glyph the reviewer presses to get a
/// list of commands. A caller that already owns its trigger uses
/// [UiPopoverMenu] directly. Retires `PopupMenuButton`.
class UiMenuTrigger extends StatefulWidget {
  /// A trigger labelled [semanticsLabel] that opens [items].
  const UiMenuTrigger({
    super.key,
    required this.items,
    required this.semanticsLabel,
    this.icon,
    this.label,
    this.menuLabel,
    this.placement = PopoverPlacement.auto,
  });

  /// The commands the menu offers.
  final List<UiMenuItem> items;

  /// What the trigger is called. Required, because the trigger is usually a
  /// glyph with no visible text (10 section 11).
  final String semanticsLabel;

  /// The glyph on the trigger. Defaults to the overflow glyph.
  final IconSpec? icon;

  /// A visible label beside the glyph, where the trigger has room for one.
  final String? label;

  /// What the menu itself is called. Normally null: see
  /// [UiPopoverMenu.semanticsLabel].
  final String? menuLabel;

  /// Where the menu sits relative to the trigger.
  final PopoverPlacement placement;

  @override
  State<UiMenuTrigger> createState() => _UiMenuTriggerState();
}

class _UiMenuTriggerState extends State<UiMenuTrigger> {
  final PopoverController _controller = PopoverController();

  @override
  void initState() {
    super.initState();
    _controller.addListener(_openChanged);
  }

  @override
  void dispose() {
    _controller
      ..removeListener(_openChanged)
      ..dispose();
    super.dispose();
  }

  void _openChanged() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return UiPopoverMenu(
      controller: _controller,
      items: widget.items,
      placement: widget.placement,
      semanticsLabel: widget.menuLabel,
      child: Pressable(
        semanticsLabel: widget.semanticsLabel,
        onPressed: _controller.toggle,
        capsule: true,
        selected: _controller.isOpen,
        builder: (BuildContext context, Set<WidgetState> states) =>
            ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: ui.density.controlHeight,
                minWidth: ui.density.controlHeight,
              ),
              child: Padding(
                padding: EdgeInsetsDirectional.symmetric(
                  horizontal: widget.label == null ? 0 : ui.space.s4,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: <Widget>[
                    UiIcon(
                      widget.icon ?? UiIcons.more,
                      color: ui.color.ink,
                    ),
                    if (widget.label != null) ...<Widget>[
                      SizedBox(width: ui.space.s2),
                      Flexible(
                        child: Text(
                          widget.label!,
                          style: ui.type.label.copyWith(color: ui.color.ink),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
      ),
    );
  }
}

/// One row of a menu.
///
/// Menu specific rather than a `UiListRow`: the shortcut column, the
/// destructive tint and the choose-then-close behaviour belong to a menu and
/// to nothing else.
class _MenuItem extends StatelessWidget {
  const _MenuItem({
    required this.item,
    required this.style,
    required this.focusNode,
    required this.autofocus,
    required this.onChosen,
  });

  final UiMenuItem item;
  final UiPopoverMenuStyle style;
  final FocusNode focusNode;
  final bool autofocus;
  final VoidCallback onChosen;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    // The row publishes its own node so that it carries the menu item role,
    // which `Pressable` has no enum member for. `Pressable` is told to
    // publish nothing, which is what its `excludeFromSemantics` is for.
    return Semantics(
      container: true,
      excludeSemantics: true,
      role: SemanticsRole.menuItem,
      button: true,
      label: item.label,
      value: item.shortcut,
      hint: item.enabled ? null : item.disabledReason,
      enabled: item.enabled,
      focusable: item.enabled,
      onTap: item.enabled ? onChosen : null,
      child: Pressable(
        semanticsLabel: item.label,
        onPressed: item.enabled ? onChosen : null,
        disabledReason: item.disabledReason,
        radius: style.itemRadius,
        focusNode: focusNode,
        autofocus: autofocus,
        // The row is as tall as the hit box and as wide as the pane, so the
        // pressable never adds slop of its own around it.
        minHitBox: 0,
        excludeFromSemantics: true,
        builder: (BuildContext context, Set<WidgetState> states) {
          final Color foreground = style.foreground.resolve(states);
          return ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: style.itemHeight < UiDensity.hitBox
                  ? UiDensity.hitBox
                  : style.itemHeight,
            ),
            child: Padding(
              padding: style.itemPadding,
              child: Row(
                children: <Widget>[
                  if (item.icon != null) ...<Widget>[
                    UiIcon(
                      item.icon!,
                      size: UiIconSize.inline,
                      color: foreground,
                    ),
                    SizedBox(width: style.gap),
                  ],
                  Expanded(
                    child: Text(
                      item.label,
                      style: style.label.copyWith(color: foreground),
                    ),
                  ),
                  if (item.shortcut != null) ...<Widget>[
                    SizedBox(width: style.gap),
                    Text(
                      item.shortcut!,
                      style: style.shortcut.copyWith(
                        color: states.contains(WidgetState.disabled)
                            ? ui.color.disabledContent
                            : style.shortcutColor,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

/// Moving the reviewer up or down the item list.
@immutable
class _MenuMoveIntent extends Intent {
  const _MenuMoveIntent(this.step);

  /// Plus one for Down, minus one for Up.
  final int step;
}
