/// The source pane (07 sections 6.1 and 6.2; 05 section 3.5; 09 section 2).
///
/// The photograph sits on a flat neutral matte with one eight point inset;
/// a colour cast on a faded label would distort the evidence.
/// Regions are drawn with the shared `RegionOverlay`, so the number tab sits
/// outside the box and no label is ever painted over the pixels the reviewer
/// is reading. Label selection frames the source consistently across layouts.
/// A fitted touch photograph scrolls with the page; magnification enables pan.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/gestures.dart';
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
import 'workbench_layout.dart'
    show paneScrollsAtThisTextScale, sourceImageMinHeight;

/// The zoom limits of the source viewer. Named here so the buttons, the
/// keyboard and the zoom to region all clamp to the same range.
const double sourceMinScale = 0.2;

/// The furthest the viewer will magnify the photograph.
const double sourceMaxScale = 12;

/// One step of the zoom in and zoom out controls.
const double sourceZoomStep = 1.3;

/// Natural photo height, bounded by space left for controls and reading.
///
/// The result includes the single eight point inset on each edge. Unknown
/// metadata uses a 4:3 placeholder; callers with metadata pass the source ratio.
/// A short viewport scrolls to retain 120 points for the photograph plus inset.
double reviewInlinePhotoHeight(
  double viewportExtent,
  double width, {
  double aspectRatio = 4 / 3,
  double reservedHeight = 0,
}) {
  final ratio = aspectRatio.isFinite && aspectRatio > 0 ? aspectRatio : 4 / 3;
  final insets = UiSpace.standard.s2 * 2;
  final natural = math.max(0.0, width - insets) / ratio + insets;
  if (!viewportExtent.isFinite) return natural;
  return math.min(
    natural,
    math.max(sourceImageMinHeight + insets, viewportExtent - reservedHeight),
  );
}

/// Image actions are overlays and reserve no separate toolbar row.
double inlineToolsHeight(BuildContext context, double availableWidth) => 0;

/// Reserves the initial reading context, using the controls' own text metrics.
///
/// The same budget is used for all record views and the loading placeholder,
/// keeping the photograph stable when the reviewer switches contexts. Image
/// actions float inside the viewport; only reading content consumes rows.
double inlineSourceReservedHeight(BuildContext context, double width) {
  final ui = context.ui;
  final scaler = MediaQuery.textScalerOf(context);
  final contentWidth = math.max(1.0, width - ui.space.s4 * 2);
  final tabs = UiTabStyle.resolve(ui, textScaler: scaler);
  final select = UiSelectStyle.resolve(ui, textScaler: scaler).input;
  final contextHeight = tabs.outerHeight;
  // Reserve the closed orientation explanation before metadata arrives too,
  // so a missing verified orientation cannot push the first reading away.
  final disclosure = UiDisclosureStyle.resolve(ui);
  final disclosurePadding = disclosure.padding.resolve(
    Directionality.of(context),
  );
  final disclosureTitle =
      TextPainter(
        text: TextSpan(
          text: 'Label overlays unavailable',
          style: disclosure.title,
        ),
        textDirection: Directionality.of(context),
        textScaler: scaler,
      )..layout(
        maxWidth: math.max(
          1,
          contentWidth -
              disclosurePadding.horizontal -
              disclosure.gap -
              ui.space.iconInline,
        ),
      );
  final disclosureHeight = math.max(
    UiDensity.hitBox,
    math.max(
      disclosure.minHeight,
      disclosureTitle.height + disclosurePadding.vertical,
    ),
  );
  disclosureTitle.dispose();
  return inlineToolsHeight(context, width) +
      (paneScrollsAtThisTextScale(scaler)
          ? UiTopBarStyle.resolve(ui).heightIn(ui, context)
          : 0) +
      contextHeight +
      ui.space.s4 +
      disclosureHeight +
      ui.space.s2 +
      UiType.lineHeightOf(select.label, context) +
      ui.space.s2 +
      select.minHeight +
      ui.space.s3 +
      math.max(UiDensity.hitBox, UiType.lineHeightOf(ui.type.label, context)) +
      ui.space.s2 +
      UiType.lineHeightOf(ui.type.mono.literal, context) +
      ui.space.s2;
}

