/// Adaptive collection navigation: native phone tabs and a spacious sidebar.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart' as material;
import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../administrator_contact.dart';
import '../models.dart';
import '../vocabulary.dart';
import '../widgets/widgets.dart';
import '../workspace.dart';
import 'routes.dart';

/// The navigation frame every collection screen is drawn inside.
class AppShell extends StatefulWidget {
  const AppShell({
    super.key,
    required this.destination,
    required this.child,
    this.specimens,
    this.specimensFocus,
    this.specimensActions,
    this.onSelectDestination,
  });

  /// The retained specimen list, full width on its route and inside the sidebar
  /// while a record is open. Its GlobalKey preserves search, selection and scroll.
  final Widget? specimens;
  final FocusNode? specimensFocus;
  final Widget? specimensActions;

  /// Restores the destination's retained branch after the leave guard passes.
  final ValueChanged<WorkspaceDestination>? onSelectDestination;

  /// The destination the current route belongs to.
  final WorkspaceDestination destination;

  /// The routed screen.
  final Widget child;

  /// The widest the sidebar's collection switcher may grow.
  static const double switcherMaxWidth = 280;

  /// What the collection switcher is called to a screen reader.
  static const String switcherLabel = 'Authorized collection';

  /// What the account control is called.
  static const String accountLabel = 'Account menu';

  /// What the help control is called, wherever it is drawn.
  static const String helpLabel = 'Help and shortcuts';

  /// What the reload control is called.
  static const String reloadLabel = 'Refresh collection';

  /// Accessible label for returning from a record to the specimen list.
  static const String backLabel = 'Back to specimens';

  /// The two destinations, in the order they are read.
  ///
  /// Sources is reached from Intake rather than from here (07 section 13), so
  /// it is not a third destination even though the registry has a glyph for
  /// it.
  static const List<UiNavDestination> destinations = <UiNavDestination>[
    UiNavDestination(label: 'Specimens', icon: UiIcons.queue),
    UiNavDestination(label: 'Intake', icon: UiIcons.intake),
  ];

  /// What the mark says where it leads the navigation.
  static const String markLabel = 'Specimen Digitization';

  /// The record [location] is inside, or null where it is a list screen.
  ///
  /// A record is the one route with a segment after `queue`, which is what
  /// `AppRoutes.specimenOf` builds.
  ///
  /// This predicate belongs beside `AppRoutes.isEntryLocation` and
  /// `isGlobalLocation` rather than here; `routes.dart` is not this slot's
  /// file, so it is written once here and the cleanup slot can move it.
  static String? recordIn(Uri location) {
    final List<String> segments = location.pathSegments;
    final int queue = segments.indexOf('queue');
    if (queue < 0 || queue >= segments.length - 1) return null;
    return Uri.decodeComponent(segments[queue + 1]);
  }

  /// True where [location] is inside a record.
  static bool insideRecord(Uri location) => recordIn(location) != null;

  /// Account actions live in the global rail, outside list toolbars.
  static bool accountInBar(WindowClass window) => false;

  /// Record toolbars also use the shared account control in the global rail.
  static bool accountOnRecordBar(WindowClass window) => false;

  /// Which sky the location paints (09 section 3.2).
  ///
  /// `sky.work` is the workbench, the region editor inside it, and the large
  /// record fallback; everything else in the collection, the queue, intake
  /// and the sources under it, is `sky.home`.
  static SkyPreset skyOf(Uri location) =>
      insideRecord(location) ? SkyPreset.work : SkyPreset.home;

  @override
  State<AppShell> createState() => _AppShellState();
}

/// Controls the same sidebar from page-level toolbars without adding another
/// navigation surface. The collection shell supplies this to all routed pages.
class AppSidebarScope extends InheritedWidget {
  const AppSidebarScope({
    super.key,
    required this.expanded,
    required this.overlay,
    required this.docked,
    this.mobileNavigation = false,
    this.mobileSpecimens,
    required this.toggle,
    required this.close,
    required super.child,
  });
  final bool expanded;
  final bool overlay;
  final bool docked;
  final bool mobileNavigation;

