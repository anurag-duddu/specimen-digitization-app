/// Labelled desktop navigation and compact bottom tabs. The specimen queue
/// is content, with an optional adaptive companion beside a record.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../administrator_contact.dart';
import '../models.dart';
import '../screens/workbench/workbench_layout.dart';
import '../screens/costs/costs_access.dart';
import '../screens/costs/costs_screen.dart' show CostsScreenCopy;
import '../widgets/widgets.dart';
import '../workspace.dart';
import 'routes.dart';
import 'collection_choices.dart';

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

  /// What the control that opens the organization's costs is called.
  static const String costsLabel = CostsScreenCopy.title;

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

  /// What the docked rail's tab list is called to a screen reader.
  static const String navigationLabel = 'Workspace navigation';

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
    this.mobileSpecimens,
    required this.toggle,
    required this.close,
    required super.child,
  });
  final bool expanded;
  final bool overlay;
  final bool docked;

  /// The retained queue content when it belongs to the Queue route.
  ///
  /// Present on desktop as well as compact windows. It is absent only while
  /// the shell owns the optional list beside an actual docked record. The
  /// retained Queue route keeps it mounted while Intake is active.
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
      mobileSpecimens != oldWidget.mobileSpecimens;
}

class _AppShellState extends State<AppShell> {
  bool? _desktopExpanded;
  bool _stacked = false;
  bool _expanded = false;
  bool _overlay = false;
  Size? _visibleSpecimensSize;
  final FocusNode _closeQueueFocus = FocusNode(
    debugLabel: 'Close specimen queue',
  );
  bool _selecting = false;

  @override
  void dispose() {
    _closeQueueFocus.dispose();
    super.dispose();
  }

  void _toggle() => _expanded ? _close() : _open();

  void _open() => setState(() => _desktopExpanded = true);

