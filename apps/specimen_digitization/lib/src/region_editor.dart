/// The region editor (13 section 4.3; 07 section 7; 05 section 3.6).
///
/// Full screen on compact and medium, a 640 dp dialog otherwise. On the route
/// it is one scroll: the photograph is a `UiCollapsingHeader` floored at 40
/// percent of the viewport with the region strip riding its lower edge, and
/// the coordinate form and the provenance scroll beneath it. Back, the title,
/// save and the order controls are the top bar's, which the editor publishes
/// into the frame itself (13 sections 3.4 and 4.3). In the dialog, which has
/// no bar of its own, they stay in the editor's own sticky footer and the
/// dialog lends the editor its one scroll rather than wrapping a second one
/// around it.
///
/// The preview fills the width and every region can be dragged by its body or
/// resized by one of four corner handles. The numeric fields stay as the precise
/// alternative and as the pointer free path WCAG 2.2 SC 2.5.7 requires, so
/// nothing here is drag only. Delete and merge are undoable inside the
/// editor, and saving with no regions is refused with a reason.
///
/// All edits stay in original pixel coordinates. The API validates and
/// versions them.
///
/// Nothing here raises a message: the editor never had a `SnackBar` to
/// convert, and the undo the blueprint asks for is the control that names the
/// last change and takes it back, which is on screen for as long as there is
/// something to undo rather than for as long as a toast lasts.
library;

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'models.dart';
import 'screens/workbench/workbench_layout.dart';
import 'source_pixels.dart';
import 'theme/motion.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

/// What the editor is called, wherever it is opened.
const String regionEditorTitle = 'Correct label regions';

/// What the control that saves a new region version is called.
const String saveRegionsLabel = 'Save region version';

/// What the control that leaves the editor is called.
const String closeEditorLabel = 'Close the region editor';

/// The four controls that change the region list, named once.
const String deleteRegionLabel = 'Delete region';

/// The step earlier in the region order.
const String moveEarlierLabel = 'Move earlier';

/// The step later in it.
const String moveLaterLabel = 'Move later';

/// The one that joins two regions into one.
const String mergeRegionsLabel = 'Merge with next';

/// What the control that adds a region is called.
const String addRegionLabel = 'Add label region';

/// What the control that turns a label reading is called.
const String rotateReadingLabel = 'Rotate label reading 90 degrees';

/// Opens the editor in the container the window earns.
///
/// Expanded and above take the dialog half of `UiDialog.showAdaptive`, which
/// is the only half this editor uses: 07 section 7 gives compact and medium a
/// full window route instead, because direct manipulation of a bounding box
/// needs the whole screen. The dialog is published as [RegionEditor] so the
/// surface stays addressable without a route, which is what the golden, dark
/// mode and guideline fixtures render.
Future<Json?> showRegionEditor(
  BuildContext context, {
  required List<Json> regions,
  required Json asset,
}) {
  if (WindowClass.of(context).isAtLeast(WindowClass.expanded)) {
    return showUiDialog<Json>(
      context: context,
      semanticsLabel: regionEditorTitle,
      builder: (_) => RegionEditor(regions: regions, asset: asset),
    );
  }
  return Navigator.of(context).push<Json>(
    uiFullScreenRoute<Json>(
      context,
      builder: (BuildContext routeContext) => UiScaffold(
        // No sky behind an editor whose whole subject is one photograph
        // (09 section 2, principle 1).
        sky: SkyPreset.none,
        topBar: UiTopBar(
          leading: UiIconButton(
            icon: UiIcons.back,
            semanticsLabel: 'Close the region editor',
            onPressed: () => Navigator.of(routeContext).maybePop(),
          ),
          title: regionEditorTitle,
        ),
        body: RegionEditorBody(regions: regions, asset: asset),
      ),
    ),
  );
}

/// The editor as a constrained dialog.
class RegionEditor extends StatelessWidget {
  const RegionEditor({super.key, required this.regions, required this.asset});

  final List<Json> regions;
  final Json asset;

  @override
  Widget build(BuildContext context) => ConstrainedBox(
    constraints: const BoxConstraints(maxWidth: DialogWidths.wide),
    // The editor carries its save in its own sticky footer beside the reason
    // it needs (07 section 7), so the dialog's action slots stay empty and
    // the footer is the one place a save can be pressed.
    child: UiDialog(
      title: regionEditorTitle,
      // The editor scrolls its own form above its own footer, so the dialog
      // lends it the height and wraps no second scroll around it: two
      // scrollables on one surface is the first line of 13 section 0 and the
      // clause 13 section 2.1 states against it.
      scrollBody: false,
      child: RegionEditorBody(regions: regions, asset: asset, inDialog: true),
    ),
  );
}

/// The editor itself, identical in the dialog and on the full screen route.
class RegionEditorBody extends StatefulWidget {
  const RegionEditorBody({
    super.key,
    required this.regions,
    required this.asset,
    this.inDialog = false,
  });

  final List<Json> regions;
  final Json asset;

