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
/// where this application reads it.
library;

import 'dart:async';

import 'package:flutter/scheduler.dart' show SchedulerBinding, SchedulerPhase;
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../administrator_contact.dart';
import '../models.dart';
import '../vocabulary.dart';
import '../widgets/widgets.dart';
import '../workspace.dart';
import 'routes.dart';

/// What a routed screen asks of the shell's top bar (13 sections 2.4 and 4.1).
///
// fe/polish-3: UiScaffoldSlots should carry the bar's title and leading the
// way it already carries the action bar, the navigation and the band's form,
// so a routed screen names the frame through one hook rather than two. This
// is that hook, written in the application until the package grows it, and it
// follows UiScaffoldSlots clause for clause: each ask is null until a screen
// makes it, each wins over what the shell derived from the route, each names
// an owner, and `release` gives back only what that owner still holds,
// because a router builds the screen arriving before it disposes the screen
// leaving.
///
/// ```dart
/// @override
/// void didChangeDependencies() {
///   super.didChangeDependencies();
///   _chrome = ShellChrome.of(context)?..setTitle(specimen.id, owner: this);
/// }
///
/// @override
/// void dispose() {
///   _chrome?.release(this);
///   super.dispose();
/// }
/// ```
///
/// Null outside the collection shell, which is what an entry screen and a
/// component test have, so a publisher is one call with no branch.
class ShellChrome extends ChangeNotifier {
  /// What the page put in the bar's title, or null for the route's own.
  String? get title => _title;
  String? _title;

  /// What the page put in the bar's leading slot, or null for the route's own.
  Widget? get leading => _leading;
  Widget? _leading;

  Object? _titleOwner;
  Object? _leadingOwner;
  bool _disposed = false;

  /// Names the screen in the bar. Null gives the slot back.
  void setTitle(String? title, {Object? owner}) {
    _titleOwner = title == null ? null : owner;
    if (title == _title) return;
    _title = title;
    _announce();
  }

  /// Puts [leading] in the bar's start slot. Null gives the slot back.
  void setLeading(Widget? leading, {Object? owner}) {
    _leadingOwner = leading == null ? null : owner;
    if (leading == _leading) return;
    _leading = leading;
    _announce();
  }

  /// Gives back every slot [owner] still holds.
  void release(Object owner) {
    if (identical(_titleOwner, owner)) setTitle(null);
    if (identical(_leadingOwner, owner)) setLeading(null);
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  /// Announces now, or after the frame when one is being built.
  ///
  /// A page publishes what it wants from the frame while it is being laid
  /// out, which is the one moment the frame above it cannot be rebuilt. The
  /// same guard `UiScaffoldSlots` carries, and for the same reason.
  void _announce() {
    final SchedulerPhase phase = SchedulerBinding.instance.schedulerPhase;
    if (phase == SchedulerPhase.persistentCallbacks ||
        phase == SchedulerPhase.midFrameMicrotasks) {
      SchedulerBinding.instance.addPostFrameCallback((Duration _) {
        if (!_disposed) notifyListeners();
      });
      return;
    }
    notifyListeners();
  }

  /// The nearest shell's chrome, or null when there is no shell above.
  ///
  /// Reads without depending: a publisher wants the object, not a rebuild
  /// every time it publishes to it.
  static ShellChrome? of(BuildContext context) =>
      context.getInheritedWidgetOfExactType<ShellChromeScope>()?.chrome;
}

/// Publishes one shell's [ShellChrome] to the screen inside it.
class ShellChromeScope extends InheritedWidget {
  /// Publishes [chrome] around [child].
  const ShellChromeScope({
    super.key,
    required this.chrome,
    required super.child,
  });

  /// What the routed screen publishes to.
  final ShellChrome chrome;

  @override
  bool updateShouldNotify(ShellChromeScope oldWidget) =>
      oldWidget.chrome != chrome;
}

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
  /// What the routed screen asks of the bar.
  final ShellChrome _chrome = ShellChrome();

  @override
  void dispose() {
    _chrome.dispose();
    super.dispose();
  }

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

