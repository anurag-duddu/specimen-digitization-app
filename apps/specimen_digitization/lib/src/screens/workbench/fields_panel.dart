/// The fields segment (screen blueprints, 6.4).
///
/// One concise review row per field, with its value state and current value.
/// The value layers and retained evidence open on demand. Corrections happen
/// in place, with the photograph still on screen, and the correction joins a
/// pending set that is saved once with one reason rather than one modal round
/// trip per field (audit findings H6.2 and H7.2, both severity 4).
library;

import 'package:flutter/widgets.dart';
// The product's own `FieldLayer` is the three named slots of a record
// field; the package's is a primitive of the field control. The screen
// means the first, and the second is never built here.
import 'package:specimen_ui/specimen_ui.dart' hide FieldLayer;

import '../../models.dart';
import '../../research/research_models.dart';
import '../../review_context.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import 'blockers.dart';
import 'evidence_picker.dart';
import 'field_presentation.dart';
import 'pending_changes.dart';
import 'value_basis.dart';
import 'value_basis_chip.dart';

/// The record's fields, their evidence and their corrections.
class WorkbenchFields extends StatefulWidget {
  const WorkbenchFields({
    super.key,
    required this.specimen,
    required this.anchors,
    required this.pending,
    required this.onPendingChanged,
    this.onFocusRegion,
    this.fieldBlockedReason,
    this.issues = const <ClearanceBlocker>[],
    this.researchForField,
  });

  final Specimen specimen;

  /// One key per field, so the blockers list can scroll to the right row.
  final Map<String, GlobalKey> anchors;

  /// The corrections not yet sent.
  final List<PendingFieldChange> pending;

  /// Called with the new pending set.
  final ValueChanged<List<PendingFieldChange>> onPendingChanged;

  /// Points the source pane at the region the field was read from.
  final ValueChanged<String?>? onFocusRegion;

  /// Why correcting a field is unavailable, or null when it is not.
  final String? fieldBlockedReason;

  /// Human-readable review issues, attached to their corresponding field.
  final List<ClearanceBlocker> issues;

  /// Research for one field, revealed with that field's supporting evidence.
  /// The host owns loading, permissions and any actual research actions.
  final Widget Function(
    String fieldKey,
    ValueChanged<ResearchReviewCandidate>? onSelectCandidate,
  )?
  researchForField;

  @override
  State<WorkbenchFields> createState() => _WorkbenchFieldsState();
}

class _WorkbenchFieldsState extends State<WorkbenchFields> {
  String? _editing;
  FieldLayer _layer = FieldLayer.asWritten;

