/// The fields segment (screen blueprints, 6.4).
///
/// One `FieldRow` per field, with the verbatim, the interpretation and the
/// standardized value in separately named slots. Correcting one happens in
/// place, with the photograph still on screen, and the correction joins a
/// pending set that is saved once with one reason rather than one modal round
/// trip per field (audit findings H6.2 and H7.2, both severity 4).
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../models.dart';
import '../../review_context.dart';
import '../../theme/icons.dart';
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
    final ThemeData theme = Theme.of(context);
    final List<Json> fields = widget.specimen.fields;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text('Record fields', style: theme.textTheme.titleMedium),
        Text(
          'As written, read as and standardized are recorded separately.',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        SizedBox(height: context.space.space2),
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
        padding: EdgeInsets.only(bottom: context.space.space2),
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
    final ThemeData theme = Theme.of(context);
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
            padding: EdgeInsets.only(bottom: context.space.space1),
            child: Row(
              children: <Widget>[
                Icon(
                  Symbols.edit_note,
                  size: context.sizes.iconInline,
                  color: context.tokens.needsReviewContent,
                ),
                SizedBox(width: context.space.space1),
                Expanded(
                  child: Text(
                    'Not saved yet: ${pending.summary}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: context.tokens.needsReviewContent,
                    ),
                  ),
                ),
              ],
            ),
          ),
        Tooltip(
          message: blocked ?? 'Tap a value to correct it in place',
          child: Semantics(
            hint: blocked ?? '',
            child: FieldRow(
              name: textOf(field['display_name'], key),
              state: state,
              required: field['required'] == true,
              asWritten: _layerValue(field, pending, FieldLayer.asWritten),
              readAs: _layerValue(field, pending, FieldLayer.readAs),
              standardized: _layerValue(
                field,
                pending,
                FieldLayer.standardized,
              ),
              authority: _authorityLine(field, pending),
              onEdit: blocked != null
                  ? null
                  : (FieldLayer layer) => _startEdit(field, layer),
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
    final ThemeData theme = Theme.of(context);
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
            padding: EdgeInsets.only(top: context.space.space1),
            child: Icon(
              Symbols.error,
              size: context.sizes.iconInline,
              color: theme.colorScheme.error,
            ),
          ),
          SizedBox(width: context.space.space1),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  message,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.error,
                  ),
                ),
                Text(
                  <String>[
                        vocabularyLabel(textOf(finding['severity'], 'finding')),
                        textOf(finding['rule_id'], ''),
                      ]
                      .where((String s) => s.isNotEmpty && s != 'Not recorded')
                      .join(' · '),
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
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

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String name = textOf(
      widget.field['display_name'],
      widget.field['field_key'].toString(),
    );

    return Card.outlined(
      child: Padding(
        padding: EdgeInsets.all(context.space.space4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text('Correct $name', style: theme.textTheme.titleSmall),
            Text(
              'The photograph stays on screen while you type.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            SizedBox(height: context.space.space3),
            DropdownButtonFormField<String>(
              initialValue: knownFieldStates.contains(_state)
                  ? _state
                  : 'unknown',
              decoration: const InputDecoration(labelText: 'Evidence state'),
              items: <DropdownMenuItem<String>>[
                for (final String s in knownFieldStates)
                  DropdownMenuItem<String>(
                    value: s,
                    child: Text(vocabularyLabel(s)),
                  ),
              ],
              onChanged: (String? s) => setState(() => _state = s!),
            ),
            SizedBox(height: context.space.space3),
            if (_state == 'supported') ...<Widget>[
              TextField(
                controller: _literal,
                autofocus: widget.layer == FieldLayer.asWritten,
                minLines: 1,
                maxLines: 4,
                onChanged: (String _) => setState(() {}),
                decoration: const InputDecoration(
                  labelText: 'As written',
                  helperText:
                      'Keep the text exactly as written. Do not add missing '
                      'evidence.',
                ),
              ),
              SizedBox(height: context.space.space3),
              TextField(
                controller: _parsed,
                autofocus: widget.layer == FieldLayer.readAs,
                decoration: const InputDecoration(labelText: 'Read as'),
              ),
              SizedBox(height: context.space.space3),
              TextField(
                controller: _normalized,
                autofocus: widget.layer == FieldLayer.standardized,
                decoration: const InputDecoration(
                  labelText: 'Standardized',
                  helperText: 'Needs an authority match and evidence.',
                ),
              ),
              SizedBox(height: context.space.space3),
              TextField(
                controller: _authority,
                decoration: const InputDecoration(
                  labelText: 'Authority identifier',
                  helperText: 'Use a match from the authority evidence below.',
                ),
              ),
              SizedBox(height: context.space.space4),
              EvidencePicker(
                choices: widget.choices,
                selected: _evidence,
                required: true,
                onChanged: (Set<String> next) =>
                    setState(() => _evidence = next),
              ),
            ] else
              const CaveatText(
                label: 'Absence is recorded as a state, never as a value.',
                why:
                    'Nothing is written into the value slots for this state, '
                    'and the record stays blocked from clearance until the '
                    'checks that need it pass.',
              ),
            SizedBox(height: context.space.space4),
            Wrap(
              alignment: WrapAlignment.end,
              spacing: context.space.space2,
              runSpacing: context.space.space2,
              children: <Widget>[
                if (widget.onDiscard != null)
                  TextButton(
                    onPressed: widget.onDiscard,
                    child: const Text('Discard this correction'),
                  ),
                TextButton(
                  onPressed: widget.onCancel,
                  child: const Text('Cancel'),
                ),
                Semantics(
                  hint: _complete ? '' : 'Enter a value and choose evidence',
                  child: FilledButton(
                    onPressed: _complete ? _commit : null,
                    child: const Text('Keep this correction'),
                  ),
                ),
              ],
            ),
            Text(
              'Corrections are saved together, with one reason.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
