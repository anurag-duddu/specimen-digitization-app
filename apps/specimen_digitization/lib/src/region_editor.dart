import 'package:flutter/material.dart';
import 'models.dart';
import 'source_pixels.dart';

/// All edits stay in original pixel coordinates. The API validates and versions them.
class RegionEditor extends StatefulWidget {
  const RegionEditor({super.key, required this.regions, required this.asset});
  final List<Json> regions;
  final Json asset;
  @override
  State<RegionEditor> createState() => _RegionEditorState();
}

class _RegionEditorState extends State<RegionEditor> {
  late final List<Json> _regions = widget.regions
      .map(
        (r) => <String, dynamic>{
          ...r,
          'bbox': List<num>.from(r['bbox'] ?? [0, 0, 1, 1]),
          'rotation_quarter_turns': r['rotation_quarter_turns'] ?? 0,
        },
      )
      .toList();
  int _selected = 0;
  int _coordinateVersion = 0;
  String? _error;
  final _invalidCoordinates = <String>{};
  bool _coordinateSubmitAttempted = false;
  String? get _visibleError => _invalidCoordinates.isEmpty
      ? _error
      : _coordinateSubmitAttempted
      ? 'Correct invalid pixel coordinates before saving.'
      : 'Coordinates must be whole pixel numbers.';
  final _reason = TextEditingController();
  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  void _add() {
    final width = (widget.asset['width'] as num?)?.toInt() ?? 1;
    final height = (widget.asset['height'] as num?)?.toInt() ?? 1;
    setState(() {
      _regions.add({
        'region_id': 'new-${DateTime.now().microsecondsSinceEpoch}',
        'bbox': [0, 0, width, height],
        'order': _regions.length,
        'rotation_quarter_turns': 0,
      });
      _selected = _regions.length - 1;
    });
  }

