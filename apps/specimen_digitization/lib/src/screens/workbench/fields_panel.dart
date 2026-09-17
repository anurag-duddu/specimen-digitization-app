/// The fields segment (screen blueprints, 6.4).
///
/// One `FieldRow` per field, with the verbatim, the interpretation and the
/// standardized value in separately named slots. Correcting one happens in
/// place, with the photograph still on screen, and the correction joins a
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
import 'pending_changes.dart';

/// The record's fields, their evidence and their corrections.
class WorkbenchFields extends StatefulWidget {
  const WorkbenchFields({
    super.key,
    required this.specimen,
    required this.anchors,
    required this.pending,
    required this.onPendingChanged,
    required this.onFocusRegion,
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
  final ValueChanged<String?> onFocusRegion;

  /// Why correcting a field is unavailable, or null when it is not.
  final String? fieldBlockedReason;

  @override
  State<WorkbenchFields> createState() => _WorkbenchFieldsState();
}

class _WorkbenchFieldsState extends State<WorkbenchFields> {
  String? _editing;
  FieldLayer _layer = FieldLayer.asWritten;

  PendingFieldChange? _pendingFor(String key) => widget.pending
      .where((PendingFieldChange p) => p.fieldKey == key)
      .firstOrNull;

  /// The region a field was read from, taken from the evidence the field
  /// cites. Nothing is guessed: a field with no evidence has no region.
  String? _regionFor(Json field) {
    final List<Object?> ids =
        (field['evidence_ids'] as List?) ?? const <Object?>[];
    for (final Object? id in ids) {
      final Json? item = widget.specimen.evidence
          .where((Json e) => e['evidence_id'] == id || e['id'] == id)
          .firstOrNull;
      final Object? region = item?['region_id'];
      if (region is String && region.isNotEmpty) return region;
    }
    return null;
  }

  void _startEdit(Json field, FieldLayer layer) {
    widget.onFocusRegion(_regionFor(field));
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
    final UiThemeData ui = context.ui;
    final List<Json> fields = widget.specimen.fields;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Semantics(
          container: true,
          header: true,
          child: Text('Record fields', style: ui.type.title),
        ),
        // Its own node: a sentence that merges upward becomes the tab
        // panel's label, and a panel named after its own help text is not a
        // panel a reader can place.
        Semantics(
          container: true,
          child: Text(
            'As written, read as and standardized are recorded separately.',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ),
        SizedBox(height: ui.space.s2),
        if (fields.isEmpty)
          const CaveatText(
            label: 'No fields recorded yet.',
            why: 'Required field checks have not run for this record.',
          ),
        for (final Json field in fields) _field(context, field),
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
            field: field,
            layer: _layer,
            pending: pending,
            choices: evidenceChoices(widget.specimen),
            onCancel: () => setState(() => _editing = null),
            onDiscard: pending == null ? null : () => _discard(key),
            onCommit: _commit,
            regionId: _regionFor(field),
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
          name: textOf(field['display_name'], key),
          state: state,
          required: field['required'] == true,
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
              '${textOf(field['display_name'], key)}',
          findings: findings.isEmpty
              ? null
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    for (final Json f in findings) _Finding(finding: f),
                  ],
                ),
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

  String? _layerValue(
    Json field,
    PendingFieldChange? pending,
    FieldLayer layer,
  ) {
    String? empty(String? value) =>
        value == null || value.isEmpty ? null : value;
    if (pending != null) {
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
    required this.field,
    required this.layer,
    required this.pending,
    required this.choices,
    required this.onCancel,
    required this.onCommit,
    required this.onDiscard,
    required this.regionId,
  });

  final Json field;
  final FieldLayer layer;
  final PendingFieldChange? pending;
  final List<EvidenceChoice> choices;
  final VoidCallback onCancel;
  final ValueChanged<PendingFieldChange> onCommit;
  final VoidCallback? onDiscard;
  final String? regionId;

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
  late Set<String> _evidence = <String>{
    ...?widget.pending?.evidenceIds,
    if (widget.pending == null)
      ...((widget.field['evidence_ids'] as List? ?? <Object?>[]).map(
        (Object? e) => e.toString(),
      )),
  };

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

  void _commit() => widget.onCommit(
    PendingFieldChange(
      fieldKey: widget.field['field_key'].toString(),
      displayName: textOf(
        widget.field['display_name'],
        widget.field['field_key'].toString(),
      ),
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

  /// The editor's own heading, and the one sentence under it.
  static const String subtitle =
      'The photograph stays on screen while you type.';

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
    final String name = textOf(
      widget.field['display_name'],
      widget.field['field_key'].toString(),
    );
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
          Text(
            subtitle,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
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
              helpText:
                  'Keep the text exactly as written. Do not add missing '
                  'evidence.',
              controller: _literal,
              autofocus: widget.layer == FieldLayer.asWritten,
              minLines: 1,
              maxLines: _literalMaxLines,
              onChanged: (String _) => setState(() {}),
            ),
            SizedBox(height: ui.space.s3),
            UiField(
              label: FieldLayer.readAs.label,
              controller: _parsed,
              autofocus: widget.layer == FieldLayer.readAs,
            ),
            SizedBox(height: ui.space.s3),
            UiField(
              label: FieldLayer.standardized.label,
              helpText: 'Needs an authority match and evidence.',
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
              label: 'Absence is recorded as a state, never as a value.',
              why:
                  'Nothing is written into the value slots for this state, '
                  'and the record stays blocked from clearance until the '
                  'checks that need it pass.',
            ),
          SizedBox(height: ui.space.s4),
          UiButtonRow(
            primary: UiButton(
              label: keepLabel,
              disabledReason: keepHint,
              onPressed: _complete ? _commit : null,
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
