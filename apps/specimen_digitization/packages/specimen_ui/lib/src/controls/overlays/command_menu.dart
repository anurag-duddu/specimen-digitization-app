/// Searchable commands composed from owned fields and rows.
library;

import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../data/list_row.dart';
import '../inputs/search_field.dart';

/// One command. Its callback is the only action the menu performs.
@immutable
class UiCommand {
  /// A command with stable identity and a sentence-case label.
  const UiCommand({
    required this.id,
    required this.label,
    this.onSelected,
    this.description,
    this.group,
    this.icon,
    this.keywords = const <String>[],
    this.disabledReason,
    this.leading,
    this.shortcut,
  });

  /// Unique identity retained while filtering or reordering.
  final String id;

  /// Visible and spoken command name.
  final String label;

  /// Activates the command. Null leaves it visible but disabled.
  final VoidCallback? onSelected;

  /// Optional supporting description.
  final String? description;

  /// Group heading; items are grouped in first-appearance order.
  final String? group;

  /// Optional Phosphor registry icon.
  final IconSpec? icon;

  /// Additional searchable terms, not displayed.
  final List<String> keywords;

  /// Reason this command is unavailable.
  final String? disabledReason;

  /// Avatar, status dot or integration mark replacing the optional icon.
  final Widget? leading;

  /// Display-only shortcut hint. The host registers the actual command binding.
  final String? shortcut;
}

/// Search and keyboard navigation for an app's commands.
///
/// This is composable content, suitable for UiDialog, UiSheet or a fixed pane.
/// The host owns visibility, dismissal and focus restoration. Escape requests
/// [onDismiss]; selecting a result calls only its [UiCommand.onSelected]. Arrow
/// keys move real focus through enabled results, Enter activates, and typing in
/// the search field filters labels, descriptions, groups and keywords.
class UiCommandMenu extends StatefulWidget {
  /// Builds searchable commands within [maxHeight].
  const UiCommandMenu({
    super.key,
    required this.commands,
    required this.onDismiss,
    this.searchLabel = 'Search commands',
    this.clearLabel = 'Clear command search',
    this.hintText = 'Search commands…',
    this.emptyLabel = 'No matching commands',
    this.maxHeight = 440,
    this.autofocus = true,
    this.searchController,
    this.header,
    this.filters,
    this.footer,
  }) : assert(maxHeight > 0);

  /// Available commands with unique IDs.
  final List<UiCommand> commands;

  /// Requests dismissal on Escape. The host closes its route or pane.
  final VoidCallback onDismiss;

  /// Search field's accessible name.
  final String searchLabel;

  /// Search clear action's accessible name.
  final String clearLabel;

  /// Search placeholder.
  final String hintText;

  /// Empty-result message.
  final String emptyLabel;

  /// Maximum total height before results scroll.
  final double maxHeight;

  /// Focuses search when mounted.
  final bool autofocus;

  /// Optional host-owned query. Otherwise the menu owns and disposes one.
  final TextEditingController? searchController;

  /// Context or breadcrumb above search.
  final Widget? header;

  /// Caller-owned category filters beneath search.
  final Widget? filters;

  /// Keyboard guidance or secondary commands below results.
  final Widget? footer;

  @override
  State<UiCommandMenu> createState() => _UiCommandMenuState();
}

