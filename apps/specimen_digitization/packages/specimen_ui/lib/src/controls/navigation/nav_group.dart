/// Roving focus and the arrow keys for a group of destinations.
///
/// Internal to the navigation family: it is not exported from
/// `navigation.dart` and no screen names it. The pill, the rail and the
/// sidebar all need one focus stop per destination and arrow keys that move
/// between them (10 section 2 clause 3), and three copies of that would drift.
///
/// The keys follow the group's own axis: `Left` and `Right` on the pill,
/// `Up` and `Down` on the rail and the sidebar. 10 section 4.4 says the rail
/// carries "the same semantics and keys" as the pill, and this is the one
/// place the family departs from it. A vertical group that swallowed `Right`
/// would trap a keyboard reviewer in the rail instead of letting them move
/// into the content, and the WAI-ARIA tabs pattern makes the orientation's
/// own keys the required pair. The deviation is recorded in the closeout.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// Which way a group of destinations runs.
enum NavAxis {
  /// A row. Moves with `Left` and `Right`, mirrored under RTL.
  horizontal,

  /// A column. Moves with `Up` and `Down`.
  vertical,
}

/// Gives a group of destinations one focus node each and moves between them
/// with the arrow keys of [axis].
///
/// Focus wraps at both ends, which is the tab list convention: a reviewer
/// holding `Right` cycles rather than falling out of the navigation. Arrows
/// move focus only; `Enter` and `Space` select, and those belong to the
/// destination itself through `Pressable`.
class NavGroup extends StatefulWidget {
  /// Builds [length] destinations, handing [builder] one focus node each.
  const NavGroup({
    super.key,
    required this.length,
    required this.axis,
    required this.builder,
  });

  /// How many destinations the group holds.
  final int length;

  /// Which way the group runs, and therefore which arrow keys move it.
  final NavAxis axis;

  /// Builds the group. The list holds one node per destination, in order.
  final Widget Function(BuildContext context, List<FocusNode> nodes) builder;

  @override
  State<NavGroup> createState() => _NavGroupState();
}

/// Moves focus [delta] destinations along the group.
@immutable
class _NavMoveIntent extends Intent {
  const _NavMoveIntent(this.delta);

  final int delta;
}

class _NavGroupState extends State<NavGroup> {
  final List<FocusNode> _nodes = <FocusNode>[];

  @override
  void initState() {
    super.initState();
    _resize();
  }

  @override
  void didUpdateWidget(NavGroup oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.length != widget.length) _resize();
  }

  @override
  void dispose() {
    for (final FocusNode node in _nodes) {
      node.dispose();
    }
    _nodes.clear();
    super.dispose();
  }

  void _resize() {
    while (_nodes.length > widget.length) {
      _nodes.removeLast().dispose();
    }
    while (_nodes.length < widget.length) {
      _nodes.add(
        FocusNode(debugLabel: 'NavGroup destination ${_nodes.length}'),
      );
    }
  }

  /// Moves focus [delta] places from whichever destination holds it.
  ///
  /// With nothing in the group focused the first destination takes it, so a
  /// reviewer who tabs into the group and presses an arrow lands somewhere
  /// rather than nowhere.
  void _move(int delta) {
    if (_nodes.isEmpty) return;
    final int from = _nodes.indexWhere(
      (FocusNode node) => node.hasPrimaryFocus,
    );
    if (from < 0) {
      _nodes.first.requestFocus();
      return;
    }
    _nodes[(from + delta) % _nodes.length].requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    // Read at build rather than inside the action so the group rebuilds if
    // the direction changes under it.
    final bool mirrored =
        widget.axis == NavAxis.horizontal &&
        Directionality.of(context) == TextDirection.rtl;
    return Shortcuts(
      shortcuts: widget.axis == NavAxis.horizontal ? _horizontal : _vertical,
      child: Actions(
        actions: <Type, Action<Intent>>{
          _NavMoveIntent: CallbackAction<_NavMoveIntent>(
            onInvoke: (_NavMoveIntent intent) {
              _move(mirrored ? -intent.delta : intent.delta);
              return null;
            },
          ),
        },
        child: widget.builder(context, List<FocusNode>.unmodifiable(_nodes)),
      ),
    );
  }

  static const Map<ShortcutActivator, Intent> _horizontal =
      <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.arrowLeft): _NavMoveIntent(-1),
        SingleActivator(LogicalKeyboardKey.arrowRight): _NavMoveIntent(1),
      };

  static const Map<ShortcutActivator, Intent> _vertical =
      <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.arrowUp): _NavMoveIntent(-1),
        SingleActivator(LogicalKeyboardKey.arrowDown): _NavMoveIntent(1),
      };
}
