/// Declared languages and scripts, per label and per reading
/// (screen blueprints, 6.3).
///
/// A declaration is recorded, never measured: what a reviewer types is kept
/// exactly as typed, an empty list records no declaration, and saving one
/// never approves the record.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'models.dart';
import 'review_context.dart';
import 'screens/workbench/moments.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

/// The declared languages and scripts per label, as chips with a Declare
/// action (screen blueprints, 6.3).
class LabelLanguagePolicy extends StatelessWidget {
  const LabelLanguagePolicy({
    super.key,
    required this.handling,
    this.regionName,
    this.onDeclare,
  });

  final Json handling;

  /// Names a region the way the region list names it. Defaults to the raw
  /// identifier only when the caller has nothing better.
  final String Function(Object?)? regionName;

  /// Opens the declaration form for one region. Null when the server does not
  /// permit a declaration on this version.
  final Future<void> Function(String regionId)? onDeclare;

  /// The heading over the whole pane.
  static const String heading = 'Label language handling';

  /// The control that opens the declaration form.
  static const String declareLabel = 'Declare';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final TextStyle line = ui.type.bodySmall.copyWith(
      color: ui.color.inkSecondary,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          container: true,
          header: true,
          child: Text(heading, style: ui.type.title),
        ),
        const CaveatText(
          label: 'Not calibrated',
          why:
              'Declared languages are recorded, not measured. Multiple languages '
              'on one label and conflicting readings are recorded separately.',
        ),
        for (final label in objects(handling['labels']))
          Padding(
            padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
            child: Surface(
              radius: ui.shape.tile,
              boundary: true,
              padding: EdgeInsetsDirectional.all(ui.space.s3),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    regionName == null
                        ? 'Label ${textOf(label['region_id'])}'
                        : regionName!(label['region_id']),
                    style: ui.type.label,
                  ),
                  if (_hasValues(label['language_candidates']) ||
                      _hasValues(label['script_candidates']))
                    _DeclarationChips(
                      languages: label['language_candidates'],
                      scripts: label['script_candidates'],
                    )
                  else
                    Text(
                      'Languages: ${_labels(label['language_candidates'])} · Scripts: ${_labels(label['script_candidates'])}',
                      style: line,
                    ),
                  Text(
                    'Multiple languages declared together: ${_state(label['mixed_declared'], 'Declared', 'Not declared')}',
                    style: line,
                  ),
                  Text(
                    'Conflicting readings: ${_state(label['conflicting_candidates'], 'Recorded', 'None recorded')}',
                    style: line,
                  ),
                  Text(
                    'Policy ${textOf(label['policy_version'])} · Review: ${_state(label['review_required'], 'Required', 'Not required')}',
                    style: line,
                  ),
                  if (label['unmeasured'] == true)
                    Text('Language is not measured.', style: line),
                  for (final reason in label['reasons'] as List? ?? [])
                    Text(vocabularyLabel(reason.toString()), style: line),
                  if (onDeclare != null && label['region_id'] is String)
                    Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: UiButton(
                        label: declareLabel,
                        variant: UiButtonVariant.ghost,
                        onPressed: () =>
                            onDeclare!(label['region_id'] as String),
                      ),
                    ),
                ],
              ),
            ),
          ),
        EvidenceDrawer(
          title: 'Versioned language policy and label evidence',
          payload: handling,
        ),
      ],
    );
  }
}

/// The declared languages and scripts, each as its own chip.
class _DeclarationChips extends StatelessWidget {
  const _DeclarationChips({required this.languages, required this.scripts});

  final dynamic languages;
  final dynamic scripts;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Wrap(
      spacing: ui.space.s2,
      runSpacing: ui.space.s2,
      children: <Widget>[
        for (final value in languages is List ? languages : const [])
          UiChip(label: 'Language: $value', icon: UiIcons.language),
        for (final value in scripts is List ? scripts : const [])
          UiChip(label: 'Script: $value', icon: UiIcons.script),
      ],
    );
  }
}

bool _hasValues(dynamic values) => values is List && values.isNotEmpty;

String _labels(dynamic values) =>
    values is List && values.isNotEmpty ? values.join(', ') : 'Not declared';

/// A recorded boolean, named in the words of the thing it describes.
/// A bare "Yes" or "No" says nothing on its own (guideline 6, rule 6).
String _state(dynamic value, String present, String absent) => value == true
    ? present
    : value == false
    ? absent
    : 'Not recorded';

String _relation(dynamic value) => switch (value) {
  'cooccurring' => 'Multiple languages on the same label',
  'alternatives' => 'Alternative language interpretations',
  'unspecified' => 'Relationship unspecified',
  _ => 'Relationship not recorded',
};

