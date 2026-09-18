/// The page frame (10 section 4.4, `UiScaffold`).
library;

import 'dart:math' as math;

import 'package:flutter/rendering.dart' show RenderProxyBox;
import 'package:flutter/scheduler.dart' show SchedulerBinding;
import 'package:flutter/widgets.dart';

import '../../foundation/fields.dart';
import '../../foundation/glass.dart';
import '../../foundation/theme.dart';
import '../../foundation/window.dart';
import '../../primitives/composition_markers.dart';
import '../../primitives/field_layer.dart';
import '../../primitives/frame_safe_notifier.dart';
import '../../primitives/glass_surface.dart';
import '../../primitives/modal_routes.dart';
import '../overlays/banner.dart';
import '../overlays/toast.dart';
import 'rail.dart';
import 'sidebar.dart';

/// The rectangle a screen asks the field layer to keep clear.
///
/// `UiScaffold.exclusion` is a constructor argument, and the frame is built by
/// the application's shell, which does not know where the photograph is. The
/// screen that does publishes it here and the enclosing scaffold clips its
/// fields out of it, so the 24 dp clear band around a matte is a clip on the
/// field layer rather than layout inside the pane. Principle 1 of 09
/// section 2 is why it exists at all: a colour cast on a faded label is a
/// data error.
///
/// ```dart
/// UiScaffoldExclusion.of(context)?.publish(matte.inflate(clearBand));
/// ```
///
/// Null outside a scaffold, which is what a component test pumping a pane on
/// its own has, so a publisher is a single call with no branch. A screen that
/// leaves publishes null, and one that stops being visible publishes null in
/// `dispose`; nothing else clears it.
class UiScaffoldExclusion extends ChangeNotifier with FrameSafeNotifier {
  /// What is kept clear now, or null for nothing.
  Rect? get rect => _rect;
  Rect? _rect;

  /// Asks for [rect] to be kept clear. Null asks for nothing.
  ///
  /// Safe to call from a layout callback, which is where a pane learns its
  /// own rectangle: a change reported while the frame is being built is
  /// announced after it, because the scaffold above is already laid out by
  /// then and rebuilding it during its own build is not allowed.
  void publish(Rect? rect) {
    if (rect == _rect) return;
    _rect = rect;
    announce();
  }

  /// The nearest scaffold's exclusion, or null when there is no scaffold.
  ///
  /// Reads without depending: a publisher wants the object, not a rebuild
  /// every time the rectangle it published itself moves.
  static UiScaffoldExclusion? of(BuildContext context) => context
      .getInheritedWidgetOfExactType<_UiScaffoldExclusionScope>()
      ?.exclusion;
}

/// What the routed screen asks of the frame around it (13 section 3.4).
///
/// The shell builds one [UiScaffold] and the router swaps the body inside it,
/// so the frame outlives the route and cannot be given the route's arguments
/// at its own call site. The screen that knows publishes them here and the
/// frame reads them, which is the same seam [UiScaffoldExclusion] already is,
/// and for the same reason.
///
/// Six asks, each null until a screen makes it, and each winning over what
/// the scaffold's caller passed:
///
/// - [setTopBar] replaces the bar across the top. A record names itself and
///   offers the way out of itself, and neither fact reaches the shell that
///   built the frame (13 sections 2.4 and 4.1).
/// - [setTitle] and [setLeading] name the bar and its start slot without
///   replacing it (polish 3). A shell derives both by route; a screen that
///   knows better publishes one of them, and the frame hands the two to the
///   `UiTopBar` in the slot through [UiTopBarAsk], whichever of the two
///   built it and whatever it is wrapped in.
/// - [setActionBar] fills the sticky pane above the navigation. The decision
///   bar of 13 section 3.3 is what goes in it.
/// - [setNavVisible] hides the navigation pill on a screen that is inside a
///   record, where the way out is the top bar's back (13 section 2.3). The
///   navigation keeps its state while it is hidden, so a pill that comes back
///   comes back on the destination it was on.
/// - [setBandCompact] asks for the one line form of the environment band.
///   The frame publishes the ask to its own banner slot, and `UiBanner`
///   resolves it, so the shell's call site does not change.
///
/// A screen publishes what it wants when it is built and gives it back when
/// it leaves, exactly as it does for an exclusion. It names itself as the
/// owner, and [release] then gives back only what it still owns:
///
/// ```dart
/// @override
/// void didChangeDependencies() {
///   super.didChangeDependencies();
///   _slots = UiScaffoldSlots.of(context)
///     ?..setNavVisible(false, owner: this)
///     ..setActionBar(_decisionBar(), owner: this);
/// }
///
/// @override
/// void dispose() {
///   _slots?.release(this);
///   super.dispose();
/// }
/// ```
///
/// The owner is what makes a route change safe. A router that swaps one
/// screen for another builds the new one before it disposes the old, so a
/// screen that cleared the slots outright on the way out would take the next
/// screen's decision bar with it.
///
/// Null outside a scaffold, which is what a component test pumping one screen
/// on its own has, so a publisher is one call with no branch.
class UiScaffoldSlots extends ChangeNotifier with FrameSafeNotifier {
  /// What the page put in the top bar, or null for the caller's own.
  Widget? get topBar => _topBar;
  Widget? _topBar;

