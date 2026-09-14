/// The region editor (screen blueprints, section 7; responsive 3.6).
///
/// Full screen on compact and medium, a 640 dp dialog otherwise. The preview
/// fills the width and every region can be dragged by its body or resized by
/// one of four corner handles. The numeric fields stay as the precise
/// alternative and as the pointer free path WCAG 2.2 SC 2.5.7 requires, so
/// nothing here is drag only. Delete and merge are undoable inside the
/// editor, and saving with no regions is refused with a reason.
///
/// All edits stay in original pixel coordinates. The API validates and
/// versions them.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'models.dart';
import 'source_pixels.dart';
import 'theme/icons.dart';
import 'theme/motion.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

/// Opens the editor in the container the window earns.
Future<Json?> showRegionEditor(
  BuildContext context, {
  required List<Json> regions,
  required Json asset,
}) {
  final WindowClass window = WindowClass.of(context);
  if (window.isAtLeast(WindowClass.expanded)) {
    return showDialog<Json>(
      context: context,
      builder: (_) => RegionEditor(regions: regions, asset: asset),
    );
  }
  return Navigator.of(context).push<Json>(
    MaterialPageRoute<Json>(
      fullscreenDialog: true,
      builder: (_) => Scaffold(
        appBar: AppBar(title: const Text('Correct label regions')),
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
  Widget build(BuildContext context) => Dialog(
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(context.shape.radiusMd),
    ),
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: DialogWidths.wide),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Padding(
            padding: EdgeInsets.fromLTRB(
              context.space.space6,
              context.space.space6,
              context.space.space6,
              context.space.space0,
            ),
            child: Text(
              'Correct label regions',
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
          Flexible(
            child: RegionEditorBody(regions: regions, asset: asset),
          ),
        ],
      ),
    ),
  );
}

/// The editor itself, identical in the dialog and on the full screen route.
class RegionEditorBody extends StatefulWidget {
  const RegionEditorBody({
    super.key,
    required this.regions,
    required this.asset,
  });

  final List<Json> regions;
  final Json asset;

  /// The shortest the photograph's band may be on a compact window
  /// (finding V-7). Below this a corner handle has no room to be dragged and
  /// the editor is a coordinate form with a thumbnail.
  static const double compactPreviewMinHeight = 240;

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

  /// True when the compact sheet's detail disclosure is open (finding V-7).
  bool _detailsOpen = false;