  /// True where the editor is the body of a `UiDialog`.
  ///
  /// A dialog has no bar across the top, so back, save and the order controls
  /// stay in the editor's own footer there, and the photograph is a band of
  /// the form rather than a header that pins. On a route the editor publishes
  /// all four into the frame's bar and the photograph is the header
  /// (13 section 4.3).
  final bool inDialog;

  /// The shortest the photograph's band may be on a compact window
  /// (finding V-7). Below this a corner handle has no room to be dragged and
  /// the editor is a coordinate form with a thumbnail.
  static const double compactPreviewMinHeight = 240;

  /// What the coordinate disclosure is called.
  static const String coordinatesTitle = 'Exact coordinates and region order';

  @override
  State<RegionEditorBody> createState() => _RegionEditorBodyState();
}

/// One undoable step: the regions as they were, and what to call the undo.
typedef _Undo = ({List<Json> regions, int selected, String label});

class _RegionEditorBodyState extends State<RegionEditorBody> {
  late final List<Json> _regions = widget.regions
      .map(
        (Json r) => <String, dynamic>{
          ...r,
          'bbox': List<num>.from(r['bbox'] ?? <num>[0, 0, 1, 1]),
          'rotation_quarter_turns': r['rotation_quarter_turns'] ?? 0,
        },
      )
      .toList();
  int _selected = 0;
  int _coordinateVersion = 0;
  String? _error;
  final Set<String> _invalidCoordinates = <String>{};
  bool _coordinateSubmitAttempted = false;

  /// What this editor has asked of the frame around it (13 section 3.4).
  UiScaffoldSlots? _slots;

  /// The one scroll of the routed form, so a save that cannot proceed can put
  /// the reason it needs back on the screen.
  final ScrollController _scroll = ScrollController();

  /// The reason field, for the same reason.
  final GlobalKey _reasonAnchor = GlobalKey();

  final TextEditingController _reason = TextEditingController();

  /// Every local change, newest last (pass criterion 3.5).
  ///
  /// One step was not enough: the criterion asks for local edits inside the
  /// dialog to be reversible, and an editor that can take back the last
  /// change and not the one before it is an editor a reviewer stops trusting
  /// halfway through a merge (finding V-11's neighbour, criterion 3.5).
  final List<_Undo> _undo = <_Undo>[];

  /// How far back the editor can go. Deep enough to cover a whole pass over
  /// one photograph, shallow enough that the snapshots stay small.
  static const int _undoDepth = 20;

  String? get _visibleError => _invalidCoordinates.isEmpty
      ? _error
      : _coordinateSubmitAttempted
      ? 'Enter whole pixel numbers before you save.'
      : 'Coordinates must be whole pixel numbers.';

