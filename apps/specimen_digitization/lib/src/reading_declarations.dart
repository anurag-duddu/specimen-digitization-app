import 'package:flutter/material.dart';
import 'models.dart';
import 'review_context.dart';
import 'theme/icons.dart';
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

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(
        'Label language handling',
        style: Theme.of(context).textTheme.titleMedium,
      ),
      const CaveatText(
        label: 'Not calibrated',
        why:
            'Declared languages are recorded, not measured. Multiple languages '
            'on one label and conflicting readings are recorded separately.',
      ),
      for (final label in objects(handling['labels']))
        Card.outlined(
          child: Padding(
            padding: EdgeInsets.all(context.space.space3),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  regionName == null
                      ? 'Label ${textOf(label['region_id'])}'
                      : regionName!(label['region_id']),
                  style: Theme.of(context).textTheme.titleSmall,
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
                  ),
                Text(
                  'Multiple languages declared together: ${_state(label['mixed_declared'], 'Declared', 'Not declared')}',
                ),
                Text(
                  'Conflicting readings: ${_state(label['conflicting_candidates'], 'Recorded', 'None recorded')}',
                ),
                Text(
                  'Policy ${textOf(label['policy_version'])} · Review: ${_state(label['review_required'], 'Required', 'Not required')}',
                ),
                if (label['unmeasured'] == true)
                  const Text('Language is not measured.'),
                for (final reason in label['reasons'] as List? ?? [])
                  Text(vocabularyLabel(reason.toString())),
                if (onDeclare != null && label['region_id'] is String)
                  Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: TextButton(
                      onPressed: () => onDeclare!(label['region_id'] as String),
                      child: const Text('Declare'),
                    ),
                  ),
              ],
            ),
          ),
        ),
      EvidenceDetails(
        title: 'Versioned language policy and label evidence',
        value: handling,
      ),
    ],
  );
}

/// The declared languages and scripts, each as its own chip.
class _DeclarationChips extends StatelessWidget {
  const _DeclarationChips({required this.languages, required this.scripts});

  final dynamic languages;
  final dynamic scripts;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: context.space.space2,
    runSpacing: context.space.space2,
    children: <Widget>[
      for (final value in languages is List ? languages : const [])
        Chip(
          avatar: Icon(Icons.translate, size: context.sizes.iconInline),
          label: Text('Language: $value'),
        ),
      for (final value in scripts is List ? scripts : const [])
        Chip(
          avatar: Icon(Icons.abc, size: context.sizes.iconInline),
          label: Text('Script: $value'),
        ),
    ],
  );
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

class ReadingDeclarationView extends StatelessWidget {
  const ReadingDeclarationView({
    super.key,
    required this.provenance,
    this.onChange,
  });
  final Json provenance;
  final Future<void> Function(Json)? onChange;
  @override
  Widget build(BuildContext context) {
    final model = objectOf(provenance['model']);
    final history = objects(provenance['human_history']);
    final superseded = history
        .map((h) => h['supersedes'])
        .whereType<String>()
        .toSet();
    final active = history.where((h) => !superseded.contains(h['id'])).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Declaration provenance · Version ${provenance['revision']}'),
        const CaveatText(
          label: 'Model declarations and original readings never change.',
          why:
              'A new declaration replaces your previous one for this reading. '
              'Saving it also removes approval.',
        ),
        Text(
          'Model languages: ${_labels(objectOf(model['candidates'])['language_candidates'])}',
        ),
        Text(
          'Model scripts: ${_labels(objectOf(model['candidates'])['script_candidates'])}',
        ),
        Text(_relation(objectOf(model['candidates'])['language_relation'])),
        Text(
          'Producer ${textOf(model['producer'])} · Version ${textOf(model['version'])}',
        ),
        if (history.isEmpty) const Text('No human declaration recorded.'),
        for (final human in history)
          Card.outlined(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    superseded.contains(human['id'])
                        ? 'Superseded human declaration'
                        : 'Current human declaration',
                  ),
                  Text(
                    'Languages: ${_labels(objectOf(human['candidates'])['language_candidates'])} · Scripts: ${_labels(objectOf(human['candidates'])['script_candidates'])}',
                  ),
                  Text(
                    _relation(
                      objectOf(human['candidates'])['language_relation'],
                    ),
                  ),
                  Text(
                    'Recorded by ${textOf(human['actor'])} · ${textOf(human['created_at'])}',
                  ),
                  Text('Reason: ${textOf(human['reason'])}'),
                  EvidenceDetails(
                    title: 'Human declaration lineage',
                    value: human,
                  ),
                ],
              ),
            ),
          ),
        EvidenceDetails(
          title: 'Retained model response and declaration history',
          value: provenance,
        ),
        if (onChange != null)
          OutlinedButton(
            onPressed: () async {
              final change = await showDialog<Json>(
                context: context,
                builder: (_) => ReadingDeclarationDialog(
                  observationId: textOf(provenance['observation_id'], ''),
                  initial: active.length == 1
                      ? objectOf(active.single['candidates'])
                      : const {},
                ),
              );
              if (change != null && context.mounted) await onChange!(change);
            },
            child: const Text('Record declaration'),
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
}) => showDialog<Json>(
  context: context,
  builder: (_) =>
      ReadingDeclarationDialog(observationId: observationId, initial: initial),
);

