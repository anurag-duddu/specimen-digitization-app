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
    this.loadHistoricalRevision,
  });
  final Specimen specimen;
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
            '${labelOf(kind)}${target == null ? '' : ': ${labelOf(target)}'}',
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
                    const Text(
                      'Creates a versioned decision. The server reruns affected checks and determines the queue.',
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
                                    child: Text(labelOf(s)),
                                  ),
                                )
                                .toList(),
                        onChanged: (s) =>
                            setDialogState(() => selectedState = s!),
                      ),
                    const SizedBox(height: 16),
                    if (kind == 'transcription_adjudication')
                      const Text(
                        'Choose an unresolved state when the source cannot support a reading. Independent observations remain unchanged and clearance stays blocked.',
                      ),
                    TextFormField(
                      controller: value,
                      minLines: 2,
                      maxLines: 6,
                      decoration: InputDecoration(
                        labelText: kind == 'segmentation_correction'
                            ? 'Regions JSON (original pixel coordinates)'
                            : 'Literal source value',
                        helperText: selectedState == 'supported'
                            ? 'Preserve literal text; do not fill missing evidence.'
                            : 'Absence is recorded as a state, not a fabricated value.',
                      ),
                      validator: (s) {
                        if (selectedState == 'supported' &&
                            (s == null || s.trim().isEmpty)) {
                          return 'Provide supported content or choose an absence state.';
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
                        decoration: const InputDecoration(
                          labelText: 'Parsed value (separate from literal)',
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextFormField(
                        controller: normalized,
                        decoration: const InputDecoration(
                          labelText: 'Normalized candidate (requires evidence)',
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextFormField(
                        controller: authority,
                        decoration: const InputDecoration(
                          labelText: 'Authority identifier (source-qualified)',
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],
                    TextFormField(
                      controller: evidence,
                      decoration: const InputDecoration(
                        labelText: 'Source / evidence IDs',
                        helperText: 'Comma-separated IDs from this specimen',
                      ),
                      validator: (s) =>
                          (kind == 'field_correction' ||
                                  kind == 'transcription_adjudication') &&
                              selectedState == 'supported' &&
                              (s == null || s.trim().isEmpty)
                          ? 'Link the supporting source evidence.'
                          : null,
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: reason,
                      minLines: 2,
                      maxLines: 4,
                      decoration: const InputDecoration(
                        labelText: 'Reason for decision',
                      ),
                      validator: (s) => s == null || s.trim().isEmpty
                          ? 'A reason is required.'
                          : null,
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
              child: const Text('Save and revalidate'),
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

  Future<void> _confirm(String kind, String title) async {
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
                'This records your review. All evidence and validation gates still apply; the server determines clearance.',
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: reason,
                minLines: 2,
                maxLines: 4,
                decoration: const InputDecoration(labelText: 'Review reason'),
                validator: (v) => v == null || v.trim().isEmpty
                    ? 'A reason is required.'
                    : null,
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
            child: const Text('Record review'),
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
        const Text(
          'Legacy source has no verified orientation derivative. Preview orientation may differ from original coordinates; region correction and overlays require a verified derivative.',
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
            child: const Text('Whole image'),
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
        'SHA-256: ${textOf(asset['sha256'])}',
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
        'Pan, pinch, or use zoom controls. View rotation does not alter the original.',
      ),
    ]);
  }

  Widget _readings() {
    final observations = widget.specimen.observations;
    final reference =
        observations.firstOrNull?['literal_text']?.toString() ?? '';
    Widget observation(Json o) {
      final literal = textOf(o['literal_text'], textOf(o['verbatim_text']));
      final differs = literal != reference;
      final referenceRunes = reference.runes.toList();
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
                    ? '≠ Differs from the first reading'
                    : 'Independent observation',
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
                  label: 'Read raw observation',
                  load: () => widget.loadArtifact!(
                    ArtifactRequest(
                      ArtifactKind.observationRaw,
                      textOf(o['id'], textOf(o['observation_id'])),
                      sha256: o['raw_sha256'] as String?,
                    ),
                  ),
                  render: (raw) => EvidenceDetails(
                    title: 'Raw observation response',
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
              ExpansionTile(
                title: const Text(
                  'Observation provenance and raw response reference',
                ),
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
        _section('Independent readings', [
          const Text(
            'Each observation is retained unchanged. Short readings show differing characters underlined; use the retained comparison for exact alignment and limits.',
          ),
          const SizedBox(height: 12),
          if (observations.isEmpty)
            const Text('No independent observations recorded yet.'),
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
        _section('Disagreements & adjudication', [
          if (widget.loadArtifact != null)
            for (final d in objects(
              objectOf(widget.specimen.data['run'])['disagreements'],
            ))
              LazyEvidence(
                key: ValueKey(
                  'alignment:${widget.specimen.id}:${widget.specimen.revision}:${d['region_id']}',
                ),
                label: 'Read comparison for region ${d['region_id']}',
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
            const Text(
              'No disagreement details recorded. This does not establish label coverage.',
            ),
          ...objects(widget.specimen.data['transcriptions']).map(
            (t) => ExpansionTile(
              title: Text(
                t['resolved'] == true
                    ? 'Adjudicated literal transcription'
                    : 'Unresolved literal transcription',
              ),
              subtitle: Text(textOf(t['verbatim_text'], textOf(t['text']))),
              children: [
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
            label: const Text('Adjudicate literal transcription'),
          ),
        ]),
      ],
    );
  }

  Widget _fields() => Column(
    children: [
      _section('Required fields & validation', [
        const Text(
          'Literal text, candidates, resolved values and authority evidence are separate. Missing mandatory values block clearance.',
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
            child: Text(
              'No extracted fields recorded. Required-field validation has not been demonstrated.',
            ),
          ),
        ...widget.specimen.fields.map(
          (f) => ExpansionTile(
            title: Text(
              '${textOf(f['display_name'], textOf(f['field_key']))}${f['required'] == true ? ' *' : ''}',
            ),
            subtitle: Text(
              '${labelOf(textOf(f['state'], 'unknown'))} · ${textOf(f['resolved_value'], 'No resolved value')}',
            ),
            children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (!knownFieldStates.contains(f['state']))
                      const Text(
                        'Unsupported field state. Editing is disabled; refresh or update the client.',
                      ),
                    Text('Literal: ${textOf(f['literal_value'])}'),
                    Text('Parsed: ${textOf(f['parsed_value'])}'),
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
      _section('Authority evidence & lookups', [
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
      final wide = constraints.maxWidth >= 1000;
      final content = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _section('Record status', [
            Text(s.status, style: Theme.of(context).textTheme.headlineSmall),
            Text('Profile ${s.profile} · Revision ${s.revision}'),
            if (s.data['run'] is Map)
              Text(
                'Stage: ${labelOf(textOf(s.data['stage']))} · Attempts: ${textOf(s.data['run']['attempts'], 'None recorded')}',
              ),
            if (s.data['run'] is Map && s.data['run']['next_retry_at'] != null)
              Text('Next retry: ${s.data['run']['next_retry_at']}'),
            if (s.data['run'] is Map && s.data['run']['dead_letter'] == true)
              Text(
                'Automatic retries stopped: ${textOf(s.data['blocker'], 'retry limit reached')}. Request a checkpoint retry after resolving the cause.',
              ),
            if (s.data['reason_codes'] is List)
              ...List<String>.from(s.data['reason_codes']).map(
                (r) => Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text('• ${labelOf(r)}'),
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
                          'Confirm all labels are covered',
                        ),
                  child: const Text('Confirm label coverage'),
                ),
                FilledButton.tonal(
                  onPressed: _blocked('approve')
                      ? null
                      : () =>
                            _confirm('approve', 'Record human review approval'),
                  child: const Text('Record review approval'),
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
                                    const Text(
                                      'This request may already have executed. Reconcile the unknown external outcome before explicitly requesting another attempt.',
                                    ),
                                  TextField(
                                    controller: controller,
                                    decoration: const InputDecoration(
                                      labelText: 'Reason for retry',
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
                                  child: const Text('Request retry'),
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
            children: ['Readings', 'Fields & evidence', 'History'].indexed
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
