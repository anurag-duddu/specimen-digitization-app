/// The adaptive collection shell (responsive and platform adaptation, section
/// 2; screen blueprints, sections 1.2, 1.3 and 11).
///
/// One navigation component per window class: a bottom bar below 600, a
/// collapsed rail to 839, an extended rail to 1199, and a permanent drawer at
/// 1200 and above. The collection switcher and the account menu move with it.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../models.dart';
import '../theme/icons.dart';
import '../vocabulary.dart';
import '../widgets/widgets.dart';
import '../workspace.dart';
import 'routes.dart';

/// The navigation frame every collection screen is drawn inside.
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.destination, required this.child});

  /// The destination the current route belongs to.
  final WorkspaceDestination destination;

  /// The routed screen.
  final Widget child;

  /// The widest the app bar's collection dropdown may grow.
  static const double switcherMaxWidth = 280;

  /// The permanent drawer's width, from the Material navigation drawer spec.
  static const double drawerWidth = 360;

  void _select(BuildContext context, WorkspaceDestination next) {
    if (next == destination) return;
    final WorkspaceController controller = WorkspaceScope.read(context);
    final String? key = controller.defaultRouteKey;
    if (key == null) return;
    context.go(
      next == WorkspaceDestination.queue
          ? AppRoutes.queueOf(key)
          : AppRoutes.intakeOf(key),
    );
  }

  @override
  Widget build(BuildContext context) {
    final WorkspaceController controller = WorkspaceScope.of(context);
    final WindowClass window = WindowClass.of(context);
    final bool drawer = window.isAtLeast(WindowClass.large);
    final bool rail = !drawer && window.isAtLeast(WindowClass.medium);
    final bool extended = rail && window.isAtLeast(WindowClass.expanded);

    return Scaffold(
      appBar: _appBar(context, controller, window),
      bottomNavigationBar: window.isCompact
          ? NavigationBar(
              selectedIndex: destination.index,
              onDestinationSelected: (int index) =>
                  _select(context, WorkspaceDestination.values[index]),
              destinations: const <Widget>[
                NavigationDestination(
                  icon: Icon(Symbols.inventory_2),
                  label: 'Queue',
                ),
                NavigationDestination(
                  icon: Icon(Symbols.add_photo_alternate),
                  label: 'Intake',
                ),
              ],
            )
          : null,
      body: Column(
        children: <Widget>[
          EnvironmentBanner(environment: controller.environment),
          _BlockerNotice(blockers: controller.repository.blockers),
          _ErrorBanner(error: controller.error),
          _ProgressRow(
            busy:
                controller.loading ||
                controller.mutating ||
                controller.loadingMore,
          ),
          Expanded(
            child: Row(
              children: <Widget>[
                if (drawer)
                  _PermanentDrawer(
                    destination: destination,
                    onSelect: (WorkspaceDestination next) =>
                        _select(context, next),
                  )
                else if (rail)
                  NavigationRail(
                    selectedIndex: destination.index,
                    extended: extended,
                    // The words are drawn at medium, where the rail is
                    // collapsed. A destination whose label is hidden produces
                    // no semantics at all, so an icon-only rail is a pair of
                    // unnamed buttons in the accessibility tree. Flutter
                    // asserts that an extended rail carries no label type,
                    // which is why this is a branch rather than a constant.
                    labelType: extended
                        ? NavigationRailLabelType.none
                        : NavigationRailLabelType.all,
                    onDestinationSelected: (int index) =>
                        _select(context, WorkspaceDestination.values[index]),
                    destinations: const <NavigationRailDestination>[
                      NavigationRailDestination(
                        icon: Icon(Symbols.inventory_2),
                        label: Text('Queue'),
                      ),
                      NavigationRailDestination(
                        icon: Icon(Symbols.add_photo_alternate),
                        label: Text('Intake'),
                      ),
                    ],
                  ),
                // The routed screen is a nested `Navigator`, and a route's
                // modal barrier blocks the semantics of everything painted
                // before it inside the same semantics boundary. The shell's
                // own chrome, the environment band and this navigation, is
                // painted first, so without a boundary of its own the screen
                // erased all of it: a reviewer working through a browser's
                // accessibility tree found a queue with no navigation and no
                // way into a record.
                Expanded(
                  child: Semantics(
                    container: true,
                    explicitChildNodes: true,
                    child: child,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  PreferredSizeWidget _appBar(
    BuildContext context,
    WorkspaceController controller,
    WindowClass window,
  ) {
    final bool drawer = window.isAtLeast(WindowClass.large);
    final bool inlineSwitcher =
        !drawer &&
        window.isAtLeast(WindowClass.medium) &&
        controller.scopes.isNotEmpty;
    final bool named = window.isAtLeast(WindowClass.expanded) && !drawer;

    return AppBar(
      title: window.isCompact && controller.scopes.isNotEmpty
          ? _CompactTitle(controller: controller)
          : const Text('Specimen Digitization'),
      actions: <Widget>[
        if (inlineSwitcher)
          Padding(
            padding: EdgeInsets.symmetric(horizontal: context.space.space2),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: switcherMaxWidth),
              child: _CollectionDropdown(controller: controller),
            ),
          ),
        IconButton(
          onPressed: controller.loading
              ? null
              : () => unawaited(
                  controller.scope == null
                      ? controller.checkAccess()
                      : controller.refresh(),
                ),
          tooltip: 'Refresh collection',
          icon: const Icon(Symbols.refresh),
        ),
        if (named)
          _AccountMenu(controller: controller)
        else if (!drawer)
          IconButton(
            onPressed: () => unawaited(controller.signOut()),
            tooltip: 'Sign out',
            icon: const Icon(Symbols.logout),
          ),
        IconButton(
          onPressed: () => context.push(AppRoutes.help),
          tooltip: 'Help and shortcuts',
          icon: const Icon(Symbols.help),
        ),
      ],
    );
  }
}

/// The compact app bar title: the collection name, tapped to switch.
class _CompactTitle extends StatelessWidget {
  const _CompactTitle({required this.controller});

  final WorkspaceController controller;

  Future<void> _open(BuildContext context) async {
    final CollectionScope? chosen = await showModalBottomSheet<CollectionScope>(
      context: context,
      useSafeArea: true,
      showDragHandle: true,
      builder: (BuildContext sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Padding(
              padding: EdgeInsets.all(sheetContext.space.space4),
              child: Text(
                'Authorized collection',
                style: Theme.of(sheetContext).textTheme.titleMedium,
              ),
            ),
            for (final CollectionScope scope in controller.scopes)
              ListTile(
                title: Text(scope.name),
                selected: scope.key == controller.scope?.key,
                trailing: scope.key == controller.scope?.key
                    ? const Icon(Symbols.check)
                    : null,
                onTap: () => Navigator.pop(sheetContext, scope),
              ),
          ],
        ),
      ),
    );
    if (chosen != null && context.mounted) {
      context.go(AppRoutes.queueOf(encodeCollectionKey(chosen.key)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final String name = controller.scope?.name ?? 'Specimen Digitization';
    return Semantics(
      button: true,
      label: 'Collection $name. Switch collection',
      excludeSemantics: true,
      child: InkWell(
        onTap: () => _open(context),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: context.sizes.targetMin),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Flexible(child: Text(name, overflow: TextOverflow.ellipsis)),
              SizedBox(width: context.space.space1),
              const Icon(Symbols.arrow_drop_down),
            ],
          ),
        ),
      ),
    );
  }
}

/// The collection switcher, as a dropdown.
class _CollectionDropdown extends StatelessWidget {
  const _CollectionDropdown({required this.controller, this.dense = true});

  final WorkspaceController controller;
  final bool dense;

  @override
  Widget build(BuildContext context) => DropdownButtonFormField<String>(
    initialValue: controller.scope?.key,
    isExpanded: true,
    isDense: dense,
    decoration: const InputDecoration(labelText: 'Authorized collection'),
    items: <DropdownMenuItem<String>>[
      for (final CollectionScope scope in controller.scopes)
        DropdownMenuItem<String>(
          value: scope.key,
          child: Text(scope.name, overflow: TextOverflow.ellipsis),
        ),
    ],
    onChanged: controller.mutating
        ? null
        : (String? key) {
            if (key == null) return;
            context.go(AppRoutes.queueOf(encodeCollectionKey(key)));
          },
  );
}

/// The account menu: the display name, and signing out.
class _AccountMenu extends StatelessWidget {
  const _AccountMenu({required this.controller});

  final WorkspaceController controller;

  @override
  Widget build(BuildContext context) {
    final String name = controller.session.displayName;
    return PopupMenuButton<String>(
      tooltip: 'Account menu',
      onSelected: (_) => controller.signOut(),
      itemBuilder: (BuildContext context) => <PopupMenuEntry<String>>[
        PopupMenuItem<String>(enabled: false, child: Text(name)),
        const PopupMenuDivider(),
        const PopupMenuItem<String>(value: 'sign-out', child: Text('Sign out')),
      ],
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: context.sizes.targetMin,
          minWidth: context.sizes.targetMin,
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: context.space.space2),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Icon(Symbols.person),
              SizedBox(width: context.space.space1),
              Flexible(child: Text(name, overflow: TextOverflow.ellipsis)),
            ],
          ),
        ),
      ),
    );
  }
}