  /// What the page named the bar, or null for the bar's own title.
  String? get title => _title;
  String? _title;

  /// What the page put in the bar's start slot, or null for the bar's own.
  Widget? get leading => _leading;
  Widget? _leading;

  /// What the page put in the action bar, or null for the caller's own.
  Widget? get actionBar => _actionBar;
  Widget? _actionBar;

  /// Whether the page wants the navigation drawn, or null for the caller's
  /// own answer.
  bool? get navVisible => _navVisible;
  bool? _navVisible;

  /// Whether the page wants the one line band, or null to leave the band as
  /// the caller built it.
  bool? get bandCompact => _bandCompact;
  bool? _bandCompact;

  Object? _topBarOwner;
  Object? _titleOwner;
  Object? _leadingOwner;
  Object? _actionBarOwner;
  Object? _navOwner;
  Object? _bandOwner;

  /// Puts [bar] across the top of the frame. Null gives the slot back, where
  /// [owner] holds it or names no one.
  ///
  /// [owner] is whoever is asking, as it is for every other slot here.
  void setTopBar(Widget? bar, {Object? owner}) {
    if (bar == null && !_mayClear(_topBarOwner, owner)) return;
    _topBarOwner = bar == null ? null : owner;
    if (bar == _topBar) return;
    _topBar = bar;
    announce();
  }

  /// Names the bar across the top [title]. Null gives the slot back, where
  /// [owner] holds it or names no one.
  ///
  /// The bar in the slot keeps everything else it was built with: a screen
  /// that is one route of a shell names itself without rebuilding the
  /// switcher and the commands the shell put beside the name.
  void setTitle(String? title, {Object? owner}) {
    if (title == null && !_mayClear(_titleOwner, owner)) return;
    _titleOwner = title == null ? null : owner;
    if (title == _title) return;
    _title = title;
    announce();
  }

  /// Puts [leading] in the bar's start slot. Null gives the slot back, where
  /// [owner] holds it or names no one.
  void setLeading(Widget? leading, {Object? owner}) {
    if (leading == null && !_mayClear(_leadingOwner, owner)) return;
    _leadingOwner = leading == null ? null : owner;
    if (leading == _leading) return;
    _leading = leading;
    announce();
  }

  /// Puts [bar] in the frame's action bar. Null gives the slot back, where
  /// [owner] holds it or names no one.
  ///
  /// [owner] is whoever is asking, normally the `State` that publishes it, so
  /// that [release] can give back only what is still theirs, and so that a
  /// screen giving back a bar it no longer needs cannot take another screen's
  /// with it: the queue stays mounted under the record pushed over it, and its
  /// null on the route change arrived one frame after the record's decision
  /// bar did.
  void setActionBar(Widget? bar, {Object? owner}) {
    if (bar == null && !_mayClear(_actionBarOwner, owner)) return;
    _actionBarOwner = bar == null ? null : owner;
    if (bar == _actionBar) return;
    _actionBar = bar;
    announce();
  }

  /// Asks for the navigation to be drawn or hidden. Null gives the answer
  /// back to the frame's caller, where [owner] holds it or names no one.
  void setNavVisible(bool? visible, {Object? owner}) {
    if (visible == null && !_mayClear(_navOwner, owner)) return;
    _navOwner = visible == null ? null : owner;
    if (visible == _navVisible) return;
    _navVisible = visible;
    announce();
  }

