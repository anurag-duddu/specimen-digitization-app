/// The fields segment (screen blueprints, 6.4).
///
/// One concise `FieldRow` per field, with its value state and current value.
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
import '../../review_context.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import 'evidence_picker.dart';
import 'field_presentation.dart';
import 'pending_changes.dart';

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
    final List<Object?> ids =
        pending?.evidenceIds ??
        (field['evidence_ids'] as List?) ??
        const <Object?>[];
    for (final Object? id in ids) {
      final Json? item = widget.specimen.evidence
          .where((Json e) => e['evidence_id'] == id || e['id'] == id)
          .firstOrNull;
      final Object? region = item?['region_id'];
      if (region is String &&
          widget.specimen.regions.any((Json r) => r['region_id'] == region)) {
        regions.add(region);
      }
    }
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

  @override
  Widget build(BuildContext context) {
    final List<Json> fields = widget.specimen.fields;
    final requiredFields = fields
        .where((field) => field['required'] == true)
        .toList(growable: false);
    final optionalFields = fields
        .where((field) => field['required'] != true)
        .toList(growable: false);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (fields.isEmpty)
          const CaveatText(
            label: 'No fields recorded yet.',
            why: 'Required field checks have not run for this record.',
          ),
        if (requiredFields.isNotEmpty)
          _group(context, 'Required', requiredFields),
        if (requiredFields.isNotEmpty && optionalFields.isNotEmpty)
          SizedBox(height: context.ui.space.s4),
        if (optionalFields.isNotEmpty)
          _group(context, 'Optional', optionalFields),
      ],
    );
  }

  Widget _group(BuildContext context, String title, List<Json> fields) =>
      Column(
        key: ValueKey<String>('field-group:$title'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Padding(
            padding: EdgeInsetsDirectional.fromSTEB(
              context.ui.space.s3,
              0,
              context.ui.space.s3,
              context.ui.space.s2,
            ),
            child: Semantics(
              header: true,
              child: Text(title, style: context.ui.type.label),
            ),
          ),
          for (final field in fields) _field(context, field),
        ],
      );

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
      key: anchor,
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
    final UiThemeData ui = context.ui;
    final String key = field['field_key'].toString();
    final List<Json> findings = widget.specimen.findings
        .where((Json f) => f['field_key'] == key)
        .toList();
    final SpecimenStatus state = SpecimenStatus.fromWire(
      pending?.state ?? field['state'] as String?,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (pending != null)
          Padding(
            padding: EdgeInsetsDirectional.only(bottom: ui.space.s1),
            child: Row(
              children: <Widget>[
                UiIcon(
                  UiIcons.editReason,
                  size: UiIconSize.inline,
                  color: ui.color.status.needsReview.content,
                ),
                SizedBox(width: ui.space.s1),
                Expanded(
                  child: Text(
                    'Not saved yet: ${pending.summary}',
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.status.needsReview.content,
                    ),
                  ),
                ),
              ],
            ),
          ),
        FieldRow(
          key: ValueKey<String>('field-row:${widget.specimen.id}:$key'),
          sourceLabel: _sourcesFor(field, pending),
          sourceDetails: _sourceDetails(context, field, pending),
          onExpansionChanged: (expanded) {
            if (expanded) {
              widget.onFocusRegion?.call(_regionFor(field, pending));
            }
          },
          name: fieldReviewName(field),
          state: state,
          required: field['required'] == true,
          showRequirementMarker: false,
          asWritten: _layerValue(field, pending, FieldLayer.asWritten),
          readAs: _layerValue(field, pending, FieldLayer.readAs),
          standardized: _layerValue(field, pending, FieldLayer.standardized),
          authority: _authorityLine(field, pending),
          onEdit: blocked != null
              ? null
              : (FieldLayer layer) => _startEdit(field, layer),
          editBlockedReason: blocked,
          // A reader that lands on the pencil directly hears the field as
          // well as the layer, rather than the fortieth "Edit read as".
          editSemanticsLabel: (FieldLayer layer) =>
              'Edit ${layer.label.toLowerCase()} for '
              '${fieldReviewName(field)}',
          findings: findings.isEmpty
              ? null
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    for (final Json f in findings) _Finding(finding: f),
                  ],
                ),
          findingCount: findings.length,
        ),
        if (blocked != null && !knownFieldStates.contains(field['state']))
          const CaveatText(
            label: 'This field cannot be edited in this version of the app.',
            why:
                'The server sent a field state this app does not recognize. '
                'Refreshing may help. Otherwise update the app.',
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
    if (retained.isEmpty) return null;
    final regions = _regionsFor(field, pending);
    final name = fieldReviewName(field);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Evidence for $name', style: ui.type.labelSmall),
        for (final item in retained)
          if (item['excerpt'] is String &&
              (item['excerpt'] as String).trim().isNotEmpty)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s1),
              child: Text(
                item['excerpt'] as String,
                style: ui.type.mono.literalDense,
              ),
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
      ],
    );
  }

  String? _layerValue(
    Json field,
    PendingFieldChange? pending,
    FieldLayer layer,
  ) {
    String? empty(String? value) =>
        value == null || value.isEmpty ? null : value;
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

/// One validation finding, in the error role, attached to its field.
class _Finding extends StatelessWidget {
  const _Finding({required this.finding});

  final Json finding;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Color error = ui.color.status.blocked.content;
    final String message = textOf(
      finding['message'],
      vocabularyLabel(textOf(finding['reason_code'], 'Validation finding')),
    );
    return Semantics(
      liveRegion: true,
      container: true,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Padding(
            padding: EdgeInsetsDirectional.only(top: ui.space.s1),
            child: UiIcon(UiIcons.error, size: UiIconSize.inline, color: error),
          ),
          SizedBox(width: ui.space.s1),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(message, style: ui.type.bodySmall.copyWith(color: error)),
                Text(
                  <String>[
                        vocabularyLabel(textOf(finding['severity'], 'finding')),
                        textOf(finding['rule_id'], ''),
                      ]
                      .where((String s) => s.isNotEmpty && s != 'Not recorded')
                      .join(' · '),
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
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
        baseLiteral: widget.field['literal_value'] as String?,
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
            UiField(
              label: FieldLayer.readAs.label,
              helpText: fieldCorrectionHelp(widget.field, FieldLayer.readAs),
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
            SizedBox(height: ui.space.s4),
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