  @override
  void didUpdateWidget(covariant WorkbenchFields oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.specimen.id != widget.specimen.id) _editing = null;
  }

  PendingFieldChange? _pendingFor(String key) => widget.pending
      .where((PendingFieldChange p) => p.fieldKey == key)
      .firstOrNull;

  /// A specimen value may cite several labels, or no retained label.
  Set<String> _regionsFor(Json field, [PendingFieldChange? pending]) {
    final Set<String> regions = <String>{};
    void retain(Object? region) {
      if (region is String &&
          widget.specimen.regions.any((Json r) => r['region_id'] == region)) {
        regions.add(region);
      }
    }

    // Direct source locators remain useful even when no Evidence citation
    // was materialized. They are view links, never correction citations.
    if (pending == null) retain(field['source_region_id']);
    final List<Object?> ids =
        pending?.evidenceIds ??
        (field['evidence_ids'] as List?) ??
        const <Object?>[];
    for (final Object? id in ids) {
      final Json? item = widget.specimen.evidence
          .where((Json e) => e['evidence_id'] == id || e['id'] == id)
          .firstOrNull;
      retain(item?['region_id']);
    }
    if (pending != null && regions.isEmpty) retain(pending.regionId);
    return regions;
  }

  String? _regionFor(Json field, [PendingFieldChange? pending]) {
    final Set<String> regions = _regionsFor(field, pending);
    return regions.length == 1 ? regions.single : null;
  }

  String _sourcesFor(Json field, PendingFieldChange? pending) {
    final Set<String> regions = _regionsFor(field, pending);
    if (regions.isEmpty) {
      return 'No label source recorded';
    }
    final List<String> labels = <String>[
      for (final (int index, Json region) in widget.specimen.regions.indexed)
        if (regions.contains(region['region_id'])) 'Label ${index + 1}',
    ];
    return 'Sources: ${labels.join(', ')}';
  }

  void _startEdit(Json field, FieldLayer layer) {
    widget.onFocusRegion?.call(
      _regionFor(field, _pendingFor(field['field_key'].toString())),
    );
    setState(() {
      _editing = field['field_key'].toString();
      _layer = layer;
    });
  }

  void _commit(PendingFieldChange change) {
    final List<PendingFieldChange> next = <PendingFieldChange>[
      for (final PendingFieldChange p in widget.pending)
        if (p.fieldKey != change.fieldKey) p,
      change,
    ];
    widget.onPendingChanged(next);
    setState(() => _editing = null);
  }

  void _discard(String fieldKey) {
    widget.onPendingChanged(<PendingFieldChange>[
      for (final PendingFieldChange p in widget.pending)
        if (p.fieldKey != fieldKey) p,
    ]);
    setState(() => _editing = null);
  }

  void _stageResearchCandidate(
    String fieldKey,
    ResearchReviewCandidate candidate,
  ) {
    final selectionId = candidate.selectionId;
    final selectionValue = candidate.selectionValue;
    if (widget.fieldBlockedReason != null ||
        selectionId == null ||
        selectionId.isEmpty ||
        selectionValue == null ||
        selectionValue.isEmpty) {
      return;
    }
    final field = widget.specimen.fields
        .where((item) => item['field_key'] == fieldKey)
        .firstOrNull;
    if (field == null) return;
    widget.onPendingChanged(<PendingFieldChange>[
      for (final existing in widget.pending)
        if (existing.fieldKey != fieldKey) existing,
      PendingFieldChange(
        fieldKey: fieldKey,
        displayName: fieldReviewName(field),
        state: textOf(field['state'], 'unknown'),
        literal: field['literal_value'] as String?,
        parsed: field['parsed_value'] as String?,
        normalized: field['normalized'] as String?,
        authorityId: textOf(field['authority_id'], ''),
        evidenceIds: (field['evidence_ids'] as List? ?? const <Object?>[])
            .whereType<String>()
            .toList(),
        regionId: _regionFor(field),
        baseLiteral: field['literal_value'] as String?,
        baseFieldBasis: fieldBasis(field),
        candidateSelectionId: selectionId,
        candidateLabel: candidate.label,
        candidateValue: selectionValue,
      ),
    ]);
    setState(() => _editing = null);
  }

  List<ClearanceBlocker> _issuesFor(String key) {
    final supplied = widget.issues.where((issue) => issue.fieldKey == key);
    if (supplied.isNotEmpty) return supplied.toList();
    // Standalone panel consumers still get the same presentation adapter as
    // the workbench; raw findings never become primary field copy here.
    return blockersFor(
      widget.specimen,
    ).where((issue) => issue.fieldKey == key).toList();
  }

  bool _needsReview(Json field) => fieldNeedsReview(
    _pendingFor(field['field_key'].toString())?.state ??
        field['state'] as String?,
    hasIssues: _issuesFor(field['field_key'].toString()).isNotEmpty,
  );

  @override
  Widget build(BuildContext context) {
    final List<Json> fields = widget.specimen.fields;
    final groups = <String, List<Json>>{
      for (final group in fieldReviewGroups)
        group:
            fields.where((field) => fieldReviewGroup(field) == group).toList()
              ..sort((left, right) {
                final attention = (_needsReview(left) ? 0 : 1).compareTo(
                  _needsReview(right) ? 0 : 1,
                );
                if (attention != 0) return attention;
                final order = fieldReviewOrder(
                  left,
                ).compareTo(fieldReviewOrder(right));
                return order != 0
                    ? order
                    : fieldReviewName(left).compareTo(fieldReviewName(right));
              }),
    };
    final reviewCount = fields.where(_needsReview).length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (fields.isEmpty)
          const CaveatText(
            label: 'No fields recorded yet.',
            why: 'Required field checks have not run for this record.',
          )
        else ...<Widget>[
          Padding(
            padding: EdgeInsetsDirectional.fromSTEB(
              context.ui.space.s3,
              0,
              context.ui.space.s3,
              context.ui.space.s3,
            ),
            child: Text(
              reviewCount == 0
                  ? 'Open a field to inspect its value and evidence.'
                  : '${reviewCount == 1 ? '1 field needs' : '$reviewCount fields need'} review. Open a field to inspect its evidence or correct its value.',
              style: context.ui.type.bodySmall.copyWith(
                color: context.ui.color.inkSecondary,
              ),
            ),
          ),
          for (final entry in groups.entries)
            if (entry.value.isNotEmpty) ...<Widget>[
              _group(context, entry.key, entry.value),
              SizedBox(height: context.ui.space.s3),
            ],
        ],
      ],
    );
  }

  Widget _group(BuildContext context, String title, List<Json> fields) {
    final reviewCount = fields.where(_needsReview).length;
    return Column(
      key: ValueKey<String>('field-group:$title'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Padding(
          padding: EdgeInsetsDirectional.fromSTEB(
            context.ui.space.s3,
            0,
            context.ui.space.s3,
            context.ui.space.s1,
          ),
          child: Semantics(
            header: true,
            child: Wrap(
              spacing: context.ui.space.s2,
              runSpacing: context.ui.space.s1,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: <Widget>[
                Text(title, style: context.ui.type.label),
                if (reviewCount > 0)
                  Text(
                    '$reviewCount to review',
                    style: context.ui.type.labelSmall.copyWith(
                      color: context.ui.color.status.needsReview.content,
                    ),
                  ),
              ],
            ),
          ),
        ),
        for (final field in fields) _field(context, field),
      ],
    );
  }

  Widget _field(BuildContext context, Json field) {
    final String key = field['field_key'].toString();
    final PendingFieldChange? pending = _pendingFor(key);
    final GlobalKey? anchor = widget.anchors[key];
    final bool known = knownFieldStates.contains(field['state']);
    final String? blocked =
        widget.fieldBlockedReason ??
        (known
            ? null
            : 'The server sent a field state this app does not recognize');

    final Widget content = _editing == key
        ? _FieldEditor(
            key: ValueKey<String>('field-editor:${widget.specimen.id}:$key'),
            field: field,
            layer: _layer,
            pending: pending,
            choices: evidenceChoices(widget.specimen),
            onCancel: () => setState(() => _editing = null),
            onDiscard: pending == null ? null : () => _discard(key),
            onCommit: _commit,
            regionId: _regionFor(field, pending),
            blockedReason: blocked,
          )
        : _row(context, field, pending, blocked);

    return KeyedSubtree(
      key:
          anchor ?? ValueKey<String>('field-anchor:${widget.specimen.id}:$key'),
      child: Padding(
        padding: EdgeInsetsDirectional.only(bottom: context.ui.space.s2),
        child: content,
      ),
    );
  }

  Widget _row(
    BuildContext context,
    Json field,
    PendingFieldChange? pending,
    String? blocked,
  ) {
    final ui = context.ui;
    final key = field['field_key'].toString();
    final name = fieldReviewName(field);
    final issues = _issuesFor(key);
    final state = SpecimenStatus.fromWire(
      pending?.state ?? field['state'] as String?,
    );
    final needsReview = fieldNeedsReview(
      pending?.state ?? field['state'] as String?,
      hasIssues: issues.isNotEmpty,
    );
    final layers = <FieldLayer, String?>{
      for (final layer in FieldLayer.values)
        layer: _layerValue(field, pending, layer),
    };
    final currentLayer = FieldLayer.values.reversed
        .where((layer) => layers[layer] != null)
        .firstOrNull;
    final value = currentLayer == null ? null : layers[currentLayer];
    final summary = <String>[
      if (needsReview) 'Needs review',
      state.label,
      ?value,
      if (field['required'] == true) 'Required',
    ].join(' · ');
    final authority = _authorityLine(field, pending);
    // A correction not yet saved is a person's decision, not the stored
    // value, so the stored value's basis is not drawn over it.
    final ValueBasis? basis = pending == null ? fieldValueBasis(field) : null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (pending != null)
          Padding(
            padding: EdgeInsetsDirectional.fromSTEB(
              ui.space.s3,
              0,
              ui.space.s3,
              ui.space.s1,
            ),
            child: Text(
              'Not saved yet: ${pending.summary}',
              style: ui.type.bodySmall.copyWith(
                color: ui.color.status.needsReview.content,
              ),
            ),
          ),
        UiDisclosure(
          key: ValueKey<String>('field-row:${widget.specimen.id}:$key'),
          title: name,
          summary: summary,
          trailing: basis == null ? null : valueBasisChip(basis),
          semanticsLabel:
              '$name${field['required'] == true ? ', required' : ', optional'}. $summary'
              '${basis == null ? '' : '. ${basis.semanticsLabel}'}',
          onExpansionChanged: (expanded) {
            if (expanded) {
              widget.onFocusRegion?.call(_regionFor(field, pending));
            }
          },
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (value != null) ...<Widget>[
                Text(
                  'Current value · ${currentLayer!.label}',
                  style: ui.type.labelSmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
                SizedBox(height: ui.space.s1),
                Text(value, style: ui.type.body),
                if (pending == null && field['layer'] == 'derived') ...<Widget>[
                  SizedBox(height: ui.space.s1),
                  Text(
                    _derivationLine(field),
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                ],
                SizedBox(height: ui.space.s2),
              ] else ...<Widget>[
                Text(
                  switch (state) {
                    SpecimenStatus.notPresent =>
                      'This field is not present on the label.',
                    SpecimenStatus.notApplicable =>
                      'This field does not apply to the specimen.',
                    SpecimenStatus.unreadable =>
                      'The label text could not be read.',
                    SpecimenStatus.ambiguous =>
                      'More than one interpretation remains possible.',
                    SpecimenStatus.unresolved =>
                      'The available evidence has not settled this field.',
                    _ => 'No value has been recorded for this field.',
                  },
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
                SizedBox(height: ui.space.s2),
              ],
              for (final issue in issues)
                Padding(
                  padding: EdgeInsets.only(bottom: ui.space.s2),
                  child: Text(
                    issue.message,
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.status.needsReview.content,
                    ),
                  ),
                ),
              Text(
                _sourcesFor(field, pending),
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
              if (_sourceDetails(context, field, pending)
                  case final details?) ...<Widget>[
                SizedBox(height: ui.space.s2),
                details,
              ],
              SizedBox(height: ui.space.s3),
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: UiButton(
                  label: 'Correct value',
                  semanticsLabel: 'Correct value for $name',
                  variant: UiButtonVariant.secondary,
                  disabledReason: blocked,
                  onPressed: blocked == null
                      ? () => _startEdit(field, FieldLayer.asWritten)
                      : null,
                ),
              ),
              if (blocked != null) ...<Widget>[
                SizedBox(height: ui.space.s1),
                Text(
                  blocked,
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
              ],
              if (layers.values.any((value) => value != null) ||
                  authority != null) ...<Widget>[
                SizedBox(height: ui.space.s2),
                UiDisclosure(
                  title: 'Value details',
                  summary:
                      'Original wording, interpretation and standardization',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      for (final layer in FieldLayer.values)
                        if (layers[layer] case final text?)
                          Padding(
                            padding: EdgeInsets.only(bottom: ui.space.s2),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              mainAxisSize: MainAxisSize.min,
                              children: <Widget>[
                                Text(
                                  layer.label,
                                  style: ui.type.labelSmall.copyWith(
                                    color: ui.color.inkSecondary,
                                  ),
                                ),
                                Text(text, style: ui.type.body),
                              ],
                            ),
                          ),
                      if (authority != null)
                        Text(authority, style: ui.type.bodySmall),
                    ],
                  ),
                ),
              ],
              if (widget.researchForField != null) ...<Widget>[
                SizedBox(height: ui.space.s2),
                widget.researchForField!(
                  key,
                  (candidate) => _stageResearchCandidate(key, candidate),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget? _sourceDetails(
    BuildContext context,
    Json field,
    PendingFieldChange? pending,
  ) {
    final ui = context.ui;
    final ids =
        pending?.evidenceIds ??
        (field['evidence_ids'] as List? ?? const <Object?>[])
            .whereType<String>()
            .toList();
    final retained = widget.specimen.evidence
        .where(
          (item) =>
              ids.contains(item['evidence_id']) || ids.contains(item['id']),
        )
        .toList();
    final regions = _regionsFor(field, pending);
    final verbatim = pending == null
        ? objectOf(field['verbatim_by_observation']).values
              .whereType<String>()
              .where((text) => text.trim().isNotEmpty)
              .toSet()
              .toList()
        : const <String>[];
    if (retained.isEmpty && regions.isEmpty && verbatim.isEmpty) return null;
    final name = fieldReviewName(field);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Evidence for $name', style: ui.type.labelSmall),
        for (final text in verbatim)
          Padding(
            padding: EdgeInsets.only(top: ui.space.s1),
            child: Text(text, style: ui.type.bodySmall),
          ),
        for (final item in retained)
          Padding(
            padding: EdgeInsets.only(top: ui.space.s1),
            child: Text(evidenceDisplaySummary(item), style: ui.type.bodySmall),
          ),
        if (widget.onFocusRegion != null && regions.isNotEmpty)
          Wrap(
            spacing: ui.space.s2,
            runSpacing: ui.space.s1,
            children: [
              for (final (index, region) in widget.specimen.regions.indexed)
                if (regions.contains(region['region_id']))
                  UiButton(
                    label: 'View Label ${index + 1}',
                    semanticsLabel: 'View Label ${index + 1} for $name',
                    variant: UiButtonVariant.ghost,
                    onPressed: () =>
                        widget.onFocusRegion!(region['region_id'] as String),
                  ),
            ],
          ),
        if (retained.any((item) => _hasRawEvidenceDetails(item)))
          UiDisclosure(
            title: 'Evidence details',
            summary: 'Retained source response',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                for (final item in retained)
                  if (_hasRawEvidenceDetails(item))
                    Padding(
                      padding: EdgeInsets.only(top: ui.space.s1),
                      child: Text(
                        item['excerpt'] as String,
                        style: ui.type.mono.literalDense,
                      ),
                    ),
              ],
            ),
          ),
      ],
    );
  }

  bool _hasRawEvidenceDetails(Json item) =>
      item['excerpt'] is String &&
      (item['excerpt'] as String).trim().isNotEmpty &&
      item['excerpt'] != evidenceDisplaySummary(item);

  String _derivationLine(Json field) {
    final keys = (field['derived_from'] as List? ?? const <Object>[])
        .whereType<String>();
    final names = <String>[
      for (final key in keys)
        if (widget.specimen.fields
                .where((value) => value['field_key'] == key)
                .firstOrNull
            case final source?)
          fieldReviewName(source),
    ];
    return names.isEmpty
        ? 'Derived from other specimen fields'
        : 'Derived from ${names.join(', ')}';
  }

  String? _layerValue(
    Json field,
    PendingFieldChange? pending,
    FieldLayer layer,
  ) {
    String? empty(String? value) =>
        value == null || value.trim().isEmpty ? null : value;
    if (pending != null) {
      if (pending.state != 'supported') return null;
      return switch (layer) {
        FieldLayer.asWritten => empty(pending.literal),
        FieldLayer.readAs => empty(pending.parsed),
        FieldLayer.standardized => empty(pending.normalized),
      };
    }
    return switch (layer) {
      FieldLayer.asWritten => empty(field['literal_value'] as String?),
      FieldLayer.readAs => empty(field['parsed_value'] as String?),
      FieldLayer.standardized => empty(field['normalized'] as String?),
    };
  }

  String? _authorityLine(Json field, PendingFieldChange? pending) {
    if (pending != null && pending.state != 'supported') return null;
    final String id = textOf(pending?.authorityId ?? field['authority_id'], '');
    if (id.isEmpty || id == 'Not recorded') return null;
    final Json identity = objectOf(field['authority_identity']);
    final String source = textOf(identity['source'], '');
    return source.isEmpty || source == 'Not recorded'
        ? 'Authority match $id'
        : 'Authority match $id from ${vocabularyLabel(source)}';
  }
}

