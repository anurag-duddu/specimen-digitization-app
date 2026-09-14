import 'dart:convert';
import 'package:flutter/material.dart';
import 'models.dart';
import 'region_editor.dart';
import 'audit_history.dart';
import 'review_context.dart';
import 'operational_panel.dart';
import 'evidence_panel.dart';
import 'reading_alignment.dart';
import 'source_pixels.dart';
import 'large_record.dart';
import 'reading_declarations.dart';
import 'risk_assessment.dart';
import 'vocabulary.dart';
import 'widgets/caveat_text.dart';

class ReviewWorkbench extends StatefulWidget {
  const ReviewWorkbench({
    super.key,
    required this.specimen,
    required this.onChange,
    required this.onRetry,
    required this.onRefresh,
    this.busy = false,
    this.collections = const [],
    this.canReview = true,
    this.canOperate = true,
    this.loadHistoryPage,
    this.loadArtifact,
    this.loadHistoricalArtifact,
    this.loadHistoricalRevision,
  });
  final Specimen specimen;
  final Future<Json> Function(Specimen, ArtifactRequest)?
  loadHistoricalArtifact;
  final Future<Json> Function(ArtifactRequest)? loadArtifact;
  final Future<void> Function(Json change) onChange;
  final Future<void> Function(String reason) onRetry;
  final VoidCallback onRefresh;
  final bool busy;
  final List<CollectionScope> collections;
  final bool canReview;
  final bool canOperate;
  final Future<HistoryPage> Function(int afterRevision, int throughRevision)?
  loadHistoryPage;
  final Future<Specimen> Function(
    int revision,
    String? runId,
    String? runSha256,
  )?
  loadHistoricalRevision;
  @override
  State<ReviewWorkbench> createState() => _ReviewWorkbenchState();
}