/// One view control: what it is called, what it draws, and what it does.
///
/// Named once so the strip of buttons and the overflow menu below a narrow
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
    this.labelReviewActive = true,
    this.compact = false,
    this.imageHeight,
    this.controller,
    this.initialView,
  }) : asHeader = false;

  /// A stable photograph block in the record's ordinary page scroll.
  ///
  /// This constructor builds a sliver, not a box. The image and its tools
  /// leave the viewport together; selecting a label does not resize or pin it.
  const WorkbenchSourcePane.header({
    super.key,
    required this.specimen,
    required this.selectedRegionId,
    required this.onSelectRegion,
    this.onExpand,
    this.controller,
    this.labelReviewActive = true,
  }) : asHeader = true,
       compact = true,
       fullScreen = false,
       imageHeight = null,
       initialView = null,
       onEditRegions = null,
       editRegionsBlockedReason = null;

  /// The record whose source is shown.
  final Specimen specimen;

  /// The region the reviewer is working on, or null for the whole image.
  final String? selectedRegionId;

  /// Called with the region id, or null for the whole image.
  final ValueChanged<String?> onSelectRegion;

  /// The record's region editor callback. The record overflow owns this
  /// command; it is not repeated beside the photograph.
  final VoidCallback? onEditRegions;

  /// Why the region editor is unavailable, when it is.
  final String? editRegionsBlockedReason;

  /// Opens the pane full screen. Null hides the control, which is what the
  /// full screen copy of the pane does.
  final VoidCallback? onExpand;

  /// True for the full screen copy, which offers a close control instead.
  final bool fullScreen;

  /// The parent record context. Source label targets remain available from
  /// every context; choosing one asks the parent to open its label review.
  final bool labelReviewActive;

  /// True for the embedded photograph in a stacked layout.
  final bool compact;

  /// The height the photograph's own pixels are given, or null to take
  /// whatever is left of the pane.
  ///
  /// The tools float inside this image band.
  final double? imageHeight;

  /// Lets the workbench drive zoom and rotation from the keyboard.
  final SourceViewController? controller;

  /// A view restored in a differently sized photo viewport.
  final SourceViewSnapshot? initialView;

  /// True when this pane is a sliver rather than a box.
  final bool asHeader;

  @override
  State<WorkbenchSourcePane> createState() => _WorkbenchSourcePaneState();
}

/// The handle the keyboard map uses to drive the view.
class SourceViewController extends ChangeNotifier {
  _WorkbenchSourcePaneState? _state;
  SourceViewSnapshot? _savedView;
  String? _savedIdentity;

  /// Magnifies the photograph one step about the centre of the pane.
  void zoomIn() => _state?.zoomBy(sourceZoomStep);

  /// Reduces the magnification one step.
  void zoomOut() => _state?.zoomBy(1 / sourceZoomStep);

  /// Returns the view to the whole photograph, unrotated.
  void fit() => _state?.fit();

  /// Reframes an explicitly chosen label, including choosing it again.
  void frameSelection() => _state?.frameSelection();

  /// Turns the view a quarter turn clockwise. The recorded coordinates do not
  /// change.
  void rotate() => _state?.rotate();
}

/// View-only state in normalized source space, independent of viewport size.
class SourceViewSnapshot {
  const SourceViewSnapshot({
    required this.sourcePoint,
    required this.scale,
    required this.rotation,
    this.isUserAdjusted = true,
  });
  final Offset sourcePoint;
  final double scale;
  final int rotation;

  /// Explicit snapshots preserve their view by default. Internally generated
  /// automatic fits instead reframe the label in the destination viewport.
  final bool isUserAdjusted;
}

