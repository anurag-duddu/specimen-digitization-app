/// The adaptive collection shell (05 section 2; 07 sections 1.2, 1.3 and 11;
/// 13 sections 2.3 and 3.4).
///
/// One navigation control per window class: a floating pill below 600, a
/// collapsed rail to 839, an extended rail to 1199, and a sidebar at 1200 and
/// above. The collection switcher and the account menu move with it, and the
/// mark leads the rail and the sidebar.
///
/// The frame is built once and the router swaps the body inside it, so what
/// the chrome says is decided here, by route: which sky paints, whether the
/// navigation is drawn, whether the bar carries the collection switcher or the
/// screen's own name and the way out, and which form the environment band
/// takes. 13 section 3.4 asks the scaffold to read the route; the shell is
/// where this application reads it. A screen that knows better than the route
/// names the frame through `UiScaffoldSlots`, the one hook for the bar, its
/// title and its start slot, the action bar, the navigation and the band's
/// form (13 section 3.4, polish 3); the shell holds no hook of its own.
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
class AppShell extends StatefulWidget {
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

  /// What the way out of a record is called, in the bar's leading slot.
  ///
  /// 13 section 2.3 gives the way out to the top bar, so this is the only
  /// back action a record needs and the row under the bar goes.
  static const String backLabel = 'Back to queue';

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

  /// True where the bar carries the account menu, which is every window
  /// narrower than large: at large the sidebar's footer carries the account
  /// and signing out, so the bar carries help on its own (07 section 10).
  ///
  /// One rule for the shell's own bars and for the bar a record publishes
  /// (13 section 4.1, polish 3), so the menu sits in the same slot on every
  /// screen of the collection and a reviewer learns where it is once.
  static bool accountInBar(WindowClass window) =>
      !window.isAtLeast(WindowClass.large);

  /// True where the bar a record publishes carries the account menu: the
  /// windows [accountInBar] names, less compact.
  ///
  /// At 390 by 844 the record's identifier has 134 dp beside back and three
  /// discs and ellipsises at 200 percent text, and the identifier is the one
  /// fact that bar exists to state (13 section 4.1). A screen over its width
  /// gives a disc up rather than cutting its fact, and the account is the one
  /// disc 4.1 did not list: the way out is back, and the queue's bar carries
  /// the account at every width below large. From medium up the record's bar
  /// has the width and carries the same menu in the same slot.
  static bool accountOnRecordBar(WindowClass window) =>
      accountInBar(window) && !window.isCompact;

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

class _AppShellState extends State<AppShell> {
  /// Goes to [next], or back to the destination's own root when the reviewer
  /// is already inside it.
  ///
  /// Pressing Intake while browsing a registered source used to do nothing,
  /// because the source route belongs to the Intake destination and the
  /// navigation only moved between destinations. That left the sources list
  /// with no way back but the system gesture, which is half of finding V2-4.
  void _select(BuildContext context, WorkspaceDestination next) {
    final WorkspaceController controller = WorkspaceScope.read(context);
    final String? key = controller.defaultRouteKey;
    if (key == null) return;
    final String root = next == WorkspaceDestination.queue
        ? AppRoutes.queueOf(key)
        : AppRoutes.intakeOf(key);
    if (GoRouterState.of(context).uri.path == root) return;
    context.go(root);
  }

