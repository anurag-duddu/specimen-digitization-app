/// The source pane (07 sections 6.1 and 6.2; 05 section 3.5; 09 section 2).
///
/// The photograph is the largest thing on the screen and it does not scroll
/// away. It sits on the neutral matte with a clear band around it, because a
/// colour cast on a faded label is a data error (09 section 2, principle 1).
/// Regions are drawn with the shared `RegionOverlay`, so the number tab sits
/// outside the box and no label is ever painted over the pixels the reviewer
/// is reading. Selecting a region moves the view to it instead of swapping
/// the image for a crop, which is what lets a reviewer keep a spatial model
/// of where on the specimen a label sits.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../region_editor.dart';
import '../../review_context.dart';
import '../../source_pixels.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import 'source_geometry.dart';
import 'workbench_layout.dart';

/// The zoom limits of the source viewer. Named here so the buttons, the
/// keyboard and the zoom to region all clamp to the same range.
const double sourceMinScale = 0.2;

/// The furthest the viewer will magnify the photograph.
const double sourceMaxScale = 12;

/// One step of the zoom in and zoom out controls.
const double sourceZoomStep = 1.3;

/// One view control: what it is called, what it draws, and what it does.
///
/// Named once so the capsule of buttons and the overflow menu below a narrow
/// width offer exactly the same set with exactly the same words.
typedef SourceViewAction = ({
  String label,
  IconSpec icon,
  VoidCallback onPressed,
});

/// The photograph, its overlays, its controls and its region list.
class WorkbenchSourcePane extends StatefulWidget {
  const WorkbenchSourcePane({
    super.key,
    required this.specimen,
    required this.selectedRegionId,
    required this.onSelectRegion,
    this.onEditRegions,
    this.editRegionsBlockedReason,
    this.onExpand,
    this.fullScreen = false,
    this.compact = false,
    this.imageHeight,
    this.controller,
  }) : asHeader = false;

  /// The pane as the record's collapsing header (13 sections 3.1 and 4.1).
  ///
  /// **This constructor builds a sliver, not a box.** It is the one region of
  /// the record screen that pins, and a pinned region is a sliver of the one
  /// scroll rather than a box above it (13 section 2.1). The photograph is the
  /// header's content and the two rows that ride its lower edge are the
  /// header's chrome: the view controls, which the band gives back as it
  /// collapses, and the region toggle strip, which is the last row and stays.
  ///
  /// One widget rather than three, because the transformation, the rotation
  /// and the framed region are one state and the three slots all read it.
  const WorkbenchSourcePane.header({
    super.key,
    required this.specimen,
    required this.selectedRegionId,
    required this.onSelectRegion,
    this.onExpand,
    this.controller,
  }) : asHeader = true,
       compact = true,
       fullScreen = false,
       imageHeight = null,
       onEditRegions = null,
       editRegionsBlockedReason = null;

  /// The record whose source is shown.
  final Specimen specimen;

  /// The region the reviewer is working on, or null for the whole image.
  final String? selectedRegionId;

  /// Called with the region id, or null for the whole image.
  final ValueChanged<String?> onSelectRegion;

  /// Opens the region editor. Null disables the control.
  final VoidCallback? onEditRegions;

  /// Why the region editor is unavailable, when it is.
  final String? editRegionsBlockedReason;

  /// Opens the pane full screen. Null hides the control, which is what the
  /// full screen copy of the pane does.
  final VoidCallback? onExpand;

  /// True for the full screen copy, which offers a close control instead.
  final bool fullScreen;

  /// True when the pane is the pinned header of a stacked layout. The region
  /// editor control and the source details then live in the evidence column
  /// beneath, because the pinned header has a fixed height to keep.
  final bool compact;

  /// The height the photograph's own pixels are given, or null to take
  /// whatever is left of the pane.
  ///
  /// The pinned header of a stacked layout passes a band rather than a pane
  /// height, so the pane's chrome is never squeezed by a box that was sized
  /// without it. That squeeze is finding V-1: a pane given less height than
  /// its own controls and region list overflows its column and the photograph
  /// is what disappears.
  final double? imageHeight;

  /// Lets the workbench drive zoom and rotation from the keyboard.
  final SourceViewController? controller;

  /// True when this pane is the record's pinned collapsing header, and so is
  /// a sliver rather than a box.
  final bool asHeader;

  @override
  State<WorkbenchSourcePane> createState() => _WorkbenchSourcePaneState();
}

/// The handle the keyboard map uses to drive the view.
class SourceViewController extends ChangeNotifier {
  _WorkbenchSourcePaneState? _state;

