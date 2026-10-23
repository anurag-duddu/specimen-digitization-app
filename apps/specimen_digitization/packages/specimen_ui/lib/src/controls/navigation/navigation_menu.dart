/// Structured application navigation with disclosure, sections and account slots.
library;

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/fit.dart';
import '../../primitives/pressable.dart';

/// A destination or expandable group in an application menu.
@immutable
class UiNavigationItem {
  /// IDs remain unique throughout the menu, including collapsed descendants.
  const UiNavigationItem({
    required this.id,
    required this.label,
    this.icon,
    this.badge,
    this.description,
    this.children = const [],
    this.enabled = true,
    this.disabledReason,
  });

  /// Stable route or group identity.
  final String id;

  /// Visible, accessible name.
  final String label;

  /// Optional Phosphor glyph.
  final IconSpec? icon;

  /// A count or short status; never the only name.
  final String? badge;

  /// Optional supporting context.
  final String? description;

  /// Child destinations. Nonempty items disclose these instead of navigating.
  final List<UiNavigationItem> children;

  /// Whether navigation or disclosure is available.
  final bool enabled;

  /// Explanation retained in disabled semantics.
  final String? disabledReason;
}

/// A labelled group of application destinations.
@immutable
class UiNavigationSection {
  /// Groups related items under an optional heading.
  const UiNavigationSection({this.label, required this.items});

  /// Optional accessible section heading.
  final String? label;

  /// Destination tree in reading order.
  final List<UiNavigationItem> items;
}

/// Sidebar menu content for desktop panes and mobile drawers.
///
/// Selection and expanded groups belong to the host. All content scrolls in
/// short windows, so header, navigation and footer remain reachable at 200%
/// text. A leading rail composes a dual-tier layout when space permits; below
/// 480 dp it stacks above the menu rather than squeezing destination labels.
class UiNavigationMenu extends StatefulWidget {
  /// Builds grouped navigation with optional search, feature and account slots.
  const UiNavigationMenu({
    super.key,
    required this.sections,
    required this.selectedId,
    required this.onSelected,
    required this.expandedIds,
    required this.onExpandedChanged,
    this.header,
    this.search,
    this.featured,
    this.footer,
    this.leadingRail,
    this.semanticsLabel = 'Application navigation',
  });

  /// Grouped destination trees.
  final List<UiNavigationSection> sections;

  /// Current leaf destination.
  final String? selectedId;

  /// Requests navigation to an enabled leaf.
  final ValueChanged<String> onSelected;

  /// Caller-owned expanded group IDs.
  final Set<String> expandedIds;

  /// Reports the complete proposed expanded set.
  final ValueChanged<Set<String>> onExpandedChanged;

  /// Brand and workspace switcher.
  final Widget? header;

  /// Search or command trigger.
  final Widget? search;

  /// Optional progress, image or contextual action card.
  final Widget? featured;

  /// Account, help and secondary navigation.
  final Widget? footer;

  /// Primary-tier rail; use the same selected-route state as the host.
  final Widget? leadingRail;

  /// Accessible landmark label.
  final String semanticsLabel;
  @override
  State<UiNavigationMenu> createState() => _UiNavigationMenuState();
}

class _NavigationEntry {
  const _NavigationEntry(this.item, this.depth, this.parent);
  final UiNavigationItem item;
  final int depth;
  final String? parent;
}

class _UiNavigationMenuState extends State<UiNavigationMenu> {
  final _nodes = <String, FocusNode>{};
  List<_NavigationEntry> get _visible {
    final rows = <_NavigationEntry>[];
    void visit(List<UiNavigationItem> items, int depth, String? parent) {
      for (final item in items) {
        rows.add(_NavigationEntry(item, depth, parent));
        if (widget.expandedIds.contains(item.id)) {
          visit(item.children, depth + 1, item.id);
        }
      }
    }

    for (final section in widget.sections) {
      visit(section.items, 0, null);
    }
    return rows;
  }

  @override
  void dispose() {
    for (final node in _nodes.values) {
      node.dispose();
    }
    super.dispose();
  }

  void _expand(UiNavigationItem item, bool value) {
    final next = {...widget.expandedIds};
    if (value) {
      next.add(item.id);
    } else {
      next.remove(item.id);
    }
    widget.onExpandedChanged(next);
  }

  void _activate(UiNavigationItem item) {
    if (!item.enabled) return;
    if (item.children.isNotEmpty) {
      _expand(item, !widget.expandedIds.contains(item.id));
    } else {
      widget.onSelected(item.id);
    }
  }

