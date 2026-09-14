import 'package:flutter/material.dart';
import 'administrator_contact.dart';
import 'models.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

Json objectOf(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : {};

class ReviewContext extends StatelessWidget {
  const ReviewContext({super.key, required this.specimen});
  final Specimen specimen;
  @override
  Widget build(BuildContext context) {
    final run = objectOf(specimen.data['run']);
    final classification = objectOf(run['classification']);
    final profile = objectOf(run['profile_snapshot']);
    final asset = specimen.assets.firstOrNull ?? {};
    final quality = objectOf(asset['quality_diagnostics']);
    final metrics = objectOf(quality['metrics']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (quality.isNotEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Server image check',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  Text(
                    '${vocabularyLabel(textOf(quality['status']))} · ${quality['width']} × ${quality['height']} pixels',
                  ),
                  if (metrics.isNotEmpty) ...[
                    Text(
                      'Brightness ${metrics['mean_luminance']} · Contrast ${metrics['contrast_stddev']}',
                    ),
                    Text(
                      'Detail signal ${metrics['mean_neighbor_gradient']} · ${textOf(metrics['algorithm_version'])}',
                    ),
                    const CaveatText(
                      label: 'Not calibrated',
                      why:
                          'A readable image does not prove the labels are legible '
                          'or that all of them are in frame.',
                    ),
                  ],
                  for (final issue in quality['issues'] as List? ?? [])
                    Text('• ${vocabularyLabel(issue.toString())}'),
                  for (final limitation
                      in quality['limitations'] as List? ?? [])
                    Text(
                      limitation == 'no_heic_or_raw_decoder' &&
                              asset['processing_derivative'] is Map
                          ? 'Quality measurements use the decoded preview. This measurement stage does not decode HEIC or RAW itself.'
                          : vocabularyLabel(limitation.toString()),
                    ),
                  EvidenceDrawer(
                    title: 'Image measurements and orientation',
                    payload: quality,
                  ),
                ],
              ),
            ),
          ),
        if (classification.isNotEmpty || profile.isNotEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Classification and profile',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  if (classification.isNotEmpty) ...[
                    Text(
                      '${vocabularyLabel(textOf(classification['status']))} · ${vocabularyLabel(textOf(classification['reason']))}',
                    ),
                    Text(
                      classification['synthetic'] == true
                          ? 'Test classifier output'
                          : 'Classifier output',
                    ),
                    if (classification['calibration_version'] == null)
                      const CaveatText(
                        label: 'Not calibrated',
                        why:
                            'Scores order the queue. They are not a measure of '
                            'whether a reading is correct.',
                      )
                    else
                      Text(
                        'Calibration ${classification['calibration_version']}',
                      ),
                    for (final candidate in objects(
                      classification['candidates'],
                    ))
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        child: Text(
                          '${candidate['collection_id']} · Score ${candidate['score']}\n${(candidate['reasons'] as List? ?? []).map((v) => vocabularyLabel(v.toString())).join(', ')}',
                        ),
                      ),
                    EvidenceDrawer(
                      title: 'Classification provenance',
                      payload: classification,
                    ),
                  ],
                  if (profile.isNotEmpty) ...[
                    Text(
                      'Profile ${profile['id']} · Version ${profile['version']}',
                    ),
                    Text(
                      'Schema ${profile['schema_version']} · Policy ${profile['clearance_policy']}',
                    ),
                    Text(
                      profile['institutional_policy_approved'] == true
                          ? 'Profile policy approved in this environment'
                          : 'Institutional policy approval is missing',
                    ),
                    Text(
                      profile['semantics_confirmed'] == true
                          ? 'Field semantics confirmed in this environment'
                          : 'Required field semantics are not confirmed',
                    ),
                    EvidenceDrawer(
                      title: 'Pinned profile dependencies and field rules',
                      payload: profile,
                    ),
                  ],
                  if (run['classification_selection'] != null)
                    EvidenceDrawer(
                      title: 'Recorded classification decision',
                      payload: run['classification_selection'],
                    ),
                  const Text(
                    'A correction starts a new run and replaces the results that '
                    'depend on it. Earlier records stay in history.',
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class ClassificationDialog extends StatefulWidget {
  const ClassificationDialog({
    super.key,
    required this.specimen,
    required this.scope,
  });
  final Specimen specimen;
  final CollectionScope scope;
  @override
  State<ClassificationDialog> createState() => _ClassificationDialogState();
}

class _ClassificationDialogState extends State<ClassificationDialog> {
  final _reason = TextEditingController();
  final _form = GlobalKey<FormState>();
  String? _node;
  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final nodes = objects(widget.scope.configuration['classification_nodes']);
    final profiles = objects(widget.scope.configuration['profiles']);
    final matching = profiles
        .where((p) => p['collection_id'] == _node)
        .toList();
    return AlertDialog(
      title: const Text('Correct classification?'),
      content: SizedBox(
        width: 560,
        child: SingleChildScrollView(
          child: Form(
            key: _form,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Authorized collection: ${widget.scope.name}'),
                const Text(
                  'Choose the classification that resolves a published profile. '
                  'The record stays in this collection.',
                ),
                const SizedBox(height: 12),
                if (nodes.isEmpty) ...<Widget>[
                  const Text(
                    'No classifications were returned. Refresh collection '
                    'access, or ask the person named below.',
                  ),
                  const AdministratorContactLine(),
                ],
                DropdownButtonFormField<String>(
                  initialValue: _node,
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'Classification',
                  ),
                  items: nodes
                      .map(
                        (n) => DropdownMenuItem(
                          value: n['id'].toString(),
                          child: Text(textOf(n['name'], n['id'].toString())),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => setState(() => _node = value),
                  validator: (value) =>
                      value == null ? 'Choose a classification.' : null,
                ),
                for (final profile in matching)
                  Text(
                    'Profile ${profile['id']} · ${profile['version']} · ${profile['state']}',
                  ),
                if (_node != null && matching.isEmpty)
                  const Text(
                    'No published profile is shown for this classification. The server will ask for review if it cannot map one.',
                  ),
                const SizedBox(height: 12),
                const Text(
                  'A new run replaces the results that depend on the profile. '
                  'Earlier evidence and decisions stay in history.',
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
          onPressed: nodes.isEmpty
              ? null
              : () {
                  if (_form.currentState!.validate()) {
                    Navigator.pop(context, <String, dynamic>{
                      'kind': 'classification_correction',
                      'value': widget.scope.collectionId,
                      'profile_collection_id': _node,
                      'reason': _reason.text.trim(),
                    });
                  }
                },
          child: const Text('Correct classification'),
        ),
      ],
    );
  }
}