  /// Asks for the one line environment band. Null gives the answer back,
  /// where [owner] holds it or names no one.
  void setBandCompact(bool? compact, {Object? owner}) {
    if (compact == null && !_mayClear(_bandOwner, owner)) return;
    _bandOwner = compact == null ? null : owner;
    if (compact == _bandCompact) return;
    _bandCompact = compact;
    announce();
  }

  /// True where a null from [asking] may give back a slot [holder] holds.
  ///
  /// A caller that names itself gives back only what it holds. A caller that
  /// names no one, which is [release] itself and a shell publishing on its
  /// own frame, gives the slot back outright.
  static bool _mayClear(Object? holder, Object? asking) =>
      asking == null || holder == null || identical(holder, asking);

  /// Gives back every slot [owner] still holds.
  ///
  /// A screen calls this in `dispose`. A slot someone else has published to
  /// since is left alone, which is what makes a route change safe: the
  /// screen arriving publishes before the screen leaving is disposed.
  void release(Object owner) {
    if (identical(_topBarOwner, owner)) setTopBar(null);
    if (identical(_titleOwner, owner)) setTitle(null);
    if (identical(_leadingOwner, owner)) setLeading(null);
    if (identical(_actionBarOwner, owner)) setActionBar(null);
    if (identical(_navOwner, owner)) setNavVisible(null);
    if (identical(_bandOwner, owner)) setBandCompact(null);
  }

  /// The nearest scaffold's slots, or null when there is no scaffold.
  ///
  /// Reads without depending, the way [UiScaffoldExclusion.of] does: a
  /// publisher wants the object, not a rebuild every time it publishes to it.
  static UiScaffoldSlots? of(BuildContext context) =>
      context.getInheritedWidgetOfExactType<_UiScaffoldSlotsScope>()?.slots;
}

/// What the routed screen asked of the frame's top bar (13 section 3.4;
/// polish 3).
///
/// Published by `UiScaffold` around its top bar slot and read by `UiTopBar`,
/// so a screen's `UiScaffoldSlots.setTitle` or `setLeading` reaches the bar
/// the shell built, whatever the shell wrapped it in, without the frame
/// having to rebuild a widget it cannot read. A bar outside a frame finds
/// none and draws its own.
class UiTopBarAsk extends InheritedWidget {
  /// Publishes [title] and [leading] to the bar in [child].
  const UiTopBarAsk({
    super.key,
    this.title,
    this.leading,
    required super.child,
  });

  /// What the page named the bar, or null for the bar's own title.
  final String? title;

  /// What the page put in the bar's start slot, or null for the bar's own.
  final Widget? leading;

  /// The nearest ask above [context], or null outside a frame.
  static UiTopBarAsk? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<UiTopBarAsk>();

  @override
  bool updateShouldNotify(UiTopBarAsk oldWidget) =>
      oldWidget.title != title || oldWidget.leading != leading;
}

/// Publishes one scaffold's slots to its body.
class _UiScaffoldSlotsScope extends InheritedWidget {
  const _UiScaffoldSlotsScope({required this.slots, required super.child});

  final UiScaffoldSlots slots;

  @override
  bool updateShouldNotify(_UiScaffoldSlotsScope oldWidget) =>
      oldWidget.slots != slots;
}

/// Publishes one scaffold's exclusion to its body.
class _UiScaffoldExclusionScope extends InheritedWidget {
  const _UiScaffoldExclusionScope({
    required this.exclusion,
    required super.child,
  });

  final UiScaffoldExclusion exclusion;

  @override
  bool updateShouldNotify(_UiScaffoldExclusionScope oldWidget) =>
      oldWidget.exclusion != exclusion;
}

/// Where a scaffold puts its navigation.
enum UiNavPlacement {
  /// Over the body, above the bottom safe area. The pill.
  floating,

  /// Beside the body, in flow, full height. The rail and the sidebar.
  beside,
}

/// What a scaffold tells its body about the frame around it.
///
/// Read with [UiScaffold.of]. A body with no scaffold above it reads [none],
/// which is a component test pumping a control on its own rather than an
/// error.
@immutable
class UiScaffoldGeometry {
  /// Binds the two facts a body needs.
  const UiScaffoldGeometry({
    required this.bottomInset,
    required this.scrolledUnder,
  });