  double get _width => (widget.asset['width'] as num?)?.toDouble() ?? 1;
  double get _height => (widget.asset['height'] as num?)?.toDouble() ?? 1;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (widget.inDialog) return;
    _slots = UiScaffoldSlots.of(context);
    _publish();
  }

  @override
  void dispose() {
    _slots?.release(this);
    _scroll.dispose();
    _reason.dispose();
    super.dispose();
  }

  /// Asks the frame for the editor's bar and hides the navigation.
  ///
  /// Back, the title, save and the four order controls, which the bar keeps
  /// two of and puts the rest in its own overflow (13 section 4.3). No pill:
  /// the way out of an editor opened over a record is the way back into the
  /// record.
  void _publish() {
    final UiScaffoldSlots? slots = _slots;
    if (slots == null) return;
    slots
      ..setTopBar(_bar(context), owner: this)
      ..setNavVisible(false, owner: this)
      ..setBandCompact(true, owner: this);
  }

  List<Json> _snapshot() => _regions
      .map(
        (Json r) => <String, dynamic>{
          ...r,
          'bbox': List<num>.from(r['bbox'] as List<num>),
        },
      )
      .toList();

  void _remember(String label) {
    _undo.add((regions: _snapshot(), selected: _selected, label: label));
    if (_undo.length > _undoDepth) _undo.removeAt(0);
  }

  void _applyUndo() {
    if (_undo.isEmpty) return;
    final _Undo step = _undo.removeLast();
    setState(() {
      _regions
        ..clear()
        ..addAll(step.regions);
      _selected = step.selected;
      _coordinateVersion++;
      _invalidCoordinates.clear();
      _error = null;
    });
  }

  void _add() {
    _remember('Add label region');
    setState(() {
      _regions.add(<String, dynamic>{
        'region_id': 'new-${DateTime.now().microsecondsSinceEpoch}',
        'bbox': <num>[0, 0, _width.toInt(), _height.toInt()],
        'order': _regions.length,
        'rotation_quarter_turns': 0,
      });
      _selected = _regions.length - 1;
      _coordinateVersion++;
    });
  }

  void _delete() {
    if (_regions.isEmpty) return;
    _remember('Delete label region');
    setState(() {
      final Json removed = _regions.removeAt(_selected);
      _invalidCoordinates.removeWhere(
        (String key) => key.startsWith('${removed['region_id']}-'),
      );
      _selected = 0;
      _coordinateVersion++;
    });
  }

  void _merge() {
    if (_selected >= _regions.length - 1) return;
    _remember('Merge with the next label region');
    setState(() {
      final Json selected = _regions[_selected];
      final List<num> box = selected['bbox'] as List<num>;
      final Json removed = _regions.removeAt(_selected + 1);
      _invalidCoordinates.removeWhere(
        (String key) => key.startsWith('${removed['region_id']}-'),
      );
      final List<num> next = removed['bbox'] as List<num>;
      _coordinateVersion++;
      selected['bbox'] = <num>[
        box[0] < next[0] ? box[0] : next[0],
        box[1] < next[1] ? box[1] : next[1],
        box[2] > next[2] ? box[2] : next[2],
        box[3] > next[3] ? box[3] : next[3],
      ];
    });
  }

  /// Direct manipulation writes straight into the recorded coordinates, with
  /// no animation, because a box that lags the finger reads as a box that
  /// does not belong to the number beside it (04 catalog row 74).
  void _drag(int corner, Offset delta, Size box) {
    final Json? selected = _current;
    if (selected == null) return;
    final List<num> bbox = selected['bbox'] as List<num>;
    final double dx = delta.dx / box.width * _width;
    final double dy = delta.dy / box.height * _height;
    setState(() {
      if (corner == _dragBody) {
        final double w = (bbox[2] - bbox[0]).toDouble();
        final double h = (bbox[3] - bbox[1]).toDouble();
        final double left = (bbox[0] + dx).clamp(0, _width - w);
        final double top = (bbox[1] + dy).clamp(0, _height - h);
        bbox[0] = left.roundToDouble();
        bbox[1] = top.roundToDouble();
        bbox[2] = (left + w).roundToDouble();
        bbox[3] = (top + h).roundToDouble();
      } else {
        final int xIndex = corner.isEven ? 0 : 2;
        final int yIndex = corner < 2 ? 1 : 3;
        bbox[xIndex] = (bbox[xIndex] + dx).clamp(0, _width).roundToDouble();
        bbox[yIndex] = (bbox[yIndex] + dy).clamp(0, _height).roundToDouble();
      }
      _coordinateVersion++;
    });
  }

  Json? get _current => _regions.isEmpty
      ? null
      : _regions[_selected.clamp(0, _regions.length - 1)];

  /// Puts the reason back on the screen, for a save that cannot proceed
  /// without it.
  ///
  /// The routed form's save is in the bar and the reason is at the end of the
  /// scroll, so a reviewer who presses save with an empty reason would
  /// otherwise be told by a line they cannot see.
  void _revealReason() {
    if (widget.inDialog) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final BuildContext? anchor = _reasonAnchor.currentContext;
      if (!mounted || anchor == null) return;
      Scrollable.ensureVisible(
        anchor,
        duration: context.ui.motion.standard,
        curve: MotionTokens.standardCurve,
        alignment: 0.1,
      );
    });
  }

  void _save() {
    if (_invalidCoordinates.isNotEmpty) {
      setState(() => _coordinateSubmitAttempted = true);
      _revealReason();
      return;
    }
    if (_regions.isEmpty) {
      setState(
        () => _error =
            'A record needs at least one label region. Add one, or cancel to '
            'keep the regions that are saved.',
      );
      _revealReason();
      return;
    }
    if (_reason.text.trim().isEmpty) {
      setState(() => _error = reasonRequired);
      _revealReason();
      return;
    }
    for (final Json r in _regions) {
      final List<num> b = r['bbox'] as List<num>;
      if (b.any((num v) => !v.isFinite) ||
          b[0] < 0 ||
          b[1] < 0 ||
          b[2] <= b[0] ||
          b[3] <= b[1] ||
          b[2] > _width ||
          b[3] > _height) {
        setState(
          () => _error =
              'Each region must have positive area and fit inside the '
              'original image.',
        );
        return;
      }
    }
    Navigator.of(context).pop(<String, dynamic>{
      'kind': 'segmentation_correction',
      'reason': _reason.text.trim(),
      'regions': _regions.indexed
          .map(((int, Json) e) => <String, dynamic>{...e.$2, 'order': e.$1})
          .toList(),
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.inDialog) _publish();
    return widget.inDialog ? _dialogForm(context) : _routedForm(context);
  }

  /// The editor inside a dialog: the form above the footer that saves it.
  ///
  /// One scroll, and the dialog wraps no second one around it
  /// (`UiDialog.scrollBody` is false at the call site).
  Widget _dialogForm(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Flexible(
          child: SingleChildScrollView(
            padding: EdgeInsetsDirectional.all(ui.space.s6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                ..._intro(context),
                ..._provenance(context),
                SizedBox(height: ui.space.s3),
                _regionStrip(context),
                ..._emptyOrPreview(context, banded: true),
                ..._form(context),
              ],
            ),
          ),
        ),
        _footer(context),
      ],
    );
  }

  /// The editor on its own route (13 section 4.3).
  ///
  /// The photograph is the header, floored at 40 percent of the viewport with
  /// the region strip riding its lower edge; the form, the provenance and the
  /// reason scroll beneath it; back, the title, save and the order controls
  /// are the bar's.
  Widget _routedForm(BuildContext context) {
    final UiThemeData ui = context.ui;
    final EdgeInsetsGeometry gutter = EdgeInsetsDirectional.symmetric(
      horizontal: ui.space.s6,
    );
    return CustomScrollView(
      controller: _scroll,
      slivers: <Widget>[
        if (_current != null && widget.asset['preview_bytes'] != null)
          _header(context, ui),
        SliverPadding(
          padding: gutter.add(EdgeInsets.only(top: ui.space.s4)),
          sliver: SliverToBoxAdapter(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                ..._intro(context),
                SizedBox(height: ui.space.s3),
                _regionStrip(context),
                ..._emptyOrPreview(context, banded: false),
                ..._form(context),
                ..._provenance(context),
                SizedBox(height: ui.space.s4),
                _reasonField(context),
                SizedBox(
                  height: ui.space.s6 + UiScaffold.of(context).bottomInset,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  /// The photograph as the one region this route pins.
  ///
  /// The band and nothing else. A header with a chrome row draws `glass.flat`
  /// behind that row once it is collapsed, which is a second frosted pane on
  /// a window 13 section 2.2 allows one, and this editor's region list has
  /// the whole width of the form to sit in.
  ///
  /// Built `primary: true`: the photograph is the thing this editor exists to
  /// show, so the header publishes `PrimaryRegion` on it at the extent it
  /// pins and no `PinnedChrome`, and spends nothing of the chrome budget, for
  /// the reason `WorkbenchSourcePane` states and the pattern now carries (13
  /// sections 2.3 and 3.1, polish 3). 13 section 5 names no fold expectation
  /// for the editor and the fold clause runs at compact only, so the marker
  /// states what the header is and no gate reads a number off it that it did
  /// not read before: the editor's chrome is the frame's bar alone, as it was
  /// with the zero extent wrapper this replaces.
  Widget _header(BuildContext context, UiThemeData ui) {
    // The band takes the height the photograph actually needs, between the
    // floor 13 section 4.3 gives it and the 55 percent 13 section 3.1 starts
    // at. The overlay maps recorded pixel coordinates onto the image, so the
    // image keeps the asset's ratio at every width and a band taller than
    // that is empty ground between the pixels and the form under them.
    final Size viewport = MediaQuery.sizeOf(context);
    final double natural =
        (viewport.width - 2 * ui.space.s6) * _height / _width;
    return UiCollapsingHeader(
      primary: true,
      maxFraction: (natural / viewport.height).clamp(
        sourceHeaderMinFraction,
        sourceHeaderMaxFraction,
      ),
      minFraction: sourceHeaderMinFraction,
      content: Padding(
        padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s6),
        child: Center(child: _previewImage(context, _box)),
      ),
    );
  }

  /// The selected region's box, or an empty list where there is none.
  List<num> get _box {
    final Json? selected = _current;
    return selected == null ? const <num>[] : selected['bbox'] as List<num>;
  }

  /// The one sentence that says what this editor does.
  List<Widget> _intro(BuildContext context) => const <Widget>[
    Text('Add, resize, rotate, reorder or merge label regions.'),
  ];

  /// The region list, which is also the header's chrome row on a route.
  Widget _regionStrip(BuildContext context) => UiCapsuleToggle<int>(
    selection: UiToggleSelection.single,
    selected: <int>{_selected},
    // Single mode clears the option already on; a region list has no "none"
    // state, so choosing the current one again leaves the selection where it
    // is.
    onChanged: (Set<int> next) {
      if (next.isEmpty) return;
      SpecimenHaptics.selectionChanged();
      setState(() => _selected = next.first);
    },
    options: <UiToggleOption<int>>[
      for (final (int i, Json _) in _regions.indexed)
        UiToggleOption<int>(value: i, label: 'Label ${i + 1}'),
    ],
  );

  /// The empty state, or the photograph where the form draws it itself.
  List<Widget> _emptyOrPreview(BuildContext context, {required bool banded}) {
    final UiThemeData ui = context.ui;
    if (_regions.isEmpty) {
      return <Widget>[
        Padding(
          padding: EdgeInsetsDirectional.only(top: ui.space.s2),
          child: EmptyState(
            icon: UiIcons.wholeImage.glyph,
            title: 'No label regions',
            body:
                'This record cannot be saved without at least one region. Add '
                'one below.',
          ),
        ),
      ];
    }
    if (!banded || widget.asset['preview_bytes'] == null) {
      return <Widget>[SizedBox(height: ui.space.s4)];
    }
    return <Widget>[SizedBox(height: ui.space.s4), _preview(context, _box)];
  }

  /// The rotation, the coordinates, the order controls where they are not the
  /// bar's, and the two local edits.
  List<Widget> _form(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Json? selected = _current;
    return <Widget>[
      if (selected != null) ...<Widget>[
        SizedBox(height: ui.space.s2),
        Text(
          'Label reading rotation: '
          '${(selected['rotation_quarter_turns'] as int) * _quarterDegrees} '
          'degrees clockwise. Source coordinates stay unchanged.',
          style: ui.type.bodySmall,
        ),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: UiButton(
            label: rotateReadingLabel,
            variant: UiButtonVariant.ghost,
            leading: UiIcons.rotateView,
            onPressed: () => setState(
              () => selected['rotation_quarter_turns'] =
                  ((selected['rotation_quarter_turns'] as int) + 1) % 4,
            ),
          ),
        ),
        SizedBox(height: ui.space.s2),
        ..._coordinateBlock(context, selected, _box),
      ],
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: UiButton(
          label: addRegionLabel,
          variant: UiButtonVariant.secondary,
          leading: UiIcons.add,
          onPressed: _add,
        ),
      ),
      if (_undo.isNotEmpty)
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: UiButton(
            label: 'Undo ${_undo.last.label.toLowerCase()}',
            variant: UiButtonVariant.ghost,
            leading: UiIcons.undo,
            onPressed: _applyUndo,
          ),
        ),
    ];
  }

  /// The bar the routed editor publishes into the frame (13 section 4.3).
  Widget _bar(BuildContext context) => UiTopBar(
    leading: UiIconButton(
      icon: UiIcons.back,
      semanticsLabel: closeEditorLabel,
      tooltip: closeEditorLabel,
      onPressed: () => Navigator.of(context).maybePop(),
    ),
    title: regionEditorTitle,
    actions: <Widget>[
      UiTopBarAction(
        icon: UiIcons.save,
        label: saveRegionsLabel,
        onPressed: _save,
      ),
      ..._orderActions(context),
    ],
  );

  /// Delete, move earlier, move later and merge, as commands rather than as a
  /// row of the form (13 section 4.3).
  List<UiTopBarAction> _orderActions(BuildContext context) {
    final bool first = _selected == 0;
    final bool last = _selected >= _regions.length - 1;
    return <UiTopBarAction>[
      UiTopBarAction(
        icon: UiIcons.remove,
        label: deleteRegionLabel,
        onPressed: _regions.isEmpty ? null : _delete,
        disabledReason: _regions.isEmpty
            ? 'There is no label region to delete.'
            : null,
      ),
      UiTopBarAction(
        icon: UiIcons.previous,
        label: moveEarlierLabel,
        onPressed: first ? null : _moveEarlier,
        disabledReason: first
            ? 'This is already the first label region.'
            : null,
      ),
      UiTopBarAction(
        icon: UiIcons.next,
        label: moveLaterLabel,
        onPressed: last ? null : _moveLater,
        disabledReason: last ? 'This is already the last label region.' : null,
      ),
    ];
  }

  void _moveEarlier() => setState(() {
    final Json item = _regions.removeAt(_selected);
    _regions.insert(--_selected, item);
  });

  void _moveLater() => setState(() {
    final Json item = _regions.removeAt(_selected);
    _regions.insert(++_selected, item);
  });

  /// The provenance lines: what saving replaces, and the source basis.
  ///
  /// Shown inline on a dialog and behind the compact disclosure, so a phone
  /// opens on the photograph rather than on three paragraphs about it.
  List<Widget> _provenance(BuildContext context) {
    final UiThemeData ui = context.ui;
    return <Widget>[
      const CaveatText(
        label: 'Saving replaces the readings that depend on these regions.',
        why:
            'Coordinates follow the recorded source basis. Earlier readings '
            'stay in history.',
      ),
      SizedBox(height: ui.space.s2),
      Text(
        'Source coordinate dimensions: ${widget.asset['width']} by '
        '${widget.asset['height']} pixels',
        style: ui.type.bodySmall,
      ),
      SourceBasisNotice(asset: widget.asset),
    ];
  }

  /// The numeric path and the region order controls.
  List<Widget> _coordinateBlock(
    BuildContext context,
    Json selected,
    List<num> box,
  ) {
    final UiThemeData ui = context.ui;
    return <Widget>[
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: UiLabel(
          'Exact coordinates',
          style: ui.type.label.copyWith(color: ui.color.inkSecondary),
        ),
      ),
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: Text(
          'Typing here is the precise alternative to dragging, and the path '
          'that needs no pointer.',
          style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
        ),
      ),
      SizedBox(height: ui.space.s2),
      _coordinates(context, selected, box),
      SizedBox(height: ui.space.s3),
      // Merge keeps its word wherever it is drawn. 13 section 4.3 puts the
      // order controls in the bar's overflow and a `UiTopBarAction` is a
      // glyph with a word beside it in the menu; the registry has no merge
      // glyph, and reusing one that already means something else would give
      // one glyph two meanings (09 section 7). So delete, earlier and later
      // are the bar's on a route and this one is the form's on both.
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: UiButton(
          label: mergeRegionsLabel,
          variant: UiButtonVariant.ghost,
          onPressed: _selected >= _regions.length - 1 ? null : _merge,
          disabledReason: _selected >= _regions.length - 1
              ? 'There is no later label region to merge with.'
              : null,
        ),
      ),
      // The dialog has no bar to carry the rest, so it keeps the toolbar
      // 07 section 7 gave it. Not a `UiButtonRow`: that is the arrangement
      // for a primary and its way out, and it draws the primary last, which
      // would put the one destructive control at the end of the reading
      // order. These are peers, so they keep the order they shipped in.
      if (widget.inDialog)
        Wrap(
          spacing: ui.space.s2,
          runSpacing: ui.space.s2,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            UiIconButton(
              icon: UiIcons.remove,
              semanticsLabel: deleteRegionLabel,
              onPressed: _regions.isEmpty ? null : _delete,
            ),
            UiIconButton(
              icon: UiIcons.previous,
              semanticsLabel: moveEarlierLabel,
              onPressed: _selected == 0 ? null : _moveEarlier,
              disabledReason: _selected == 0
                  ? 'This is already the first label region.'
                  : null,
            ),
            UiIconButton(
              icon: UiIcons.next,
              semanticsLabel: moveLaterLabel,
              onPressed: _selected >= _regions.length - 1 ? null : _moveLater,
              disabledReason: _selected >= _regions.length - 1
                  ? 'This is already the last label region.'
                  : null,
            ),
          ],
        ),
    ];
  }

  /// The photograph, with every region drawn over it.
  ///
  /// On a compact window the band is floored at
  /// [RegionEditorBody.compactPreviewMinHeight] so the image is the dominant
  /// element of the sheet and a 48 dp corner handle has somewhere to go
  /// (finding V-7). The image itself keeps the asset's own ratio at every
  /// width, because the overlay maps recorded pixel coordinates onto it and a
  /// stretched image would move every handle off the pixel it names.
  Widget _preview(BuildContext context, List<num> box) {
    final Widget image = _previewImage(context, box);
    if (!WindowClass.of(context).isCompact) return image;
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints outer) {
        final double natural = outer.maxWidth.isFinite
            ? outer.maxWidth * _height / _width
            : RegionEditorBody.compactPreviewMinHeight;
        return SizedBox(
          height: math.max(natural, RegionEditorBody.compactPreviewMinHeight),
          child: Center(child: image),
        );
      },
    );
  }

  Widget _previewImage(BuildContext context, List<num> box) => AspectRatio(
    aspectRatio: _width / _height,
    child: LayoutBuilder(
      builder: (BuildContext context, BoxConstraints c) {
        final Size size = Size(c.maxWidth, c.maxHeight);
        return Stack(
          fit: StackFit.expand,
          children: <Widget>[
            SourcePixels(
              asset: widget.asset,
              semanticLabel: 'Unmodified source for region correction',
            ),
            for (final (int i, Json r) in _regions.indexed)
              _RegionBox(
                key: ValueKey<Object>(r['region_id'] ?? i),
                index: i + 1,
                selected: i == _selected,
                bbox: r['bbox'] as List<num>,
                imageWidth: _width,
                imageHeight: _height,
                size: size,
                onSelect: () => setState(() => _selected = i),
                onDragBody: i == _selected
                    ? (Offset d) => _drag(_dragBody, d, size)
                    : null,
                onDragCorner: i == _selected
                    ? (int corner, Offset d) => _drag(corner, d, size)
                    : null,
              ),
            if (box.length == 4) const SizedBox.shrink(),
          ],
        );
      },
    ),
  );

  Widget _coordinates(BuildContext context, Json selected, List<num> box) {
    final UiThemeData ui = context.ui;
    return Wrap(
      spacing: ui.space.s3,
      runSpacing: ui.space.s3,
      children: <Widget>[
        for (final (int i, String label) in _coordinateLabels.indexed)
          SizedBox(
            width: coordinateFieldWidth,
            child: _CoordinateField(
              label: label,
              value: '${box[i]}',
              // The version is what tells the field its value moved under it:
              // a drag, a merge or an undo rewrites the box, and typing does
              // not, so the caret never jumps while a reviewer is in it.
              version: _coordinateVersion,
              errorText:
                  _invalidCoordinates.contains('${selected['region_id']}-$i')
                  ? 'Whole pixels'
                  : null,
              onChanged: (String v) {
                final String coordinateKey = '${selected['region_id']}-$i';
                final int? n = int.tryParse(v);
                setState(() {
                  _coordinateSubmitAttempted = false;
                  if (n != null) {
                    box[i] = n;
                    _invalidCoordinates.remove(coordinateKey);
                  } else {
                    _invalidCoordinates.add(coordinateKey);
                  }
                });
              },
            ),
          ),
      ],
    );
  }

  /// The reason, and the line that says why a save cannot proceed.
  ///
  /// The same two on both surfaces, in the footer of the dialog and at the
  /// end of the route's one scroll, because a reason is what the save is
  /// recorded under and belongs beside the change it explains.
  Widget _reasonField(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String? error = _visibleError;
    return Column(
      key: _reasonAnchor,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        UiTextArea(
          controller: _reason,
          label: 'Reason',
          helpText: reasonHelperText,
          minLines: _reasonMinLines,
          maxLines: _reasonMaxLines,
        ),
        // No shake. The message names the fix; the motion only gets it on
        // screen without a jump (04 catalog row 80).
        MotionReveal(
          visible: error != null,
          child: Padding(
            padding: EdgeInsetsDirectional.only(top: ui.space.s2),
            child: Semantics(
              liveRegion: true,
              child: Text(
                error ?? '',
                style: ui.type.bodySmall.copyWith(
                  color: ui.color.status.blocked.content,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  /// The dialog's sticky footer: the reason, and the two controls that end
  /// the editor (07 section 7).
  ///
  /// The route has neither, because its bar carries the save and its scroll
  /// carries the reason (13 section 4.3).
  Widget _footer(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Surface(
      role: SurfaceRole.paper,
      radius: ui.shape.none,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: EdgeInsetsDirectional.all(ui.space.s4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              _reasonField(context),
              SizedBox(height: ui.space.s3),
              UiButtonRow(
                primary: UiButton(
                  label: saveRegionsLabel,
                  leading: UiIcons.save,
                  onPressed: _save,
                ),
                secondary: UiButton(
                  label: 'Cancel',
                  variant: UiButtonVariant.ghost,
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// The corner index that means "move the whole box".
  static const int _dragBody = -1;
  static const int _quarterDegrees = 90;
  static const int _reasonMinLines = 2;
  static const int _reasonMaxLines = 4;
  static const List<String> _coordinateLabels = <String>[
    'Left x',
    'Top y',
    'Right x',
    'Bottom y',
  ];
}

/// How wide one coordinate field is drawn.
///
/// Four digits, a unit and the field's own padding: the widest coordinate a
/// forty megapixel original can carry, so the four fields never disagree
/// about their width as the numbers change.
const double coordinateFieldWidth = 140;

/// A full window route built on `package:flutter/widgets.dart`.
///
/// `MaterialPageRoute` is the only route `PageTransitionsTheme` reaches, and
/// it comes with `material.dart`, which no screen imports any more. The
/// entrance is therefore the system's own: the emphasized pair `ModalRoutes`
/// uses, which collapses to nothing under reduced motion because the duration
/// does.
/// Open: a `UiPageRoute` in the package, so a screen pushing a full window
/// surface gets one entrance rather than each writing its own. Two are
/// written today. This one, which the editor and the source pane's full
/// window view share, and the `MaterialPageRoute` the capture route keeps
/// because it is the only route a `PageTransitionsTheme` reaches, and with it
/// the platform's own back gesture, which a bare `PageRouteBuilder` has no
/// answer for.
PageRoute<T> uiFullScreenRoute<T>(
  BuildContext context, {
  required WidgetBuilder builder,
}) {
  final MotionTokens motion = context.ui.motion;
  return PageRouteBuilder<T>(
    transitionDuration: motion.emphasized,
    reverseTransitionDuration: motion.standard,
    fullscreenDialog: true,
    pageBuilder:
        (
          BuildContext context,
          Animation<double> animation,
          Animation<double> secondary,
        ) => builder(context),
    transitionsBuilder:
        (
          BuildContext context,
          Animation<double> animation,
          Animation<double> secondary,
          Widget child,
        ) {
          final CurvedAnimation curved = CurvedAnimation(
            parent: animation,
            curve: MotionTokens.emphasizedEnterCurve,
            reverseCurve: MotionTokens.emphasizedExitCurve,
          );
          return FadeTransition(
            opacity: curved,
            child: SlideTransition(
              position: Tween<Offset>(
                begin: const Offset(0, fullScreenEntranceRise),
                end: Offset.zero,
              ).animate(curved),
              child: child,
            ),
          );
        },
  );
}

/// How far a full window surface rises as it arrives, as a fraction of it.
///
/// The same rise `ModalRoutes` gives a sheet, so the two entrances read as
/// one system.
const double fullScreenEntranceRise = 0.08;

/// One coordinate, as a field the reviewer can type a whole pixel into.
///
/// `UiField` edits through a controller rather than an initial value, so the
/// two ways a coordinate changes are kept apart here: typing writes through
/// [onChanged] and leaves the text alone, and a drag, a merge or an undo
/// arrives as a new [version] and rewrites it.
class _CoordinateField extends StatefulWidget {
  const _CoordinateField({
    required this.label,
    required this.value,
    required this.version,
    required this.errorText,
    required this.onChanged,
  });

  final String label;
  final String value;
  final int version;
  final String? errorText;
  final ValueChanged<String> onChanged;

  @override
  State<_CoordinateField> createState() => _CoordinateFieldState();
}

class _CoordinateFieldState extends State<_CoordinateField> {
  late final TextEditingController _controller = TextEditingController(
    text: widget.value,
  );

  @override
  void didUpdateWidget(_CoordinateField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.version == oldWidget.version ||
        _controller.text == widget.value) {
      return;
    }
    _controller.value = TextEditingValue(
      text: widget.value,
      selection: TextSelection.collapsed(offset: widget.value.length),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return UiField(
      label: widget.label,
      controller: _controller,
      keyboardType: TextInputType.number,
      inputFormatters: <TextInputFormatter>[
        FilteringTextInputFormatter.digitsOnly,
      ],
      errorText: widget.errorText,
      onChanged: widget.onChanged,
      // The unit, not an action: it names what the number is in and is read
      // out of the field's own label rather than as a control of its own
      // (02 section 4.14).
      trailing: ExcludeSemantics(
        child: UiLabel(
          'px',
          style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
        ),
      ),
    );
  }
}

/// One draggable region over the preview.
class _RegionBox extends StatefulWidget {
  const _RegionBox({
    super.key,
    required this.index,
    required this.selected,
    required this.bbox,
    required this.imageWidth,
    required this.imageHeight,
    required this.size,
    required this.onSelect,
    required this.onDragBody,
    required this.onDragCorner,
  });

  final int index;
  final bool selected;
  final List<num> bbox;
  final double imageWidth;
  final double imageHeight;
  final Size size;
  final VoidCallback onSelect;
  final void Function(Offset)? onDragBody;
  final void Function(int, Offset)? onDragCorner;

  @override
  State<_RegionBox> createState() => _RegionBoxState();
}

class _RegionBoxState extends State<_RegionBox> {
  /// False for the single frame after a region is added, which is what gives
  /// the opacity somewhere to come from (04 catalog row 77).
  bool _shown = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) setState(() => _shown = true);
    });
  }

  @override
  Widget build(BuildContext context) {
    final List<num> bbox = widget.bbox;
    final int index = widget.index;
    final bool selected = widget.selected;
    final Size size = widget.size;
    if (bbox.length != 4) return const SizedBox.shrink();
    final Rect rect = Rect.fromLTRB(
      bbox[0] / widget.imageWidth * size.width,
      bbox[1] / widget.imageHeight * size.height,
      bbox[2] / widget.imageWidth * size.width,
      bbox[3] / widget.imageHeight * size.height,
    );
    final void Function(Offset)? body = widget.onDragBody;
    final MotionTokens motion = context.ui.motion;

    // The rectangle itself follows the numbers with zero animation, always:
    // typing a coordinate and watching the box lag two hundred milliseconds
    // behind makes a reviewer distrust the coordinate (row 74). Only its
    // arrival is animated (row 77).
    return AnimatedOpacity(
      opacity: _shown ? 1 : 0,
      duration: motion.standard,
      curve: MotionTokens.enterCurve,
      child: _box(context, rect, index, selected, body),
    );
  }

  Widget _box(
    BuildContext context,
    Rect rect,
    int index,
    bool selected,
    void Function(Offset)? body,
  ) {
    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        RegionOverlay(
          index: index,
          rect: rect,
          selected: selected,
          onTap: widget.onSelect,
        ),
        if (body != null)
          Positioned.fromRect(
            rect: rect,
            child: Semantics(
              label: 'Move Label $index',
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onPanUpdate: (DragUpdateDetails d) => body(d.delta),
                child: const SizedBox.expand(),
              ),
            ),
          ),
        if (widget.onDragCorner != null)
          for (int corner = 0; corner < 4; corner++)
            _CornerHandle(
              corner: corner,
              centre: Offset(
                corner.isEven ? rect.left : rect.right,
                corner < 2 ? rect.top : rect.bottom,
              ),
              label: _cornerNames[corner],
              index: index,
              onDrag: (Offset d) => widget.onDragCorner!(corner, d),
            ),
      ],
    );
  }

  static const List<String> _cornerNames = <String>[
    'top left',
    'top right',
    'bottom left',
    'bottom right',
  ];
}

/// A corner handle whose hit box is a full target even though the square the
/// reviewer sees is small, so it never covers the pixels underneath it
/// (05 section 4, touch targets).
class _CornerHandle extends StatelessWidget {
  const _CornerHandle({
    required this.corner,
    required this.centre,
    required this.label,
    required this.index,
    required this.onDrag,
  });

  final int corner;
  final Offset centre;
  final String label;
  final int index;
  final ValueChanged<Offset> onDrag;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double target = ui.space.targetMin;
    final double visual = ui.space.s3;
    return Positioned(
      left: centre.dx - target / 2,
      top: centre.dy - target / 2,
      width: target,
      height: target,
      child: Semantics(
        label: 'Label $index $label corner',
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onPanUpdate: (DragUpdateDetails d) => onDrag(d.delta),
          child: Center(
            child: SizedBox.square(
              dimension: visual,
              child: DecoratedBox(
                // The handle belongs to the selected region's marker, so it
                // carries the same accent and the same casing the stroke
                // does: one marker, with somewhere to take hold of it
                // (09 section 3.4).
                decoration: ShapeDecoration(
                  color: ui.color.accent,
                  shape: Squircle.border(
                    ui.shape.inner,
                    side: BorderSide(
                      color: ui.color.ink,
                      width: ui.shape.stroke.hairline,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The editor's own motion budget, named so the file reads as tokenised even
/// though every move in it is direct manipulation and therefore instant.
const Duration regionEditorDirectManipulation = MotionTokens.instantRaw;