/// The in-place editor one layer opens into.
class _FieldEditor extends StatefulWidget {
  const _FieldEditor({
    super.key,
    required this.field,
    required this.layer,
    required this.pending,
    required this.choices,
    required this.onCancel,
    required this.onCommit,
    required this.onDiscard,
    required this.regionId,
    required this.blockedReason,
  });

  final Json field;
  final FieldLayer layer;
  final PendingFieldChange? pending;
  final List<EvidenceChoice> choices;
  final VoidCallback onCancel;
  final ValueChanged<PendingFieldChange> onCommit;
  final VoidCallback? onDiscard;
  final String? regionId;
  final String? blockedReason;

  @override
  State<_FieldEditor> createState() => _FieldEditorState();
}

class _FieldEditorState extends State<_FieldEditor> {
  late final String? _baseLiteral;
  late final String _baseFieldBasis;

  @override
  void initState() {
    super.initState();
    _baseLiteral = widget.pending != null
        ? widget.pending!.baseLiteral
        : widget.field['literal_value'] as String?;
    _baseFieldBasis =
        widget.pending?.baseFieldBasis ?? fieldBasis(widget.field);
  }

  late final TextEditingController _literal = TextEditingController(
    text: widget.pending?.literal ?? textOf(widget.field['literal_value'], ''),
  );
  late final TextEditingController _parsed = TextEditingController(
    text: widget.pending?.parsed ?? textOf(widget.field['parsed_value'], ''),
  );
  late final TextEditingController _normalized = TextEditingController(
    text: widget.pending?.normalized ?? textOf(widget.field['normalized'], ''),
  );
  late final TextEditingController _authority = TextEditingController(
    text:
        widget.pending?.authorityId ?? textOf(widget.field['authority_id'], ''),
  );
  late String _state =
      widget.pending?.state ?? textOf(widget.field['state'], 'unknown');
  late Set<String> _evidence =
      <String>{
        ...?widget.pending?.evidenceIds,
        if (widget.pending == null)
          ...((widget.field['evidence_ids'] as List? ?? <Object?>[]).map(
            (Object? e) => e.toString(),
          )),
      }.intersection(
        widget.choices.map((EvidenceChoice choice) => choice.id).toSet(),
      );

