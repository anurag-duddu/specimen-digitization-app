import 'package:flutter/material.dart';
import 'models.dart';
import 'review_context.dart';

class LabelLanguagePolicy extends StatelessWidget {
  const LabelLanguagePolicy({super.key, required this.handling});
  final Json handling;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(
        'Label language handling',
        style: Theme.of(context).textTheme.titleMedium,
      ),
      const Text(
        'Declared candidates are uncalibrated. Multiple languages on one label and conflicting interpretations are recorded separately.',
      ),
      for (final label in objects(handling['labels']))
        Card.outlined(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Label ${textOf(label['region_id'])}'),
                Text(
                  'Languages: ${_labels(label['language_candidates'])} · Scripts: ${_labels(label['script_candidates'])}',
                ),
                Text(
                  'Multiple languages declared together: ${_flag(label['mixed_declared'])}',
                ),
                Text(
                  'Conflicting candidate interpretations: ${_flag(label['conflicting_candidates'])}',
                ),
                Text(
                  'Policy ${textOf(label['policy_version'])} · Review required: ${_flag(label['review_required'])}',
                ),
                if (label['unmeasured'] == true)
                  const Text('Language confidence is not measured.'),
                for (final reason in label['reasons'] as List? ?? [])
                  Text(labelOf(reason.toString())),
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

String _labels(dynamic values) =>
    values is List && values.isNotEmpty ? values.join(', ') : 'Not declared';
String _flag(dynamic value) => value == true
    ? 'Yes'
    : value == false
    ? 'No'
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
        Text('Declaration provenance · Revision ${provenance['revision']}'),
        const Text(
          'Model declarations and original readings remain immutable. A new human declaration supersedes the previous human declaration for this observation and invalidates approval.',
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
            child: const Text('Record language and script declaration'),
          ),
      ],
    );
  }
}

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
      return 'Each candidate must be distinct.';
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
              const Text(
                'Enter one candidate per line. Labels are preserved as declarations; no language or script is inferred. Leave a list empty to record no declaration. This does not approve the record.',
              ),
              TextFormField(
                controller: _languages,
                minLines: 2,
                maxLines: 5,
                decoration: const InputDecoration(
                  labelText: 'Language candidates',
                ),
                validator: (v) {
                  final error = _validate(v);
                  if (error != null) return error;
                  if (_relation != 'unspecified' && _values(v ?? '').length < 2) {
                    return 'This relationship requires at least 2 distinct languages.';
                  }
                  return null;
                },
              ),
              TextFormField(
                controller: _scripts,
                minLines: 2,
                maxLines: 5,
                decoration: const InputDecoration(
                  labelText: 'Script candidates',
                ),
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
                  labelText: 'Reason for declaration',
                ),
                validator: (v) => v == null || v.trim().isEmpty
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