/// The permanent navigation drawer at large and extra large.
class _PermanentDrawer extends StatelessWidget {
  const _PermanentDrawer({required this.destination, required this.onSelect});

  final WorkspaceDestination destination;
  final ValueChanged<WorkspaceDestination> onSelect;

  @override
  Widget build(BuildContext context) {
    final WorkspaceController controller = WorkspaceScope.of(context);
    return SizedBox(
      width: AppShell.drawerWidth,
      child: NavigationDrawer(
        selectedIndex: destination.index,
        onDestinationSelected: (int index) =>
            onSelect(WorkspaceDestination.values[index]),
        children: <Widget>[
          Padding(
            padding: EdgeInsets.fromLTRB(
              context.space.space4,
              context.space.space4,
              context.space.space4,
              context.space.space2,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  'Specimen Digitization',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                SizedBox(height: context.space.space2),
                if (controller.scopes.isNotEmpty)
                  _CollectionDropdown(controller: controller, dense: false),
              ],
            ),
          ),
          const NavigationDrawerDestination(
            icon: Icon(Symbols.inventory_2),
            label: Text('Queue'),
          ),
          const NavigationDrawerDestination(
            icon: Icon(Symbols.add_photo_alternate),
            label: Text('Intake'),
          ),
          const Divider(),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: context.space.space4),
            child: Text(
              controller.session.displayName,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
          Padding(
            padding: EdgeInsets.all(context.space.space2),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: TextButton.icon(
                onPressed: () => controller.signOut(),
                icon: const Icon(Symbols.logout),
                label: const Text('Sign out'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The repository's own processing blockers, stated once, above the screen.
class _BlockerNotice extends StatelessWidget {
  const _BlockerNotice({required this.blockers});

  final List<dynamic> blockers;

  @override
  Widget build(BuildContext context) {
    final String named = blockers
        .map((dynamic blocker) => vocabularyLabel(blocker.toString()))
        .join(', ');
    // Height and opacity, so the screen below does not snap down the moment
    // the repository answers (motion catalog, row 10).
    return MotionReveal(
      visible: blockers.isNotEmpty,
      child: Padding(
        padding: EdgeInsets.all(context.space.space3),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Processing is blocked: $named.'),
            Text(
              'Ask your collection administrator to review it.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

/// The screen level error surface: one banner, one recovery action for the
/// failure class it is reporting (screen blueprints, section 11).
class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.error});

  final WorkspaceError? error;

  @override
  Widget build(BuildContext context) {
    final WorkspaceError? failure = error;
    // The banner arrives and leaves with the shared reveal rather than
    // snapping the layout, and it is never a snackbar: it carries a recovery
    // action and must persist until it is resolved (motion catalog, row 10).
    return MotionReveal(
      visible: failure != null,
      child: failure == null
          ? const SizedBox(width: double.infinity)
          : MaterialBanner(
              content: Semantics(
                liveRegion: true,
                child: Text(failure.message),
              ),
              leading: const Icon(Symbols.info),
              actions: <Widget>[
                TextButton(
                  onPressed: () => failure.action(),
                  child: Text(failure.actionLabel),
                ),
              ],
            ),
    );
  }
}

/// A four pixel row that is always occupied, so showing progress never moves
/// the screen (motion catalog, row 11).
///
/// The row keeps its height whether or not it is busy. The indicator itself is
/// built only while it is busy: an indeterminate indicator animates forever,
/// and an animation that never ends is an animation a test can never settle.
class _ProgressRow extends StatelessWidget {
  const _ProgressRow({required this.busy});

  final bool busy;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: context.space.space1,
    child: busy
        ? const LinearProgressIndicator(
            semanticsLabel: 'Loading collection data',
          )
        : null,
  );
}