  @override
  void dispose() {
    _literal.dispose();
    _parsed.dispose();
    _normalized.dispose();
    _authority.dispose();
    super.dispose();
  }

  bool get _complete {
    if (_state != 'supported') return true;
    return _literal.text.trim().isNotEmpty && _evidence.isNotEmpty;
  }

  void _commit() {
    if (widget.blockedReason != null) return;
    widget.onCommit(
      PendingFieldChange(
        fieldKey: widget.field['field_key'].toString(),
        displayName: fieldReviewName(widget.field),
        state: _state,
        literal: _state == 'supported' ? _literal.text : null,
        parsed: _parsed.text,
        normalized: _normalized.text,
        authorityId: _authority.text,
        evidenceIds: _evidence.toList(),
        regionId: widget.regionId,
        baseLiteral: _baseLiteral,
        baseFieldBasis: _baseFieldBasis,
      ),
    );
  }

  /// What the commit control is called, and why it is disabled.
  static const String keepLabel = 'Keep this correction';
  static const String keepHint = 'Enter a value and choose evidence';

  /// The two ways out.
  static const String cancelLabel = 'Cancel';
  static const String discardLabel = 'Discard this correction';

  /// The sentence under the actions.
  static const String batchNote =
      'Corrections are saved together, with one reason.';