class _ReviewWorkbenchState extends State<ReviewWorkbench> {
  bool get _reviewBlocked => widget.busy || !widget.canReview;
  bool _blocked(String action) =>
      _reviewBlocked ||
      !(widget.specimen.data['available_actions'] as List? ?? []).contains(
        action,
      );
  bool get _retryBlocked =>
      widget.busy ||
      (DateTime.tryParse(
            textOf(objectOf(widget.specimen.data['run'])['lease_until'], ''),
          )?.isAfter(DateTime.now()) ??
          false) ||
      !widget.canOperate ||
      !(widget.specimen.data['available_actions'] as List? ?? []).contains(
        'retry',
      );
  int _tab = 0;
  int _rotation = 0;
  String? _region;
  final _transform = TransformationController();
  @override
  void didUpdateWidget(covariant ReviewWorkbench oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.specimen.data['active_run_id'] !=
            widget.specimen.data['active_run_id'] ||
        (_region != null &&
            !widget.specimen.regions.any((r) => r['region_id'] == _region))) {
      _region = null;
      _rotation = 0;
      _transform.value = Matrix4.identity();
    }
  }

  @override
  void dispose() {
    _transform.dispose();
    super.dispose();
  }

  Future<void> _edit({
    required String kind,
    String? target,
    String initial = '',
    String state = 'supported',
  }) async {
    if (!knownFieldStates.contains(state) || _reviewBlocked) return;
    final value = TextEditingController(text: initial);
    final field = widget.specimen.fields
        .where((f) => f['field_key'] == target)
        .firstOrNull;
    final parsed = TextEditingController(text: textOf(field?['parsed'], ''));
    final normalized = TextEditingController(
      text: textOf(field?['normalized'], ''),
    );
    final authority = TextEditingController(
      text: textOf(field?['authority_id'], ''),
    );
    final reason = TextEditingController();
    final evidence = TextEditingController();
    final form = GlobalKey<FormState>();
    var selectedState = state;
    final result = await showDialog<Json>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(
            '${vocabularyLabel(kind)}${target == null ? '' : ': ${vocabularyLabel(target)}'}',
          ),
          content: SizedBox(
            width: 520,
            child: Form(
              key: form,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'Saving records a decision on version '
                      '${widget.specimen.revision} and reruns the affected '
                      'checks. The server decides the queue.',
                    ),
                    const SizedBox(height: 16),
                    if (kind == 'field_correction' ||
                        kind == 'transcription_adjudication')
                      DropdownButtonFormField<String>(
                        initialValue: selectedState,
                        decoration: const InputDecoration(
                          labelText: 'Evidence state',
                        ),
                        items:
                            [
                                  'supported',
                                  'unknown',
                                  'unreadable',
                                  'ambiguous',
                                  'not_present',
                                  'not_applicable',
                                  'unresolved',
                                ]
                                .where(
                                  (s) =>
                                      kind != 'transcription_adjudication' ||
                                      s != 'not_applicable',
                                )
                                .map(
                                  (s) => DropdownMenuItem(
                                    value: s,
                                    child: Text(vocabularyLabel(s)),
                                  ),
                                )
                                .toList(),
                        onChanged: (s) =>
                            setDialogState(() => selectedState = s!),
                      ),
                    const SizedBox(height: 16),
                    if (kind == 'transcription_adjudication')
                      const CaveatText(
                        label:
                            'Choose an unresolved state if the source does not '
                            'support a reading.',
                        why:
                            'Both readings are kept unchanged. The record stays '
                            'blocked from clearance.',
                      ),
                    TextFormField(
                      controller: value,
                      minLines: 2,
                      maxLines: 6,
                      decoration: InputDecoration(
                        labelText: kind == 'segmentation_correction'
                            ? 'Regions JSON (original pixel coordinates)'
                            : 'Value as written',
                        helperText: selectedState == 'supported'
                            ? 'Keep the text exactly as written, and do not add missing evidence.'
                            : 'Absence is recorded as a state, never as a made-up value.',
                      ),
                      validator: (s) {
                        if (selectedState == 'supported' &&
                            (s == null || s.trim().isEmpty)) {
                          return 'Enter the supported value, or choose an absence state.';
                        }
                        if (kind == 'segmentation_correction') {
                          try {
                            if (jsonDecode(s!) is! List) {
                              return 'Enter a JSON array of regions.';
                            }
                          } catch (_) {
                            return 'Enter valid JSON.';
                          }
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),
                    if (kind == 'field_correction') ...[
                      TextFormField(
                        controller: parsed,
                        decoration: const InputDecoration(labelText: 'Read as'),
                      ),
                      const SizedBox(height: 12),
                      TextFormField(
                        controller: normalized,
                        decoration: const InputDecoration(
                          labelText: 'Standardized (needs evidence)',
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextFormField(
                        controller: authority,
                        decoration: const InputDecoration(
                          labelText: 'Authority identifier',
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],
                    TextFormField(
                      controller: evidence,
                      decoration: const InputDecoration(
                        labelText: 'Evidence IDs',
                        helperText: 'Comma-separated IDs from this specimen',
                      ),
                      validator: (s) =>
                          (kind == 'field_correction' ||
                                  kind == 'transcription_adjudication') &&
                              selectedState == 'supported' &&
                              (s == null || s.trim().isEmpty)
                          ? 'Enter the evidence IDs that support this value.'
                          : null,
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: reason,
                      minLines: 2,
                      maxLines: 4,
                      decoration: const InputDecoration(
                        labelText: 'Reason',
                        helperText: reasonHelperText,
                      ),
                      validator: (s) =>
                          s == null || s.trim().isEmpty ? reasonRequired : null,
                    ),
                  ],
                ),
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
                if (form.currentState!.validate()) {
                  Navigator.pop(context, <String, dynamic>{
                    'kind': kind,
                    'target_id': target,
                    'value': selectedState == 'supported' ? value.text : null,
                    'state': selectedState,
                    'parsed':
                        selectedState == 'supported' && parsed.text.isNotEmpty
                        ? parsed.text
                        : null,
                    'normalized':
                        selectedState == 'supported' &&
                            normalized.text.isNotEmpty
                        ? normalized.text
                        : null,
                    'authority_id':
                        selectedState == 'supported' &&
                            authority.text.isNotEmpty
                        ? authority.text
                        : null,
                    'reason': reason.text.trim(),
                    'evidence_ids': evidence.text
                        .split(',')
                        .map((s) => s.trim())
                        .where((s) => s.isNotEmpty)
                        .toList(),
                    if (kind == 'segmentation_correction')
                      'regions': jsonDecode(value.text),
                  });
                }
              },
              child: const Text('Save correction'),
            ),
          ],
        ),
      ),
    );
    // Dialog exit transitions may still reference controllers; dispose on the next frame.
    await Future<void>.delayed(const Duration(milliseconds: 250));
    value.dispose();
    parsed.dispose();
    normalized.dispose();
    authority.dispose();
    reason.dispose();
    evidence.dispose();
    if (result != null && mounted) await widget.onChange(result);
  }

  Future<void> _classification() async {
    final scope = widget.collections
        .where((c) => c.collectionId == widget.specimen.data['collection_id'])
        .firstOrNull;
    if (scope == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Collection configuration is unavailable. Refresh collection access.',
          ),
        ),
      );
      return;
    }
    final result = await showDialog<Json>(
      context: context,
      builder: (_) =>
          ClassificationDialog(specimen: widget.specimen, scope: scope),
    );
    if (result != null && mounted) await widget.onChange(result);
  }

  Future<void> _confirm(String kind, String title, String action) async {
    final reason = TextEditingController();
    final form = GlobalKey<FormState>();
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Form(
          key: form,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'All evidence and validation checks still apply. The server '
                'decides clearance.',
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: reason,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(
                  labelText: 'Reason',
                  helperText: reasonHelperText,
                ),
                validator: (v) =>
                    v == null || v.trim().isEmpty ? reasonRequired : null,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (form.currentState!.validate()) {
                Navigator.pop(context, reason.text.trim());
              }
            },
            child: Text(action),
          ),
        ],
      ),
    );
    if (result != null && mounted) {
      await widget.onChange({'kind': kind, 'reason': result});
    }
  }

  Widget _section(String title, List<Widget> children) => Card(
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    ),
  );

  Widget _record(Json data) => SelectableText(
    const JsonEncoder.withIndent('  ').convert(data),
    style: Theme.of(
      context,
    ).textTheme.bodySmall?.copyWith(fontFamily: 'monospace'),
  );

  Widget _source() {
    final specimen = widget.specimen;
    final asset = specimen.assets.isEmpty
        ? <String, dynamic>{}
        : specimen.assets.first;
    final legacyOrientation =
        asset['media_type'] != null && asset['preview_is_derivative'] != true;
    final selected = (legacyOrientation ? <Json>[] : specimen.regions)
        .where((r) => r['region_id'] == _region)
        .firstOrNull;
    final crop = (selected?['bbox'] as List?)?.cast<num>();
    final width = (asset['width'] as num?)?.toDouble() ?? 1;
    final height = (asset['height'] as num?)?.toDouble() ?? 1;
    return _section('Source image', [
      if (legacyOrientation)
        const CaveatText(
          label:
              'This image has no verified orientation, so region editing is '
              'unavailable.',
          why:
              'The preview may be rotated differently from the original '
              'coordinates. Region correction needs a verified orientation.',
        ),
      Wrap(
        spacing: 8,
        children: [
          IconButton(
            tooltip: 'Rotate view 90 degrees',
            onPressed: () => setState(() => _rotation++),
            icon: const Icon(Icons.rotate_right),
          ),
          IconButton(
            tooltip: 'Zoom in',
            onPressed: () {
              _transform.value = _transform.value.clone()
                ..scaleByDouble(1.3, 1.3, 1, 1);
            },
            icon: const Icon(Icons.zoom_in),
          ),
          IconButton(
            tooltip: 'Reset image view',
            onPressed: () {
              _transform.value = Matrix4.identity();
              setState(() => _rotation = 0);
            },
            icon: const Icon(Icons.fit_screen),
          ),
          TextButton(
            onPressed: () => setState(() => _region = null),
            child: const Text('Show whole image'),
          ),
        ],
      ),
      Container(
        height: 380,
        color: const Color(0xffe7ebe7),
        child: asset['preview_bytes'] == null
            ? const Center(
                child: Text(
                  'Preview unavailable. Refresh to renew source access.',
                ),
              )
            : ClipRect(
                child: InteractiveViewer(
                  transformationController: _transform,
                  minScale: .2,
                  maxScale: 12,
                  child: Center(
                    child: RotatedBox(
                      quarterTurns:
                          _rotation +
                          (crop == null
                              ? 0
                              : (selected?['rotation_quarter_turns'] as int? ??
                                    0)),
                      child: AspectRatio(
                        aspectRatio: crop == null
                            ? width / height
                            : (crop[2] - crop[0]) / (crop[3] - crop[1]),
                        child: Stack(
                          fit: StackFit.expand,
                          children: [
                            if (crop != null)
                              FittedBox(
                                fit: BoxFit.contain,
                                child: SizedBox(
                                  width: (crop[2] - crop[0]).toDouble(),
                                  height: (crop[3] - crop[1]).toDouble(),
                                  child: ClipRect(
                                    child: Stack(
                                      children: [
                                        Positioned(
                                          left: -crop[0].toDouble(),
                                          top: -crop[1].toDouble(),
                                          width: width,
                                          height: height,
                                          child: SourcePixels(
                                            asset: asset,
                                            semanticLabel:
                                                'Source pixels for selected label region',
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              )
                            else
                              SourcePixels(
                                asset: asset,
                                semanticLabel:
                                    'Immutable original specimen image',
                              ),
                            if (_region == null && !legacyOrientation)
                              ...specimen.regions.map((r) {
                                final box = (r['bbox'] as List?)?.cast<num>();
                                if (box == null || box.length != 4) {
                                  return const SizedBox.shrink();
                                }
                                return LayoutBuilder(
                                  builder: (context, c) => Stack(
                                    children: [
                                      Positioned(
                                        left: box[0] / width * c.maxWidth,
                                        top: box[1] / height * c.maxHeight,
                                        width:
                                            (box[2] - box[0]) /
                                            width *
                                            c.maxWidth,
                                        height:
                                            (box[3] - box[1]) /
                                            height *
                                            c.maxHeight,
                                        child: Semantics(
                                          label:
                                              'Label region ${r['region_id']}',
                                          button: true,
                                          child: InkWell(
                                            onTap: () => setState(
                                              () => _region = r['region_id']
                                                  .toString(),
                                            ),
                                            child: Container(
                                              decoration: BoxDecoration(
                                                border: Border.all(
                                                  color: Colors.amber,
                                                  width: 3,
                                                ),
                                              ),
                                              child: Align(
                                                alignment: Alignment.topLeft,
                                                child: Container(
                                                  color: Colors.black87,
                                                  child: Text(
                                                    textOf(r['region_id']),
                                                    style: const TextStyle(
                                                      color: Colors.white,
                                                    ),
                                                  ),
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                );
                              }),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
      ),
      const SizedBox(height: 12),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: specimen.regions
            .map(
              (r) => ChoiceChip(
                label: Text(
                  'Label ${specimen.regions.indexWhere((item) => item['region_id'] == r['region_id']) + 1}',
                ),
                selected: _region == r['region_id'],
                onSelected: (_) => setState(() {
                  _region = r['region_id'].toString();
                  _transform.value = Matrix4.identity();
                }),
              ),
            )
            .toList(),
      ),
      const SizedBox(height: 12),
      SourceBasisNotice(asset: asset),
      Text('Asset: ${textOf(asset['asset_id'])}'),
      SelectableText(
        'Checksum (SHA-256): ${textOf(asset['sha256'])}',
        style: Theme.of(context).textTheme.bodySmall,
      ),
      TextButton.icon(
        onPressed: legacyOrientation || _blocked('regions')
            ? null
            : () async {
                final result = await showDialog<Json>(
                  context: context,
                  builder: (context) =>
                      RegionEditor(regions: specimen.regions, asset: asset),
                );
                if (result != null && mounted) await widget.onChange(result);
              },
        icon: const Icon(Icons.crop),
        label: const Text('Correct label regions'),
      ),
      const Text(
        'Pan, pinch or use the zoom controls. Rotating the view does not '
        'change the original.',
      ),
    ]);
  }

  Widget _readings() {
    final observations = widget.specimen.observations;
    String literalOf(Json o) =>
        textOf(o['literal_text'], textOf(o['verbatim_text']));
    final references = <String, String>{};
    for (final o in observations) {
      final region = o['region_id'];
      if (region is String && region.trim().isNotEmpty) {
        references.putIfAbsent(region, () => literalOf(o));
      }
    }
    Widget observation(Json o) {
      final literal = literalOf(o);
      final reference = references[o['region_id']];
      final differs = reference != null && literal != reference;
      final referenceRunes = reference?.runes.toList() ?? const <int>[];
      return Card.outlined(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                textOf(o['model_id']),
                style: Theme.of(context).textTheme.titleSmall,
              ),
              const SizedBox(height: 8),
              Text(
                differs
                    ? 'Differs from the first reading for this label'
                    : 'Independent reading',
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              SelectionArea(
                child: Text.rich(
                  TextSpan(
                    children: literal.length > 4000
                        ? [TextSpan(text: literal)]
                        : literal.runes.indexed
                              .map(
                                (e) => TextSpan(
                                  text: String.fromCharCode(e.$2),
                                  style:
                                      differs &&
                                          (e.$1 >= referenceRunes.length ||
                                              referenceRunes[e.$1] != e.$2)
                                      ? const TextStyle(
                                          decoration: TextDecoration.underline,
                                          fontWeight: FontWeight.w700,
                                          backgroundColor: Color(0xffffe7a3),
                                        )
                                      : null,
                                ),
                              )
                              .toList(),
                  ),
                ),
              ),
              if (widget.loadArtifact != null && o['raw_ref'] != null)
                LazyEvidence(
                  key: ValueKey(
                    'raw:${widget.specimen.id}:${widget.specimen.revision}:${o['id']}',
                  ),
                  label: 'Read raw reading',
                  load: () => widget.loadArtifact!(
                    ArtifactRequest(
                      ArtifactKind.observationRaw,
                      textOf(o['id'], textOf(o['observation_id'])),
                      sha256: o['raw_sha256'] as String?,
                    ),
                  ),
                  render: (raw) => EvidenceDetails(
                    title: 'Raw reading response',
                    value: raw,
                  ),
                ),
              if (widget.loadArtifact != null &&
                  objectOf(
                        objectOf(
                          widget.specimen.data['run'],
                        )['reading_metadata'],
                      )[o['id']] !=
                      null)
                LazyEvidence(
                  key: ValueKey(
                    'metadata:${widget.specimen.id}:${widget.specimen.revision}:${o['id']}',
                  ),
                  label: 'Read language and script metadata',
                  load: () => widget.loadArtifact!(
                    ArtifactRequest(
                      ArtifactKind.readingMetadata,
                      textOf(o['id']),
                    ),
                  ),
                  render: (metadata) => ReadingMetadataView(metadata: metadata),
                ),
              if (widget.loadArtifact != null &&
                  o['declaration_evidence'] is Map)
                LazyEvidence(
                  key: ValueKey(
                    'declaration:${widget.specimen.id}:${widget.specimen.revision}:${o['id']}',
                  ),
                  label: 'Read declaration provenance',
                  load: () => widget.loadArtifact!(
                    ArtifactRequest(
                      ArtifactKind.readingDeclarations,
                      textOf(o['id']),
                    ),
                  ),
                  render: (value) => ReadingDeclarationView(
                    provenance: value,
                    onChange: _blocked('reading_metadata')
                        ? null
                        : widget.onChange,
                  ),
                ),
              if (o.containsKey('latency_seconds') ||
                  o.containsKey('completion_state'))
                ObservationExecutionDetails(observation: o),
              ExpansionTile(
                title: const Text('Reading provenance and raw response'),
                children: [
                  Padding(padding: const EdgeInsets.all(12), child: _record(o)),
                ],
              ),
            ],
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (objectOf(widget.specimen.data['run'])['label_language_handling']
            is Map)
          LabelLanguagePolicy(
            handling: objectOf(
              objectOf(widget.specimen.data['run'])['label_language_handling'],
            ),
          ),
        _section('Independent readings', [
          const Text(
            'Each reading is kept unchanged. Short readings underline the '
            'characters that differ.',
          ),
          Text(
            'Use the saved comparison for exact alignment and its limits.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          if (observations.isEmpty)
            const Text('No independent readings recorded yet.'),
          LayoutBuilder(
            builder: (context, c) => Wrap(
              spacing: 8,
              runSpacing: 8,
              children: observations
                  .map(
                    (o) => SizedBox(
                      width: c.maxWidth >= 520
                          ? (c.maxWidth - 8) / 2
                          : c.maxWidth,
                      child: observation(o),
                    ),
                  )
                  .toList(),
            ),
          ),
        ]),
        _section('Differences and resolution', [
          if (widget.loadArtifact != null)
            for (final d in objects(
              objectOf(widget.specimen.data['run'])['disagreements'],
            ))
              LazyEvidence(
                key: ValueKey(
                  'alignment:${widget.specimen.id}:${widget.specimen.revision}:${d['region_id']}',
                ),
                label: 'Read comparison for label ${d['region_id']}',
                load: () => widget.loadArtifact!(
                  ArtifactRequest(
                    ArtifactKind.disagreement,
                    textOf(d['region_id']),
                  ),
                ),
                render: (alignment) {
                  String? retained(String side) =>
                      observations
                              .where(
                                (o) =>
                                    o['id'] ==
                                    objectOf(alignment[side])['observation_id'],
                              )
                              .firstOrNull?['literal_text']
                          as String?;
                  return ReadingAlignmentView(
                    alignment: alignment,
                    leftText: retained('left'),
                    rightText: retained('right'),
                  );
                },
              ),
          ...objects(widget.specimen.data['disagreements']).map(
            (d) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: _record(d),
            ),
          ),
          if (objects(widget.specimen.data['disagreements']).isEmpty)
            const CaveatText(
              label: 'No differences recorded between the readings.',
              why:
                  'Agreement between readings does not mean every label was '
                  'found.',
            ),
          ...objects(widget.specimen.data['transcriptions']).map(
            (t) => ExpansionTile(
              title: Text(
                t['resolved'] == true
                    ? 'Resolved transcription'
                    : 'Unresolved transcription',
              ),
              subtitle: Text(textOf(t['verbatim_text'], textOf(t['text']))),
              children: [
                if (t.containsKey('alignment_status'))
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: TranscriptionComparisonSummary(transcription: t),
                  ),
                Padding(padding: const EdgeInsets.all(12), child: _record(t)),
              ],
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.tonalIcon(
            onPressed:
                _blocked('transcription') || widget.specimen.regions.isEmpty
                ? null
                : () => _edit(
                    kind: 'transcription_adjudication',
                    target:
                        _region ?? widget.specimen.regions.first['region_id'],
                  ),
            icon: const Icon(Icons.edit_note),
            label: const Text('Resolve reading'),
          ),
        ]),
      ],
    );
  }

  Widget _fields() => Column(
    children: [
      _section('Required fields and checks', [
        const Text(
          'As written, read as, standardized and authority values are recorded '
          'separately.',
        ),
        Text(
          'Missing required values block clearance.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        ...widget.specimen.findings.map(
          (f) => ListTile(
            leading: const Icon(Icons.rule),
            title: Text(textOf(f['message'], textOf(f['reason_code']))),
            subtitle: Text(
              '${textOf(f['field_key'], 'Record')} · ${textOf(f['severity'])} · ${textOf(f['rule_id'])}',
            ),
          ),
        ),
        if (widget.specimen.fields.isEmpty)
          const Padding(
            padding: EdgeInsets.all(12),
            child: CaveatText(
              label: 'No fields recorded yet.',
              why: 'Required-field checks have not run for this record.',
            ),
          ),
        ...widget.specimen.fields.map(
          (f) => ExpansionTile(
            title: Text(
              '${textOf(f['display_name'], textOf(f['field_key']))}${f['required'] == true ? ' *' : ''}',
            ),
            subtitle: Text(
              '${vocabularyLabel(textOf(f['state'], 'unknown'))} · ${textOf(f['resolved_value'], 'Not resolved')}',
            ),
            children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (!knownFieldStates.contains(f['state']))
                      const CaveatText(
                        label:
                            'This field cannot be edited in this version of the '
                            'app.',
                        why:
                            'The server sent a field state this app does not '
                            'recognize. Refreshing may help. Otherwise update the '
                            'app.',
                      ),
                    Text('As written: ${textOf(f['literal_value'])}'),
                    Text('Read as: ${textOf(f['parsed_value'])}'),
                    const SizedBox(height: 8),
                    _record(f),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        onPressed:
                            _blocked('field') ||
                                !knownFieldStates.contains(f['state'])
                            ? null
                            : () => _edit(
                                kind: 'field_correction',
                                target: f['field_key'].toString(),
                                initial: textOf(f['literal_value'], ''),
                                state: textOf(f['state'], 'unknown'),
                              ),
                        icon: const Icon(Icons.edit_outlined),
                        label: const Text('Correct supported value'),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ]),
      _section('Authority evidence', [
        if (widget.specimen.evidence.isEmpty)
          const Text('No authority evidence recorded.'),
        ...widget.specimen.evidence.map(
          (e) => ExpansionTile(
            title: Text('${textOf(e['source'])} · ${textOf(e['outcome'])}'),
            subtitle: Text(textOf(e['evidence_id'])),
            children: [
              Padding(padding: const EdgeInsets.all(12), child: _record(e)),
            ],
          ),
        ),
      ]),
    ],
  );

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final s = widget.specimen;
      if (s.data['artifact_receipt'] is Map) {
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(s.title, style: Theme.of(context).textTheme.headlineSmall),
            Text('${s.status} · Version ${s.revision}'),
            TextButton(
              onPressed: widget.busy ? null : widget.onRefresh,
              child: const Text('Refresh current record'),
            ),
            LargeRecordEvidence(
              key: ValueKey('graph:${s.id}:${s.revision}'),
              specimen: s,
              load: widget.loadArtifact,
            ),
            OperationalPanel(
              specimen: s,
              canOperate: widget.canOperate,
              busy: widget.busy,
              onAction: widget.onChange,
            ),
            AuditHistoryPanel(
              key: ValueKey('history:${s.id}:${s.revision}'),
              specimen: s,
              loadPage: widget.loadHistoryPage,
              loadRevision: widget.loadHistoricalRevision,
              loadArtifact: widget.loadHistoricalArtifact,
            ),
          ],
        );
      }
      final wide = constraints.maxWidth >= 1000;
      final content = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _section('Record status', [
            Text(s.status, style: Theme.of(context).textTheme.headlineSmall),
            Text('Profile ${s.profile} · Version ${s.revision}'),
            if (s.data['run'] is Map)
              Text(
                'Step: ${vocabularyLabel(textOf(s.data['stage']))} · Attempts: ${textOf(s.data['run']['attempts'], 'None recorded')}',
              ),
            if (s.data['run'] is Map && s.data['run']['next_retry_at'] != null)
              Text('Next retry: ${s.data['run']['next_retry_at']}'),
            if (s.data['run'] is Map && s.data['run']['dead_letter'] == true)
              Text(
                'Automatic retries have stopped: ${vocabularyLabel(textOf(s.data['blocker'], 'retry limit reached'))}. Fix the cause, then retry from the checkpoint.',
              ),
            if (s.data['reason_codes'] is List)
              ...List<String>.from(s.data['reason_codes']).map(
                (r) => Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text('• ${vocabularyLabel(r)}'),
                ),
              ),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                OutlinedButton(
                  onPressed: _blocked('coverage')
                      ? null
                      : () => _confirm(
                          'coverage',
                          'Confirm coverage?',
                          'Confirm coverage',
                        ),
                  child: const Text('Confirm label coverage'),
                ),
                FilledButton.tonal(
                  onPressed: _blocked('approve')
                      ? null
                      : () => _confirm(
                          'approve',
                          'Approve record?',
                          'Approve record',
                        ),
                  child: const Text('Approve record'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            ...objects(s.data['issues']).map(_record),
            if (s.data['blocker'] != null)
              _record({'blocker': s.data['blocker']}),
            if (s.data['risk'] != null)
              _record({'review_risk': s.data['risk']}),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: _blocked('classification')
                      ? null
                      : _classification,
                  icon: const Icon(Icons.account_tree_outlined),
                  label: const Text('Correct classification'),
                ),
                OutlinedButton.icon(
                  onPressed: _retryBlocked
                      ? null
                      : () async {
                          final controller = TextEditingController();
                          final reason = await showDialog<String>(
                            context: context,
                            builder: (context) => AlertDialog(
                              title: const Text('Retry from checkpoint'),
                              content: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (textOf(
                                    objectOf(s.data['run'])['blocker'],
                                    '',
                                  ).contains('external_outcome_unknown'))
                                    const CaveatText(
                                      label:
                                          'The last request may already have run. '
                                          'Its result is unknown.',
                                      why:
                                          'Reconcile that request before you retry. '
                                          'This app never retries it for you.',
                                    ),
                                  TextField(
                                    controller: controller,
                                    decoration: const InputDecoration(
                                      labelText: 'Reason',
                                      helperText: reasonHelperText,
                                    ),
                                  ),
                                ],
                              ),
                              actions: [
                                TextButton(
                                  onPressed: () => Navigator.pop(context),
                                  child: const Text('Cancel'),
                                ),
                                FilledButton(
                                  onPressed: () {
                                    if (controller.text.trim().isNotEmpty) {
                                      Navigator.pop(
                                        context,
                                        controller.text.trim(),
                                      );
                                    }
                                  },
                                  child: const Text('Retry from checkpoint'),
                                ),
                              ],
                            ),
                          );
                          await Future<void>.delayed(
                            const Duration(milliseconds: 250),
                          );
                          controller.dispose();
                          if (reason != null && mounted) {
                            await widget.onRetry(reason);
                          }
                        },
                  icon: const Icon(Icons.replay),
                  label: const Text('Retry processing'),
                ),
              ],
            ),
          ]),
          ReviewContext(specimen: s),
          OperationalPanel(
            specimen: s,
            canOperate: widget.canOperate,
            busy: widget.busy,
            onAction: widget.onChange,
          ),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: ['Readings', 'Fields and evidence', 'History'].indexed
                .map(
                  (e) => ChoiceChip(
                    label: Text(e.$2),
                    selected: _tab == e.$1,
                    onSelected: (_) => setState(() => _tab = e.$1),
                  ),
                )
                .toList(),
          ),
          const SizedBox(height: 12),
          if (_tab == 0) _readings(),
          if (_tab == 1) ...[
            _fields(),
            if (widget.loadArtifact != null)
              EvidencePanel(
                key: ValueKey('evidence:${s.id}:${s.revision}'),
                specimen: s,
                load: widget.loadArtifact!,
                onChange: widget.onChange,
                canReview: !_blocked('authority_resolution'),
              ),
          ],
          if (_tab == 2)
            AuditHistoryPanel(
              key: ValueKey('${s.id}:${s.revision}'),
              specimen: s,
              loadPage: widget.loadHistoryPage,
              loadRevision: widget.loadHistoricalRevision,
              loadArtifact: widget.loadHistoricalArtifact,
            ),
        ],
      );
      return SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        s.title,
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      SelectableText(s.id),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: widget.busy ? null : widget.onRefresh,
                  tooltip: 'Refresh evidence',
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            const SizedBox(height: 16),
            if (wide)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: _source()),
                  const SizedBox(width: 16),
                  Expanded(child: content),
                ],
              )
            else ...[
              _source(),
              const SizedBox(height: 16),
              content,
            ],
          ],
        ),
      );
    },
  );
}