  void _close() => setState(() => _desktopExpanded = false);

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
    // Read without depending on InheritedNotifier: quiet queue polls must not
    // rebuild structural nav. Chrome (busy strip, error) listens separately.
    final WorkspaceController controller = WorkspaceScope.read(context);
    return ListenableBuilder(
      listenable: controller.chromeChanges,
      builder: (BuildContext context, Widget? _) {
        final location = GoRouterState.of(context).uri;
        final record = AppShell.insideRecord(location);
        final listRoute =
            widget.destination == WorkspaceDestination.queue && !record;
        final busy =
            controller.loading ||
            controller.recordLoading ||
            controller.mutating ||
            controller.loadingMore;
        final ui = context.ui;
        // One answer for the whole window, from the design system (05 section 2,
        // amended 2026-10-17). The intake page, the record's loading bar, the
        // routes, the sheets and the band ask the same question of the same
        // function, so a phone on its side that draws the tab bar also gets the
        // sheet and the strip.
        final arrangement = WindowArrangement.of(context);
        _stacked = arrangement.isStacked;
        final navVisible =
            _stacked && !record && MediaQuery.viewInsetsOf(context).bottom == 0;

        return LayoutBuilder(
          builder: (context, constraints) {
            final textScaler = MediaQuery.textScalerOf(context);
            final navigationWidth = UiSidebar.widthOf(
              context,
              destinations: AppShell.destinations,
            );
            final layout = UiLayoutMetrics.fromConstraints(
              constraints,
              textScaler: textScaler,
            );
            final listBesideRecord = record && !_stacked;
            // A companion must leave room for the photograph and inspector. On
            // tablet widths it overlays the record instead of changing its layout.
            final scale = math.max(1.0, textScaler.scale(16) / 16);
            final panelLayout = UiSidePanelLayout.resolve(
              availableWidth: math.max(
                0.0,
                constraints.maxWidth - (_stacked ? 0 : navigationWidth),
              ),
              panelWidth: WindowArrangement.listPaneWidthOf(textScaler),
              minBodyWidth:
                  2 * reviewColumnMinWidth * scale +
                  layout.gap +
                  layout.gutter * 2,
            );
            _overlay =
                listBesideRecord && panelLayout.mode == UiSidePanelMode.overlay;
            _expanded =
                listRoute ||
                (listBesideRecord && (_desktopExpanded ?? !_overlay));
            final sidebar = _sidebar(
              context,
              controller,
              canClose: listBesideRecord,
              busy: busy,
            );
            return AppSidebarScope(
              expanded: _expanded,
              overlay: _overlay,
              docked: !_stacked,
              mobileSpecimens: listBesideRecord ? null : sidebar,
              toggle: _toggle,
              close: _close,
              child: QueueWorkspaceScope(
                expanded: _expanded,
                showQueue: listBesideRecord ? _toggle : null,
                hideQueue: () {
                  if (_overlay) _close();
                },
                child: ColoredBox(
                  color: ui.color.ground,
                  child: Column(
                    children: <Widget>[
                      Expanded(
                        child: MediaQuery.removePadding(
                          context: context,
                          removeBottom: navVisible,
                          child: SafeArea(
                            top: false,
                            left: false,
                            right: false,
                            bottom: _stacked && record,
                            // The frame stays at this one place in the tree at
                            // every arrangement, so resizing across one keeps
                            // the open record, its drafts and its scroll: only
                            // the `nav` slot comes and goes beside the body.
                            child: UiSidePanel(
                              open: listBesideRecord && _expanded,
                              mode: panelLayout.mode,
                              width: panelLayout.width,
                              panel: listBesideRecord ? sidebar : null,
                              leading: _stacked
                                  ? null
                                  : _navigation(context, controller),
                              leadingWidth: _stacked ? 0 : navigationWidth,
                              // Opening a queue on a touch tablet must not summon
                              // the keyboard before the reviewer chooses search.
                              initialFocusNode: _closeQueueFocus,
                              semanticsLabel: 'Specimen queue',
                              dismissLabel: 'Hide queue',
                              onDismiss: _close,
                              child: UiScaffold(
                                sky: AppShell.skyOf(location),
                                header: _stacked && !record
                                    ? _compactTopBar(
                                        controller,
                                        listRoute: listRoute,
                                      )
                                    : null,
                                banner: _stacked && listRoute
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
                        ),
                      ),
                      if (navVisible) _mobileNav(context),
                    ],
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  /// The one compact top bar: the collection switcher and the account, on
  /// every compact destination that is not a record.
  ///
  /// This used to be built twice, once inside the Specimens list (on `paper`)
  /// and once above Intake (on `ground`), which left a seam under the status
  /// strip on one tab and not the other. It is `UiTopBar` in its workspace
  /// form now (10 section 4.4): an opaque `paper` ground that also fills the
  /// top safe inset, drawn by the design system rather than padded here, so
  /// the strip and the bar are one surface on every tab and every platform.
  /// A record draws its own bar and the shell draws none above it.
  Widget _compactTopBar(
    WorkspaceController controller, {
    required bool listRoute,
  }) => UiTopBar(
    key: const ValueKey<String>('shell-top-bar'),
    form: UiTopBarForm.workspace,
    leading: Row(
      children: [
        Padding(
          padding: EdgeInsetsDirectional.only(start: context.ui.space.s2),
          child: UiMark(label: AppShell.markLabel, size: context.ui.space.s8),
        ),
        SizedBox(width: context.ui.space.s2),
        Expanded(
          child: _CollectionSwitcher(controller: controller, sheet: true),
        ),
      ],
    ),
    actions: <Widget>[
      if (EnvironmentBanner.showsBand(controller.environment))
        _EnvironmentContext(controller: controller, compact: true),
      ShellAccountMenu(controller: controller),
    ],
  );

  /// The compact bottom tab bar.
  ///
  /// One brand component on every platform (10 section 4.4, `UiTabBar`): the
  /// window class chose it, and the platform only supplies the safe inset
  /// under it. A `CupertinoTabBar` here and a `NavigationBar` there were two
  /// products' identities in one app (09 section 2 principle 5).
  Widget _mobileNav(BuildContext context) => UiTabBar(
    key: const ValueKey<String>('mobile-navigation'),
    destinations: AppShell.destinations,
    labels: UiNavigationLabels.selectedOnly,
    currentIndex: widget.destination.index,
    iconKeyOf: (index) => ValueKey<String>(
      'mobile-nav-${AppShell.destinations[index].label.toLowerCase()}',
    ),
    onSelect: (index) => _select(WorkspaceDestination.values[index]),
  );

  Widget _sidebar(
    BuildContext context,
    WorkspaceController controller, {
    required bool canClose,
    required bool busy,
  }) {
    final ui = context.ui;
    return ColoredBox(
      key: ValueKey<String>(_stacked ? 'mobile-specimens' : 'global-sidebar'),
      color: ui.color.paper,
      child: SafeArea(
        left: _stacked,
        right: _stacked,
        child: Padding(
          padding: EdgeInsets.only(
            bottom: _stacked ? MediaQuery.viewInsetsOf(context).bottom : 0,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              if (canClose)
                Padding(
                  padding: EdgeInsets.all(ui.space.s2),
                  child: Row(
                    children: [
                      const Spacer(),
                      UiIconButton(
                        key: const ValueKey<String>('queue-panel-close'),
                        icon: UiIcons.close,
                        semanticsLabel: 'Hide queue',
                        focusNode: _closeQueueFocus,
                        onPressed: _close,
                      ),
                    ],
                  ),
                ),
              if (_stacked)
                _Chrome(
                  controller: controller,
                  busy: busy,
                  window: WindowClass.of(context),
                ),
              Expanded(
                child: widget.specimens == null
                    ? const SizedBox.shrink()
                    : LayoutBuilder(
                        builder: (context, constraints) {
                          if (_expanded) {
                            _visibleSpecimensSize = constraints.biggest;
                          }
                          // The phone's queue lives in an offstage route while
                          // a record is open. Retain its last visible viewport
                          // so hidden layout cannot clamp its scroll offset.
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
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _navigation(BuildContext context, WorkspaceController controller) {
    final ui = context.ui;
    return ColoredBox(
      color: ui.color.paper,
      child: SafeArea(
        child: UiSidebar(
          key: const ValueKey<String>('global-rail'),
          destinations: AppShell.destinations,
          currentIndex: widget.destination.index,
          semanticsLabel: AppShell.navigationLabel,
          onSelect: (index) => _select(WorkspaceDestination.values[index]),
          header: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: EdgeInsets.symmetric(vertical: ui.space.s2),
                child: UiMark(label: AppShell.markLabel, size: ui.space.s8),
              ),
              SizedBox(height: ui.space.s4),
              Align(
                key: const ValueKey<String>('global-sidebar-collection'),
                alignment: AlignmentDirectional.centerStart,
                child: _CollectionSwitcher(
                  controller: controller,
                  sheet: false,
                ),
              ),
            ],
          ),
          footer: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (EnvironmentBanner.showsBand(controller.environment))
                _EnvironmentContext(controller: controller),
              ShellAccountMenu(controller: controller, showLabel: true),
            ],
          ),
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
      semanticsLabel: pilot ? 'Pilot environment' : 'Test environment',
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
/// Catalog context comes from the server; only session-authorized scopes
/// can be selected.
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
      trailingIcon: true,
      semanticsLabel: '${AppShell.switcherLabel}, $name. Switch collection',
      menuLabel: 'Choose a collection',
      menuMaxHeight: 520,
      menuSurface: PopoverSurface.paper,
      menuDescription:
          controller.scopes.any((scope) => scope.catalogNodes.isNotEmpty)
          ? 'Only enabled collections can be opened.'
          : null,
      items: <UiMenuItem>[
        for (final choice in collectionChoices(
          controller.scopes,
          selectedKey: controller.scope?.key,
        ))
          UiMenuItem(
            label: choice.name,
            groupLabel: choice.groupLabel,
            indent: choice.depth,
            isHeading: choice.headingOnly,
            selected: choice.key == controller.scope?.key,
            disabledReason: choice.scope == null
                ? 'This collection is not enabled for this account.'
                : blocked,
            onSelected: blocked != null || choice.scope == null
                ? null
                : () => unawaited(_select(context, choice.key)),
          ),
      ],
    );
  }

  Future<void> _choose(BuildContext context) async {
    final currentRow = GlobalKey();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final target = currentRow.currentContext;
      if (target != null) {
        unawaited(
          Scrollable.ensureVisible(
            target,
            alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtEnd,
          ),
        );
      }
    });
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
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            if (controller.scopes.any((scope) => scope.catalogNodes.isNotEmpty))
              Padding(
                padding: EdgeInsets.all(context.ui.space.s3),
                child: Text(
                  'Only enabled collections can be opened.',
                  style: context.ui.type.labelSmall.copyWith(
                    color: context.ui.color.inkSecondary,
                  ),
                ),
              ),
            for (final choice in collectionChoices(
              controller.scopes,
              selectedKey: controller.scope?.key,
            )) ...[
              if ((choice.headingOnly ? choice.name : choice.groupLabel)
                  case final String group)
                Padding(
                  padding: EdgeInsetsDirectional.fromSTEB(
                    context.ui.space.s3,
                    context.ui.space.s4,
                    context.ui.space.s3,
                    context.ui.space.s2,
                  ),
                  child: Semantics(
                    header: true,
                    child: Text(
                      group,
                      style: context.ui.type.labelSmall.copyWith(
                        color: context.ui.color.inkSecondary,
                      ),
                    ),
                  ),
                ),
              if (!choice.headingOnly)
                Padding(
                  padding: EdgeInsetsDirectional.only(
                    start: (choice.depth * context.ui.space.s4)
                        .clamp(0, context.ui.space.s12)
                        .toDouble(),
                  ),
                  child: UiListRow(
                    key: choice.key == controller.scope?.key
                        ? currentRow
                        : null,
                    title: choice.name,
                    selected: choice.key == controller.scope?.key,
                    trailing: choice.key == controller.scope?.key
                        ? const UiIcon(UiIcons.check, size: UiIconSize.inline)
                        : null,
                    disabledReason: choice.scope == null
                        ? 'This collection is not enabled for this account.'
                        : _blockedReason,
                    onPressed: controller.mutating || choice.scope == null
                        ? null
                        : () => Navigator.of(sheetContext).pop(choice.key),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
    if (!context.mounted || selected == null) return;
    await _select(context, selected);
  }

  Future<void> _select(BuildContext context, String selected) async {
    if (controller.mutating ||
        !controller.scopes.any(
          (CollectionScope scope) => scope.key == selected,
        )) {
      return;
    }
    if (selected == controller.scope?.key) return;
    if (!await controller.mayLeaveReview() ||
        !context.mounted ||
        controller.mutating ||
        !controller.scopes.any((scope) => scope.key == selected)) {
      return;
    }
    context.go(AppRoutes.queueOf(encodeCollectionKey(selected)));
  }
}

/// The account menu: the signed-in name, help, and signing out.
///
/// Shared with the record's published bar so account access remains available
/// after removing the sidebar. Compact records reach it via Back to queue.
class ShellAccountMenu extends StatelessWidget {
  /// The menu for the account [controller] holds.
  const ShellAccountMenu({
    super.key,
    required this.controller,
    this.showLabel = false,
  });

  /// A visible name in the labelled desktop navigation.
  final bool showLabel;

  /// The workspace whose session the menu names and signs out of.
  final WorkspaceController controller;

  @override
  Widget build(BuildContext context) {
    final String name = controller.session.displayName;
    return UiMenuTrigger(
      label: showLabel ? 'Account' : null,
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
        // Offered to an administrator of the open collection's organization
        // and to nobody else, and hidden rather than disabled where the build
        // has no costs to show (13 section 4.7). Nobody else is ever asked to
        // open it, so nobody else's session is ever the one a refusal ends.
        if (costAccessFor(controller) != null)
          UiMenuItem(
            label: AppShell.costsLabel,
            icon: UiIcons.record,
            onSelected: () => context.push(AppRoutes.costs),
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
    final explanations = blockers
        .map(
          (dynamic blocker) => switch (blocker.toString()) {
            'worker_readiness_not_verified' =>
              'An operator must confirm that processing is ready.',
            'institutional_policy_unapproved' =>
              'An administrator must approve the collection policy.',
            'mandatory_semantics_unconfirmed' ||
            'field_semantics_unconfirmed' =>
              'An administrator must confirm the collection’s field rules.',
            _ => 'An operator must review the processing setup.',
          },
        )
        .toSet()
        .join(' ');
    // Height and opacity, so the screen below does not snap down the moment
    // the repository answers (04 section 4, row 10).
    return MotionReveal(
      visible: blockers.isNotEmpty,
      child: UiBanner(
        message: 'Processing awaits collection setup.',
        tone: UiBannerTone.blocked,
        detail: '$explanations ${contact.sentence}',
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