  /// The field that names the evidence state.
  static const String stateLabel = 'Evidence state';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String name = fieldReviewName(widget.field);
    final VoidCallback? discard = widget.onDiscard;

    return Surface(
      radius: ui.shape.tile,
      boundary: true,
      padding: EdgeInsetsDirectional.all(ui.space.s4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Semantics(
            container: true,
            header: true,
            child: Text('Correct $name', style: ui.type.label),
          ),
          if (widget.blockedReason != null) ...[
            SizedBox(height: ui.space.s2),
            Text(widget.blockedReason!, style: ui.type.bodySmall),
          ],
          SizedBox(height: ui.space.s3),
          UiSelect<String>(
            label: stateLabel,
            placeholder: stateLabel,
            value: knownFieldStates.contains(_state) ? _state : 'unknown',
            options: <UiSelectOption<String>>[
              for (final String option in knownFieldStates)
                UiSelectOption<String>(
                  value: option,
                  label: vocabularyLabel(option),
                ),
            ],
            onChanged: (String? next) {
              if (next != null) setState(() => _state = next);
            },
          ),
          SizedBox(height: ui.space.s3),
          if (_state == 'supported') ...<Widget>[
            UiField(
              label: FieldLayer.asWritten.label,
              helpText: fieldCorrectionHelp(widget.field, FieldLayer.asWritten),
              controller: _literal,
              autofocus: widget.layer == FieldLayer.asWritten,
              minLines: 1,
              maxLines: _literalMaxLines,
              onChanged: (String _) => setState(() {}),
            ),
            SizedBox(height: ui.space.s3),
            UiDisclosure(
              title: 'Interpretation and standardization',
              summary: 'Keep these values separate from the label wording',
              initiallyExpanded: widget.layer != FieldLayer.asWritten,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  UiField(
                    label: FieldLayer.readAs.label,
                    helpText: fieldCorrectionHelp(
                      widget.field,
                      FieldLayer.readAs,
                    ),
                    controller: _parsed,
                    autofocus: widget.layer == FieldLayer.readAs,
                  ),
                  SizedBox(height: ui.space.s3),
                  UiField(
                    label: FieldLayer.standardized.label,
                    helpText: fieldCorrectionHelp(
                      widget.field,
                      FieldLayer.standardized,
                    ),
                    controller: _normalized,
                    autofocus: widget.layer == FieldLayer.standardized,
                  ),
                  SizedBox(height: ui.space.s3),
                  UiField(
                    label: 'Authority identifier',
                    helpText: 'Use a match from the authority evidence below.',
                    controller: _authority,
                  ),
                ],
              ),
            ),
            SizedBox(height: ui.space.s3),
            EvidencePicker(
              choices: widget.choices,
              selected: _evidence,
              required: true,
              onChanged: (Set<String> next) => setState(() => _evidence = next),
            ),
          ] else
            const CaveatText(
              label: 'No value will be saved for this state.',
              why: 'Required checks still apply.',
            ),
          SizedBox(height: ui.space.s4),
          UiButtonRow(
            primary: UiButton(
              label: keepLabel,
              disabledReason: widget.blockedReason ?? keepHint,
              onPressed: _complete && widget.blockedReason == null
                  ? _commit
                  : null,
            ),
            secondary: UiButton(
              label: cancelLabel,
              variant: UiButtonVariant.ghost,
              onPressed: widget.onCancel,
            ),
            tertiary: <UiButton>[
              if (discard != null)
                UiButton(
                  label: discardLabel,
                  variant: UiButtonVariant.ghost,
                  onPressed: discard,
                ),
            ],
          ),
          SizedBox(height: ui.space.s2),
          Text(
            batchNote,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ],
      ),
    );
  }

  /// How far the verbatim field grows before it scrolls.
  static const int _literalMaxLines = 4;
}