class _UiCommandMenuState extends State<UiCommandMenu> {
  final TextEditingController _ownedController = TextEditingController();
  final FocusNode _search = FocusNode(debugLabel: 'Command search');
  final Map<String, FocusNode> _nodes = <String, FocusNode>{};
  final Map<String, GlobalKey> _keys = <String, GlobalKey>{};
  TextEditingController get _controller =>
      widget.searchController ?? _ownedController;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_queryChanged);
  }

  @override
  void didUpdateWidget(UiCommandMenu oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.searchController != widget.searchController) {
      (oldWidget.searchController ?? _ownedController).removeListener(
        _queryChanged,
      );
      _controller.addListener(_queryChanged);
    }
  }

  void _queryChanged() => setState(() {});

  @override
  void dispose() {
    _controller.removeListener(_queryChanged);
    _ownedController.dispose();
    _search.dispose();
    for (final FocusNode node in _nodes.values) {
      node.dispose();
    }
    super.dispose();
  }

  List<UiCommand> get _visible {
    final List<String> words = _controller.text.trim().toLowerCase().split(
      RegExp(r'\s+'),
    );
    final Map<String?, List<UiCommand>> groups = <String?, List<UiCommand>>{};
    for (final UiCommand item in widget.commands) {
      final String text =
          '${item.label} ${item.description ?? ''} ${item.group ?? ''} ${item.keywords.join(' ')}'
              .toLowerCase();
      if (words.every(text.contains)) {
        (groups[item.group] ??= <UiCommand>[]).add(item);
      }
    }
    return groups.values.expand((List<UiCommand> group) => group).toList();
  }

  void _focus(UiCommand item) {
    _nodes[item.id]?.requestFocus();
    final BuildContext? rowContext = _keys[item.id]?.currentContext;
    if (rowContext != null) {
      unawaited(Scrollable.ensureVisible(rowContext, alignment: .5));
    }
  }

  void _activateFirst() {
    for (final UiCommand item in _visible) {
      if (item.onSelected != null) {
        item.onSelected!();
        return;
      }
    }
  }

  KeyEventResult _key(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }
    final LogicalKeyboardKey key = event.logicalKey;
    if (key == LogicalKeyboardKey.escape) {
      widget.onDismiss();
      return KeyEventResult.handled;
    }
    final List<UiCommand> enabled = _visible
        .where((UiCommand item) => item.onSelected != null)
        .toList();
    if (enabled.isEmpty) return KeyEventResult.ignored;
    final int index = enabled.indexWhere(
      (UiCommand item) => _nodes[item.id]?.hasFocus ?? false,
    );
    if (key == LogicalKeyboardKey.arrowDown) {
      _focus(enabled[index < 0 ? 0 : (index + 1) % enabled.length]);
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.arrowUp) {
      if (index == 0) {
        _search.requestFocus();
      } else {
        _focus(enabled[index < 0 ? enabled.length - 1 : index - 1]);
      }
      return KeyEventResult.handled;
    }
    // Home/End remain editing commands while the search field owns focus.
    if (index >= 0 &&
        (key == LogicalKeyboardKey.home || key == LogicalKeyboardKey.end)) {
      _focus(key == LogicalKeyboardKey.home ? enabled.first : enabled.last);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    assert(
      widget.commands.map((UiCommand item) => item.id).toSet().length ==
          widget.commands.length,
      'Command IDs must be unique.',
    );
    final UiThemeData ui = context.ui;
    final List<UiCommand> visible = _visible;
    return Focus(
      canRequestFocus: false,
      onKeyEvent: _key,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: widget.maxHeight),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            if (widget.header != null) ...[
              widget.header!,
              SizedBox(height: ui.space.s2),
            ],
            UiSearchField(
              label: widget.searchLabel,
              clearLabel: widget.clearLabel,
              hintText: widget.hintText,
              controller: _controller,
              focusNode: _search,
              autofocus: widget.autofocus,
              onSubmitted: (_) => _activateFirst(),
              onEscape: widget.onDismiss,
            ),
            SizedBox(height: ui.space.s2),
            if (widget.filters != null) ...[
              widget.filters!,
              SizedBox(height: ui.space.s2),
            ],
            Flexible(
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    if (visible.isEmpty)
                      Padding(
                        padding: EdgeInsets.all(ui.space.s4),
                        child: Semantics(
                          liveRegion: true,
                          child: Text(
                            widget.emptyLabel,
                            style: ui.type.body.copyWith(
                              color: ui.color.inkSecondary,
                            ),
                          ),
                        ),
                      ),
                    for (
                      int index = 0;
                      index < visible.length;
                      index++
                    ) ...<Widget>[
                      if (visible[index].group != null &&
                          (index == 0 ||
                              visible[index - 1].group != visible[index].group))
                        Padding(
                          padding: EdgeInsets.all(ui.space.s3),
                          child: Semantics(
                            header: true,
                            child: Text(
                              visible[index].group!,
                              style: ui.type.labelSmall.copyWith(
                                color: ui.color.inkSecondary,
                              ),
                            ),
                          ),
                        ),
                      UiListRow(
                        key: _keys.putIfAbsent(
                          visible[index].id,
                          GlobalKey.new,
                        ),
                        title: visible[index].label,
                        subtitle: visible[index].description,
                        leading:
                            visible[index].leading ??
                            (visible[index].icon == null
                                ? null
                                : UiIcon(
                                    visible[index].icon!,
                                    color: ui.color.inkSecondary,
                                  )),
                        trailing: visible[index].shortcut == null
                            ? null
                            : Text(
                                visible[index].shortcut!,
                                style: ui.type.labelSmall.copyWith(
                                  color: ui.color.inkSecondary,
                                ),
                              ),
                        onPressed: visible[index].onSelected,
                        disabledReason: visible[index].disabledReason,
                        focusNode: _nodes.putIfAbsent(
                          visible[index].id,
                          () => FocusNode(debugLabel: visible[index].label),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            if (widget.footer != null) ...[
              SizedBox(height: ui.space.s2),
              widget.footer!,
            ],
          ],
        ),
      ),
    );
  }
}