  /// Bumped only when the editor has to force the disclosure open, so the
  /// tile is rebuilt in that state without losing focus on every toggle.
  int _detailsVersion = 0;

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
  void dispose() {
    _reason.dispose();
    super.dispose();
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
  /// does not belong to the number beside it (motion catalog row 74).
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

  /// Opens the compact disclosure, for an error that lives inside it.
  void _revealDetails() {
    if (_detailsOpen) return;
    _detailsOpen = true;
    _detailsVersion++;
  }

  void _save() {
    if (_invalidCoordinates.isNotEmpty) {
      setState(() {
        _coordinateSubmitAttempted = true;
        _revealDetails();
      });
      return;
    }
    if (_regions.isEmpty) {
      setState(
        () => _error =
            'A record needs at least one label region. Add one, or cancel to '
            'keep the regions that are saved.',
      );
      return;
    }
    if (_reason.text.trim().isEmpty) {
      setState(() => _error = reasonRequired);
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
    final ThemeData theme = Theme.of(context);
    final Json? selected = _current;
    final List<num> box = selected == null
        ? const <num>[]
        : selected['bbox'] as List<num>;
    // Finding V-7. On a phone the photograph was a thin strip between the
    // region chips above it and the coordinate form below it, which is not
    // enough to drag a 48 dp corner handle on. On a compact window the
    // preview now comes first and everything that is not the photograph goes
    // behind one disclosure, so the sheet's main content is the pixels.
    final bool compact = WindowClass.of(context).isCompact;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Flexible(
          child: SingleChildScrollView(
            padding: EdgeInsets.all(context.space.space6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Text(
                  'Add, resize, rotate, reorder or merge label regions.',
                ),
                if (!compact) ..._provenance(context),
                SizedBox(height: context.space.space3),
                Wrap(
                  spacing: context.space.space2,
                  runSpacing: context.space.space2,
                  children: <Widget>[
                    for (final (int i, Json r) in _regions.indexed)
                      ChoiceChip(
                        // The region list takes focus on open (accessibility,
                        // section 4.2 step 5; finding V-10). Deliberately not
                        // a coordinate field: a touch reviewer opening the
                        // editor should see the photograph, not a keyboard.
                        autofocus: i == 0,
                        // Reordering a `Wrap` cannot be animated and is not
                        // worth building. The numbering change is carried by
                        // a label cross-fade (motion catalog, row 79).
                        label: AnimatedSwitcher(
                          duration: context.motion.quick,
                          switchInCurve: MotionTokens.standardCurve,
                          child: Text(
                            'Label ${i + 1}',
                            key: ValueKey<String>(
                              'editor-chip-${r['region_id'] ?? i}-${i + 1}',
                            ),
                          ),
                        ),
                        selected: _selected == i,
                        onSelected: (_) {
                          SpecimenHaptics.selectionChanged();
                          setState(() => _selected = i);
                        },
                      ),
                  ],
                ),
                if (_regions.isEmpty)
                  Padding(
                    padding: EdgeInsets.only(top: context.space.space2),
                    child: const EmptyState(
                      icon: Symbols.crop_free,
                      title: 'No label regions',
                      body:
                          'This record cannot be saved without at least one '
                          'region. Add one below.',
                    ),
                  ),
                if (selected != null) ...<Widget>[
                  SizedBox(height: context.space.space4),
                  if (widget.asset['preview_bytes'] != null)
                    _preview(context, box, compact: compact),
                  SizedBox(height: context.space.space2),
                  Text(
                    'Label reading rotation: '
                    '${(selected['rotation_quarter_turns'] as int) * _quarterDegrees} degrees clockwise. '
                    'Source coordinates stay unchanged.',
                    style: theme.textTheme.bodySmall,
                  ),
                  Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: TextButton.icon(
                      onPressed: () => setState(
                        () => selected['rotation_quarter_turns'] =
                            ((selected['rotation_quarter_turns'] as int) + 1) %
                            4,
                      ),
                      icon: const Icon(Symbols.rotate_right),
                      label: const Text('Rotate label reading 90 degrees'),
                    ),
                  ),
                  SizedBox(height: context.space.space2),
                  if (compact)
                    // One disclosure, an `ExpansionTile` like every other
                    // disclosure in the product (pass criterion 4.1). The
                    // pointer free path WCAG 2.2 SC 2.5.7 asks for is inside
                    // it, reachable by keyboard, and the editor opens it
                    // itself when a coordinate it holds is wrong.
                    ExpansionTile(
                      key: ValueKey<String>('region-details-$_detailsVersion'),
                      initiallyExpanded: _detailsOpen,
                      onExpansionChanged: (bool open) => _detailsOpen = open,
                      tilePadding: EdgeInsets.zero,
                      childrenPadding: EdgeInsets.zero,
                      expandedCrossAxisAlignment: CrossAxisAlignment.stretch,
                      title: const Text('Exact coordinates and region order'),
                      subtitle: const Text(
                        'Type coordinates, reorder, merge or delete.',
                      ),
                      children: <Widget>[
                        ..._provenance(context),
                        SizedBox(height: context.space.space2),
                        ..._coordinateBlock(context, selected, box),
                      ],
                    )
                  else
                    ..._coordinateBlock(context, selected, box),
                ],
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: OutlinedButton.icon(
                    onPressed: _add,
                    icon: const Icon(Symbols.add),
                    label: const Text('Add label region'),
                  ),
                ),
                if (_undo.isNotEmpty)
                  Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: TextButton.icon(
                      onPressed: _applyUndo,
                      icon: const Icon(Symbols.undo),
                      label: Text('Undo ${_undo.last.label.toLowerCase()}'),
                    ),
                  ),
              ],
            ),
          ),
        ),
        _footer(context),
      ],
    );
  }

  /// The provenance lines: what saving replaces, and the source basis.
  ///
  /// Shown inline on a dialog and behind the compact disclosure, so a phone
  /// opens on the photograph rather than on three paragraphs about it.
  List<Widget> _provenance(BuildContext context) => <Widget>[
    const CaveatText(
      label: 'Saving replaces the readings that depend on these regions.',
      why:
          'Coordinates follow the recorded source basis. Earlier readings '
          'stay in history.',
    ),
    SizedBox(height: context.space.space2),
    Text(
      'Source coordinate dimensions: ${widget.asset['width']} by '
      '${widget.asset['height']} pixels',
      style: Theme.of(context).textTheme.bodySmall,
    ),
    SourceBasisNotice(asset: widget.asset),
  ];

  /// The numeric path and the region order controls.
  List<Widget> _coordinateBlock(
    BuildContext context,
    Json selected,
    List<num> box,
  ) {
    final ThemeData theme = Theme.of(context);
    return <Widget>[
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: Text(
          'Exact coordinates',
          style: theme.textTheme.labelMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ),
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: Text(
          'Typing here is the precise alternative to dragging, and the path '
          'that needs no pointer.',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ),
      SizedBox(height: context.space.space2),
      _coordinates(context, selected, box),
      SizedBox(height: context.space.space3),
      Wrap(
        spacing: context.space.space2,
        runSpacing: context.space.space2,
        children: <Widget>[
          TextButton.icon(
            onPressed: _delete,
            icon: const Icon(Symbols.delete),
            label: const Text('Delete region'),
          ),
          TextButton(
            onPressed: _selected == 0
                ? null
                : () => setState(() {
                    final Json item = _regions.removeAt(_selected);
                    _regions.insert(--_selected, item);
                  }),
            child: const Text('Move earlier'),
          ),
          TextButton(
            onPressed: _selected >= _regions.length - 1
                ? null
                : () => setState(() {
                    final Json item = _regions.removeAt(_selected);
                    _regions.insert(++_selected, item);
                  }),
            child: const Text('Move later'),
          ),
          TextButton(
            onPressed: _selected >= _regions.length - 1 ? null : _merge,
            child: const Text('Merge with next'),
          ),
        ],
      ),
    ];
  }

  /// The photograph, with every region drawn over it.
  ///
  /// On a compact window the band is floored at
  /// [RegionEditorBody.compactPreviewMinHeight] so
  /// the image is the dominant element of the sheet and a 48 dp corner handle
  /// has somewhere to go (finding V-7). The image itself keeps the asset's
  /// own ratio at every width, because the overlay maps recorded pixel
  /// coordinates onto it and a stretched image would move every handle off
  /// the pixel it names.
  Widget _preview(
    BuildContext context,
    List<num> box, {
    required bool compact,
  }) {
    final Widget image = _previewImage(context, box);
    if (!compact) return image;
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
                bbox: (r['bbox'] as List<num>),
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

  Widget _coordinates(BuildContext context, Json selected, List<num> box) =>
      Wrap(
        spacing: context.space.space3,
        runSpacing: context.space.space3,
        children: <Widget>[
          for (final (int i, String label) in <String>[
            'Left x',
            'Top y',
            'Right x',
            'Bottom y',
          ].indexed)
            SizedBox(
              width: _coordinateFieldWidth,
              child: TextFormField(
                key: ValueKey<String>(
                  '${selected['region_id']}-$i-$_coordinateVersion',
                ),
                initialValue: '${box[i]}',
                keyboardType: TextInputType.number,
                inputFormatters: <TextInputFormatter>[
                  FilteringTextInputFormatter.digitsOnly,
                ],
                decoration: InputDecoration(
                  labelText: label,
                  suffixText: 'px',
                  errorText:
                      _invalidCoordinates.contains(
                        '${selected['region_id']}-$i',
                      )
                      ? 'Whole pixels'
                      : null,
                ),
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

  Widget _footer(BuildContext context) {
    final String? error = _visibleError;
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainer,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: EdgeInsets.all(context.space.space4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              TextField(
                controller: _reason,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Reason',
                  helperText: reasonHelperText,
                ),
              ),
              // No shake. The message names the fix; the motion only gets it
              // on screen without a jump (motion catalog, row 80).
              MotionReveal(
                visible: error != null,
                child: Padding(
                  padding: EdgeInsets.only(top: context.space.space2),
                  child: Semantics(
                    liveRegion: true,
                    child: Text(
                      error ?? '',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ),
                ),
              ),
              SizedBox(height: context.space.space3),
              Wrap(
                alignment: WrapAlignment.end,
                spacing: context.space.space2,
                runSpacing: context.space.space2,
                children: <Widget>[
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    onPressed: _save,
                    child: const Text('Save region version'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// The corner index that means "move the whole box".
  static const int _dragBody = -1;
  static const double _coordinateFieldWidth = 140;
  static const int _quarterDegrees = 90;
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
  /// the opacity somewhere to come from (motion catalog, row 77).
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
    final MotionTokens motion = context.motion;

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
/// (responsive 4, touch targets).
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
    final double target = context.sizes.targetMin;
    final double visual = context.space.space3;
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
                decoration: BoxDecoration(
                  color: context.tokens.regionSelectedCore,
                  border: Border.all(
                    color: context.tokens.regionSelectedCasing,
                    width: context.shape.strokeHairline,
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