  /// The space the bottom safe area and the floating chrome occupy.
  ///
  /// A scroll view in the body pads its content by this so its last row
  /// clears the pill and the action bar instead of hiding under them. It is
  /// the bottom safe area, or the keyboard when that is taller, plus the
  /// measured height of whatever the scaffold floats above it.
  final double bottomInset;

  /// True once the body has scrolled under the top bar.
  ///
  /// `UiTopBar` reads this to decide whether to fill with `glass.flat`.
  final bool scrolledUnder;

  /// What a body with no scaffold above it reads.
  static const UiScaffoldGeometry none = UiScaffoldGeometry(
    bottomInset: 0,
    scrolledUnder: false,
  );

  @override
  bool operator ==(Object other) =>
      other is UiScaffoldGeometry &&
      other.bottomInset == bottomInset &&
      other.scrolledUnder == scrolledUnder;

  @override
  int get hashCode => Object.hash(bottomInset, scrolledUnder);
}

/// The resolved measurements of one scaffold (10 section 1.5).
@immutable
class UiScaffoldStyle {
  /// Binds every token the frame draws with.
  const UiScaffoldStyle({
    required this.gap,
    required this.gutter,
    required this.actionBarPadding,
    required this.actionBarRadius,
  });

  /// The space under the floating navigation, and between it and the action
  /// bar. 16 dp (10 section 4.4).
  final double gap;

  /// The space between the floating chrome and the window's side edges.
  final double gutter;

  /// The padding inside the action bar's pane.
  final EdgeInsetsGeometry actionBarPadding;

  /// The action bar's corner radius.
  final double actionBarRadius;

  /// The style for [ui].
  static UiScaffoldStyle resolve(UiThemeData ui) => UiScaffoldStyle(
    gap: ui.space.s4,
    gutter: ui.space.s4,
    actionBarPadding: EdgeInsetsDirectional.all(ui.space.s2),
    // A tile rather than a capsule: an action bar carries a sentence about
    // what is about to change as often as it carries a row of buttons, and a
    // capsule around two lines of text reads as a pill that grew.
    actionBarRadius: ui.shape.tile,
  );
}

/// The page frame: the ground, the sky, and the slots a page is made of.
///
/// It paints `ground` and a [SkyPreset] through `FieldLayer`, then lays out
/// [topBar], [banner], [body], [actionBar], [nav] and [overlays]. The
/// navigation either floats over the body, which is what a pill does, or sits
/// beside it, which is what a rail and a sidebar do; [navPlacement] says
/// which, and is inferred from the widget when it is left null.
///
/// Safe areas: the top bar owns the top and side insets so its pane reaches
/// the window's edges, and everything below it is given a `MediaQuery` with
/// the padding removed, so nothing insets twice. What the body needs to know
/// about the bottom, where the pill and the keyboard are, it reads from
/// [UiScaffold.of].
///
/// Paint order in the body area is body, [overlays], then the action bar and
/// the navigation, so an overlay sits over the page and under the chrome
/// (10 section 4.4). With no [overlays] of its own the frame wraps [body] in
/// a `UiToastHost` given [UiScaffoldGeometry.bottomInset], so `UiToasts.show`
/// reaches a host from anywhere in any page and its toasts clear the chrome.
///
/// Retires `Scaffold`.
class UiScaffold extends StatefulWidget {
  /// A page frame with the given slots.
  const UiScaffold({
    super.key,
    this.body,
    this.topBar,
    this.banner,
    this.actionBar,
    this.nav,
    this.overlays,
    this.sky = SkyPreset.home,
    this.exclusion,
    this.navPlacement,
    this.navVisible = true,
  });

  /// The page itself.
  final Widget? body;

  /// The bar across the top. A `UiTopBar` on every page that has one.
  ///
  /// A routed screen that names itself replaces it through
  /// `UiScaffoldSlots.of(context).setTopBar`, and what the screen asks for
  /// wins over this, exactly as it does for the action bar.
  final Widget? topBar;

  /// A full width message under the top bar. The environment banner.
  final Widget? banner;

  /// The sticky actions, drawn on a `glass.floating` pane above the
  /// navigation.
  final Widget? actionBar;

  /// The navigation: a `UiPillNav`, a `UiRail` or a `UiSidebar`, chosen by
  /// the caller from the window class (05 section 2).
  final Widget? nav;