    return ShellChromeScope(
      chrome: _chrome,
      child: ListenableBuilder(
        listenable: _chrome,
        builder: (BuildContext context, Widget? child) => UiScaffold(
          // The queue, intake and sources routes are the home sky; the record
          // route is the work sky (09 section 3.2). The pane that draws the
          // photograph publishes the matte's clear band through
          // `UiScaffoldExclusion.of(context)?.publish(rect)`, which the frame
          // clips its fields out of.
          sky: AppShell.skyOf(location),
          topBar: _TopBar(
            controller: controller,
            window: window,
            sidebar: sidebar,
            location: location,
            chrome: _chrome,
          ),
          banner: _Chrome(controller: controller, busy: busy, window: window),
          nav: navigation,
          navVisible: !(inRecord && !sidebar && !rail),
          body: child,
        ),
        // The routed screen is a nested `Navigator`, and a route's modal
        // barrier blocks the semantics of everything painted before it inside
        // the same semantics boundary. The shell's own chrome, the environment
        // band and this navigation, is painted first, so without a boundary of
        // its own the screen erased all of it: a reviewer working through a
        // browser's accessibility tree found a queue with no navigation and no
        // way into a record.
        //
        // Built once, outside the builder: what the bar says changing must not
        // rebuild the screen that said it.
        child: Semantics(
          container: true,
          explicitChildNodes: true,
          child: widget.child,
        ),
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
class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.controller,
    required this.window,
    required this.sidebar,
    required this.location,
    required this.chrome,
  });

  final WorkspaceController controller;
  final WindowClass window;
  final bool sidebar;
  final Uri location;
  final ShellChrome chrome;

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
    // title slot (13 section 4.1).
    //
    // The centre takes a widget, so a record names itself in
    // `mono.identifier`, which is the role 13 section 4.1 gives a specimen
    // id and which the title slot cannot draw. It also keeps the bar's last
    // action clear of the window's edge: `Popover` anchors a menu's start to
    // its trigger's start and flips only vertically (10 section 3), so a
    // trigger hard against the end of the bar opens its menu off the window.
    // That is a package defect and is recorded as one; this arrangement is
    // what 13 asks for anyway.
    final Widget? named = chrome.title != null
        ? _BarName(text: chrome.title!, style: context.ui.type.title)
        : inRecord
        ? _BarName(text: record, style: context.ui.type.mono.identifier)
        : null;
    final String? title = named != null || window.isCompact
        ? null
        : AppShell.markLabel;

    return _SolidBar(
      child: UiTopBar(
        // The rail and the sidebar carry the mark, so the bar carries it only
        // on a compact window, where there is neither. Inside a record the
        // slot is the way out, which is what 13 section 2.3 puts there.
        leading:
            chrome.leading ??
            (inRecord
                ? UiIconButton(
                    icon: UiIcons.back,
                    semanticsLabel: AppShell.backLabel,
                    tooltip: AppShell.backLabel,
                    onPressed: () => _leaveRecord(context),
                  )
                : window.isCompact
                ? const UiMark(label: AppShell.markLabel)
                : null),
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
          //
          // Not inside a record below large, where 13 section 4.1 gives the
          // bar three things: back, the specimen id and refresh. The account
          // is a tap away on the queue, and a menu opened from the last slot
          // of a bar that has no centre opens off the window: `Popover`
          // anchors a pane's start to its trigger's start and flips only
          // vertically, so a trigger at the window's end takes its pane with
          // it. That is a package defect, recorded as one, and this is 13's
          // own arrangement regardless.
          if (sidebar)
            UiTopBarAction(
              icon: UiIcons.help,
              label: AppShell.helpLabel,
              onPressed: () => context.push(AppRoutes.help),
            )
          else if (!inRecord)
            _AccountMenu(controller: controller),
        ],
      ),
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

/// The bar's surface on a compact window (13 section 2.2, wave A amendment).
///
// fe/polish-3: `UiTopBar` should take the scaffold's compact pane policy
// itself. The frame already turns the blur off inside itself, so the bar
// drawn under that policy is a `GlassSurface` with an opaque fill, which is
// still a pane where the budget is one. The amendment asks for the same
// surface drawn solid, so the bar keeps its fill and spends no pane: `ground`
// behind the bar and `scrolledUnder: false` on it, which is exactly what
// `UiStickyBar` draws behind the row that sticks under it.
///
/// Above compact the bar keeps the frosted pane the budget affords it.
class _SolidBar extends StatelessWidget {
  const _SolidBar({required this.child});

  /// The bar.
  final UiTopBar child;

  @override
  Widget build(BuildContext context) {
    if (!WindowClass.of(context).isCompact) return child;
    final UiTopBar bar = UiTopBar(
      leading: child.leading,
      title: child.title,
      center: child.center,
      actions: child.actions,
      scrolledUnder: false,
    );
    return UiScaffold.of(context).scrolledUnder
        ? ColoredBox(color: context.ui.color.ground, child: bar)
        : bar;
  }
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
      UiBandForm(
        form: window.isCompact ? UiBannerForm.strip : UiBannerForm.full,
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
