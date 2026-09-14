/// The source pane (screen blueprints, 6.1 and 6.2).
///
/// The photograph is the largest thing on the screen and it does not scroll
/// away. Regions are drawn with the shared `RegionOverlay`, so the number tab
/// sits outside the box and no label is ever painted over the pixels the
/// reviewer is reading. Selecting a region moves the view to it instead of
/// swapping the image for a crop, which is what lets a reviewer keep a
/// spatial model of where on the specimen a label sits.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../models.dart';
import '../../review_context.dart';
import '../../vocabulary.dart';
import '../../source_pixels.dart';
import '../../theme/icons.dart';
import '../../theme/motion.dart';
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
  });

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
    final MotionTokens motion = context.motion;
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

  /// One view control: what it is called, what it draws, and what it does.
  ///
  /// Named once so the row of buttons and the overflow menu below a narrow
  /// width offer exactly the same set with exactly the same words.
  List<({String label, IconData icon, VoidCallback onPressed})> _viewActions(
    BuildContext context,
  ) => <({String label, IconData icon, VoidCallback onPressed})>[
    (
      label: 'Rotate the view 90 degrees',
      icon: Symbols.rotate_right,
      onPressed: rotate,
    ),
    (
      label: 'Zoom in',
      icon: Symbols.zoom_in,
      onPressed: () => zoomBy(sourceZoomStep),
    ),
    (
      label: 'Zoom out',
      icon: Symbols.zoom_out,
      onPressed: () => zoomBy(1 / sourceZoomStep),
    ),
    (
      label: 'Fit the whole photograph',
      icon: Symbols.fit_screen,
      onPressed: fit,
    ),
    if (widget.onExpand case final VoidCallback expand)
      (
        label: 'Open the photograph full screen',
        icon: Symbols.open_in_full,
        onPressed: expand,
      ),
    if (widget.fullScreen)
      (
        label: 'Close the full screen photograph',
        icon: Symbols.close_fullscreen,
        onPressed: () => Navigator.of(context).maybePop(),
      ),
  ];

  /// The view controls, as a row of buttons, or as one menu when the pane is
  /// narrower than [sourceControlsOverflowWidth].
  ///
  /// Five 48 dp targets do not fit beside each other on a phone at a large
  /// text scale without wrapping to a second row, and a second row of chrome
  /// is height taken from the photograph (finding V-1).
  Widget _controls(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints c) {
      final List<({String label, IconData icon, VoidCallback onPressed})>
      actions = _viewActions(context);
      // One row of 48 dp targets, or one menu. The threshold is the width the
      // row actually needs rather than a device width, so the controls stay
      // in reach wherever they fit and never wrap to a second row, which
      // would be chrome taken from the photograph (finding V-1).
      final double needed =
          actions.length * context.sizes.targetMin +
          (actions.length - 1) * context.space.space1;
      if (c.maxWidth >= needed) {
        return Wrap(
          spacing: context.space.space1,
          children: <Widget>[
            for (final (
                  label: String label,
                  icon: IconData icon,
                  onPressed: VoidCallback onPressed,
                )
                in actions)
              IconButton(
                tooltip: label,
                onPressed: onPressed,
                icon: Icon(icon),
              ),
          ],
        );
      }
      return Align(
        alignment: AlignmentDirectional.centerStart,
        child: MenuAnchor(
          builder: (BuildContext context, MenuController menu, Widget? _) =>
              IconButton(
                tooltip: 'Photograph view controls',
                onPressed: () => menu.isOpen ? menu.close() : menu.open(),
                icon: const Icon(Symbols.more_vert),
              ),
          menuChildren: <Widget>[
            for (final (
                  label: String label,
                  icon: IconData icon,
                  onPressed: VoidCallback onPressed,
                )
                in actions)
              MenuItemButton(
                leadingIcon: Icon(icon),
                onPressed: onPressed,
                child: Text(label),
              ),
          ],
        ),
      );
    },
  );

  Widget _image(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints c) {
      _viewport = Size(c.maxWidth, c.maxHeight);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _frameSelection();
      });
      if (_asset['preview_bytes'] == null) {
        return Center(
          child: Padding(
            padding: EdgeInsets.all(context.space.space4),
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
      // (motion and microinteractions, 6.4 item 4).
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
                  // (motion catalog, row 30; performance 6.4 item 3).
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
                            // live magnification and hand it to each box.
                            // Without that a 2dp outline is a 24dp band at
                            // 12x, straight over the label (motion,
                            // catalog row 38).
                            ListenableBuilder(
                              listenable: _transform,
                              builder: (BuildContext context, Widget? _) =>
                                  Stack(
                                    clipBehavior: Clip.none,
                                    children: <Widget>[
                                      for (final (int i, Json r)
                                          in _regions.indexed)
                                        if (_boxOf(r) case final List<num> bbox)
                                          RegionOverlay(
                                            index: i + 1,
                                            viewerScale: _viewerScale,
                                            rect: Rect.fromLTRB(
                                              bbox[0] / _width * box.maxWidth,
                                              bbox[1] / _height * box.maxHeight,
                                              bbox[2] / _width * box.maxWidth,
                                              bbox[3] / _height * box.maxHeight,
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

  static List<num>? _boxOf(Json region) {
    final List<num>? bbox = (region['bbox'] as List?)?.cast<num>();
    return bbox != null && bbox.length == 4 ? bbox : null;
  }

  /// The region list. This is the required accessible alternative to the
  /// on-image overlays (accessibility, 2.2 finding 2 and 3.1): a screen
  /// reader or switch user selects a region here without hunting for a box on
  /// a photograph. Do not remove it as apparently redundant.
  Widget _regionChips(BuildContext context) {
    final Widget chips = Wrap(
      spacing: context.space.space2,
      runSpacing: context.space.space2,
      children: _chipList(context),
    );
    // The pinned header has a fixed height, so its region list scrolls
    // sideways rather than wrapping into it.
    return widget.compact
        ? SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              spacing: context.space.space2,
              children: _chipList(context),
            ),
          )
        : chips;
  }

  List<Widget> _chipList(BuildContext context) => <Widget>[
    ChoiceChip(
      label: const Text('Whole image'),
      selected: widget.selectedRegionId == null,
      onSelected: (_) => _select(null),
    ),
    for (final (int i, Json r) in _regions.indexed)
      ChoiceChip(
        // The overlay speaks the same name, computed the same way. A `Wrap`
        // cannot animate a reorder and building one is not worth a week, so
        // the numbering change is carried by a label cross-fade
        // (motion catalog, row 40).
        label: AnimatedSwitcher(
          duration: context.motion.quick,
          switchInCurve: MotionTokens.standardCurve,
          child: Text(
            'Label ${i + 1}',
            key: ValueKey<String>('region-chip-${r['region_id']}-${i + 1}'),
          ),
        ),
        selected: widget.selectedRegionId == r['region_id'],
        onSelected: (_) => _select(r['region_id'].toString()),
      ),
  ];

  Widget _details(BuildContext context) => SourceDetails(asset: _asset);

  @override
  Widget build(BuildContext context) {
    final double? band = widget.imageHeight;
    final Widget pixels = DecoratedBox(
      decoration: BoxDecoration(
        // The letterbox behind the photograph, so label paper reads as
        // paper in both themes (blueprint 12).
        color: context.sourceMatte,
        borderRadius: BorderRadius.circular(context.shape.radiusSm),
      ),
      child: _image(context),
    );

    List<Widget> parts(Widget image) => <Widget>[
      // The caveat is three lines of body text, and on a stacked layout the
      // pinned header cannot afford them: it moves to the evidence column
      // instead, next to the region editor control it is about
      // (`SourceOrientationCaveat`, finding V-1).
      if (_unverifiedOrientation && !widget.compact)
        Padding(
          padding: EdgeInsets.only(bottom: context.space.space2),
          child: const SourceOrientationCaveat.text(),
        ),
      _controls(context),
      image,
      SizedBox(height: context.space.space2),
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
        children: parts(SizedBox(height: band, child: pixels)),
      );
    }

    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints c) {
        // At a large text scale the pane's own fixed rows, the caveat, the
        // controls, the region chips, the region editor control and the
        // source details, are together taller than the pane. Pinning them
        // around the photograph then lays the pane out past the box it was
        // given, which is finding V-1 in the side by side regimes. The pane
        // scrolls instead, and the photograph keeps the blueprint's share of
        // it (pass criteria 8.4 and 8.5).
        if (paneScrollsAtThisTextScale(MediaQuery.textScalerOf(context))) {
          final double height = c.maxHeight.isFinite
              ? c.maxHeight * sourcePaneMinViewportFraction
              : sourceImageMinHeight;
          return SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: parts(
                SizedBox(
                  height: height < sourceImageMinHeight
                      ? sourceImageMinHeight
                      : height,
                  child: pixels,
                ),
              ),
            ),
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: parts(Expanded(child: pixels)),
        );
      },
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

  // `MergeSemantics` is what puts the reason on the button's own node. A bare
  // `Semantics(hint:)` around a disabled button leaves the hint on a parent
  // node, and a screen reader focusing the control then hears the name and
  // the dimmed state but never why (accessibility, section 3.2).
  @override
  Widget build(BuildContext context) => Tooltip(
    message: blockedReason ?? 'Add, resize, reorder or merge the label regions',
    child: MergeSemantics(
      child: Semantics(
        hint: blockedReason ?? '',
        // Repeated here because a merge boundary keeps its own flags: a node
        // that does not say it is disabled is read as if it were live.
        enabled: onEditRegions != null,
        child: Align(
          alignment: AlignmentDirectional.centerStart,
          child: TextButton.icon(
            onPressed: onEditRegions,
            icon: const Icon(Symbols.crop),
            label: const Text('Correct label regions'),
          ),
        ),
      ),
    ),
  );
}

/// The checksum and the coordinate basis, one disclosure away
/// (screen blueprints, 6.2).
class SourceDetails extends StatelessWidget {
  const SourceDetails({super.key, required this.asset});

  final Json asset;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Json processing = objectOf(asset['processing_derivative']);
    final double width = (asset['width'] as num?)?.toDouble() ?? 1;
    final double height = (asset['height'] as num?)?.toDouble() ?? 1;
    return ExpansionTile(
      title: const Text('Source details'),
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.only(bottom: context.space.space2),
      children: <Widget>[
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                'Source pixels: ${width.toStringAsFixed(0)} by '
                '${height.toStringAsFixed(0)} pixels',
                style: theme.textTheme.bodySmall,
              ),
              Text(
                'Asset: ${textOf(asset['asset_id'])}',
                style: theme.textTheme.bodySmall,
              ),
              SelectableText(
                'Checksum (SHA-256): ${textOf(asset['sha256'])}',
                style: context.mono.identifier,
              ),
              SizedBox(height: context.space.space1),
              SourceBasisNotice(asset: asset),
              if (processing.isEmpty)
                Text(
                  'Coordinate basis: ${vocabularyLabel(textOf(asset['pixel_basis']))}',
                  style: theme.textTheme.bodySmall,
                ),
              Text(
                'Rotating the view does not change the original.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
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
          ),
        ),
      ],
    );
  }
}

/// Opens the source pane full screen (blueprint 6.1, pass criterion 8.4).
Future<void> showSourceFullScreen(
  BuildContext context, {
  required Specimen specimen,
  required String? selectedRegionId,
  required ValueChanged<String?> onSelectRegion,
}) {
  String? selected = selectedRegionId;
  return Navigator.of(context).push(
    MaterialPageRoute<void>(
      fullscreenDialog: true,
      builder: (BuildContext routeContext) => Scaffold(
        appBar: AppBar(title: Text(specimen.title)),
        body: SafeArea(
          child: Padding(
            padding: EdgeInsets.all(routeContext.space.space4),
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

/// The photograph's one and only entrance (motion catalog, row 30).
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
    final MotionTokens motion = context.motion;
    if (motion.reduced) return widget.child;
    return AnimatedOpacity(
      opacity: _painted ? 1 : 0,
      duration: motion.standard,
      curve: MotionTokens.enterCurve,
      child: widget.child,
    );
  }
}