  /// The layer over the body and under the navigation.
  ///
  /// Its intended occupant is a `UiToastHost`, and a scaffold installs one
  /// itself when this is null, wrapping [body] so that `UiToasts.show` works
  /// from anywhere inside any page with no ceremony at the call site. The
  /// host is given [UiScaffoldGeometry.bottomInset], so a toast clears the
  /// pill and the action bar rather than sitting over them.
  ///
  /// A caller that wants something else page wide, or no toast layer at all,
  /// passes it here: whatever this holds replaces the default, and is laid
  /// over the body and under the chrome.
  final Widget? overlays;

  /// Which sky preset paints behind the page (09 section 3.2).
  final SkyPreset sky;

  /// A rectangle the fields are clipped out of, in the frame's coordinates.
  ///
  /// The photograph matte plus `UiFields.matteExclusion`. A colour cast on a
  /// faded label is a data error (09 section 2, principle 1).
  final Rect? exclusion;

  /// Where the navigation goes. Null infers it from [nav].
  final UiNavPlacement? navPlacement;

  /// Whether the navigation is drawn.
  ///
  /// A screen inside a record hides the pill, because the way out of a record
  /// is the top bar's back and a pill that offers three other places to be is
  /// chrome the reviewer did not ask for (13 section 2.3). The routed screen
  /// asks for it through `UiScaffoldSlots.of(context).setNavVisible(false)`,
  /// and what the page asks for wins over this.
  ///
  /// A hidden navigation keeps its state and takes no height, so a pill that
  /// comes back comes back on the destination it was on rather than gliding
  /// in from the first one.
  final bool navVisible;

  /// Where [nav] goes when a caller does not say.
  ///
  /// A rail and a sidebar are columns beside the body; everything else,
  /// the pill included, floats over it.
  static UiNavPlacement placementOf(Widget? nav) =>
      nav is UiRail || nav is UiSidebar
      ? UiNavPlacement.beside
      : UiNavPlacement.floating;

  /// What the nearest scaffold tells this context about the frame.
  ///
  /// Returns [UiScaffoldGeometry.none] when there is no scaffold above.
  static UiScaffoldGeometry of(BuildContext context) =>
      context
          .dependOnInheritedWidgetOfExactType<_UiScaffoldScope>()
          ?.geometry ??
      UiScaffoldGeometry.none;

  @override
  State<UiScaffold> createState() => _UiScaffoldState();
}

class _UiScaffoldState extends State<UiScaffold> {
  bool _scrolledUnder = false;
  double _floatingHeight = 0;

  /// What the page inside this frame asks to be kept clear.
  final UiScaffoldExclusion _exclusion = UiScaffoldExclusion();

  /// What the page inside this frame asks of the frame itself.
  final UiScaffoldSlots _slots = UiScaffoldSlots();

  /// Whether a modal shown from inside this frame is over it.
  final UiModalScope _modal = UiModalScope();

  @override
  void initState() {
    super.initState();
    _slots.addListener(_slotsChanged);
    _modal.addListener(_slotsChanged);
  }

  @override
  void dispose() {
    _slots.removeListener(_slotsChanged);
    _modal.removeListener(_slotsChanged);
    _slots.dispose();
    _modal.dispose();
    _exclusion.dispose();
    super.dispose();
  }

  void _slotsChanged() {
    if (mounted) setState(() {});
  }

  UiThemeData? _flatFrom;
  UiThemeData? _flatCache;

  /// [base] with the blur turned off, so every frosted pane under it draws as
  /// the solid surface `GlassQuality.off` specifies.
  ///
  /// Cached on the identity of what it was built from, because [UiThemeData]
  /// has no value equality and a fresh one per build would tell every widget
  /// in the page that its tokens had changed.
  UiThemeData _flat(UiThemeData base) {
    if (!identical(base, _flatFrom)) {
      _flatFrom = base;
      _flatCache = base.copyWith(quality: GlassQuality.off);
    }
    return _flatCache!;
  }

  /// True once a vertical scroll view in the body has anything above its
  /// viewport.
  ///
  /// Depth zero only, so a list inside a pane inside the page does not put
  /// the top bar's fill on and off while the reviewer scrolls something else.
  bool _onScroll(ScrollNotification notification) {
    if (notification.depth != 0) return false;
    if (notification.metrics.axis != Axis.vertical) return false;
    final bool under = notification.metrics.extentBefore > 0;
    if (under != _scrolledUnder) {
      setState(() => _scrolledUnder = under);
    }
    return false;
  }