  /// The same list panel the desktop sidebar carries. On a phone it belongs
  /// to the Queue route below a record, so native Back reveals real content.
  final Widget? mobileSpecimens;
  final VoidCallback toggle;
  final VoidCallback close;
  static AppSidebarScope? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppSidebarScope>();
  @override
  bool updateShouldNotify(AppSidebarScope oldWidget) =>
      expanded != oldWidget.expanded ||
      overlay != oldWidget.overlay ||
      docked != oldWidget.docked ||
      mobileNavigation != oldWidget.mobileNavigation ||
      mobileSpecimens != oldWidget.mobileSpecimens;
}

class _AppShellState extends State<AppShell> {
  bool? _desktopExpanded;
  bool _mobileNavigation = false;
  bool _docked = false;
  bool _expanded = false;
  Size? _visibleSpecimensSize;
  final FocusNode _toggleFocus = FocusNode(
    debugLabel: 'Open workspace sidebar',
  );
  final FocusScopeNode _sidebarFocus = FocusScopeNode(
    debugLabel: 'Workspace sidebar',
    traversalEdgeBehavior: TraversalEdgeBehavior.parentScope,
  );
  FocusNode? _returnFocus;
  bool _selecting = false;

  @override
  void dispose() {
    _toggleFocus.dispose();
    _sidebarFocus.dispose();
    super.dispose();
  }

  void _toggle() => _expanded ? _close() : _open();

