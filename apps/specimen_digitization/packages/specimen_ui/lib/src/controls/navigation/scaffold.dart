/// The page frame (10 section 4.4, `UiScaffold`).
library;

import 'dart:math' as math;

import 'package:flutter/rendering.dart' show RenderProxyBox;
import 'package:flutter/scheduler.dart' show SchedulerBinding;
import 'package:flutter/widgets.dart';

import '../../foundation/fields.dart';
import '../../foundation/glass.dart';
import '../../foundation/theme.dart';
import '../../primitives/field_layer.dart';
import '../../primitives/glass_surface.dart';
import 'rail.dart';
import 'sidebar.dart';

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
/// (10 section 4.4). A toast host in [overlays] positions its toasts clear of
/// the chrome with [UiScaffoldGeometry.bottomInset].
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

  // TODO(fe/overlays): document UiToastHost as the intended occupant.
  /// A widget laid over the body and under the navigation.
  ///
  /// The toast layer goes here once the overlays family lands. Until then a
  /// caller may put anything page wide in it that is not part of the page.
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

    final List<Widget> floatingChrome = <Widget>[
      if (widget.actionBar != null)
        GlassSurface(
          level: GlassLevel.floating,
          radius: style.actionBarRadius,
          padding: style.actionBarPadding,
          child: widget.actionBar!,
        ),
      if (widget.actionBar != null && floats) SizedBox(height: style.gap),
      if (floats) widget.nav!,
    ];

    final double bottomInset = floatingChrome.isEmpty
        ? bottomSafe
        : bottomSafe + style.gap + _floatingHeight;

    Widget bodyArea = Stack(
      children: <Widget>[
        if (widget.body != null) Positioned.fill(child: widget.body!),
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
        if (beside) widget.nav!,
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

    return _UiScaffoldScope(
      geometry: UiScaffoldGeometry(
        bottomInset: bottomInset,
        scrolledUnder: _scrolledUnder,
      ),
      child: FieldLayer(
        preset: widget.sky,
        exclusion: widget.exclusion,
        child: Column(
          children: <Widget>[
            ?widget.topBar,
            ?widget.banner,
            Expanded(child: belowBar),
          ],
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