  void _floatingMeasured(double height) {
    if (!mounted || height == _floatingHeight) return;
    setState(() => _floatingHeight = height);
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiScaffoldStyle style = UiScaffoldStyle.resolve(ui);
    final EdgeInsets safe = MediaQuery.paddingOf(context);
    final double keyboard = MediaQuery.viewInsetsOf(context).bottom;
    // The keyboard covers the home indicator, so the two do not add up.
    final double bottomSafe = math.max(safe.bottom, keyboard);

    // Where the frame's panes go (13 section 2.2; 09 section 3.3).
    //
    // Every pinned region used to draw its own: the top bar's fill once
    // content scrolled under it, the action bar, the pill, and a collapsed
    // collapsing header's chrome. That is four panes on a phone where the
    // budget is one, and two of them stacked is the "glass decision bar over
    // a glass pill" 13 section 0 reads as a defect. A compact window spends
    // its one pane where the reviewer's thumb is, on the chrome the frame
    // floats, and turns the blur off everywhere else inside itself, so a pane
    // that is no longer frosted is still the surface it was, drawn solid. A
    // window with no action bar spends it on the navigation instead, because
    // a pill is the only thing floating over the page on a list screen.
    //
    // A medium window spends two (polish 3): the chrome the frame floats and
    // the pane over the photograph, a collapsed header's chrome in the body.
    // The top bar is never one of them, at any class. Its fill once content
    // scrolls under it is the same surface drawn solid, as it is at compact,
    // so a record at medium blurs the action bar and the collapsed header's
    // chrome and nothing else; the wider classes have room for more panes
    // and spend none of it on a bar that is chrome the reviewer scrolls
    // past.
    //
    // A sheet or a dialog is pushed over the frame rather than inside it and
    // keeps its own pane, which is the surface 13 section 2.2 exempts and 09
    // section 3.3 counts within the window's budget. While one is over this
    // frame, every pane the frame draws is under its scrim, and a pane under
    // a scrim is a save layer nobody sees: the frame draws them all solid
    // until the modal begins to leave (polish 3).
    final bool compact = WindowClass.of(context).isCompact;
    final bool covered = _modal.isOpen;
    final UiThemeData? published = context
        .dependOnInheritedWidgetOfExactType<UiTheme>()
        ?.data;
    final UiThemeData ambient = published ?? ui;
    final UiThemeData flat = _flat(ambient);
    // Every region is wrapped in a theme whatever it is given, and only the
    // tokens change: a wrapper that came and went with a modal would rebuild
    // the page under it from nothing, and the reviewer's scroll position
    // with it.
    //
    // The solid form of every pane under [child].
    Widget solid(Widget child) => UiTheme(data: flat, child: child);
    // The chrome the frame floats: its pane, unless a modal covers it.
    Widget floated(Widget child) =>
        UiTheme(data: covered ? flat : ambient, child: child);
    // A region the frame does not float: solid at compact, as built above it.
    Widget unfloated(Widget child) =>
        UiTheme(data: compact || covered ? flat : ambient, child: child);

    final UiNavPlacement placement =
        widget.navPlacement ?? UiScaffold.placementOf(widget.nav);
    final bool beside =
        widget.nav != null && placement == UiNavPlacement.beside;
    final bool floats =
        widget.nav != null && placement == UiNavPlacement.floating;
    // What the page asked for wins over what the caller passed, the rule the
    // exclusion already follows: the shell builds the frame and the routed
    // screen is the one that knows what the route needs (13 section 3.4).
    final bool navShown = _slots.navVisible ?? widget.navVisible;
    final Widget? actionBar = _slots.actionBar ?? widget.actionBar;
    final Widget? bar = _slots.topBar ?? widget.topBar;

    // Where the one pane goes at compact: the action bar has it wherever
    // there is one, and the navigation keeps its own otherwise.
    final bool navKeepsPane = compact && actionBar == null;
    final bool pillShown = floats && navShown;

    // The action bar's two forms (polish 3). Above a pill it floats as a
    // tile, with the pill's own gap under it, because the pill is the lowest
    // chrome and a capsule floats over the page by design (10 section 4.4).
    // Where nothing floats under it, inside a record or beside a rail, the
    // bar is the lowest chrome and anchors to the window's bottom edge: the
    // pane spans the body's width with its top corners turned, and the
    // bottom system inset is padding inside the pane below the bar, so the
    // page's content never shows in a band between the bar and the edge. The
    // device captures found about 48 dp of the record's evidence scrolling
    // under the decision bar on a phone with gesture navigation, and the
    // readings' footer rows under it on a tablet with a home indicator.
    //
    // The keyboard covers the home indicator, so when it is up the pane
    // sits on the keyboard's edge and carries no inset of its own.
    final bool anchored = actionBar != null && !pillShown;
    final double insetInside = anchored && keyboard <= safe.bottom
        ? safe.bottom
        : 0;
    // The distance from the window's bottom edge to the floating column.
    final double chromeBottom = anchored
        ? bottomSafe - insetInside
        : bottomSafe + style.gap;
    final List<Widget> floatingChrome = <Widget>[
      if (actionBar != null)
        floated(
          GlassSurface(
            level: GlassLevel.floating,
            radius: anchored ? null : style.actionBarRadius,
            corners: anchored
                ? BorderRadius.vertical(
                    top: Radius.circular(style.actionBarRadius),
                  )
                : null,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              // A floating tile keeps the width of what it holds, as it always
              // did; an anchored bar spans the body.
              crossAxisAlignment: anchored
                  ? CrossAxisAlignment.stretch
                  : CrossAxisAlignment.center,
              children: <Widget>[
                // The marker measures the bar and its padding, the 64 dp of
                // 13 section 4.1, and not the system inset the pane extends
                // through: that inset is the device's, and content could not
                // have used it either way.
                PinnedChrome(
                  region: UiPinnedRegion.actionBar,
                  child: Padding(
                    padding: style.actionBarPadding,
                    child: unfloated(actionBar),
                  ),
                ),
                if (insetInside > 0) SizedBox(height: insetInside),
              ],
            ),
          ),
        ),
      if (actionBar != null && pillShown) SizedBox(height: style.gap),
      // Hidden rather than removed: a pill taken out of the tree loses the
      // destination it was on and glides in from the first one when the
      // reviewer leaves the record. Offstage keeps the state and takes no
      // height, so the chrome budget counts it at nothing.
      if (floats)
        PinnedChrome(
          region: UiPinnedRegion.navigation,
          child: navKeepsPane
              ? floated(Offstage(offstage: !navShown, child: widget.nav!))
              : unfloated(Offstage(offstage: !navShown, child: widget.nav!)),
        ),
    ];

