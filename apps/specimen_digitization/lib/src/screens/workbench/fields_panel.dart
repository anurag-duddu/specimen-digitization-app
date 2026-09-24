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
import '../../reason_codes.dart';
import '../../review_context.dart';
import '../../thread/thread.dart';
import '../../vocabulary.dart';
import '../../widgets/widgets.dart';
import 'evidence_picker.dart';
import 'pending_changes.dart';
import 'reader_name.dart';

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
    this.thread,
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

  /// The run's thread, which says who wrote each field's text and what
  /// settled its value (UI.md T2.3). Null until the thread has loaded.
  final SpecimenThread? thread;

  /// The heading over the fields the record cannot be cleared without.
  static const String requiredTitle = 'Required fields';

  /// The heading over the rest.
  static const String optionalTitle = 'Optional fields';

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
    // Grouped by the flag each row's "(required)" marker reads, so a heading
    // and its rows never disagree, in the record's order within each group
    // (UI.md T2.3).
    final List<(String, List<Json>)> groups = <(String, List<Json>)>[
      (
        WorkbenchFields.requiredTitle,
        <Json>[
          for (final Json f in fields)
            if (f['required'] == true) f,
        ],
      ),
      (
        WorkbenchFields.optionalTitle,
        <Json>[
          for (final Json f in fields)
            if (f['required'] != true) f,
        ],
      ),
    ].where(((String, List<Json>) group) => group.$2.isNotEmpty).toList();

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
        // The space goes above a heading and none below it: a row carries its
        // own padding, so the heading sits nearer its rows than the text
        // before it.
        for (final (String title, List<Json> group) in groups) ...<Widget>[
          SizedBox(height: ui.space.s2),
          GroupHeading(title),
          for (final Json field in group) _field(context, field),
        ],
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
    final ThreadField? run = _asRunLeftIt(field, pending);
    // The decision's warnings and notes for this field, while it stands as
    // the run left it. Hard findings come from the record, above, so none
    // is stated twice (UI.md T2.4).
    final List<ThreadFinding> noted = <ThreadFinding>[
      if (run != null)
        for (final ThreadFinding f
            in widget.thread?.decision?.findings ?? const <ThreadFinding>[])
          if (f.fieldKey == key && _notedSeverities.contains(f.severity)) f,
    ];

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
          writtenBy: _writtenBy(run),
          asWrittenNote: _settledElsewhere(run),
          readAsNote: _centuryNote(run),
          evidence: <String>[
            for (final ThreadEvidence item
                in run?.evidence ?? const <ThreadEvidence>[])
              _evidenceLine(item),
          ],
          onEdit: blocked != null
              ? null
              : (FieldLayer layer) => _startEdit(field, layer),
          editBlockedReason: blocked,
          // A reader that lands on the pencil directly hears the field as
          // well as the layer, rather than the fortieth "Edit read as".
          editSemanticsLabel: (FieldLayer layer) =>
              'Edit ${layer.label.toLowerCase()} for '
              '${textOf(field['display_name'], key)}',
          findings: findings.isEmpty && noted.isEmpty
              ? null
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    for (final Json f in findings) _Finding(finding: f),
                    for (final ThreadFinding f in noted) _Noted(finding: f),
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

  /// The thread's account of [field], while the record's field stands
  /// exactly as the run left it: no pending correction, and the same state,
  /// text, reading, standardized value and authority record (UI.md T2.3).
  /// A saved correction changes one of them, and the row then shows the
  /// record alone, so the run's account never sits beside a value it does
  /// not describe.
  ThreadField? _asRunLeftIt(Json field, PendingFieldChange? pending) {
    if (pending != null) return null;
    final ThreadField? run = widget.thread?.fields
        .where((ThreadField f) => f.fieldKey == field['field_key'])
        .firstOrNull;
    if (run == null) return null;
    String? present(Object? value) =>
        value is String && value.isNotEmpty ? value : null;
    final List<ThreadVerbatim> written = run.verbatim;
    final String? literal = present(field['literal_value']);
    // One text is the record's text; one per reader leaves the record none.
    final bool sameText = written.length == 1
        ? literal == written.single.text
        : literal == null;
    final bool same =
        sameText &&
        field['state'] == run.state &&
        present(field['parsed_value']) == run.parsed &&
        present(field['normalized']) == run.normalized &&
        present(field['authority_id']) == run.authorityId;
    return same ? run : null;
  }

  /// Who wrote each text, where that is news: every reader's text when the
  /// first pass chose none (G27, G28), each label's text when the field was
  /// found on more than one (G32), or the one reader a single text was taken
  /// from (G20). A single decided transcript names no reader: the Readings
  /// segment shows how the transcript was decided. An entry whose reading
  /// settled the value says so (UI.md T2.3 part three).
  List<AttributedText> _writtenBy(ThreadField? run) {
    final List<ThreadVerbatim> written =
        run?.verbatim ?? const <ThreadVerbatim>[];
    if (written.length == 1 &&
        written.single.inputSource != ThreadInputSource.rawReading) {
      return const <AttributedText>[];
    }
    final Set<String> settled = <String>{...?run?.settledObservationIds};
    // The label leads only where the texts come from more than one.
    final bool perLabel =
        written.map((ThreadVerbatim item) => item.regionId).toSet().length > 1;
    return <AttributedText>[
      for (final ThreadVerbatim item in written)
        if (item.text case final String text)
          (source: _attribution(item, perLabel, settled), text: text),
    ];
  }

  /// One entry's source line: its label where the field spans labels, its
  /// reader where the entry names one, where the text came from, and
  /// whether it settled the value.
  String _attribution(ThreadVerbatim item, bool perLabel, Set<String> settled) {
    final String? label = perLabel
        ? labelName(widget.specimen, widget.thread, item.regionId)
        : null;
    final String? reading = item.observationId;
    return <String>[
      ?label,
      if (reading != null) readerName(widget.specimen, widget.thread, reading),
      FirstPassSummary.sourceWords(item.inputSource, item.inputSourceName),
      if (settled.contains(reading)) settledWords,
    ].join(' · ');
  }

  /// Where a single decided transcript's value came from, when a fallback
  /// lookup settled it from another reader's raw reading instead (G20): that
  /// reading is in `settled_observation_ids` but not among the texts.
  String? _settledElsewhere(ThreadField? run) {
    final List<ThreadVerbatim> written =
        run?.verbatim ?? const <ThreadVerbatim>[];
    if (run == null ||
        written.length != 1 ||
        written.single.inputSource == ThreadInputSource.rawReading) {
      return null;
    }
    final String? shown = written.single.observationId;
    for (final String reading in run.settledObservationIds) {
      if (reading == shown) continue;
      return <String>[
        readerName(widget.specimen, widget.thread, reading),
        FirstPassSummary.sourceWords(ThreadInputSource.rawReading, null),
        settledWords,
      ].join(' · ');
    }
    return null;
  }

  /// What an entry whose reading settled the value adds to its source line.
  static const String settledWords = 'settled the value';

  /// A Google locator, `place/{place id}` (DATA_CONTRACT.md rule 1.6).
  static const String _placePrefix = 'place/';

  /// The findings that never change the disposition.
  static const Set<String> _notedSeverities = <String>{'warning', 'info'};

  /// How one source bears on the value (G23), with where in the source. A
  /// Google record is named only by its place ID (G26). A source, relation
  /// or outcome this client does not know keeps the server's word.
  static String _evidenceLine(ThreadEvidence evidence) {
    final String source = switch (evidence.source) {
      final String id => vocabularyLabel(id),
      null => 'A source',
    };
    final String claim = switch (evidence.relation) {
      'decides' => '$source decides this value',
      'supports' => '$source supports this value',
      'contradicts' => '$source contradicts this value',
      final String other => '$source: ${vocabularyLabel(other)}',
      null => source,
    };
    final String? locator = evidence.locator;
    final String? outcome = evidence.outcome;
    return <String>[
      claim,
      if (locator != null)
        locator.startsWith(_placePrefix)
            ? 'place ID ${locator.substring(_placePrefix.length)}'
            : locator,
      if (outcome != null && outcome != 'success') vocabularyLabel(outcome),
    ].join(' · ');
  }

  /// The century a rule set for a two-digit year (G24), in the words the
  /// coordinator chose on 2026-09-23. Null for a four-digit year and for
  /// anything that is not a date.
  static String? _centuryNote(ThreadField? run) {
    final String? rule = run?.centuryRule;
    if (rule == null) return null;
    const String said = "Century from the profile's rule";
    final String? century = RegExp(
      r'century=(\d{4})',
    ).firstMatch(rule)?.group(1);
    return century == null ? said : '$said: ${century}s';
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
      reasonLabel(textOf(finding['reason_code'], 'Validation finding')),
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

/// A warning or a note from the run's decision, attached to its field
/// (UI.md T2.4). It never changes the disposition, so it takes the caution
/// or the secondary tone rather than the error role, and it is not a live
/// region: nothing about it happened just now.
class _Noted extends StatelessWidget {
  const _Noted({required this.finding});

  final ThreadFinding finding;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final bool warning = finding.severity == 'warning';
    final Color tone = warning
        ? ui.color.status.needsReview.content
        : ui.color.inkSecondary;
    final String words = reasonLabel(
      finding.reasonCode ?? finding.ruleId ?? 'finding',
    );
    return Semantics(
      container: true,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Padding(
            padding: EdgeInsetsDirectional.only(top: ui.space.s1),
            child: UiIcon(
              warning ? UiIcons.needsReview : UiIcons.info,
              size: UiIconSize.inline,
              color: tone,
            ),
          ),
          SizedBox(width: ui.space.s1),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  words,
                  style: ui.type.bodySmall.copyWith(
                    color: warning ? tone : ui.color.ink,
                  ),
                ),
                Text(
                  <String>[
                    vocabularyLabel(finding.severity ?? 'finding'),
                    ?finding.ruleId,
                  ].join(' · '),
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