  @override
  Widget build(BuildContext context) {
    final WorkspaceController controller = WorkspaceScope.of(context);
    final WindowClass window = WindowClass.of(context);
    final Uri location = GoRouterState.of(context).uri;
    final bool sidebar = window.isAtLeast(WindowClass.large);
    final bool rail = !sidebar && window.isAtLeast(WindowClass.medium);
    final bool extended = rail && window.isAtLeast(WindowClass.expanded);
    // 13 section 2.3: the pill hides on a screen that is inside a record,
    // where the way out is the top bar's back. The frame owns this by route,
    // and a record that asks for it again through the scaffold's own slot
    // asks for what it already has.
    //
    // The pill, and only the pill. A rail and a sidebar are columns beside
    // the body rather than chrome over it: they spend width, the budget in
    // 13 section 2.3 is a share of the height, and a desktop with its
    // navigation taken away inside a record has no navigation at all.
    final bool inRecord = AppShell.insideRecord(location);
    final bool busy =
        controller.loading ||
        controller.recordLoading ||
        controller.mutating ||
        controller.loadingMore;

    final Widget navigation = sidebar
        ? UiSidebar(
            destinations: AppShell.destinations,
            currentIndex: widget.destination.index,
            onSelect: (int index) =>
                _select(context, WorkspaceDestination.values[index]),
            header: _SidebarHeader(controller: controller),
            footer: _SidebarFooter(controller: controller),
          )
        : rail
        ? UiRail(
            destinations: AppShell.destinations,
            currentIndex: widget.destination.index,
            extended: extended,
            onSelect: (int index) =>
                _select(context, WorkspaceDestination.values[index]),
            // The bar's title already says the product's name, so the mark
            // beside it is decoration: a screen reader that reads both hears
            // it twice on the way into the navigation.
            leading: const ExcludeSemantics(
              child: UiMark(label: AppShell.markLabel),
            ),
          )
        : UiPillNav(
            destinations: AppShell.destinations,
            currentIndex: widget.destination.index,
            onSelect: (int index) =>
                _select(context, WorkspaceDestination.values[index]),
          );

    return UiScaffold(
      // The queue, intake and sources routes are the home sky; the record
      // route is the work sky (09 section 3.2). The pane that draws the
      // photograph publishes the matte's clear band through
      // `UiScaffoldExclusion.of(context)?.publish(rect)`, which the frame
      // clips its fields out of.
      sky: AppShell.skyOf(location),
      // What the route says the bar carries. A screen that names itself or
      // its way out publishes through `UiScaffoldSlots`, and the frame draws
      // what it asked for over this (13 section 3.4).
      topBar: _TopBar(
        controller: controller,
        window: window,
        sidebar: sidebar,
        location: location,
      ),
      banner: _Chrome(controller: controller, busy: busy, window: window),
      nav: navigation,
      navVisible: !(inRecord && !sidebar && !rail),
      // The routed screen is a nested `Navigator`, and a route's modal
      // barrier blocks the semantics of everything painted before it inside
      // the same semantics boundary. The shell's own chrome, the environment
      // band and this navigation, is painted first, so without a boundary of
      // its own the screen erased all of it: a reviewer working through a
      // browser's accessibility tree found a queue with no navigation and no
      // way into a record.
      body: Semantics(
        container: true,
        explicitChildNodes: true,
        child: widget.child,
      ),
    );
  }
}

/// The bar across the top of every collection screen (13 sections 2.3 and 4).
///
/// Two arrangements, chosen by route. On a list screen the bar carries the
/// mark, the collection switcher and the commands. Inside a record it carries
/// the way out and the record's own name instead: a reviewer in a record is
/// not choosing a collection, and the switcher there would offer to leave the
/// thing they are reading without saying so.
///
/// The record publishes a bar of its own into the frame through
/// `UiScaffoldSlots.setTopBar`, with its commands and, from `expanded` up, its
/// decision (13 section 4.1), and the frame draws that over this one. What
/// this builds inside a record is what the frame shows until the record has
/// loaded, and it agrees with the record's bar on everything the two share.
/// A screen that names the bar or its start slot alone, through `setTitle` or
/// `setLeading`, reaches this bar through `UiTopBarAsk`, which `UiTopBar`
/// reads itself (13 section 3.4, polish 3); the shell holds no hook for it.
class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.controller,
    required this.window,
    required this.sidebar,
    required this.location,
  });

  final WorkspaceController controller;
  final WindowClass window;
  final bool sidebar;
  final Uri location;

  @override
  Widget build(BuildContext context) {
    final String? record = AppShell.recordIn(location);
    final bool inRecord = record != null;
    final bool switchable = controller.scopes.isNotEmpty;
    // The switcher is reachable at every window class (07 section 1.2): in
    // the bar's centre from medium up, in the bar's own title row on compact,
    // and in the sidebar's header at large. Not inside a record, where the
    // bar's one job is to say which record this is and how to leave it.
    final bool inBar = !sidebar && switchable && !inRecord;
    // What the bar names on this route, in the centre slot rather than the
    // title slot (13 section 4.1): the centre takes a widget, so a record
    // names itself in `mono.identifier`, which is the role 13 section 4.1
    // gives a specimen id and which the title slot cannot draw.
    final Widget? named = inRecord
        ? _BarName(text: record, style: context.ui.type.mono.identifier)
        : null;
    final String? title = named != null || window.isCompact
        ? null
        : AppShell.markLabel;

    // The frame draws the bar solid at every class, so it spends no pane
    // (13 section 2.2, polish 3): nothing wraps it here.
    return UiTopBar(
      // The rail and the sidebar carry the mark, so the bar carries it only
      // on a compact window, where there is neither. Inside a record the
      // slot is the way out, which is what 13 section 2.3 puts there.
      leading: inRecord
          ? UiIconButton(
              icon: UiIcons.back,
              semanticsLabel: AppShell.backLabel,
              tooltip: AppShell.backLabel,
              onPressed: () => _leaveRecord(context),
            )
          : window.isCompact
          ? const UiMark(label: AppShell.markLabel)
          : null,
      title: title,
      center: inBar
          ? ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: AppShell.switcherMaxWidth,
              ),
              child: _CollectionSwitcher(controller: controller),
            )
          : named,
      // Declared commands rather than discs: a `UiTopBarAction` carries the
      // label, the glyph and the reason a menu row needs, so the bar can put
      // the ones past the second into its overflow menu on a window too
      // narrow to draw them beside the title. The account menu is a trigger
      // of its own and stays a widget, which the bar reads as "keep them all
      // drawn"; it is the last action wherever it appears, so nothing
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
        // Below large the account menu closes the bar, inside a record as
        // well (13 section 4.1, polish 3): the record's own bar carries the
        // same menu in the same slot, and `Popover` fits its pane inside the
        // window at every width now (10 section 3), so a menu opened from the
        // last slot of a bar opens inside it. At large the sidebar's footer
        // carries the account and signing out, and the bar carries help on
        // its own.
        if (AppShell.accountInBar(window))
          ShellAccountMenu(controller: controller)
        else
          UiTopBarAction(
            icon: UiIcons.help,
            label: AppShell.helpLabel,
            onPressed: () => context.push(AppRoutes.help),
          ),
      ],
    );
  }

  /// Leaves the record for the queue it was opened from.
  void _leaveRecord(BuildContext context) {
    final String? key = AppRoutes.collectionKeyIn(location);
    context.go(
      key == null
          ? AppRoutes.queueOf(controller.defaultRouteKey ?? '')
          : AppRoutes.queueOf(key),
    );
  }
}