  void _open() {
    _returnFocus = FocusManager.instance.primaryFocus;
    setState(() {
      _desktopExpanded = true;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_expanded) return;
      if (AppShell.insideRecord(GoRouterState.of(context).uri)) {
        widget.specimensFocus?.requestFocus();
      } else {
        _sidebarFocus.requestFocus();
      }
    });
  }

  void _close() {
    final previous = _returnFocus;
    _returnFocus = null;
    setState(() {
      _desktopExpanded = false;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _expanded) return;
      if (previous?.context != null && previous!.canRequestFocus) {
        previous.requestFocus();
      } else {
        _toggleFocus.requestFocus();
      }
    });
  }

  Future<void> _select(WorkspaceDestination next) async {
    if (_selecting) return;
    final controller = WorkspaceScope.read(context);
    final key = controller.defaultRouteKey;
    final userId = controller.session.userId;
    if (key == null) return;
    final root = next == WorkspaceDestination.queue
        ? AppRoutes.queueOf(key)
        : AppRoutes.intakeOf(key);
    if (GoRouterState.of(context).uri.path == root) return;
    _selecting = true;
    try {
      if (!await controller.mayLeaveReview() ||
          !mounted ||
          !controller.session.signedIn ||
          controller.session.userId != userId ||
          controller.defaultRouteKey != key) {
        return;
      }
      final select = widget.onSelectDestination;
      if (select != null) {
        select(next);
      } else {
        context.go(root);
      }
    } finally {
      _selecting = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final controller = WorkspaceScope.of(context);
    final location = GoRouterState.of(context).uri;
    final record = AppShell.insideRecord(location);
    final listRoute =
        widget.destination == WorkspaceDestination.queue && !record;
    final busy =
        controller.loading ||
        controller.recordLoading ||
        controller.mutating ||
        controller.loadingMore;
    return LayoutBuilder(
      builder: (context, constraints) {
        final ui = context.ui;
        final scale = (MediaQuery.textScalerOf(context).scale(16) / 16).clamp(
          1.0,
          2.0,
        );
        _mobileNavigation =
            constraints.maxWidth < 768 * scale || constraints.maxHeight < 600;
        final navVisible =
            _mobileNavigation && MediaQuery.viewInsetsOf(context).bottom == 0;
        _docked = !_mobileNavigation;
        _expanded =
            listRoute ||
            (_docked &&
                (_desktopExpanded ?? constraints.maxWidth >= 1100 * scale));
        final railWidth = ui.space.s16 + MediaQuery.paddingOf(context).left;
        final sidebarWidth = math.min(
          (320 * scale / 8).ceil() * 8.0,
          math.max(0.0, constraints.maxWidth - railWidth - ui.space.s4),
        );
        final contentInset = _docked
            ? railWidth + (_expanded ? sidebarWidth : 0)
            : 0.0;
        final sidebar = _sidebar(
          context,
          controller,
          canClose: !listRoute && !_mobileNavigation,
          busy: busy,
        );
        return AppSidebarScope(
          expanded: _expanded,
          overlay: false,
          docked: _docked,
          mobileNavigation: _mobileNavigation,
          mobileSpecimens: _mobileNavigation ? sidebar : null,
          toggle: _toggle,
          close: _close,
          child: QueueWorkspaceScope(
            expanded: _expanded,
            showQueue: record && !_mobileNavigation ? _toggle : null,
            hideQueue: () {},
            child: CallbackShortcuts(
              bindings: <ShortcutActivator, VoidCallback>{
                if (_expanded && !listRoute && !_mobileNavigation)
                  const SingleActivator(LogicalKeyboardKey.escape): _close,
              },
              child: ColoredBox(
                color: ui.color.ground,
                child: Column(
                  children: <Widget>[
                    Expanded(
                      child: MediaQuery.removePadding(
                        context: context,
                        removeBottom: navVisible,
                        child: Stack(
                          fit: StackFit.expand,
                          children: <Widget>[
                            PositionedDirectional(
                              start: contentInset,
                              end: 0,
                              top: 0,
                              bottom: 0,
                              child: MediaQuery.removePadding(
                                context: context,
                                removeLeft: _docked,
                                child: UiScaffold(
                                  sky: AppShell.skyOf(location),
                                  header:
                                      _mobileNavigation &&
                                          widget.destination ==
                                              WorkspaceDestination.intake
                                      ? _mobileHeader(context, controller)
                                      : null,
                                  banner: _mobileNavigation && listRoute
                                      ? null
                                      : _Chrome(
                                          controller: controller,
                                          busy: busy,
                                          window: WindowClass.of(context),
                                        ),
                                  body: Semantics(
                                    container: true,
                                    explicitChildNodes: true,
                                    child: widget.child,
                                  ),
                                ),
                              ),
                            ),
                            if (_docked)
                              PositionedDirectional(
                                start: railWidth,
                                top: 0,
                                bottom: 0,
                                width: sidebarWidth,
                                child: Offstage(
                                  offstage: !_expanded,
                                  child: ExcludeFocus(
                                    excluding: !_expanded,
                                    child: ExcludeSemantics(
                                      excluding: !_expanded,
                                      child: FocusScope(
                                        node: _sidebarFocus,
                                        child: sidebar,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            if (_docked)
                              PositionedDirectional(
                                start: 0,
                                top: 0,
                                bottom: 0,
                                width: railWidth,
                                child: _rail(context, controller),
                              ),
                          ],
                        ),
                      ),
                    ),
                    if (navVisible) _mobileNav(context),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _mobileHeader(BuildContext context, WorkspaceController controller) =>
      SafeArea(
        bottom: false,
        child: Padding(
          padding: EdgeInsets.all(context.ui.space.s2),
          child: Row(
            children: <Widget>[
              Expanded(
                child: Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: _CollectionSwitcher(
                    controller: controller,
                    sheet: true,
                  ),
                ),
              ),
              if (EnvironmentBanner.showsBand(controller.environment))
                _EnvironmentContext(controller: controller, compact: true),
              ShellAccountMenu(controller: controller),
            ],
          ),
        ),
      );

  Widget _mobileNav(BuildContext context) {
    final ui = context.ui;
    final selected = widget.destination.index;
    Widget icon(int index) => UiIcon(
      AppShell.destinations[index].icon,
      key: ValueKey<String>(
        'mobile-nav-${AppShell.destinations[index].label.toLowerCase()}',
      ),
      current: index == selected,
      color: index == selected ? ui.color.ink : ui.color.inkSecondary,
    );
    void select(int index) => _select(WorkspaceDestination.values[index]);
    if (defaultTargetPlatform == TargetPlatform.iOS) {
      return cupertino.CupertinoTabBar(
        key: const ValueKey<String>('mobile-navigation'),
        currentIndex: selected,
        onTap: select,
        backgroundColor: ui.color.paper,
        activeColor: ui.color.ink,
        inactiveColor: ui.color.inkSecondary,
        height: math.max(56, 32 + MediaQuery.textScalerOf(context).scale(16)),
        items: <cupertino.BottomNavigationBarItem>[
          for (var i = 0; i < AppShell.destinations.length; i++)
            cupertino.BottomNavigationBarItem(
              icon: icon(i),
              label: AppShell.destinations[i].label,
            ),
        ],
      );
    }
    return material.NavigationBarTheme(
      data: material.NavigationBarThemeData(
        labelTextStyle: WidgetStatePropertyAll(
          ui.type.label.copyWith(color: ui.color.ink),
        ),
      ),
      child: material.NavigationBar(
        key: const ValueKey<String>('mobile-navigation'),
        animationDuration: ui.motion.navigationGlide,
        selectedIndex: selected,
        onDestinationSelected: select,
        backgroundColor: ui.color.paper,
        indicatorColor: ui.color.ink.withValues(alpha: .08),
        surfaceTintColor: GroundPalette.transparent,
        elevation: 0,
        destinations: <Widget>[
          for (var i = 0; i < AppShell.destinations.length; i++)
            material.NavigationDestination(
              icon: icon(i),
              label: AppShell.destinations[i].label,
            ),
        ],
      ),
    );
  }

  Widget _toggleButton() => UiIconButton(
    icon: UiIcons.sidebar,
    semanticsLabel: 'Open sidebar',
    focusNode: _toggleFocus,
    onPressed: () {
      _toggleFocus.requestFocus();
      FocusManager.instance.applyFocusChangesIfNeeded();
      _open();
    },
  );

  Widget _sidebar(
    BuildContext context,
    WorkspaceController controller, {
    required bool canClose,
    required bool busy,
  }) {
    final ui = context.ui;
    return DecoratedBox(
      key: ValueKey<String>(
        _mobileNavigation ? 'mobile-specimens' : 'global-sidebar',
      ),
      decoration: BoxDecoration(
        color: ui.color.paper,
        border: _mobileNavigation
            ? null
            : BorderDirectional(end: BorderSide(color: ui.color.boundary)),
      ),
      child: SafeArea(
        left: _mobileNavigation,
        right: _mobileNavigation,
        child: Padding(
          padding: EdgeInsets.only(
            bottom: _mobileNavigation
                ? MediaQuery.viewInsetsOf(context).bottom
                : 0,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Padding(
                padding: EdgeInsets.all(ui.space.s2),
                child: Row(
                  children: <Widget>[
                    Expanded(
                      child: Align(
                        key: const ValueKey<String>(
                          'global-sidebar-collection',
                        ),
                        alignment: AlignmentDirectional.centerStart,
                        child: _CollectionSwitcher(
                          controller: controller,
                          sheet: !_docked,
                        ),
                      ),
                    ),
                    ?widget.specimensActions,
                    if (_mobileNavigation &&
                        EnvironmentBanner.showsBand(controller.environment))
                      _EnvironmentContext(
                        controller: controller,
                        compact: true,
                      ),
                    if (_mobileNavigation)
                      ShellAccountMenu(controller: controller),
                    if (canClose)
                      UiIconButton(
                        icon: UiIcons.sidebar,
                        semanticsLabel: 'Close sidebar',
                        onPressed: _close,
                      ),
                  ],
                ),
              ),
              if (_mobileNavigation)
                _Chrome(
                  controller: controller,
                  busy: busy,
                  window: WindowClass.of(context),
                ),
              Expanded(
                child: widget.specimens != null
                    ? LayoutBuilder(
                        builder: (context, constraints) {
                          if (_expanded) {
                            _visibleSpecimensSize = constraints.biggest;
                          }
                          final retained = _expanded
                              ? null
                              : _visibleSpecimensSize;
                          return OverflowBox(
                            alignment: AlignmentDirectional.topStart,
                            minWidth: retained?.width,
                            maxWidth: retained?.width,
                            minHeight: retained?.height,
                            maxHeight: retained?.height,
                            child: widget.specimens,
                          );
                        },
                      )
                    : const SizedBox.shrink(),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _rail(BuildContext context, WorkspaceController controller) =>
      DecoratedBox(
        key: const ValueKey<String>('global-rail'),
        decoration: BoxDecoration(color: context.ui.color.ground),
        child: SafeArea(
          right: false,
          child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: IntrinsicHeight(
                  child: Padding(
                    padding: EdgeInsets.all(context.ui.space.s2),
                    child: Column(
                      children: <Widget>[
                        ShellSidebarNavigation(
                          destination: widget.destination,
                          onSelect: _select,
                          compact: true,
                        ),
                        if (!_expanded) _toggleButton(),
                        const Spacer(),
                        if (EnvironmentBanner.showsBand(controller.environment))
                          _EnvironmentContext(
                            controller: controller,
                            compact: true,
                          ),
                        ShellAccountMenu(controller: controller),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
}

/// Global destinations use one icon-and-label row, with a compact icon form.
class ShellSidebarNavigation extends StatefulWidget {
  const ShellSidebarNavigation({
    super.key,
    required this.destination,
    required this.onSelect,
    this.compact = false,
  });
  final WorkspaceDestination destination;
  final ValueChanged<WorkspaceDestination> onSelect;
  final bool compact;
  @override
  State<ShellSidebarNavigation> createState() => _ShellSidebarNavigationState();
}

/// Compatibility name for integration harnesses that locate the global navigation.
typedef ShellTopNavigation = ShellSidebarNavigation;

class _ShellSidebarNavigationState extends State<ShellSidebarNavigation> {
  final _nodes = <FocusNode>[
    FocusNode(debugLabel: 'Specimens navigation'),
    FocusNode(debugLabel: 'Intake navigation'),
  ];
  @override
  void dispose() {
    for (final node in _nodes) {
      node.dispose();
    }
    super.dispose();
  }

  void _move(int delta) {
    final index = _nodes.indexWhere((node) => node.hasFocus);
    _nodes[(index + delta) % _nodes.length].requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return CallbackShortcuts(
      bindings: <ShortcutActivator, VoidCallback>{
        const SingleActivator(LogicalKeyboardKey.arrowDown): () => _move(1),
        const SingleActivator(LogicalKeyboardKey.arrowUp): () => _move(-1),
      },
      child: Semantics(
        container: true,
        explicitChildNodes: true,
        label: 'Workspace navigation',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            for (int i = 0; i < AppShell.destinations.length; i++)
              Padding(
                padding: EdgeInsets.only(bottom: ui.space.s2),
                child: UiTooltip(
                  message:
                      'Open ${AppShell.destinations[i].label.toLowerCase()}',
                  child: Pressable(
                    semanticsLabel: AppShell.destinations[i].label,
                    role: PressableRole.tab,
                    selected: i == widget.destination.index,
                    focusNode: _nodes[i],
                    radius: ui.shape.tile,
                    onPressed: () =>
                        widget.onSelect(WorkspaceDestination.values[i]),
                    builder: (context, states) => DecoratedBox(
                      decoration: BoxDecoration(
                        color: i == widget.destination.index
                            ? ui.color.ink.withValues(alpha: .06)
                            : GroundPalette.transparent,
                        borderRadius: BorderRadius.circular(ui.shape.tile),
                      ),
                      child: Padding(
                        padding: EdgeInsets.all(ui.space.s2),
                        child: Row(
                          mainAxisAlignment: widget.compact
                              ? MainAxisAlignment.center
                              : MainAxisAlignment.start,
                          children: <Widget>[
                            UiIcon(
                              AppShell.destinations[i].icon,
                              current: i == widget.destination.index,
                            ),
                            if (!widget.compact) ...<Widget>[
                              SizedBox(width: ui.space.s4),
                              Expanded(
                                child: Text(
                                  AppShell.destinations[i].label,
                                  style: ui.type.label,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Account access is owned by the sidebar. Kept as a component for hosts that
/// display an isolated record outside the application shell.
class RecordAccountActions extends StatelessWidget {
  const RecordAccountActions({super.key, required this.controller});
  final WorkspaceController controller;
  @override
  Widget build(BuildContext context) =>
      ShellAccountMenu(controller: controller);
}

class _EnvironmentContext extends StatelessWidget {
  const _EnvironmentContext({required this.controller, this.compact = false});
  final bool compact;
  final WorkspaceController controller;
  @override
  Widget build(BuildContext context) {
    final bool pilot = EnvironmentBanner.isPilot(controller.environment);
    final String headline = pilot
        ? EnvironmentBanner.pilotHeadlineFor(pilotScopeDefine)
        : EnvironmentBanner.headlineFor(controller.environment);
    void showEnvironment() => unawaited(
      showProductModal<void>(
        context: context,
        title: pilot
            ? 'Pilot scope'
            : EnvironmentBanner.nameFor(controller.environment),
        body: (context) => Text(
          '$headline ${EnvironmentBanner.detailFor(controller.environment, contactSentence: AdministratorContact.of(controller.scope).sentence)}',
        ),
        secondaryAction: (context) => UiButton(
          label: 'Close',
          variant: UiButtonVariant.ghost,
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
    );
    if (compact) {
      return UiIconButton(
        icon: UiIcons.info,
        semanticsLabel: pilot ? 'Pilot environment' : 'Test environment',
        onPressed: showEnvironment,
      );
    }
    return UiButton(
      label: pilot ? 'Pilot' : 'Test',
      semanticsLabel: headline,
      variant: UiButtonVariant.ghost,
      onPressed: showEnvironment,
    );
  }
}

/// Repository blockers, screen errors and active progress above the content.
class _Chrome extends StatelessWidget {
  const _Chrome({
    required this.controller,
    required this.busy,
    required this.window,
  });

  final WorkspaceController controller;
  final bool busy;
  final WindowClass window;

  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[
      _BlockerNotice(blockers: controller.repository.blockers),
      _ErrorBanner(error: controller.error, onDismiss: controller.clearError),
      _ProgressStrip(busy: busy),
    ],
  );
}

/// The collection switcher.
///
/// A dropdown where there is room, and a touch sheet in narrow windows.
/// Both are sourced exclusively from the session's authorized scopes.
class _CollectionSwitcher extends StatelessWidget {
  const _CollectionSwitcher({required this.controller, required this.sheet});

  final bool sheet;

  final WorkspaceController controller;

  /// Why the switcher is unavailable, or null when it is available.
  String? get _blockedReason => controller.mutating
      ? 'A save is still going out. The collection can change once it lands.'
      : null;

  @override
  Widget build(BuildContext context) {
    final String? blocked = _blockedReason;
    final String name = controller.scope?.name ?? 'No collection chosen';
    if (sheet) {
      return UiButton(
        key: const ValueKey<String>('collection-sheet-trigger'),
        label: name,
        variant: UiButtonVariant.ghost,
        trailing: UiIcons.expand,
        semanticsLabel: '${AppShell.switcherLabel}, $name. Switch collection',
        disabledReason: blocked,
        onPressed: blocked != null ? null : () => unawaited(_choose(context)),
      );
    }
    return UiMenuTrigger(
      label: name,
      icon: UiIcons.expand,
      semanticsLabel: '${AppShell.switcherLabel}, $name. Switch collection',
      menuLabel: 'Choose a collection',
      items: <UiMenuItem>[
        for (final CollectionScope scope in controller.scopes)
          UiMenuItem(
            label: scope.name,
            icon: UiIcons.collection,
            disabledReason: blocked,
            onSelected: blocked != null
                ? null
                : () async {
                    if (await controller.mayLeaveReview() && context.mounted) {
                      context.go(
                        AppRoutes.queueOf(encodeCollectionKey(scope.key)),
                      );
                    }
                  },
          ),
      ],
    );
  }

  Future<void> _choose(BuildContext context) async {
    final String? selected = await UiSheet.show<String>(
      context: context,
      title: 'Choose a collection',
      secondaryAction: (BuildContext sheetContext) => UiButton(
        label: 'Cancel',
        variant: UiButtonVariant.ghost,
        onPressed: () => Navigator.of(sheetContext).pop(),
      ),
      body: (BuildContext sheetContext) => AnimatedBuilder(
        animation: controller,
        builder: (BuildContext context, Widget? child) => Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            for (final CollectionScope scope in controller.scopes)
              UiListRow(
                title: scope.name,
                subtitle: scope.key == controller.scope?.key
                    ? 'Current collection'
                    : null,
                leading: const UiIcon(UiIcons.collection),
                onPressed: controller.mutating
                    ? null
                    : () => Navigator.of(sheetContext).pop(scope.key),
              ),
          ],
        ),
      ),
    );
    if (!context.mounted ||
        selected == null ||
        controller.mutating ||
        !controller.scopes.any(
          (CollectionScope scope) => scope.key == selected,
        )) {
      return;
    }
    if (!await controller.mayLeaveReview() || !context.mounted) return;
    context.go(AppRoutes.queueOf(encodeCollectionKey(selected)));
  }
}

/// The account menu: the signed-in name, help, and signing out.
///
/// Shared with the record's published bar so account access remains available
/// after removing the sidebar. Compact records reach it via Back to queue.
class ShellAccountMenu extends StatelessWidget {
  /// The menu for the account [controller] holds.
  const ShellAccountMenu({super.key, required this.controller});

  /// The workspace whose session the menu names and signs out of.
  final WorkspaceController controller;

  @override
  Widget build(BuildContext context) {
    final String name = controller.session.displayName;
    return UiMenuTrigger(
      icon: UiIcons.account,
      semanticsLabel: '${AppShell.accountLabel}, signed in as $name',
      menuLabel: AppShell.accountLabel,
      items: <UiMenuItem>[
        // The signed-in address, at every window class. A reviewer on a
        // phone used to have no way to see which account they were using
        // (05 section 2).
        UiMenuItem(label: name, onSelected: null),
        UiMenuItem(
          label: AppShell.reloadLabel,
          icon: UiIcons.reload,
          disabledReason: controller.loading
              ? 'The collection is loading.'
              : null,
          onSelected: controller.loading
              ? null
              : () async {
                  if (await controller.mayLeaveReview()) {
                    await (controller.scope == null
                        ? controller.checkAccess()
                        : controller.refresh());
                  }
                },
        ),
        UiMenuItem(
          label: AppShell.helpLabel,
          icon: UiIcons.help,
          onSelected: () => context.push(AppRoutes.help),
        ),
        UiMenuItem(
          label: 'Sign out',
          icon: UiIcons.signOut,
          onSelected: () async {
            if (await controller.mayLeaveReview()) await controller.signOut();
          },
        ),
      ],
    );
  }
}

/// The repository's own processing blockers, stated once, above the screen.
class _BlockerNotice extends StatelessWidget {
  const _BlockerNotice({required this.blockers});

  final List<dynamic> blockers;

  @override
  Widget build(BuildContext context) {
    final WorkspaceScope? scope = context
        .getInheritedWidgetOfExactType<WorkspaceScope>();
    final AdministratorContact contact = AdministratorContact.of(
      scope?.notifier?.scope,
    );
    final String named = blockers
        .map((dynamic blocker) => vocabularyLabel(blocker.toString()))
        .join(', ');
    // Height and opacity, so the screen below does not snap down the moment
    // the repository answers (04 section 4, row 10).
    return MotionReveal(
      visible: blockers.isNotEmpty,
      child: UiBanner(
        message: 'Processing is blocked: $named.',
        tone: UiBannerTone.blocked,
        detail: 'A person has to review it. ${contact.sentence}',
        detailLabel: 'Show who unblocks it',
      ),
    );
  }
}

/// The screen level error surface: one band, one recovery action for the
/// failure class it is reporting (07 section 11).
class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.error, required this.onDismiss});

  final WorkspaceError? error;

  /// Drops the band. The reviewer's, never a background process's: a poll
  /// that answers successfully must not take away a message nobody has read
  /// yet (pass criterion 9.5).
  final VoidCallback onDismiss;

  /// The word on the control that drops the band.
  static const String dismissLabel = 'Dismiss';

  @override
  Widget build(BuildContext context) {
    final WorkspaceError? failure = error;
    // The band arrives and leaves with the shared reveal rather than snapping
    // the layout, and it is never a toast: it carries a recovery action and
    // must persist until it is resolved (04 section 4, row 10).
    return MotionReveal(
      visible: failure != null,
      child: failure == null
          ? const SizedBox(width: double.infinity)
          : UiBanner(
              message: failure.message,
              tone: UiBannerTone.blocked,
              actionLabel: failure.actionLabel,
              onAction: () => unawaited(failure.action()),
              onDismiss: onDismiss,
              dismissLabel: _ErrorBanner.dismissLabel,
            ),
    );
  }
}

/// A four pixel strip that is always occupied, so showing progress never moves
/// the screen (04 section 4, row 11).
///
/// The strip keeps its height whether or not it is busy. The indicator itself
/// is built only while it is busy: an indeterminate indicator animates
/// forever, and an animation that never ends is an animation a test can never
/// settle.
///
/// Visual only. The strip used to be a live region reading "Loading
/// collection data" while the screen under it announced its own load, so the
/// first frame of every collection said two things at once and a screen
/// reader user heard neither whole (06 section 3: a status change is
/// announced once). The screen is the one that knows what is loading, so the
/// screen keeps the announcement and this keeps the picture.
class _ProgressStrip extends StatelessWidget {
  const _ProgressStrip({required this.busy});

  final bool busy;

  /// What the strip would be called, if it were read.
  ///
  /// Kept because `UiProgress` requires a label of every indicator and the
  /// requirement is right: the day this strip is the only thing reporting a
  /// load, taking it back into the tree is deleting one widget.
  static const String label = 'Loading collection data';

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: busy
        ? SizedBox(
            height: context.ui.space.s1,
            child: const UiProgress.bar(semanticsLabel: label),
          )
        : const SizedBox.shrink(),
  );
}
