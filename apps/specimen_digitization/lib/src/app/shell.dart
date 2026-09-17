/// The adaptive collection shell (05 section 2; 07 sections 1.2, 1.3 and 11).
///
/// One navigation control per window class: a floating pill below 600, a
/// collapsed rail to 839, an extended rail to 1199, and a sidebar at 1200 and
/// above. The collection switcher and the account menu move with it, and the
/// mark leads the rail and the sidebar.
library;

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../administrator_contact.dart';
import '../models.dart';
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

  /// The widest the top bar's collection switcher may grow.
  static const double switcherMaxWidth = 280;

  /// What the switcher is called, in the bar and to a screen reader.
  static const String switcherLabel = 'Authorized collection';

  /// What the account control is called.
  static const String accountLabel = 'Account menu';

  /// What the help control is called, wherever it is drawn.
  static const String helpLabel = 'Help and shortcuts';

  /// What the reload control is called.
  static const String reloadLabel = 'Refresh collection';

  /// The two destinations, in the order they are read.
  ///
  /// Sources is reached from Intake rather than from here (07 section 13), so
  /// it is not a third destination even though the registry has a glyph for
  /// it.
  static const List<UiNavDestination> destinations = <UiNavDestination>[
    UiNavDestination(label: 'Queue', icon: UiIcons.queue),
    UiNavDestination(label: 'Intake', icon: UiIcons.intake),
  ];

  /// What the mark says where it leads the navigation.
  static const String markLabel = 'Specimen Digitization';

  /// Which sky the location paints (09 section 3.2).
  ///
  /// `sky.work` is the workbench, the region editor inside it, and the large
  /// record fallback; everything else in the collection, the queue, intake
  /// and the sources under it, is `sky.home`. A record is the one route with
  /// a segment after `queue`, which is what `AppRoutes.specimenOf` builds.
  ///
  /// This predicate belongs beside `AppRoutes.isEntryLocation` and
  /// `isGlobalLocation` rather than here; `routes.dart` is not this slot's
  /// file, so it is written once here and the cleanup slot can move it.
  static SkyPreset skyOf(Uri location) {
    final List<String> segments = location.pathSegments;
    final int queue = segments.indexOf('queue');
    return queue >= 0 && queue < segments.length - 1
        ? SkyPreset.work
        : SkyPreset.home;
  }

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
    final bool sidebar = window.isAtLeast(WindowClass.large);
    final bool rail = !sidebar && window.isAtLeast(WindowClass.medium);
    final bool extended = rail && window.isAtLeast(WindowClass.expanded);
    final bool busy =
        controller.loading ||
        controller.recordLoading ||
        controller.mutating ||
        controller.loadingMore;

    final Widget navigation = sidebar
        ? UiSidebar(
            destinations: destinations,
            currentIndex: destination.index,
            onSelect: (int index) =>
                _select(context, WorkspaceDestination.values[index]),
            header: _SidebarHeader(controller: controller),
            footer: _SidebarFooter(controller: controller),
          )
        : rail
        ? UiRail(
            destinations: destinations,
            currentIndex: destination.index,
            extended: extended,
            onSelect: (int index) =>
                _select(context, WorkspaceDestination.values[index]),
            // The bar's title already says the product's name, so the mark
            // beside it is decoration: a screen reader that reads both hears
            // it twice on the way into the navigation.
            leading: const ExcludeSemantics(child: UiMark(label: markLabel)),
          )
        : UiPillNav(
            destinations: destinations,
            currentIndex: destination.index,
            onSelect: (int index) =>
                _select(context, WorkspaceDestination.values[index]),
          );

    return UiScaffold(
      // The queue, intake and sources routes are the home sky; the record
      // route is the work sky (09 section 3.2). The pane that draws the
      // photograph publishes the matte's clear band through
      // `UiScaffoldExclusion.of(context)?.publish(rect)`, which the frame
      // clips its fields out of.
      sky: skyOf(GoRouterState.of(context).uri),
      topBar: _TopBar(controller: controller, window: window, sidebar: sidebar),
      banner: _Chrome(controller: controller, busy: busy),
      nav: navigation,
      // The routed screen is a nested `Navigator`, and a route's modal
      // barrier blocks the semantics of everything painted before it inside
      // the same semantics boundary. The shell's own chrome, the environment
      // band and this navigation, is painted first, so without a boundary of
      // its own the screen erased all of it: a reviewer working through a
      // browser's accessibility tree found a queue with no navigation and no
      // way into a record.
      body: Semantics(container: true, explicitChildNodes: true, child: child),
    );
  }
}