/// What the bar names, in the slot that takes a role rather than a string.
///
/// One line, ellipsised, with the whole of it on the semantics node and in a
/// tooltip when it does not fit, which is what `UiLabel` is for.
class _BarName extends StatelessWidget {
  const _BarName({required this.text, required this.style});

  /// The name.
  final String text;

  /// The role it is set in: `mono.identifier` for a record, `title` for a
  /// screen that published its own name.
  final TextStyle style;

  @override
  Widget build(BuildContext context) =>
      UiLabel(text, style: style.copyWith(color: context.ui.color.ink));
}

/// Everything that sits between the top bar and the screen: the environment
/// band, the repository's blockers, the screen level error and the progress
/// strip.
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
      // 13 section 2.3: at compact the band is one `label` line on its tint,
      // 32 dp inside a 48 dp hit box, with the sentence, the contact and the
      // recovery behind a tap. The ask is published around this banner alone:
      // the blocker notice and the screen level error below it carry their own
      // recovery, and a band whose recovery is behind a tap is a band a
      // reviewer has to open before they can act.
      //
      // A route that asked the frame for a form comes first (13 section 3.4):
      // the record asks for the strip at every window, because its decision
      // bar and the band together are what its chrome budget is spent on. The
      // window decides only where no route asked.
      UiBandForm(
        form:
            UiBandForm.of(context) ??
            (window.isCompact ? UiBannerForm.strip : UiBannerForm.full),
        child: EnvironmentBanner(
          environment: controller.environment,
          // The open collection names its own administrator, which is a
          // better answer than the build time default meant to cover every
          // collection at once (07 section 10).
          contactSentence: AdministratorContact.of(controller.scope).sentence,
        ),
      ),
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
///
/// The shell's, and drawn at the end of every bar the shell owns below large
/// (`AppShell.accountInBar`). Public because the record publishes a bar of its
/// own into the frame and 13 section 4.1 (polish 3) puts the same menu on it
/// in the same slot, so a reviewer inside a record can read which account
/// they are using and sign out without leaving it (05 section 2).
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