class ReadingDeclarationDialog extends StatefulWidget {
  const ReadingDeclarationDialog({
    super.key,
    required this.observationId,
    this.initial = const {},
  });
  final String observationId;
  final Json initial;
  @override
  State<ReadingDeclarationDialog> createState() =>
      _ReadingDeclarationDialogState();
}

class _ReadingDeclarationDialogState extends State<ReadingDeclarationDialog> {
  final _form = GlobalKey<FormState>();
  late final _languages = TextEditingController(
    text: (widget.initial['language_candidates'] as List? ?? []).join('\n'),
  );
  late final _scripts = TextEditingController(
    text: (widget.initial['script_candidates'] as List? ?? []).join('\n'),
  );
  final _reason = TextEditingController();
  late String _relation = textOf(
    widget.initial['language_relation'],
    'unspecified',
  );
  List<String> _values(String text) =>
      text.split('\n').map((s) => s.trim()).where((s) => s.isNotEmpty).toList();
  String? _validate(String? text) {
    final values = _values(text ?? '');
    if (values.length > 8 || values.any((v) => v.runes.length > 100)) {
      return 'Use up to 8 labels, each at most 100 characters.';
    }
    if (values.toSet().length != values.length) {
      return 'Each entry must be different.';
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

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Record language and script declaration'),
    content: SingleChildScrollView(
      child: SizedBox(
        width: 480,
        child: Form(
          key: _form,
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
              TextFormField(
                controller: _languages,
                minLines: 2,
                maxLines: 5,
                decoration: const InputDecoration(labelText: 'Languages'),
                validator: (v) {
                  final error = _validate(v);
                  if (error != null) return error;
                  if (_relation != 'unspecified' &&
                      _values(v ?? '').length < 2) {
                    return 'This relationship requires at least 2 distinct languages.';
                  }
                  return null;
                },
              ),
              TextFormField(
                controller: _scripts,
                minLines: 2,
                maxLines: 5,
                decoration: const InputDecoration(labelText: 'Scripts'),
                validator: _validate,
              ),
              DropdownButtonFormField<String>(
                initialValue: _relation,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Language relationship',
                ),
                items: const [
                  DropdownMenuItem(
                    value: 'unspecified',
                    child: Text('Unspecified'),
                  ),
                  DropdownMenuItem(
                    value: 'cooccurring',
                    child: Text('Multiple languages on this label'),
                  ),
                  DropdownMenuItem(
                    value: 'alternatives',
                    child: Text('Alternative interpretations'),
                  ),
                ],
                onChanged: (v) {
                  if (v != null) setState(() => _relation = v);
                },
              ),
              TextFormField(
                controller: _reason,
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
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: () {
          if (_form.currentState!.validate()) {
            Navigator.pop(context, <String, dynamic>{
              'kind': 'reading_metadata',
              'target_id': widget.observationId,
              'reason': _reason.text.trim(),
              'language_candidates': _values(_languages.text),
              'script_candidates': _values(_scripts.text),
              'language_relation': _relation,
            });
          }
        },
        child: const Text('Save declaration'),
      ),
    ],
  );
}