/// One reading's declarations: what the model said, and what a human recorded.
class ReadingDeclarationView extends StatelessWidget {
  const ReadingDeclarationView({
    super.key,
    required this.provenance,
    this.onChange,
  });

  final Json provenance;
  final Future<void> Function(Json)? onChange;

  /// The control that opens the declaration form.
  static const String recordLabel = 'Record declaration';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final model = objectOf(provenance['model']);
    final history = objects(provenance['human_history']);
    final superseded = history
        .map((h) => h['supersedes'])
        .whereType<String>()
        .toSet();
    final active = history.where((h) => !superseded.contains(h['id'])).toList();
    final TextStyle line = ui.type.bodySmall.copyWith(
      color: ui.color.inkSecondary,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Declaration provenance · Version ${provenance['revision']}',
          style: ui.type.label,
        ),
        const CaveatText(
          label: 'Model declarations and original readings never change.',
          why:
              'A new declaration replaces your previous one for this reading. '
              'Saving it also removes approval.',
        ),
        Text(
          'Model languages: ${_labels(objectOf(model['candidates'])['language_candidates'])}',
          style: line,
        ),
        Text(
          'Model scripts: ${_labels(objectOf(model['candidates'])['script_candidates'])}',
          style: line,
        ),
        Text(
          _relation(objectOf(model['candidates'])['language_relation']),
          style: line,
        ),
        Text(
          'Producer ${textOf(model['producer'])} · Version ${textOf(model['version'])}',
          style: line,
        ),
        if (history.isEmpty)
          Text('No human declaration recorded.', style: line),
        for (final human in history)
          Padding(
            padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
            child: Surface(
              radius: ui.shape.tile,
              boundary: true,
              padding: EdgeInsetsDirectional.all(ui.space.s3),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    superseded.contains(human['id'])
                        ? 'Superseded human declaration'
                        : 'Current human declaration',
                    style: ui.type.label,
                  ),
                  Text(
                    'Languages: ${_labels(objectOf(human['candidates'])['language_candidates'])} · Scripts: ${_labels(objectOf(human['candidates'])['script_candidates'])}',
                    style: line,
                  ),
                  Text(
                    _relation(
                      objectOf(human['candidates'])['language_relation'],
                    ),
                    style: line,
                  ),
                  Text(
                    'Recorded by ${textOf(human['actor'])} · '
                    '${absoluteInstant(human['created_at'])}',
                    style: line,
                  ),
                  Text('Reason: ${textOf(human['reason'])}', style: line),
                  EvidenceDrawer(
                    title: 'Human declaration lineage',
                    payload: human,
                  ),
                ],
              ),
            ),
          ),
        EvidenceDrawer(
          title: 'Retained model response and declaration history',
          payload: provenance,
        ),
        if (onChange != null)
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiButton(
              label: recordLabel,
              variant: UiButtonVariant.secondary,
              onPressed: () async {
                final change = await showDeclarationForm(
                  context,
                  observationId: textOf(provenance['observation_id'], ''),
                  initial: active.length == 1
                      ? objectOf(active.single['candidates'])
                      : const {},
                );
                if (change != null && context.mounted) await onChange!(change);
              },
            ),
          ),
      ],
    );
  }
}

/// Opens the declaration form for one reading.
Future<Json?> showDeclarationForm(
  BuildContext context, {
  required String observationId,
  Json initial = const {},
}) => showAdaptiveModal<Json>(
  context,
  title: ReadingDeclarationDialog.title,
  body: (BuildContext formContext) =>
      ReadingDeclarationDialog(observationId: observationId, initial: initial),
);

/// The declaration form.
///
/// Exposed as a widget rather than a route so it can be pumped and reviewed
/// on its own; [showDeclarationForm] is how a screen opens it.
class ReadingDeclarationDialog extends StatefulWidget {
  const ReadingDeclarationDialog({
    super.key,
    required this.observationId,
    this.initial = const {},
  });

  final String observationId;
  final Json initial;

  /// The form's own title.
  static const String title = 'Record language and script declaration';

  /// The commit control.
  static const String action = 'Save declaration';

  /// The two list fields.
  static const String languagesLabel = 'Languages';
  static const String scriptsLabel = 'Scripts';

  /// The field that names how several languages relate.
  static const String relationLabel = 'Language relationship';

  /// The limits a declaration is held to, in the words the form uses.
  static const String tooMany =
      'Use up to 8 labels, each at most 100 characters.';
  static const String notDistinct = 'Each entry must be different.';
  static const String needsTwo =
      'This relationship requires at least 2 distinct languages.';

  /// How many entries one declaration may carry.
  static const int maxEntries = 8;

  /// How long one entry may be.
  static const int maxEntryRunes = 100;

