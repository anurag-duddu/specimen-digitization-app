/// The page frame (10 section 4.4, `UiScaffold`).
library;

import 'dart:math' as math;

import 'package:flutter/rendering.dart' show RenderProxyBox;
import 'package:flutter/scheduler.dart' show SchedulerBinding, SchedulerPhase;
import 'package:flutter/widgets.dart';

import '../../foundation/fields.dart';
import '../../foundation/glass.dart';
import '../../foundation/theme.dart';
import '../../primitives/composition_markers.dart';
import '../../primitives/field_layer.dart';
import '../../primitives/glass_surface.dart';
import '../overlays/banner.dart';
import '../overlays/toast.dart';
import 'rail.dart';
import 'sidebar.dart';

/// Announces a change now, or after the frame when one is being built.
///
/// A page publishes what it wants from the frame while it is being laid out,
/// which is the one moment the frame above it cannot be rebuilt. Both of the
/// scaffold's published channels defer to the end of the frame when they are
/// written during one, and announce immediately otherwise.
mixin _FrameSafeNotifier on ChangeNotifier {
  bool _disposed = false;

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

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
}

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
class UiScaffoldExclusion extends ChangeNotifier with _FrameSafeNotifier {
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
    _announce();
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
/// Three asks, each null until a screen makes it, and each winning over what
/// the scaffold's caller passed:
///
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
class UiScaffoldSlots extends ChangeNotifier with _FrameSafeNotifier {
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

  Object? _actionBarOwner;
  Object? _navOwner;
  Object? _bandOwner;

  /// Puts [bar] in the frame's action bar. Null gives the slot back.
  ///
  /// [owner] is whoever is asking, normally the `State` that publishes it, so
  /// that [release] can give back only what is still theirs.
  void setActionBar(Widget? bar, {Object? owner}) {
    _actionBarOwner = bar == null ? null : owner;
    if (bar == _actionBar) return;
    _actionBar = bar;
    _announce();
  }

  /// Asks for the navigation to be drawn or hidden. Null gives the answer
  /// back to the frame's caller.
  void setNavVisible(bool? visible, {Object? owner}) {
    _navOwner = visible == null ? null : owner;
    if (visible == _navVisible) return;
    _navVisible = visible;
    _announce();
  }

  /// Asks for the one line environment band. Null gives the answer back.
  void setBandCompact(bool? compact, {Object? owner}) {
    _bandOwner = compact == null ? null : owner;
    if (compact == _bandCompact) return;
    _bandCompact = compact;
    _announce();
  }

  /// Gives back every slot [owner] still holds.
  ///
  /// A screen calls this in `dispose`. A slot someone else has published to
  /// since is left alone, which is what makes a route change safe: the
  /// screen arriving publishes before the screen leaving is disposed.
  void release(Object owner) {
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

  @override
  void initState() {
    super.initState();
    _slots.addListener(_slotsChanged);
  }

  @override
  void dispose() {
    _slots.removeListener(_slotsChanged);
    _slots.dispose();
    _exclusion.dispose();
    super.dispose();
  }

  void _slotsChanged() {
    if (mounted) setState(() {});
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

    final List<Widget> floatingChrome = <Widget>[
      if (actionBar != null)
        PinnedChrome(
          region: UiPinnedRegion.actionBar,
          child: GlassSurface(
            level: GlassLevel.floating,
            radius: style.actionBarRadius,
            padding: style.actionBarPadding,
            child: actionBar,
          ),
        ),
      if (actionBar != null && floats && navShown) SizedBox(height: style.gap),
      // Hidden rather than removed: a pill taken out of the tree loses the
      // destination it was on and glides in from the first one when the
      // reviewer leaves the record. Offstage keeps the state and takes no
      // height, so the chrome budget counts it at nothing.
      if (floats)
        PinnedChrome(
          region: UiPinnedRegion.navigation,
          child: Offstage(offstage: !navShown, child: widget.nav!),
        ),
    ];

    final double bottomInset = floatingChrome.isEmpty
        ? bottomSafe
        : bottomSafe + style.gap + _floatingHeight;

    // With no overlay layer of its own, the frame installs the one every page
    // wants: a toast host around the body, so `UiToasts.show` finds an
    // ancestor from anywhere inside the page. It has to wrap the body rather
    // than sit beside it, because `UiToastHost.maybeOf` walks upward.
    final Widget? body = widget.body == null
        ? null
        : widget.overlays != null
        ? widget.body!
        : UiToastHost(bottomInset: bottomInset, child: widget.body!);

    Widget bodyArea = Stack(
      children: <Widget>[
        if (body != null) Positioned.fill(child: body),
        if (widget.overlays != null) Positioned.fill(child: widget.overlays!),
        if (floatingChrome.isNotEmpty)
          PositionedDirectional(
            start: 0,
            end: 0,
            bottom: bottomSafe + style.gap,
            child: Padding(
              padding: EdgeInsets.only(
                left: safe.left + style.gutter,
                right: safe.right + style.gutter,
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
        if (beside) Offstage(offstage: !navShown, child: widget.nav!),
        Expanded(child: bodyArea),
      ],
    );

    // The side navigation and the body clear the side notches; the top bar
    // does its own, because its pane has to reach the window's edge.
    belowBar = Padding(
      padding: EdgeInsets.only(left: safe.left, right: safe.right),
      child: belowBar,
    );
    if (widget.topBar == null && safe.top > 0) {
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
      banner = PinnedChrome(region: UiPinnedRegion.band, child: banner);
    }
    final Widget? topBar = widget.topBar == null
        ? null
        : PinnedChrome(region: UiPinnedRegion.topBar, child: widget.topBar!);

    return _UiScaffoldScope(
      geometry: UiScaffoldGeometry(
        bottomInset: bottomInset,
        scrolledUnder: _scrolledUnder,
      ),
      child: _UiScaffoldExclusionScope(
        exclusion: _exclusion,
        child: _UiScaffoldSlotsScope(
          slots: _slots,
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