    // What the body pads its content by: everything from the window's edge
    // to the top of whatever the frame floats, inset included, so the last
    // row clears the pane and not only the bar in it.
    final double bottomInset = floatingChrome.isEmpty
        ? bottomSafe
        : chromeBottom + _floatingHeight;

    // With no overlay layer of its own, the frame installs the one every page
    // wants: a toast host around the body, so `UiToasts.show` finds an
    // ancestor from anywhere inside the page. It has to wrap the body rather
    // than sit beside it, because `UiToastHost.maybeOf` walks upward.
    final Widget? body = widget.body == null
        ? null
        : unfloated(
            widget.overlays != null
                ? widget.body!
                : UiToastHost(bottomInset: bottomInset, child: widget.body!),
          );

    Widget bodyArea = Stack(
      children: <Widget>[
        if (body != null) Positioned.fill(child: body),
        if (widget.overlays != null) Positioned.fill(child: widget.overlays!),
        if (floatingChrome.isNotEmpty)
          PositionedDirectional(
            start: 0,
            end: 0,
            bottom: chromeBottom,
            // The body area already clears the side safe areas (see
            // `belowBar`), so the gutter is the whole of the side padding; an
            // anchored bar spans the body's width and has none.
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: anchored ? 0 : style.gutter,
              ),
              child: _MeasureHeight(
                onHeight: _floatingMeasured,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: floatingChrome,
                ),
              ),
            ),
          ),
      ],
    );

    bodyArea = NotificationListener<ScrollNotification>(
      onNotification: _onScroll,
      child: bodyArea,
    );

    Widget belowBar = Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        // A screen's ask hides the navigation the frame floats, the pill,
        // where the way out is the bar's back (13 section 2.3). A rail and a
        // sidebar are columns beside the body rather than chrome over it, and
        // a desktop with its navigation taken away inside a record has no
        // navigation at all, so only the caller's own answer hides them.
        if (beside)
          unfloated(Offstage(offstage: !widget.navVisible, child: widget.nav!)),
        Expanded(child: bodyArea),
      ],
    );

    // The side navigation and the body clear the side notches; the top bar
    // does its own, because its pane has to reach the window's edge.
    belowBar = Padding(
      padding: EdgeInsets.only(left: safe.left, right: safe.right),
      child: belowBar,
    );
    if (bar == null && safe.top > 0) {
      belowBar = Padding(
        padding: EdgeInsets.only(top: safe.top),
        child: belowBar,
      );
    }
    belowBar = MediaQuery.removePadding(
      context: context,
      removeTop: true,
      removeLeft: true,
      removeRight: true,
      removeBottom: true,
      child: belowBar,
    );

    // The band's form is the third thing a route asks for. The frame passes
    // the ask down to its own banner slot rather than out to the shell that
    // built it, and `UiBanner` resolves it, so the shell's call site is the
    // same on every route (13 sections 3.4 and 3.5).
    final bool? bandCompact = _slots.bandCompact;
    Widget? banner = widget.banner;
    if (banner != null) {
      if (bandCompact != null) {
        banner = UiBandForm(
          form: bandCompact ? UiBannerForm.strip : UiBannerForm.full,
          child: banner,
        );
      }
      banner = PinnedChrome(
        region: UiPinnedRegion.band,
        child: unfloated(banner),
      );
    }
    // Never a pane, at any class: see the policy above. The title and the
    // leading a screen asked for ride down to the bar in the slot.
    final Widget? topBar = bar == null
        ? null
        : PinnedChrome(
            region: UiPinnedRegion.topBar,
            child: UiTopBarAsk(
              title: _slots.title,
              leading: _slots.leading,
              child: solid(bar),
            ),
          );

    return _UiScaffoldScope(
      geometry: UiScaffoldGeometry(
        bottomInset: bottomInset,
        scrolledUnder: _scrolledUnder,
      ),
      child: _UiScaffoldExclusionScope(
        exclusion: _exclusion,
        child: _UiScaffoldSlotsScope(
          slots: _slots,
          child: UiModalScope.publish(
            scope: _modal,
            child: ListenableBuilder(
              listenable: _exclusion,
              builder: (BuildContext context, Widget? child) => FieldLayer(
                preset: widget.sky,
                // What the page asked for wins over what the caller passed, and
                // the caller's is the fallback: a shell that knows the rectangle
                // still states it, and a screen inside one that does not can say
                // so for itself.
                exclusion: _exclusion.rect ?? widget.exclusion,
                child: child,
              ),
              child: Column(
                children: <Widget>[
                  ?topBar,
                  ?banner,
                  Expanded(child: belowBar),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Publishes one scaffold's geometry to its body.
class _UiScaffoldScope extends InheritedWidget {
  const _UiScaffoldScope({required this.geometry, required super.child});

  final UiScaffoldGeometry geometry;

  @override
  bool updateShouldNotify(_UiScaffoldScope oldWidget) =>
      oldWidget.geometry != geometry;
}

/// Reports its own height after each layout that changes it.
///
/// The scaffold publishes an exact [UiScaffoldGeometry.bottomInset], and the
/// action bar's height belongs to the caller, so the frame has to measure
/// what it floats rather than guess it. The report is a post frame callback,
/// so the inset a body reads is the one from the frame before: the same one
/// frame of lag `Scaffold` documents for `ScaffoldGeometry`, and it settles
/// because the measured column does not depend on the inset.
class _MeasureHeight extends SingleChildRenderObjectWidget {
  const _MeasureHeight({required this.onHeight, required Widget super.child});

  final ValueChanged<double> onHeight;

  @override
  RenderObject createRenderObject(BuildContext context) =>
      _RenderMeasureHeight(onHeight);

  @override
  void updateRenderObject(
    BuildContext context,
    covariant _RenderMeasureHeight renderObject,
  ) {
    renderObject.onHeight = onHeight;
  }
}

class _RenderMeasureHeight extends RenderProxyBox {
  _RenderMeasureHeight(this.onHeight);

  ValueChanged<double> onHeight;
  double? _reported;

  @override
  void performLayout() {
    super.performLayout();
    if (_reported == size.height) return;
    _reported = size.height;
    final double measured = size.height;
    SchedulerBinding.instance.addPostFrameCallback(
      (Duration _) => onHeight(measured),
    );
  }
}