  @override
  Widget build(BuildContext context) {
    final selected = _regions.isEmpty
        ? null
        : _regions[_selected.clamp(0, _regions.length - 1)];
    final box = selected == null ? <num>[] : selected['bbox'] as List<num>;
    return AlertDialog(
      title: const Text('Correct label regions'),
      content: SizedBox(
        width: 680,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Add missed labels, resize bounds, rotate a label reading, reorder, or merge adjacent regions. Coordinates follow the recorded source basis. Saving supersedes affected observations.',
              ),
              const SizedBox(height: 12),
              Text(
                'Source coordinate dimensions: ${widget.asset['width']} × ${widget.asset['height']} pixels',
              ),
              SourceBasisNotice(asset: widget.asset),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: _regions.indexed
                    .map(
                      (e) => ChoiceChip(
                        label: Text('Label ${e.$1 + 1}'),
                        selected: _selected == e.$1,
                        onSelected: (_) => setState(() => _selected = e.$1),
                      ),
                    )
                    .toList(),
              ),
              if (selected != null) ...[
                const SizedBox(height: 16),
                if (widget.asset['preview_bytes'] != null)
                  SizedBox(
                    height: 180,
                    child: Center(
                      child: AspectRatio(
                        aspectRatio:
                            (widget.asset['width'] as num) /
                            (widget.asset['height'] as num),
                        child: LayoutBuilder(
                          builder: (context, c) => Stack(
                            fit: StackFit.expand,
                            children: [
                              SourcePixels(
                                asset: widget.asset,
                                semanticLabel:
                                    'Unmodified source for region correction',
                              ),
                              if (box[2] > box[0] && box[3] > box[1])
                                Positioned(
                                  left:
                                      box[0] /
                                      (widget.asset['width'] as num) *
                                      c.maxWidth,
                                  top:
                                      box[1] /
                                      (widget.asset['height'] as num) *
                                      c.maxHeight,
                                  width:
                                      (box[2] - box[0]) /
                                      (widget.asset['width'] as num) *
                                      c.maxWidth,
                                  height:
                                      (box[3] - box[1]) /
                                      (widget.asset['height'] as num) *
                                      c.maxHeight,
                                  child: IgnorePointer(
                                    child: DecoratedBox(
                                      decoration: BoxDecoration(
                                        border: Border.all(
                                          color: Colors.amber,
                                          width: 3,
                                        ),
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
                Text(
                  'Label reading rotation: ${(selected['rotation_quarter_turns'] as int) * 90}° clockwise. Source coordinates stay unchanged.',
                ),
                TextButton.icon(
                  onPressed: () => setState(
                    () => selected['rotation_quarter_turns'] =
                        ((selected['rotation_quarter_turns'] as int) + 1) % 4,
                  ),
                  icon: const Icon(Icons.rotate_right),
                  label: const Text('Rotate label reading 90 degrees'),
                ),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: ['Left x', 'Top y', 'Right x', 'Bottom y'].indexed
                      .map(
                        (e) => SizedBox(
                          width: 140,
                          child: TextFormField(
                            key: ValueKey(
                              '${selected['region_id']}-${e.$1}-$_coordinateVersion',
                            ),
                            initialValue: '${box[e.$1]}',
                            keyboardType: TextInputType.number,
                            decoration: InputDecoration(labelText: e.$2),
                            onChanged: (v) {
                              final coordinateKey =
                                  '${selected['region_id']}-${e.$1}';
                              final n = int.tryParse(v);
                              setState(() {
                                _coordinateSubmitAttempted = false;
                                if (n != null) {
                                  box[e.$1] = n;
                                  _invalidCoordinates.remove(coordinateKey);
                                } else {
                                  _invalidCoordinates.add(coordinateKey);
                                }
                              });
                            },
                          ),
                        ),
                      )
                      .toList(),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  children: [
                    TextButton.icon(
                      onPressed: () => setState(() {
                        final removed = _regions.removeAt(_selected);
                        _invalidCoordinates.removeWhere(
                          (key) => key.startsWith('${removed['region_id']}-'),
                        );
                        _selected = 0;
                      }),
                      icon: const Icon(Icons.delete_outline),
                      label: const Text('Delete region'),
                    ),
                    TextButton(
                      onPressed: _selected == 0
                          ? null
                          : () => setState(() {
                              final item = _regions.removeAt(_selected);
                              _regions.insert(--_selected, item);
                            }),
                      child: const Text('Move earlier'),
                    ),
                    TextButton(
                      onPressed: _selected >= _regions.length - 1
                          ? null
                          : () => setState(() {
                              final item = _regions.removeAt(_selected);
                              _regions.insert(++_selected, item);
                            }),
                      child: const Text('Move later'),
                    ),
                    TextButton(
                      onPressed: _selected >= _regions.length - 1
                          ? null
                          : () => setState(() {
                              final removed = _regions.removeAt(_selected + 1);
                              _invalidCoordinates.removeWhere(
                                (key) =>
                                    key.startsWith('${removed['region_id']}-'),
                              );
                              final next = removed['bbox'] as List<num>;
                              _coordinateVersion++;
                              selected['bbox'] = [
                                box[0] < next[0] ? box[0] : next[0],
                                box[1] < next[1] ? box[1] : next[1],
                                box[2] > next[2] ? box[2] : next[2],
                                box[3] > next[3] ? box[3] : next[3],
                              ];
                            }),
                      child: const Text('Merge with next'),
                    ),
                  ],
                ),
              ],
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  onPressed: _add,
                  icon: const Icon(Icons.add),
                  label: const Text('Add label region'),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _reason,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Reason for segmentation correction',
                ),
              ),
              if (_visibleError != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(_visibleError!),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            if (_invalidCoordinates.isNotEmpty) {
              setState(() => _coordinateSubmitAttempted = true);
              return;
            }
            final width = (widget.asset['width'] as num?)?.toDouble() ?? 0;
            final height = (widget.asset['height'] as num?)?.toDouble() ?? 0;
            if (_reason.text.trim().isEmpty) {
              setState(() => _error = 'A reason is required.');
              return;
            }
            for (final r in _regions) {
              final b = r['bbox'] as List<num>;
              if (b.any((v) => !v.isFinite) ||
                  b[0] < 0 ||
                  b[1] < 0 ||
                  b[2] <= b[0] ||
                  b[3] <= b[1] ||
                  b[2] > width ||
                  b[3] > height) {
                setState(
                  () => _error =
                      'Each region must have positive area and fit inside the original image.',
                );
                return;
              }
            }
            Navigator.pop(context, <String, dynamic>{
              'kind': 'segmentation_correction',
              'reason': _reason.text.trim(),
              'regions': _regions.indexed
                  .map((e) => {...e.$2, 'order': e.$1})
                  .toList(),
            });
          },
          child: const Text('Save region version'),
        ),
      ],
    );
  }
}