/// The bar across the top of every collection screen.
class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.controller,
    required this.window,
    required this.sidebar,
  });

  final WorkspaceController controller;
  final WindowClass window;
  final bool sidebar;

  @override
  Widget build(BuildContext context) {
    final bool switchable = controller.scopes.isNotEmpty;
    // The switcher is reachable at every window class (07 section 1.2): in
    // the bar's centre from medium up, in the bar's own title row on compact,
    // and in the sidebar's header at large.
    final bool inBar = !sidebar && switchable;

    return UiTopBar(
      // The rail and the sidebar carry the mark, so the bar carries it only
      // on a compact window, where there is neither.
      leading: window.isCompact
          ? const UiMark(label: AppShell.markLabel)
          : null,
      title: window.isCompact ? null : AppShell.markLabel,
      center: inBar
          ? ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: AppShell.switcherMaxWidth,
              ),
              child: _CollectionSwitcher(controller: controller),
            )
          : null,
      // Declared commands rather than discs: a `UiTopBarAction` carries the
      // label, the glyph and the reason a menu row needs, so the bar can put
      // the ones past the second into its overflow menu on a window too
      // narrow to draw them beside the title. The account menu is a trigger
      // of its own and stays a widget, which the bar reads as "keep them all
      // drawn"; it is the second action wherever it appears, so nothing
      // collapses today and the bar is ready for the third.
      actions: <Widget>[
        UiTopBarAction(
          icon: UiIcons.reload,
          label: AppShell.reloadLabel,
          onPressed: controller.loading
              ? null
              : () => unawaited(
                  controller.scope == null
                      ? controller.checkAccess()
                      : controller.refresh(),
                ),
          disabledReason: controller.loading
              ? 'The collection is loading. This is available once it lands.'
              : null,
        ),
        // At large the sidebar's footer carries the account and signing out,
        // so the bar carries help on its own; everywhere else the account
        // menu is where help and signing out live.
        if (sidebar)
          UiTopBarAction(
            icon: UiIcons.help,
            label: AppShell.helpLabel,
            onPressed: () => context.push(AppRoutes.help),
          )
        else
          _AccountMenu(controller: controller),
      ],
    );
  }
}

/// Everything that sits between the top bar and the screen: the environment
/// band, the repository's blockers, the screen level error and the progress
/// strip.
class _Chrome extends StatelessWidget {
  const _Chrome({required this.controller, required this.busy});

  final WorkspaceController controller;
  final bool busy;

  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[
      EnvironmentBanner(environment: controller.environment),
      _BlockerNotice(blockers: controller.repository.blockers),
      _ErrorBanner(error: controller.error, onDismiss: controller.clearError),
      _ProgressStrip(busy: busy),
    ],
  );
}

/// The collection switcher.
///
/// A `UiSelect` at every window class: 07 section 1.2 asks for the switcher to
/// be reachable everywhere, and one control reached the same way in the bar,
/// in the bar's title and in the sidebar's header is one thing to learn.
class _CollectionSwitcher extends StatelessWidget {
  const _CollectionSwitcher({required this.controller});

  final WorkspaceController controller;

  /// Why the switcher is unavailable, or null when it is available.
  String? get _blockedReason => controller.mutating
      ? 'A save is still going out. The collection can change once it lands.'
      : null;

  @override
  Widget build(BuildContext context) {
    final String? blocked = _blockedReason;
    final String name = controller.scope?.name ?? 'No collection chosen';
    return UiSelect<String>(
      label: AppShell.switcherLabel,
      showLabel: false,
      semanticsLabel: '${AppShell.switcherLabel}, $name. Switch collection',
      placeholder: 'No collection chosen',
      value: controller.scope?.key,
      options: <UiSelectOption<String>>[
        for (final CollectionScope scope in controller.scopes)
          UiSelectOption<String>(
            value: scope.key,
            label: scope.name,
            leading: UiIcons.collection,
          ),
      ],
      disabledReason: blocked,
      onChanged: blocked != null
          ? null
          : (String key) =>
                context.go(AppRoutes.queueOf(encodeCollectionKey(key))),
    );
  }
}

/// The account menu: the signed-in name, help, and signing out.
class _AccountMenu extends StatelessWidget {
  const _AccountMenu({required this.controller});

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
          label: AppShell.helpLabel,
          icon: UiIcons.help,
          onSelected: () => context.push(AppRoutes.help),
        ),
        UiMenuItem(
          label: 'Sign out',
          icon: UiIcons.signOut,
          onSelected: () => unawaited(controller.signOut()),
        ),
      ],
    );
  }
}

/// The sidebar's header: the mark, the product name and the switcher.
class _SidebarHeader extends StatelessWidget {
  const _SidebarHeader({required this.controller});

  final WorkspaceController controller;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Row(
          children: <Widget>[
            const ExcludeSemantics(child: UiMark(label: AppShell.markLabel)),
            SizedBox(width: ui.space.s2),
            Expanded(
              child: Text(
                AppShell.markLabel,
                style: ui.type.title.copyWith(color: ui.color.ink),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
        if (controller.scopes.isNotEmpty) ...<Widget>[
          SizedBox(height: ui.space.s4),
          _CollectionSwitcher(controller: controller),
        ],
      ],
    );
  }
}

/// The sidebar's footer: who is signed in, and the way out.
class _SidebarFooter extends StatelessWidget {
  const _SidebarFooter({required this.controller});

  final WorkspaceController controller;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          controller.session.displayName,
          style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        SizedBox(height: ui.space.s2),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: UiButton(
            label: 'Sign out',
            variant: UiButtonVariant.ghost,
            leading: UiIcons.signOut,
            onPressed: () => unawaited(controller.signOut()),
          ),
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
    child: SizedBox(
      height: context.ui.space.s1,
      child: busy ? const UiProgress.bar(semanticsLabel: label) : null,
    ),
  );
}