  void _focus(String id) {
    final node = _nodes[id];
    node?.requestFocus();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || node?.context == null) return;
      Scrollable.ensureVisible(node!.context!, alignment: .5);
    });
  }

  KeyEventResult _key(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }
    final rows = _visible;
    final current = rows.indexWhere(
      (row) => _nodes[row.item.id]?.hasFocus ?? false,
    );
    // Never steal editing keys from the optional search field.
    if (current < 0) return KeyEventResult.ignored;
    final key = event.logicalKey;
    if (key == LogicalKeyboardKey.arrowDown ||
        key == LogicalKeyboardKey.arrowUp) {
      final step = key == LogicalKeyboardKey.arrowDown ? 1 : -1;
      for (
        var next = current + step;
        next >= 0 && next < rows.length;
        next += step
      ) {
        if (rows[next].item.enabled) {
          _focus(rows[next].item.id);
          break;
        }
      }
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.home || key == LogicalKeyboardKey.end) {
      final destinations = rows.where((row) => row.item.enabled);
      if (destinations.isNotEmpty) {
        _focus(
          key == LogicalKeyboardKey.home
              ? destinations.first.item.id
              : destinations.last.item.id,
        );
      }
      return KeyEventResult.handled;
    }
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final forward = rtl
        ? LogicalKeyboardKey.arrowLeft
        : LogicalKeyboardKey.arrowRight;
    final backward = rtl
        ? LogicalKeyboardKey.arrowRight
        : LogicalKeyboardKey.arrowLeft;
    final row = rows[current];
    if (key == forward && row.item.enabled && row.item.children.isNotEmpty) {
      if (!widget.expandedIds.contains(row.item.id)) {
        _expand(row.item, true);
      } else {
        for (
          var next = current + 1;
          next < rows.length && rows[next].depth > row.depth;
          next++
        ) {
          if (rows[next].item.enabled) {
            _focus(rows[next].item.id);
            break;
          }
        }
      }
      return KeyEventResult.handled;
    }
    if (key == backward) {
      if (row.item.enabled && widget.expandedIds.contains(row.item.id)) {
        _expand(row.item, false);
      } else if (row.parent != null) {
        _focus(row.parent!);
      }
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final rows = _visible;
    return Semantics(
      container: true,
      explicitChildNodes: true,
      label: widget.semanticsLabel,
      child: Focus(
        canRequestFocus: false,
        onKeyEvent: _key,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final compact = constraints.maxWidth < 480;
            final body = SingleChildScrollView(
              child: Padding(
                padding: EdgeInsets.all(ui.space.s3),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (compact && widget.leadingRail != null) ...[
                      widget.leadingRail!,
                      SizedBox(height: ui.space.s3),
                    ],
                    if (widget.header != null) ...[
                      widget.header!,
                      SizedBox(height: ui.space.s4),
                    ],
                    if (widget.search != null) ...[
                      widget.search!,
                      SizedBox(height: ui.space.s3),
                    ],
                    for (final section in widget.sections) ...[
                      if (section.label != null)
                        Padding(
                          padding: EdgeInsets.all(ui.space.s2),
                          child: Semantics(
                            header: true,
                            child: Text(
                              section.label!,
                              style: ui.type.labelSmall.copyWith(
                                color: ui.color.inkSecondary,
                              ),
                            ),
                          ),
                        ),
                      for (final entry in rows.where(
                        (row) => _belongs(section.items, row.item.id),
                      ))
                        _row(entry),
                      SizedBox(height: ui.space.s3),
                    ],
                    if (widget.featured != null) ...[
                      widget.featured!,
                      SizedBox(height: ui.space.s3),
                    ],
                    if (widget.footer != null) widget.footer!,
                  ],
                ),
              ),
            );
            if (widget.leadingRail == null || compact) return body;
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Flexible(
                  flex: 1,
                  child: SingleChildScrollView(child: widget.leadingRail!),
                ),
                Expanded(flex: 3, child: body),
              ],
            );
          },
        ),
      ),
    );
  }

  bool _belongs(List<UiNavigationItem> items, String id) =>
      items.any((item) => item.id == id || _belongs(item.children, id));
  Widget _row(_NavigationEntry entry) {
    final ui = context.ui;
    final item = entry.item;
    final selected = item.id == widget.selectedId;
    final expanded = widget.expandedIds.contains(item.id);
    final ink = !item.enabled
        ? ui.color.disabledContent
        : selected
        ? ui.color.accent
        : ui.color.ink;
    return Padding(
      padding: EdgeInsetsDirectional.only(start: entry.depth * ui.space.s4),
      child: Semantics(
        expanded: item.children.isEmpty ? null : expanded,
        child: Pressable(
          semanticsLabel: [
            item.label,
            ?item.badge,
            ?item.description,
          ].join(', '),
          selected: selected,
          disabledReason: item.disabledReason,
          focusNode: _nodes.putIfAbsent(
            item.id,
            () => FocusNode(debugLabel: item.label),
          ),
          onPressed: item.enabled ? () => _activate(item) : null,
          builder: (context, states) => Container(
            decoration: BoxDecoration(
              color: selected ? ui.color.stateLayer(.06) : null,
              borderRadius: BorderRadius.circular(ui.shape.inner),
            ),
            padding: EdgeInsets.all(ui.space.s3),
            child: Row(
              children: [
                if (item.icon != null) ...[
                  UiIcon(item.icon!, color: ink),
                  SizedBox(width: ui.space.s3),
                ],
                Expanded(child: _itemContent(item, ink)),
                if (item.children.isNotEmpty)
                  Padding(
                    padding: EdgeInsetsDirectional.only(start: ui.space.s2),
                    child: UiIcon(
                      expanded ? UiIcons.collapse : UiIcons.expand,
                      color: ink,
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _itemContent(UiNavigationItem item, Color ink) {
    final ui = context.ui;
    final Widget copy = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(item.label, style: ui.type.label.copyWith(color: ink)),
        if (item.description != null)
          Text(
            item.description!,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
      ],
    );
    if (item.badge == null) return copy;
    final Widget badge = Text(
      item.badge!,
      style: ui.type.labelSmall.copyWith(color: ink),
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        final double labelRoom = math.min(
          ui.space.labelMin,
          measureLabel(context, item.label, ui.type.label).width,
        );
        final double badgeWidth = measureLabel(
          context,
          item.badge!,
          ui.type.labelSmall,
        ).width;
        if (labelRoom + ui.space.s2 + badgeWidth > constraints.maxWidth) {
          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              copy,
              SizedBox(height: ui.space.s1),
              badge,
            ],
          );
        }
        return Row(
          children: [
            Expanded(child: copy),
            SizedBox(width: ui.space.s2),
            badge,
          ],
        );
      },
    );
  }
}