  @override
  State<ReadingDeclarationDialog> createState() =>
      _ReadingDeclarationDialogState();
}

class _ReadingDeclarationDialogState extends State<ReadingDeclarationDialog> {
  late final _languages = TextEditingController(
    text: (widget.initial['language_candidates'] as List? ?? []).join('\n'),
  );
  late final _scripts = TextEditingController(
    text: (widget.initial['script_candidates'] as List? ?? []).join('\n'),
  );
  final _reason = TextEditingController();
  late String _relationValue = textOf(
    widget.initial['language_relation'],
    'unspecified',
  );
  String? _languagesError;
  String? _scriptsError;
  String? _reasonError;

  List<String> _values(String text) =>
      text.split('\n').map((s) => s.trim()).where((s) => s.isNotEmpty).toList();

  String? _validate(String text) {
    final values = _values(text);
    if (values.length > ReadingDeclarationDialog.maxEntries ||
        values.any(
          (v) => v.runes.length > ReadingDeclarationDialog.maxEntryRunes,
        )) {
      return ReadingDeclarationDialog.tooMany;
    }
    if (values.toSet().length != values.length) {
      return ReadingDeclarationDialog.notDistinct;
    }
    return null;
  }

  @override
  void dispose() {
    _languages.dispose();
    _scripts.dispose();
    _reason.dispose();
    super.dispose();
  }

  void _save() {
    String? languages = _validate(_languages.text);
    if (languages == null &&
        _relationValue != 'unspecified' &&
        _values(_languages.text).length < 2) {
      languages = ReadingDeclarationDialog.needsTwo;
    }
    final String? scripts = _validate(_scripts.text);
    final String reason = _reason.text.trim();
    setState(() {
      _languagesError = languages;
      _scriptsError = scripts;
      _reasonError = reason.isEmpty ? reasonRequired : null;
    });
    if (languages != null || scripts != null || reason.isEmpty) return;
    Navigator.pop(context, <String, dynamic>{
      'kind': 'reading_metadata',
      'target_id': widget.observationId,
      'reason': reason,
      'language_candidates': _values(_languages.text),
      'script_candidates': _values(_scripts.text),
      'language_relation': _relationValue,
    });
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const CaveatText(
            label: 'Enter one language per line.',
            why:
                'Your entries are recorded exactly as typed. Nothing is '
                'inferred. An empty list records no declaration, and saving '
                'does not approve the record.',
          ),
          SizedBox(height: ui.space.s3),
          UiTextArea(
            label: ReadingDeclarationDialog.languagesLabel,
            errorText: _languagesError,
            controller: _languages,
            minLines: _listMinLines,
            maxLines: _listMaxLines,
            onChanged: (String _) {
              if (_languagesError != null) {
                setState(() => _languagesError = null);
              }
            },
          ),
          SizedBox(height: ui.space.s3),
          UiTextArea(
            label: ReadingDeclarationDialog.scriptsLabel,
            errorText: _scriptsError,
            controller: _scripts,
            minLines: _listMinLines,
            maxLines: _listMaxLines,
            onChanged: (String _) {
              if (_scriptsError != null) setState(() => _scriptsError = null);
            },
          ),
          SizedBox(height: ui.space.s3),
          UiSelect<String>(
            label: ReadingDeclarationDialog.relationLabel,
            placeholder: ReadingDeclarationDialog.relationLabel,
            value: _relationValue,
            options: const <UiSelectOption<String>>[
              UiSelectOption<String>(
                value: 'unspecified',
                label: 'Unspecified',
              ),
              UiSelectOption<String>(
                value: 'cooccurring',
                label: 'Multiple languages on this label',
              ),
              UiSelectOption<String>(
                value: 'alternatives',
                label: 'Alternative interpretations',
              ),
            ],
            onChanged: (String? value) {
              if (value != null) setState(() => _relationValue = value);
            },
          ),
          SizedBox(height: ui.space.s3),
          UiTextArea(
            label: 'Reason',
            helpText: reasonHelperText,
            errorText: _reasonError,
            controller: _reason,
            minLines: _reasonMinLines,
            maxLines: _reasonMaxLines,
            onChanged: (String _) {
              if (_reasonError != null) setState(() => _reasonError = null);
            },
          ),
          SizedBox(height: ui.space.s6),
          UiButtonRow(
            primary: UiButton(
              label: ReadingDeclarationDialog.action,
              onPressed: _save,
            ),
            secondary: UiButton(
              label: 'Cancel',
              variant: UiButtonVariant.ghost,
              onPressed: () => Navigator.pop(context),
            ),
          ),
        ],
      ),
    );
  }

  static const int _listMinLines = 2;
  static const int _listMaxLines = 5;
  static const int _reasonMinLines = 2;
  static const int _reasonMaxLines = 4;
}