  /// Magnifies the photograph one step about the centre of the pane.
  void zoomIn() => _state?.zoomBy(sourceZoomStep);

  /// Reduces the magnification one step.
  void zoomOut() => _state?.zoomBy(1 / sourceZoomStep);

  /// Returns the view to the whole photograph, unrotated.
  void fit() => _state?.fit();

  /// Turns the view a quarter turn clockwise. The recorded coordinates do not
  /// change.
  void rotate() => _state?.rotate();
}

class _WorkbenchSourcePaneState extends State<WorkbenchSourcePane>
    with SingleTickerProviderStateMixin {
  final TransformationController _transform = TransformationController();
  late final AnimationController _drive = AnimationController(vsync: this);
  Animation<Matrix4>? _tween;
  Size _viewport = Size.zero;
  int _rotation = 0;
  String? _framed;

  @override
  void initState() {
    super.initState();
    widget.controller?._state = this;
    _drive.addListener(() {
      final Animation<Matrix4>? tween = _tween;
      if (tween != null) _transform.value = tween.value;
    });
  }

  @override
  void didUpdateWidget(covariant WorkbenchSourcePane oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller?._state = null;
      widget.controller?._state = this;
    }
    if (oldWidget.selectedRegionId != widget.selectedRegionId) {
      _framed = null;
    }
  }

  @override
  void dispose() {
    widget.controller?._state = null;
    _drive.dispose();
    _transform.dispose();
    super.dispose();
  }

  Json get _asset => widget.specimen.assets.isEmpty
      ? const <String, dynamic>{}
      : widget.specimen.assets.first;

  double get _width => (_asset['width'] as num?)?.toDouble() ?? 1;
  double get _height => (_asset['height'] as num?)?.toDouble() ?? 1;

  /// The preview has no verified orientation, so overlays and region editing
  /// would be drawn against coordinates the client cannot map. The pane says
  /// so rather than drawing boxes it cannot stand behind.
  bool get _unverifiedOrientation => SourceOrientationCaveat.unverified(_asset);

  List<Json> get _regions =>
      _unverifiedOrientation ? const <Json>[] : widget.specimen.regions;

  /// The magnification the viewer is currently at. Never zero: the matrix is
  /// only ever scaled and translated, and the viewer clamps the scale.
  double get _viewerScale {
    final double scale = _transform.value.getMaxScaleOnAxis();
    return scale > 0 ? scale : 1;
  }

  /// Runs the view to [target], instantly under reduced motion.
  void _driveTo(Matrix4 target) {
    final MotionTokens motion = context.ui.motion;
    final Duration duration = motion.emphasized;
    if (duration == Duration.zero) {
      _drive.stop();
      _transform.value = target;
      return;
    }
    _tween = Matrix4Tween(begin: _transform.value, end: target).animate(
      CurvedAnimation(parent: _drive, curve: MotionTokens.emphasizedCurve),
    );
    _drive
      ..duration = duration
      ..forward(from: 0);
  }

  /// Magnifies about the centre of the pane, without animation: a zoom button
  /// held down must track the presses, not queue transitions.
  void zoomBy(double factor) {
    if (_viewport.isEmpty) return;
    setState(() {
      _transform.value = scaleAbout(
        _transform.value,
        _viewport,
        factor,
        minScale: sourceMinScale,
        maxScale: sourceMaxScale,
      );
    });
  }

  void fit() {
    widget.onSelectRegion(null);
    setState(() {
      _rotation = 0;
      _framed = null;
    });
    _driveTo(Matrix4.identity());
  }

  void rotate() {
    setState(() {
      _rotation++;
      _framed = null;
    });
  }

  /// Frames the selected region once the pane has been laid out.
  void _frameSelection() {
    final String? id = widget.selectedRegionId;
    final String key = '$id:$_rotation:${_viewport.width}x${_viewport.height}';
    if (_framed == key || _viewport.isEmpty) return;
    _framed = key;
    if (id == null) {
      _driveTo(Matrix4.identity());
      return;
    }
    final Json? region = _regions
        .where((Json r) => r['region_id'] == id)
        .firstOrNull;
    final List<num>? bbox = (region?['bbox'] as List?)?.cast<num>();
    if (bbox == null || bbox.length != 4) return;
    _driveTo(
      frameRect(
        _viewport,
        regionRectIn(_viewport, bbox, _width, _height, _rotation),
        minScale: sourceMinScale,
        maxScale: sourceMaxScale,
      ),
    );
  }

  void _select(String? id) {
    if (id != null) HapticFeedback.selectionClick();
    widget.onSelectRegion(id);
  }

  /// The quarter turns applied to the photograph: the reviewer's own view
  /// rotation plus the selected region's recorded reading rotation, so the
  /// label the reviewer asked for reads upright.
  int get _quarterTurns {
    final Json? region = _regions
        .where((Json r) => r['region_id'] == widget.selectedRegionId)
        .firstOrNull;
    return _rotation + ((region?['rotation_quarter_turns'] as int?) ?? 0);
  }

  List<SourceViewAction> _viewActions(BuildContext context) =>
      <SourceViewAction>[
        (
          label: 'Rotate the view 90 degrees',
          icon: UiIcons.rotateView,
          onPressed: rotate,
        ),
        (
          label: 'Zoom in',
          icon: UiIcons.zoomIn,
          onPressed: () => zoomBy(sourceZoomStep),
        ),
        (
          label: 'Zoom out',
          icon: UiIcons.zoomOut,
          onPressed: () => zoomBy(1 / sourceZoomStep),
        ),
        (
          label: 'Fit the whole photograph',
          icon: UiIcons.fitToView,
          onPressed: fit,
        ),
        if (widget.onExpand case final VoidCallback expand)
          (
            label: 'Open the photograph full screen',
            icon: UiIcons.enterFullscreen,
            onPressed: expand,
          ),
        if (widget.fullScreen)
          (
            label: 'Close the full screen photograph',
            icon: UiIcons.exitFullscreen,
            onPressed: () => Navigator.of(context).maybePop(),
          ),
      ];

  /// The view controls as the header's own row, with no surface of its own.
  ///
  /// In the header the band behind the row is the surface, and a capsule
  /// inside it would be the second surface 13 section 2.2 refuses a compact
  /// window. The row scrolls with faded edges where the window is narrower
  /// than five hit boxes, which is the one horizontal strip 13 section 2.1
  /// allows inside the vertical scroll.
  Widget _controlRow(BuildContext context) {
    final UiThemeData ui = context.ui;
    final List<SourceViewAction> actions = _viewActions(context);
    return EdgeFadedRow(
      index: 0,
      length: actions.length,
      fadeExtent: ui.space.s6,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        spacing: ui.space.s1,
        children: <Widget>[
          for (final SourceViewAction action in actions)
            UiIconButton(
              icon: action.icon,
              semanticsLabel: action.label,
              tooltip: action.label,
              onPressed: action.onPressed,
            ),
        ],
      ),
    );
  }

  /// The view controls: one `glass.floating` capsule over the matte.
  ///
  /// The arrangement the side by side regimes keep, where the photograph has
  /// a pane of its own and the chrome floats over its lower edge. Five 48 dp
  /// targets do not fit beside each other at a large text scale, and below
  /// the width the capsule needs the same set with the same words collapses
  /// into one menu, which is the fit policy 11 section 3.3 gives a row of
  /// commands.
  Widget _controls(BuildContext context) {
    final UiThemeData ui = context.ui;
    final List<SourceViewAction> actions = _viewActions(context);
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints c) {
        final double needed =
            actions.length * ui.space.targetMin +
            (actions.length + 1) * ui.space.s1;
        return GlassSurface(
          level: GlassLevel.floating,
          capsule: true,
          padding: EdgeInsetsDirectional.all(ui.space.s1),
          child: c.maxWidth >= needed
              ? Row(
                  mainAxisSize: MainAxisSize.min,
                  spacing: ui.space.s1,
                  children: <Widget>[
                    for (final SourceViewAction action in actions)
                      UiIconButton(
                        icon: action.icon,
                        semanticsLabel: action.label,
                        onPressed: action.onPressed,
                      ),
                  ],
                )
              : UiMenuTrigger(
                  semanticsLabel: 'Photograph view controls',
                  icon: UiIcons.more,
                  items: <UiMenuItem>[
                    for (final SourceViewAction action in actions)
                      UiMenuItem(
                        label: action.label,
                        icon: action.icon,
                        onSelected: action.onPressed,
                      ),
                  ],
                ),
        );
      },
    );
  }

  Widget _image(BuildContext context) {
    final UiThemeData ui = context.ui;
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints c) {
        _viewport = Size(c.maxWidth, c.maxHeight);
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) _frameSelection();
        });
        if (_asset['preview_bytes'] == null) {
          return Center(
            child: Padding(
              padding: EdgeInsetsDirectional.all(ui.space.s4),
              child: SingleChildScrollView(
                child: Text(
                  textOf(
                    _asset['preview_error'],
                    'The photograph is not available. Refresh to renew source '
                    'access.',
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          );
        }
        // No `ClipRect` here: `InteractiveViewer` already defaults to
        // `Clip.hardEdge`, and two clips is one extra layer for no benefit
        // (04 section 6.4 item 4).
        return InteractiveViewer(
          transformationController: _transform,
          minScale: sourceMinScale,
          maxScale: sourceMaxScale,
          child: Center(
            // A quarter turn swaps the constraints, which is what keeps a
            // rotated landscape photograph inside the pane.
            child: RotatedBox(
              quarterTurns: _quarterTurns,
              child: AspectRatio(
                aspectRatio: _width / _height,
                child: Stack(
                  fit: StackFit.expand,
                  children: <Widget>[
                    // A forty megapixel photograph appearing as a hard pop
                    // reads as a rendering glitch; a 200 ms fade reads as
                    // "it loaded". No blur-up, no progressive reveal, and a
                    // repaint boundary so an overlay repaint on every hover
                    // does not re-rasterise the decoded image
                    // (04 catalog row 30; section 6.4 item 3).
                    RepaintBoundary(
                      child: _FadeInPixels(
                        assetId: textOf(_asset['asset_id']),
                        child: SourcePixels(
                          asset: _asset,
                          semanticLabel: 'Immutable original specimen image',
                        ),
                      ),
                    ),
                    if (_regions.isNotEmpty)
                      Positioned.fill(
                        child: LayoutBuilder(
                          builder: (BuildContext context, BoxConstraints box) =>
                              // The overlays sit inside the transformed
                              // subtree, so they are redrawn against the
                              // live magnification and hand it to each
                              // box. Without that a 2dp outline is a 24dp
                              // band at 12x, straight over the label
                              // (04 catalog row 38).
                              ListenableBuilder(
                                listenable: _transform,
                                builder: (BuildContext context, Widget? _) =>
                                    Stack(
                                      clipBehavior: Clip.none,
                                      children: <Widget>[
                                        for (final (int i, Json r)
                                            in _regions.indexed)
                                          if (_boxOf(r)
                                              case final List<num> bbox)
                                            RegionOverlay(
                                              index: i + 1,
                                              viewerScale: _viewerScale,
                                              rect: Rect.fromLTRB(
                                                bbox[0] / _width * box.maxWidth,
                                                bbox[1] /
                                                    _height *
                                                    box.maxHeight,
                                                bbox[2] / _width * box.maxWidth,
                                                bbox[3] /
                                                    _height *
                                                    box.maxHeight,
                                              ),
                                              selected:
                                                  widget.selectedRegionId ==
                                                  r['region_id'],
                                              onTap: () => _select(
                                                r['region_id'].toString(),
                                              ),
                                            ),
                                      ],
                                    ),
                              ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  /// The record's source header, as the one region the screen pins.
  ///
  /// `UiCollapsingHeader` between [sourceHeaderMaxFraction] and
  /// [sourceHeaderMinFraction] of the viewport (13 sections 3.1 and 4.1), the
  /// photograph on its matte as the content, the view controls and the region
  /// toggle strip as the two rows riding its lower edge.
  ///
  /// Two markers, and each says a different thing about the same band.
  ///
  /// `PrimaryRegion` is on the photograph, because the photograph is what the
  /// screen exists to show and what 13 section 2.5 measures. Its minimum is
  /// the height the header keeps once collapsed, less the one chrome row that
  /// rides the edge at that point: the header holds the fraction and the row
  /// is drawn inside it, so the pixels are the difference. It is on the
  /// content rather than on the header itself because a `PrimaryRegion` around
  /// a sliver has no box, and a rectangle is what the clause is about.
  ///
  /// `PinnedChrome` is on the header at nothing, which is what a source
  /// header spends of the chrome budget. The package's own marker, inside
  /// this one, declares the whole collapsed extent; the gates count the
  /// outermost, so this is the answer and the package's is shadowed.
  ///
  /// Nothing, rather than the row of controls on its edge, because the
  /// arithmetic decides it. 13 section 4.1 pins this header at 40 percent of
  /// a phone and 13 section 2.3 gives the whole of the chrome 28, so the two
  /// cannot both be read with the header inside the budget; 13 section 4.1's
  /// own total of 152 dp counts the top bar, the band and the decision bar
  /// and not this header. Nor is the chrome row a workable half measure: at
  /// 200 percent text on a 390 by 844 phone the frame's own top bar is 69,
  /// the one line band 52 and the action bar 80, which is 201 of the 236 the
  /// budget allows, and the row riding this header's edge is 80 on its own.
  /// A header that is the thing under review is measured by 13 section 2.5,
  /// at the minimum it pins, and is counted once.
  ///
  /// fe/polish-3: `UiCollapsingHeader` should publish no `PinnedChrome` where
  /// `primary` is true, and this marker goes with it. Integration note (slot
  /// P2, 2026-09-17): slot P1 settles it in the pattern, a header built with
  /// `primary: true` publishes `PrimaryRegion` and no `PinnedChrome`, and a
  /// header without `primary` keeps its marker. This header passes no
  /// `primary`, because the rectangle the fold clause reads has to be the
  /// photograph's box and a `PrimaryRegion` around a sliver has none, so at
  /// the merge either the call site moves to `primary: true` and P1's marker
  /// declares the minimum this one does (the pinned extent less the chrome
  /// row, floored at `sourceImageMinHeight`), and both wrappers come out; or
  /// it stays as it is and this zero extent wrapper stays with it. Against
  /// the package at 4735cfa the wrapper is what the gates read, and it stays.
  Widget _header(BuildContext context, UiThemeData ui) {
    final UiCollapsingHeaderStyle style = UiCollapsingHeaderStyle.resolve(
      ui,
      context,
    );
    final double viewport = MediaQuery.sizeOf(context).height;
    final double chromeRow =
        style.chromeRowHeight +
        style.chromePadding.resolve(Directionality.of(context)).vertical;
    final double pinned = math.max(
      sourceHeaderMinFraction * viewport,
      chromeRow,
    );
    return PinnedChrome(
      region: UiPinnedRegion.header,
      extent: 0,
      child: UiCollapsingHeader(
        maxFraction: sourceHeaderMaxFraction,
        minFraction: sourceHeaderMinFraction,
        content: PrimaryRegion(
          minExtent: math.max(pinned - chromeRow, sourceImageMinHeight),
          child: SourceMatte(child: _image(context)),
        ),
        chrome: <Widget>[_controlRow(context), _regionChips(context)],
      ),
    );
  }

  static List<num>? _boxOf(Json region) {
    final List<num>? bbox = (region['bbox'] as List?)?.cast<num>();
    return bbox != null && bbox.length == 4 ? bbox : null;
  }

  /// The region list. This is the required accessible alternative to the
  /// on-image overlays (06 sections 2.2 finding 2 and 3.1): a screen reader
  /// or switch user selects a region here without hunting for a box on a
  /// photograph. Do not remove it as apparently redundant.
  Widget _regionChips(BuildContext context) {
    final Widget toggle = UiCapsuleToggle<String?>(
      selection: UiToggleSelection.single,
      selected: <String?>{widget.selectedRegionId},
      // A single mode toggle clears itself when the option already on is
      // chosen again. The whole image is a real state rather than the absence
      // of one, so an empty set means it, and the row never reads as nothing
      // selected.
      onChanged: (Set<String?> next) =>
          _select(next.isEmpty ? null : next.first),
      options: <UiToggleOption<String?>>[
        const UiToggleOption<String?>(value: null, label: 'Whole image'),
        for (final (int i, Json r) in _regions.indexed)
          UiToggleOption<String?>(
            // The overlay speaks the same name, computed the same way.
            value: textOf(r['region_id']),
            label: 'Label ${i + 1}',
          ),
      ],
    );
    // The pinned header has a fixed height, so its region list runs off the
    // side rather than wrapping into it. An unbounded width lays the group's
    // `Wrap` out on one line, which is the same set in the same order.
    return widget.compact
        ? SingleChildScrollView(scrollDirection: Axis.horizontal, child: toggle)
        : toggle;
  }

  Widget _details(BuildContext context) => SourceDetails(asset: _asset);

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    if (widget.asHeader) return _header(context, ui);
    final double? band = widget.imageHeight;

    List<Widget> parts(Widget image) => <Widget>[
      // The caveat is three lines of body text, and on a stacked layout the
      // pinned header cannot afford them: it moves to the evidence column
      // instead, next to the region editor control it is about
      // (`SourceOrientationCaveat`, finding V-1).
      if (_unverifiedOrientation && !widget.compact)
        Padding(
          padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
          child: const SourceOrientationCaveat.text(),
        ),
      image,
      SizedBox(height: ui.space.s2),
      _regionChips(context),
      if (!widget.fullScreen && !widget.compact) ...<Widget>[
        SourceRegionEditControl(
          onEditRegions: widget.onEditRegions,
          blockedReason: widget.editRegionsBlockedReason,
        ),
        _details(context),
      ],
    ];

    if (band != null) {
      // A band, so the pane is exactly as tall as its own parts and can never
      // be handed a box shorter than its chrome (finding V-1).
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: parts(
          SourceMatte(
            controls: _controls,
            height: band,
            child: _image(context),
          ),
        ),
      );
    }

    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints c) {
        // At a large text scale the pane's own fixed rows, the caveat, the
        // region list, the region editor control and the source details, are
        // together taller than the pane. Pinning them around the photograph
        // then lays the pane out past the box it was given, which is finding
        // V-1 in the side by side regimes. The pane scrolls instead, and the
        // photograph keeps the blueprint's share of it (pass criteria 8.4
        // and 8.5).
        if (paneScrollsAtThisTextScale(MediaQuery.textScalerOf(context))) {
          final double height = c.maxHeight.isFinite
              ? c.maxHeight * sourceHeaderMinFraction
              : sourceImageMinHeight;
          return SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: parts(
                SourceMatte(
                  controls: _controls,
                  height: height < sourceImageMinHeight
                      ? sourceImageMinHeight
                      : height,
                  child: _image(context),
                ),
              ),
            ),
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: parts(
            Expanded(
              child: SourceMatte(controls: _controls, child: _image(context)),
            ),
          ),
        );
      },
    );
  }
}

/// The letterbox behind the photograph, and the band that keeps colour off it.
///
/// Two rules of 09 section 2, principle 1, in one widget. The photograph sits
/// on the neutral `matte` at `shape.sheet`, inset far enough that the corner
/// never cuts it. Around the matte is `UiFields.matteExclusion` of opaque
/// `ground`, so no light field, no glass and no tint reaches within 24 dp of
/// the evidence: a colour cast on a faded label is a data error.
///
/// The band is painted rather than clipped, which costs
/// `UiFields.matteExclusion` of layout on every side. It was written that way
/// because `UiScaffold.exclusion` was a constructor argument of a frame this
/// pane does not build. It is not any more: polish 2 added
/// `UiScaffoldExclusion.of(context)?.publish(rect)`, which the enclosing
/// scaffold answers itself, so a pane can hand the frame the matte's rect and
/// let `FieldLayer` clip its light out of it. What is left is measuring that
/// rect in the frame's coordinates and giving back the gutter, which moves
/// the photograph on every workbench window. Open, with the API in place.
class SourceMatte extends StatelessWidget {
  const SourceMatte({
    super.key,
    required this.child,
    this.controls,
    this.height,
  });

  /// The photograph and its overlays.
  final Widget child;

  /// The view controls, drawn floating over the matte, or null where the
  /// caller draws them somewhere else.
  ///
  /// Null in the record's collapsing header, where the controls ride the
  /// header's own lower edge: a capsule over the matte is a surface inside a
  /// surface, which is the depth 13 section 2.2 allows a compact window none
  /// of (13 section 0, "things inside things").
  final WidgetBuilder? controls;

  /// The height the photograph's own box is given, or null to fill the pane.
  final double? height;

  /// How far the photograph sits inside the matte.
  ///
  /// Twelve clears a 28 dp superellipse at the corner, where the shape comes
  /// closest to the box inside it, so the pixels are never cut.
  static double insetOf(UiThemeData ui) => ui.space.s3;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Widget matte = Surface(
      role: SurfaceRole.matte,
      radius: ui.shape.sheet,
      child: Stack(
        children: <Widget>[
          Positioned.fill(
            child: Padding(
              padding: EdgeInsetsDirectional.all(insetOf(ui)),
              child: child,
            ),
          ),
          // One glass capsule, floating over the matte's lower edge: the
          // chrome is the glass and the specimen is under it (09 section 1).
          // Low and centred rather than in a corner, because a label is read
          // from its first line down and a corner is where that line ends.
          //
          // Both edges are pinned, not just one: a `Stack` gives a child
          // positioned on a single edge an unbounded width, and the capsule
          // reads the width it is given to decide between its row and its
          // menu (11 section 3.3). Pinned on one edge it would never see a
          // narrow pane at all.
          if (controls case final WidgetBuilder floating)
            PositionedDirectional(
              bottom: insetOf(ui),
              start: insetOf(ui),
              end: insetOf(ui),
              child: Align(
                alignment: AlignmentDirectional.bottomCenter,
                child: floating(context),
              ),
            ),
        ],
      ),
    );
    return ColoredBox(
      color: ui.color.ground,
      child: Padding(
        padding: EdgeInsetsDirectional.all(UiFields.matteExclusion),
        child: height == null ? matte : SizedBox(height: height, child: matte),
      ),
    );
  }
}

/// Why the label regions are not drawn on this photograph.
///
/// Shown inside the pane at the widths where the pane has room for it, and in
/// the evidence column beneath on a stacked layout, where the pinned header
/// has a height to keep.
class SourceOrientationCaveat extends StatelessWidget {
  /// Shows the caveat when [asset] has no verified orientation.
  const SourceOrientationCaveat({super.key, required this.asset});

  /// The caveat itself, for a caller that has already decided to show it.
  const SourceOrientationCaveat.text({super.key})
    : asset = const <String, dynamic>{};

  /// The photograph the caveat is about.
  final Json asset;

  /// True when the preview has no verified orientation, so overlays and
  /// region editing would be drawn against coordinates the client cannot map.
  static bool unverified(Json asset) =>
      asset['media_type'] != null && asset['preview_is_derivative'] != true;

  @override
  Widget build(BuildContext context) {
    if (asset.isNotEmpty && !unverified(asset)) return const SizedBox.shrink();
    return const CaveatText(
      label:
          'This photograph has no verified orientation, so label regions are '
          'not drawn.',
      why:
          'The preview may be rotated differently from the recorded '
          'coordinates. Region correction needs a verified orientation.',
    );
  }
}

/// The region editor control, with the reason when it is unavailable.
class SourceRegionEditControl extends StatelessWidget {
  const SourceRegionEditControl({
    super.key,
    required this.onEditRegions,
    required this.blockedReason,
  });

  /// Opens the region editor. Null disables the control.
  final VoidCallback? onEditRegions;

  /// Why the region editor is unavailable, when it is.
  final String? blockedReason;

  /// What the control says, wherever it is drawn.
  static const String label = 'Correct label regions';

  /// What it does, for a reviewer who has not pressed it yet.
  static const String help = 'Add, resize, reorder or merge the label regions';

  // The control aligns itself rather than leaving it to a caller: the pane
  // draws it beside the photograph and the workbench draws it in the evidence
  // column on a stacked layout, and a stretched column would centre it in one
  // of the two.
  @override
  Widget build(BuildContext context) => Align(
    alignment: AlignmentDirectional.centerStart,
    child: UiTooltip(
      message: blockedReason ?? help,
      // `UiButton` carries the reason on the control's own semantics node
      // through `Pressable`, which is what a screen reader focusing a
      // forbidden control needs (06 section 3.2). The tooltip is the
      // pointer's copy of it: a disabled `Pressable` reports no hover.
      child: UiButton(
        label: label,
        variant: UiButtonVariant.ghost,
        leading: UiIcons.correctRegions,
        onPressed: onEditRegions,
        disabledReason: blockedReason,
      ),
    ),
  );
}

/// The checksum and the coordinate basis, one disclosure away
/// (07 section 6.2).
class SourceDetails extends StatelessWidget {
  const SourceDetails({super.key, required this.asset}) : disclosed = true;

  /// The same lines with no disclosure around them, for a surface that is
  /// already the disclosure: the sheet the composed record opens from its top
  /// bar. A disclosure inside a sheet titled with the same words is the
  /// "heading over a disclosure over a pane" of 13 section 0.
  const SourceDetails.lines({super.key, required this.asset})
    : disclosed = false;

  final Json asset;

  /// True where the lines are drawn behind their own disclosure.
  final bool disclosed;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Json processing = objectOf(asset['processing_derivative']);
    final double width = (asset['width'] as num?)?.toDouble() ?? 1;
    final double height = (asset['height'] as num?)?.toDouble() ?? 1;
    final TextStyle line = ui.type.bodySmall;
    final Widget lines = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          'Source pixels: ${width.toStringAsFixed(0)} by '
          '${height.toStringAsFixed(0)} pixels',
          style: line,
        ),
        Text('Asset: ${textOf(asset['asset_id'])}', style: line),
        // The v1 line was a `SelectableText`. A copy control keeps the
        // capability, names itself, and is a 48 dp target rather than a
        // drag a touch reviewer has to discover, which is what the shell
        // did with the build line for the same reason.
        _CopyableChecksum(value: textOf(asset['sha256'])),
        SizedBox(height: ui.space.s1),
        SourceBasisNotice(asset: asset),
        if (processing.isEmpty)
          Text(
            'Coordinate basis: '
            '${vocabularyLabel(textOf(asset['pixel_basis']))}',
            style: line,
          ),
        Text(
          'Rotating the view does not change the original.',
          style: line.copyWith(color: ui.color.inkSecondary),
        ),
        EvidenceDrawer(
          payload: <String, dynamic>{
            'asset_id': asset['asset_id'],
            'sha256': asset['sha256'],
            'width': asset['width'],
            'height': asset['height'],
            'pixel_basis': asset['pixel_basis'],
            'processing_derivative': asset['processing_derivative'],
            'view_derivative': asset['view_derivative'],
          },
        ),
      ],
    );
    return disclosed
        ? UiDisclosure(title: sourceDetailsSheetTitle, child: lines)
        : lines;
  }
}

/// The source details as a sheet, for a record that has no room to disclose
/// them in place (13 section 4.1).
///
/// The photograph's checksum and coordinate basis are a command of the record
/// rather than a row of its evidence, so on the composed record they are in
/// the top bar's overflow and this is what it opens. The same
/// [SourceDetails] the side by side regimes draw inline.
Future<void> showSourceDetailsSheet(
  BuildContext context, {
  required Json asset,
}) => UiSheet.show<void>(
  context: context,
  title: sourceDetailsSheetTitle,
  dismissLabel: 'Close',
  body: (BuildContext sheetContext) => SourceDetails.lines(asset: asset),
);

/// What the source details sheet is called.
const String sourceDetailsSheetTitle = 'Source details';

/// The checksum, with a control that puts it on the clipboard.
class _CopyableChecksum extends StatelessWidget {
  const _CopyableChecksum({required this.value});

  final String value;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String line = 'Checksum (SHA-256): $value';
    return MergeSemantics(
      child: Row(
        children: <Widget>[
          Expanded(child: Text(line, style: ui.type.mono.identifier)),
          UiIconButton(
            icon: UiIcons.copy,
            semanticsLabel: 'Copy the checksum',
            tooltip: 'Copy the checksum',
            onPressed: () =>
                unawaited(Clipboard.setData(ClipboardData(text: value))),
          ),
        ],
      ),
    );
  }
}

/// Opens the source pane full screen (07 section 6.1, pass criterion 8.4).
///
/// The route carries no sky: a window whose whole subject is one photograph
/// has no room for a light field that principle 1 would then have to be kept
/// 24 dp away from.
Future<void> showSourceFullScreen(
  BuildContext context, {
  required Specimen specimen,
  required String? selectedRegionId,
  required ValueChanged<String?> onSelectRegion,
}) {
  String? selected = selectedRegionId;
  return Navigator.of(context).push<void>(
    uiFullScreenRoute<void>(
      context,
      builder: (BuildContext routeContext) => UiScaffold(
        sky: SkyPreset.none,
        topBar: UiTopBar(
          leading: UiIconButton(
            icon: UiIcons.back,
            semanticsLabel: 'Close the full screen photograph',
            onPressed: () => Navigator.of(routeContext).maybePop(),
          ),
          title: specimen.title,
        ),
        body: SafeArea(
          child: Padding(
            padding: EdgeInsetsDirectional.all(routeContext.ui.space.s4),
            child: StatefulBuilder(
              builder: (BuildContext context, StateSetter setPaneState) =>
                  WorkbenchSourcePane(
                    specimen: specimen,
                    selectedRegionId: selected,
                    fullScreen: true,
                    onSelectRegion: (String? id) {
                      setPaneState(() => selected = id);
                      onSelectRegion(id);
                    },
                  ),
            ),
          ),
        ),
      ),
    ),
  );
}

/// The photograph's one and only entrance (04 catalog row 30).
///
/// It fades once, when the bytes for a given asset first paint. Changing
/// panel, selecting a region or rotating the view never replays it: the fade
/// is keyed by asset id, and the source pixels are the reference, so they do
/// not move unless the reviewer moves them.
class _FadeInPixels extends StatefulWidget {
  const _FadeInPixels({required this.assetId, required this.child});

  final String assetId;
  final Widget child;

  @override
  State<_FadeInPixels> createState() => _FadeInPixelsState();
}

class _FadeInPixelsState extends State<_FadeInPixels> {
  bool _painted = false;
  String? _asset;

  @override
  void initState() {
    super.initState();
    _asset = widget.assetId;
    _schedule();
  }

  @override
  void didUpdateWidget(covariant _FadeInPixels oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.assetId == _asset) return;
    _asset = widget.assetId;
    _painted = false;
    _schedule();
  }

  void _schedule() => WidgetsBinding.instance.addPostFrameCallback((_) {
    if (mounted) setState(() => _painted = true);
  });

  @override
  Widget build(BuildContext context) {
    final MotionTokens motion = context.ui.motion;
    if (motion.reduced) return widget.child;
    return AnimatedOpacity(
      opacity: _painted ? 1 : 0,
      duration: motion.standard,
      curve: MotionTokens.enterCurve,
      child: widget.child,
    );
  }
}