class _WorkbenchSourcePaneState extends State<WorkbenchSourcePane>
    with SingleTickerProviderStateMixin {
  final TransformationController _transform = TransformationController();
  final FocusNode _canvasFocus = FocusNode(debugLabel: 'Source photograph');
  SourceViewSnapshot? _pendingView;
  bool _isUserAdjusted = false;
  Matrix4? _interactionStartTransform;
  late final AnimationController _drive = AnimationController(vsync: this);
  Animation<Matrix4>? _tween;
  Size _viewport = Size.zero;
  int _rotation = 0;
  String? _framed;
  bool _panEnabled = false;
  bool _pointerInside = false;
  bool _usingMouse = false;
  double _touchStartScale = 1;
  Offset _touchSourcePoint = Offset.zero;
  final ValueNotifier<Offset?> _hoverPosition = ValueNotifier<Offset?>(null);
  Offset? _hoverGlobalPosition;
  bool _hoverValidationPending = false;
  final GlobalKey _canvasRegionKey = GlobalKey();
  final GlobalKey _expandControlKey = GlobalKey();
  final GlobalKey _imageToolsKey = GlobalKey();
  final GlobalKey _labelMenuKey = GlobalKey();
  final GlobalKey _resetControlKey = GlobalKey();
  final Set<String> _openMenus = <String>{};

  @override
  void initState() {
    super.initState();
    _usingMouse = WidgetsBinding.instance.mouseTracker.mouseIsConnected;
    widget.controller?._state = this;
    _pendingView =
        widget.initialView ??
        (widget.controller?._savedIdentity == _viewIdentity
            ? widget.controller?._savedView
            : null);
    _rotation = _pendingView?.rotation ?? 0;
    _isUserAdjusted = _pendingView?.isUserAdjusted ?? false;
    if (!_isUserAdjusted) _pendingView = null;
    _drive.addListener(() {
      final Animation<Matrix4>? tween = _tween;
      if (tween != null) _transform.value = tween.value;
    });
    _transform.addListener(_syncPanAvailability);
  }

  @override
  void didUpdateWidget(covariant WorkbenchSourcePane oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller?._state = null;
      widget.controller?._state = this;
    }
    if (_sourceIdentity(oldWidget.specimen) !=
        _sourceIdentity(widget.specimen)) {
      // Consecutive records often reuse region ids (for example r1). Their
      // image coordinates and view rotation are never interchangeable.
      _drive.stop();
      _pendingView = null;
      _isUserAdjusted = false;
      _rotation = 0;
      _framed = null;
      _transform.value = Matrix4.identity();
    } else if (oldWidget.selectedRegionId != widget.selectedRegionId ||
        _selectionGeometry(oldWidget.specimen, oldWidget.selectedRegionId) !=
            _selectionGeometry(widget.specimen, widget.selectedRegionId)) {
      _drive.stop();
      _pendingView = null;
      _isUserAdjusted = false;
      _framed = null;
    }
    _scheduleHoverValidation();
  }

  @override
  void dispose() {
    if (widget.controller?._state == this) widget.controller?._state = null;
    _drive.dispose();
    _transform.removeListener(_syncPanAvailability);
    _transform.dispose();
    _hoverPosition.dispose();
    _canvasFocus.dispose();
    super.dispose();
  }

  Json get _asset => widget.specimen.assets.isEmpty
      ? const <String, dynamic>{}
      : widget.specimen.assets.first;

  double get _width => (_asset['width'] as num?)?.toDouble() ?? 1;
  double get _height => (_asset['height'] as num?)?.toDouble() ?? 1;

  bool get _embeddedNarrow =>
      !widget.fullScreen &&
      (widget.asHeader || widget.compact || WindowClass.of(context).isCompact);

  String get _viewIdentity =>
      '${widget.specimen.id}:${widget.specimen.revision}:${widget.specimen.data['active_run_id']}:${_asset['asset_id']}:${widget.selectedRegionId}';

  static String _sourceIdentity(Specimen specimen) {
    final asset = specimen.assets.firstOrNull;
    return '${specimen.id}:${specimen.data['active_run_id']}:'
        '${asset?['asset_id']}:${asset?['sha256']}:'
        '${asset?['width']}x${asset?['height']}';
  }

  static String _selectionGeometry(Specimen specimen, String? id) {
    final region = specimen.regions
        .where((region) => region['region_id'] == id)
        .firstOrNull;
    return '${region?['bbox']}:${region?['rotation_quarter_turns']}';
  }

  void _saveViewSnapshot() {
    if (_viewport.isEmpty) return;
    widget.controller?._savedIdentity = _viewIdentity;
    widget.controller?._savedView = _snapshot;
  }

  void _recordUserView() {
    _isUserAdjusted = true;
    // InteractiveViewer publishes its matrix before its update callback.
    // Republish the ownership too, so a layout remount restores a manual view.
    _saveViewSnapshot();
  }

  void _applyUserTransform(Matrix4 next) {
    if (next == _transform.value) return;
    _isUserAdjusted = true;
    _transform.value = next;
  }

  /// A fitted inline image leaves dragging to the page. Deliberate zoom or
  /// label framing enters image inspection, including on touch screens.
  void _syncPanAvailability() {
    final bool canPan = _viewerScale > 1.001;
    _saveViewSnapshot();
    if (mounted) {
      setState(() => _panEnabled = canPan);
      _scheduleHoverValidation();
    }
  }

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

  bool get _canResetView {
    if (_quarterTurns % 4 != 0) return true;
    final matrix = _transform.value;
    for (var row = 0; row < 4; row++) {
      for (var column = 0; column < 4; column++) {
        final fitted = row == column ? 1.0 : 0.0;
        if ((matrix.entry(row, column) - fitted).abs() > 0.001) return true;
      }
    }
    return false;
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
    _drive.stop();
    setState(() {
      _applyUserTransform(
        scaleAbout(
          _transform.value,
          _viewport,
          factor,
          minScale: sourceMinScale,
          maxScale: sourceMaxScale,
        ),
      );
    });
  }

  void fit() {
    _drive.stop();
    _pendingView = null;
    _isUserAdjusted = false;
    widget.onSelectRegion(null);
    setState(() {
      _rotation = 0;
      _framed = null;
      _saveViewSnapshot();
    });
    _driveTo(Matrix4.identity());
  }

  void rotate() {
    _drive.stop();
    _pendingView = null;
    _isUserAdjusted = false;
    setState(() {
      _rotation++;
      _framed = null;
      _saveViewSnapshot();
    });
    _scheduleHoverValidation();
  }

  void frameSelection() {
    if (!mounted) return;
    _drive.stop();
    _pendingView = null;
    _isUserAdjusted = false;
    _framed = null;
    _saveViewSnapshot();
    _frameSelection();
  }

  /// Frames the selected region once the pane has been laid out.
  void _frameSelection() {
    final String? id = widget.selectedRegionId;
    final String key =
        '${_sourceIdentity(widget.specimen)}:$id:$_quarterTurns:'
        '${_regions.where((r) => r['region_id'] == id).firstOrNull?['bbox']}:'
        '${_viewport.width}x${_viewport.height}';
    if (_framed == key || _viewport.isEmpty) return;
    _framed = key;
    if (_pendingView case final SourceViewSnapshot view) {
      _pendingView = null;
      final Rect box = sourceBoxIn(_viewport, _width, _height, _quarterTurns);
      final Offset unit = rotateUnit(view.sourcePoint, _quarterTurns);
      final Offset point =
          box.topLeft + Offset(unit.dx * box.width, unit.dy * box.height);
      _transform.value = Matrix4.identity()
        ..translateByDouble(
          _viewport.width / 2 - point.dx * view.scale,
          _viewport.height / 2 - point.dy * view.scale,
          0,
          1,
        )
        ..scaleByDouble(view.scale, view.scale, 1, 1);
      return;
    }
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
        regionRectIn(_viewport, bbox, _width, _height, _quarterTurns),
        minScale: sourceMinScale,
        maxScale: sourceMaxScale,
      ),
    );
  }

  SourceViewSnapshot get _snapshot {
    final Rect box = sourceBoxIn(_viewport, _width, _height, _quarterTurns);
    final Offset point = _transform.toScene(_viewport.center(Offset.zero));
    return SourceViewSnapshot(
      sourcePoint: rotateUnit(
        Offset(
          (point.dx - box.left) / box.width,
          (point.dy - box.top) / box.height,
        ),
        -_quarterTurns,
      ),
      scale: _viewerScale,
      rotation: _rotation,
      isUserAdjusted: _isUserAdjusted,
    );
  }

  void _restore(SourceViewSnapshot view) {
    _drive.stop();
    setState(() {
      _rotation = view.rotation;
      _isUserAdjusted = view.isUserAdjusted;
      _pendingView = view.isUserAdjusted ? view : null;
      _framed = null;
    });
  }

  KeyEventResult _canvasKey(FocusNode node, KeyEvent event) {
    if (!_canvasFocus.hasFocus ||
        (event is! KeyDownEvent && event is! KeyRepeatEvent) ||
        HardwareKeyboard.instance.isControlPressed ||
        HardwareKeyboard.instance.isMetaPressed ||
        HardwareKeyboard.instance.isAltPressed) {
      return KeyEventResult.ignored;
    }
    final key = event.logicalKey;
    final double step = context.ui.space.targetMin;
    final Offset? pan = switch (key) {
      LogicalKeyboardKey.arrowLeft => Offset(step, 0),
      LogicalKeyboardKey.arrowRight => Offset(-step, 0),
      LogicalKeyboardKey.arrowUp => Offset(0, step),
      LogicalKeyboardKey.arrowDown => Offset(0, -step),
      _ => null,
    };
    if (pan != null) {
      _drive.stop();
      final current = _transform.value;
      final scale = _viewerScale;
      if (scale > 1) {
        final next = current.clone();
        next.setEntry(
          0,
          3,
          (current.entry(0, 3) + pan.dx).clamp(
            _viewport.width * (1 - scale) - _panBuffer,
            _panBuffer,
          ),
        );
        next.setEntry(
          1,
          3,
          (current.entry(1, 3) + pan.dy).clamp(
            _viewport.height * (1 - scale) - _panBuffer,
            _panBuffer,
          ),
        );
        _applyUserTransform(next);
      }
    } else if (key == LogicalKeyboardKey.equal ||
        key == LogicalKeyboardKey.add) {
      zoomBy(sourceZoomStep);
    } else if (key == LogicalKeyboardKey.minus ||
        key == LogicalKeyboardKey.numpadSubtract) {
      zoomBy(1 / sourceZoomStep);
    } else if (key == LogicalKeyboardKey.digit0) {
      fit();
    } else if (key == LogicalKeyboardKey.keyR &&
        HardwareKeyboard.instance.isShiftPressed) {
      rotate();
    } else if (int.tryParse(key.keyLabel) case final int digit
        when digit > 0 && digit <= _regions.length) {
      _select(textOf(_regions[digit - 1]['region_id']));
    } else {
      return KeyEventResult.ignored;
    }
    return KeyEventResult.handled;
  }

  void _select(String? id) {
    if (id != null) HapticFeedback.selectionClick();
    widget.onSelectRegion(id);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) frameSelection();
    });
    // A semantics action does not dispatch pointer-down. Selecting through
    // either accessible entry must still give the photograph its keyboard.
    _canvasFocus.requestFocus();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _canvasFocus.requestFocus();
    });
  }

  void _updateHover(PointerHoverEvent event) {
    _hoverGlobalPosition = event.position;
    _revalidateHover();
  }

  // Image geometry can change while the mouse is stationary. Keep the lens
  // on its screen pixel when it still covers the image, and clear it over
  // matte or controls. Wait for layout so a moved pane uses its new origin.
  void _scheduleHoverValidation() {
    if (_hoverGlobalPosition == null || _hoverValidationPending) return;
    _hoverValidationPending = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _hoverValidationPending = false;
      if (mounted) _revalidateHover();
    });
  }

  void _revalidateHover() {
    final position = _hoverGlobalPosition;
    final canvas = _canvasRegionKey.currentContext?.findRenderObject();
    if (position == null ||
        !_pointerInside ||
        canvas is! RenderBox ||
        !canvas.hasSize) {
      _hoverPosition.value = null;
      return;
    }
    final localPosition = canvas.globalToLocal(position);
    if (!(Offset.zero & canvas.size).contains(localPosition)) {
      _hoverPosition.value = null;
      return;
    }
    // The controls float over real image pixels. Their measured hit bounds,
    // rather than a guessed toolbar height, exclude those pixels from inspect.
    final overControl =
        [
          _expandControlKey,
          _imageToolsKey,
          _labelMenuKey,
          _resetControlKey,
        ].any((key) {
          final box = key.currentContext?.findRenderObject();
          return box is RenderBox &&
              box.hasSize &&
              (Offset.zero & box.size).contains(box.globalToLocal(position));
        });
    if (_openMenus.isNotEmpty || overControl) {
      _hoverPosition.value = null;
      return;
    }
    // A lens cannot fit inside a very small split pane. The view controls
    // still provide the same zoom without covering the entire photograph.
    final double lensSize = context.ui.space.targetMin * 2;
    if (_viewport.width < lensSize || _viewport.height < lensSize) {
      _hoverPosition.value = null;
      return;
    }
    final Rect source = MatrixUtils.transformRect(
      _transform.value,
      sourceBoxIn(_viewport, _width, _height, _quarterTurns),
    );
    final Offset? next = source.contains(localPosition) ? localPosition : null;
    _hoverPosition.value = next;
  }

  void _menuOpenChanged(String menu, bool open) {
    if (!mounted) return;
    _hoverPosition.value = null;
    setState(() {
      if (open) {
        _openMenus.add(menu);
      } else {
        _openMenus.remove(menu);
      }
    });
  }

  Widget _inspectLens(BuildContext context, Offset pointer) {
    final UiThemeData ui = context.ui;
    final double lensSize = ui.space.targetMin * 2;
    // The lens is the inspection cursor. Keep its centre on the hovered
    // pixel even at an image edge; the viewport clips the overhanging circle.
    return Positioned(
      left: pointer.dx - lensSize / 2,
      top: pointer.dy - lensSize / 2,
      child: IgnorePointer(
        child: RawMagnifier(
          size: Size.square(lensSize),
          magnificationScale: 2,
          focalPointOffset: Offset.zero,
          decoration: MagnifierDecoration(
            shape: CircleBorder(
              side: BorderSide(
                color: ui.color.ink,
                width: ui.shape.stroke.hairline,
              ),
            ),
          ),
        ),
      ),
    );
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

  List<SourceViewAction> _zoomActions() => <SourceViewAction>[
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
      label: 'Rotate image clockwise',
      icon: UiIcons.rotateView,
      onPressed: rotate,
    ),
  ];

  bool get _showImageTools =>
      !_usingMouse ||
      _pointerInside ||
      _openMenus.isNotEmpty ||
      _canvasFocus.hasFocus ||
      MediaQuery.accessibleNavigationOf(context);

  // Screen-space breathing room lets every image corner move clear of the
  // overlay controls. InteractiveViewer takes scene units; keyboard panning
  // takes screen units, so both use this same buffer through the current scale.
  double get _panBuffer => math.max(
    context.ui.space.targetMin * 2,
    UiButtonStyle.heightOf(
          context.ui,
          UiSize.md,
          textScaler: MediaQuery.textScalerOf(context),
        ) +
        context.ui.space.s2 * 2,
  );

  Widget _imageTools(BuildContext context) {
    final ui = context.ui;
    Widget backed(Widget child, {Key? key}) => DecoratedBox(
      key: key,
      decoration: BoxDecoration(
        color: ui.color.paper,
        borderRadius: BorderRadius.circular(ui.shape.inner),
      ),
      child: child,
    );
    return Opacity(
      key: const ValueKey('source-image-actions'),
      opacity: _showImageTools ? 1 : 0,
      alwaysIncludeSemantics: true,
      child: IgnorePointer(
        ignoring: !_showImageTools,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            if (widget.fullScreen && _regions.isNotEmpty) ...[
              backed(_regionChips(context), key: _labelMenuKey),
              const Spacer(),
            ],
            backed(
              UiIconButton(
                icon: widget.fullScreen
                    ? UiIcons.exitFullscreen
                    : UiIcons.enterFullscreen,
                semanticsLabel: widget.fullScreen
                    ? 'Close full screen'
                    : 'Open photograph',
                onPressed: widget.fullScreen
                    ? () => Navigator.of(context).maybePop()
                    : widget.onExpand ??
                          () => showSourceFullScreen(
                            context,
                            specimen: widget.specimen,
                            selectedRegionId: widget.selectedRegionId,
                            onSelectRegion: widget.onSelectRegion,
                            viewController: widget.controller,
                            labelReviewActive: widget.labelReviewActive,
                          ),
              ),
              key: _expandControlKey,
            ),
            SizedBox(width: ui.space.s2),
            backed(
              UiMenuTrigger(
                icon: UiIcons.more,
                semanticsLabel: 'Image tools',
                menuLabel: 'Image tools',
                onOpenChanged: (open) => _menuOpenChanged('tools', open),
                items: [
                  for (final action in _zoomActions())
                    UiMenuItem(
                      label: action.label,
                      icon: action.icon,
                      onSelected: action.onPressed,
                    ),
                ],
              ),
              key: _imageToolsKey,
            ),
          ],
        ),
      ),
    );
  }

  Widget _viewer(Widget child) {
    if (_embeddedNarrow && !_panEnabled) {
      // A disabled InteractiveViewer still competes for scroll gestures.
      // Only insert its recognizer when deliberate magnification needs pan.
      return ClipRect(
        child: ListenableBuilder(
          listenable: _transform,
          child: child,
          builder: (context, child) => Transform(
            key: const ValueKey<String>('source-inline-transform'),
            transform: _transform.value,
            child: child,
          ),
        ),
      );
    }
    final viewer = InteractiveViewer(
      transformationController: _transform,
      minScale: sourceMinScale,
      maxScale: sourceMaxScale,
      panEnabled: _panEnabled,
      boundaryMargin: EdgeInsets.all(_panBuffer / _viewerScale),
      onInteractionStart: (_) {
        _drive.stop();
        _interactionStartTransform = _transform.value.clone();
      },
      onInteractionUpdate: (_) {
        if (_interactionStartTransform != null &&
            _transform.value != _interactionStartTransform) {
          _recordUserView();
        }
      },
      child: child,
    );
    // Full screen has no competing page drag. Keep its InteractiveViewer in
    // the same element position as a pinch crosses the fitted scale; adding a
    // wrapper mid-gesture would dispose the recognizer holding the pointers.
    if (!_embeddedNarrow || !_panEnabled) return viewer;
    return RawGestureDetector(
      behavior: HitTestBehavior.opaque,
      gestures: {
        _SourceInspectionRecognizer:
            GestureRecognizerFactoryWithHandlers<_SourceInspectionRecognizer>(
              _SourceInspectionRecognizer.new,
              (recognizer) {
                recognizer.onStart = (details) {
                  _drive.stop();
                  _touchStartScale = _viewerScale;
                  _touchSourcePoint = _transform.toScene(
                    details.localFocalPoint,
                  );
                };
                recognizer.onUpdate = (details) {
                  final scale = (_touchStartScale * details.scale).clamp(
                    1.0,
                    sourceMaxScale,
                  );
                  final translation =
                      details.localFocalPoint - _touchSourcePoint * scale;
                  _applyUserTransform(
                    Matrix4.identity()
                      ..translateByDouble(
                        translation.dx.clamp(
                          _viewport.width * (1 - scale) - _panBuffer,
                          _panBuffer,
                        ),
                        translation.dy.clamp(
                          _viewport.height * (1 - scale) - _panBuffer,
                          _panBuffer,
                        ),
                        0,
                        1,
                      )
                      ..scaleByDouble(scale, scale, 1, 1),
                  );
                };
              },
            ),
      },
      child: viewer,
    );
  }

  Widget _image(BuildContext context) {
    final UiThemeData ui = context.ui;
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints c) {
        final Size nextViewport = Size(c.maxWidth, c.maxHeight);
        if (_framed != null &&
            !_viewport.isEmpty &&
            nextViewport != _viewport) {
          if (_drive.isAnimating || !_isUserAdjusted) {
            // Selection and a viewport resize can animate at the same time.
            // A transform targeted at the old viewport must not
            // overwrite framing in the new one on the next animation tick.
            // A settled automatic fit also belongs to its old viewport; only
            // deliberate inspection preserves a source-space snapshot.
            _drive.stop();
            _pendingView = null;
          } else {
            _pendingView = _snapshot;
          }
        }
        _viewport = nextViewport;
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            _frameSelection();
            _revalidateHover();
          }
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
        // The outer stack clips only the temporary inspect lens at the pane
        // edge. InteractiveViewer clips its transformed photograph itself.
        return Focus(
          focusNode: _canvasFocus,
          onKeyEvent: _canvasKey,
          onFocusChange: (_) => setState(() {}),
          child: FocusRing(
            visible: _canvasFocus.hasFocus,
            radius: ui.shape.inner,
            child: Semantics(
              key: const ValueKey<String>('source-photo-viewport'),
              label: 'Photograph canvas',
              hint:
                  'Arrow keys pan. Plus and minus zoom. Zero resets. Number keys select a label.',
              child: Listener(
                onPointerDown: (event) {
                  _hoverGlobalPosition = null;
                  _hoverPosition.value = null;
                  if (event.kind != PointerDeviceKind.mouse && _usingMouse) {
                    setState(() => _usingMouse = false);
                  }
                  _canvasFocus.requestFocus();
                },
                child: MouseRegion(
                  key: _canvasRegionKey,
                  onEnter: (event) {
                    if (event.kind == PointerDeviceKind.mouse) {
                      setState(() {
                        _usingMouse = true;
                        _pointerInside = true;
                      });
                    }
                  },
                  onHover: _updateHover,
                  onExit: (_) {
                    _hoverGlobalPosition = null;
                    _hoverPosition.value = null;
                    setState(() => _pointerInside = false);
                  },
                  child: ValueListenableBuilder<Offset?>(
                    valueListenable: _hoverPosition,
                    child: _viewer(
                      Center(
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
                                      semanticLabel:
                                          'Immutable original specimen image',
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
                                            builder:
                                                (
                                                  BuildContext context,
                                                  Widget? _,
                                                ) => Stack(
                                                  clipBehavior: Clip.none,
                                                  children: <Widget>[
                                                    for (final (int i, Json r)
                                                        in _regions.indexed)
                                                      if (_boxOf(r)
                                                          case final List<num>
                                                              bbox)
                                                        RegionOverlay(
                                                          index: i + 1,
                                                          viewerScale:
                                                              _viewerScale,
                                                          rect: Rect.fromLTRB(
                                                            bbox[0] /
                                                                _width *
                                                                box.maxWidth,
                                                            bbox[1] /
                                                                _height *
                                                                box.maxHeight,
                                                            bbox[2] /
                                                                _width *
                                                                box.maxWidth,
                                                            bbox[3] /
                                                                _height *
                                                                box.maxHeight,
                                                          ),
                                                          selected:
                                                              widget
                                                                  .selectedRegionId ==
                                                              r['region_id'],
                                                          onTap: () => _select(
                                                            r['region_id']
                                                                .toString(),
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
                    ),
                    builder:
                        (
                          BuildContext context,
                          Offset? pointer,
                          Widget? viewer,
                        ) => Stack(
                          clipBehavior: Clip.hardEdge,
                          children: <Widget>[
                            Positioned.fill(child: viewer!),
                            if (pointer != null) _inspectLens(context, pointer),
                            // This annotation precedes image and label hit
                            // targets without claiming their gestures. The
                            // controls above it retain their normal cursors.
                            Positioned.fill(
                              child: MouseRegion(
                                key: const ValueKey<String>(
                                  'source-inspection-cursor',
                                ),
                                opaque: false,
                                hitTestBehavior: HitTestBehavior.translucent,
                                cursor: pointer == null
                                    ? MouseCursor.defer
                                    : SystemMouseCursors.none,
                              ),
                            ),
                            Positioned(
                              left: ui.space.s2,
                              right: ui.space.s2,
                              top: ui.space.s2,
                              child: _imageTools(context),
                            ),
                            if (_canResetView)
                              Positioned(
                                right: ui.space.s2,
                                bottom: ui.space.s2,
                                child: ConstrainedBox(
                                  key: _resetControlKey,
                                  constraints: BoxConstraints(
                                    maxWidth: math.max(
                                      0,
                                      c.maxWidth - ui.space.s2 * 2,
                                    ),
                                  ),
                                  child: UiButton(
                                    label: 'Reset view',
                                    leading: UiIcons.fitToView,
                                    variant: UiButtonVariant.secondary,
                                    onPressed: () {
                                      fit();
                                      _canvasFocus.requestFocus();
                                    },
                                  ),
                                ),
                              ),
                          ],
                        ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  /// A stable image band with floating tools in the page scroll.
  Widget _header(BuildContext context) => SliverLayoutBuilder(
    builder: (context, constraints) {
      final double photoHeight = reviewInlinePhotoHeight(
        constraints.viewportMainAxisExtent,
        constraints.crossAxisExtent,
        aspectRatio: _width / _height,
        reservedHeight: inlineSourceReservedHeight(
          context,
          constraints.crossAxisExtent,
        ),
      );
      return SliverToBoxAdapter(
        child: Column(
          key: const ValueKey<String>('review-source-inline-block'),
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            SourceMatte(height: photoHeight, child: _image(context)),
          ],
        ),
      );
    },
  );

  static List<num>? _boxOf(Json region) {
    final List<num>? bbox = (region['bbox'] as List?)?.cast<num>();
    return bbox != null && bbox.length == 4 ? bbox : null;
  }

  /// The region list. This is the required accessible alternative to the
  /// on-image overlays (06 sections 2.2 finding 2 and 3.1): a screen reader
  /// or switch user selects a region here without hunting for a box on a
  /// photograph. Do not remove it as apparently redundant.
  Widget _regionChips(BuildContext context) {
    return UiMenuTrigger(
      icon: UiIcons.script,
      semanticsLabel: 'Choose a label',
      menuLabel: 'Choose a label',
      onOpenChanged: (open) => _menuOpenChanged('labels', open),
      items: <UiMenuItem>[
        for (final (int i, Json region) in widget.specimen.regions.indexed)
          UiMenuItem(
            label: 'Label ${i + 1}',
            onSelected: () => _select(textOf(region['region_id'])),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    if (widget.asHeader) return _header(context);
    final double? band = widget.imageHeight;

    List<Widget> parts(Widget image) => <Widget>[
      // On a stacked layout the caveat joins the ordinary evidence scroll
      // instead of enlarging the photograph band, next to the controls it
      // explains
      // (`SourceOrientationCaveat`, finding V-1).
      if (_unverifiedOrientation && !widget.compact)
        Padding(
          padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
          child: const SourceOrientationCaveat.text(),
        ),
      image,
    ];

    if (band != null) {
      // A band, so the pane is exactly as tall as its own parts and can never
      // be handed a box shorter than its chrome (finding V-1).
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: parts(SourceMatte(height: band, child: _image(context))),
      );
    }

    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints c) {
        final caveatHeight = _unverifiedOrientation && !widget.compact
            ? SourceOrientationCaveat.maxHeightFor(context, c.maxWidth) +
                  ui.space.s2
            : 0.0;
        final reserved = caveatHeight;
        final photoHeight = c.maxHeight.isFinite
            ? math.max(
                sourceImageMinHeight + SourceMatte.insetOf(ui) * 2,
                c.maxHeight - reserved,
              )
            : reviewInlinePhotoHeight(
                c.maxHeight,
                c.maxWidth,
                aspectRatio: _width / _height,
                reservedHeight: reserved,
              );
        final contents = Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: parts(
            SourceMatte(height: photoHeight, child: _image(context)),
          ),
        );
        if (c.maxHeight.isFinite && photoHeight + reserved > c.maxHeight) {
          return SingleChildScrollView(child: contents);
        }
        return contents;
      },
    );
  }
}

/// A flat neutral background with one eight point inset around the source.
class SourceMatte extends StatelessWidget {
  const SourceMatte({super.key, required this.child, this.height});

  final Widget child;

  /// Total photo surface height, including its single inset.
  final double? height;

  static double insetOf(UiThemeData ui) => ui.space.s2;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: height,
    child: ColoredBox(
      color: context.ui.color.matte,
      child: Padding(
        padding: EdgeInsets.all(insetOf(context.ui)),
        child: child,
      ),
    ),
  );
}

/// Why the label regions are not drawn on this photograph.
///
/// Shown inside the pane at the widths where the pane has room for it, and in
/// the evidence column beneath on a stacked layout, where the photograph band
/// has a height to keep.
class SourceOrientationCaveat extends StatelessWidget {
  /// Shows the caveat when [asset] has no verified orientation.
  const SourceOrientationCaveat({super.key, required this.asset});

  /// The caveat itself, for a caller that has already decided to show it.
  const SourceOrientationCaveat.text({super.key})
    : asset = const <String, dynamic>{};

  /// The photograph the caveat is about.
  final Json asset;

  static const String _label =
      'This photograph has no verified orientation, so label regions are '
      'not drawn.';
  static const String _why =
      'The preview may be rotated differently from the recorded '
      'coordinates. Region correction needs a verified orientation.';

  /// The space the notice needs with its explanation open, including scaled
  /// text and the disclosure button. Reserving both states keeps opening
  /// evidence from taking height away from the photograph.
  static double maxHeightFor(BuildContext context, double width) {
    final UiThemeData ui = context.ui;
    final TextScaler scaler = MediaQuery.textScalerOf(context);
    double textHeight(String text, TextStyle style) {
      final TextPainter painter = TextPainter(
        text: TextSpan(text: text, style: style),
        textDirection: Directionality.of(context),
        textScaler: scaler,
      )..layout(maxWidth: width);
      final double height = painter.height;
      painter.dispose();
      return height;
    }

    return textHeight(_label, ui.type.body) +
        UiButtonStyle.heightOf(
          ui,
          UiSize.md,
          textScaler: scaler,
        ).clamp(ui.space.targetMin, double.infinity) +
        textHeight(_why, ui.type.bodySmall) +
        ui.space.s2;
  }

  /// True when the preview has no verified orientation, so overlays and
  /// region editing would be drawn against coordinates the client cannot map.
  static bool unverified(Json asset) =>
      asset['media_type'] != null && asset['preview_is_derivative'] != true;

  @override
  Widget build(BuildContext context) {
    if (asset.isNotEmpty && !unverified(asset)) return const SizedBox.shrink();
    return const CaveatText(label: _label, why: _why);
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
/// rather than a row of its evidence, so they are in the top bar's overflow
/// at every width and this is what it opens.
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
  SourceViewController? viewController,
  bool labelReviewActive = true,
}) async {
  String? selected = selectedRegionId;
  final SourceViewController fullScreenController = SourceViewController();
  final SourceViewSnapshot? initial = viewController?._state?._snapshot;
  SourceViewSnapshot? finalView;
  await Navigator.of(context, rootNavigator: true).push<void>(
    uiFullScreenRoute<void>(
      context,
      builder: (BuildContext routeContext) => PopScope<void>(
        onPopInvokedWithResult: (didPop, _) {
          if (didPop) finalView = fullScreenController._state?._snapshot;
        },
        child: UiScaffold(
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
                      labelReviewActive: labelReviewActive,
                      controller: fullScreenController,
                      initialView: initial,
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
    ),
  );
  if (finalView case final SourceViewSnapshot view) {
    viewController?._state?._restore(view);
  }
  fullScreenController.dispose();
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

/// Magnified inline inspection claims a deliberate drag before an ancestor
/// page scroll, while stationary taps still reach the label targets.
class _SourceInspectionRecognizer extends ScaleGestureRecognizer {
  final Map<int, Offset> _starts = {};

  @override
  void addAllowedPointer(PointerDownEvent event) {
    _starts[event.pointer] = event.position;
    super.addAllowedPointer(event);
  }

  @override
  void handleEvent(PointerEvent event) {
    final start = _starts[event.pointer];
    if (event is PointerMoveEvent && start != null) {
      if ((event.position - start).distance > kTouchSlop / 2) {
        resolve(GestureDisposition.accepted);
      }
    }
    super.handleEvent(event);
    if (event is PointerUpEvent || event is PointerCancelEvent) {
      _starts.remove(event.pointer);
    }
  }
}
