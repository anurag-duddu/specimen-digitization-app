import 'dart:convert';
import 'package:flutter/material.dart';
import 'models.dart';

Json objectOf(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : {};

class EvidenceDetails extends StatelessWidget {
  const EvidenceDetails({super.key, required this.title, required this.value});
  final String title;
  final Object? value;
  @override
  Widget build(BuildContext context) => ExpansionTile(
    title: Text(title),
    children: [
      Padding(
        padding: const EdgeInsets.all(12),
        child: SelectionArea(
          child: Text(
            const JsonEncoder.withIndent('  ').convert(value),
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(fontFamily: 'monospace'),
          ),
        ),
      ),
    ],
  );
}

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
                    '${labelOf(textOf(quality['status']))} · ${quality['width']} × ${quality['height']} pixels',
                  ),
                  if (metrics.isNotEmpty) ...[
                    Text(
                      'Brightness ${metrics['mean_luminance']} · Contrast ${metrics['contrast_stddev']}',
                    ),
                    Text(
                      'Detail signal ${metrics['mean_neighbor_gradient']} · ${textOf(metrics['algorithm_version'])}',
                    ),
                    const Text(
                      'Uncalibrated measurements. A valid image is not proof of readable labels or complete coverage.',
                    ),
                  ],
                  for (final issue in quality['issues'] as List? ?? [])
                    Text('• ${labelOf(issue.toString())}'),
                  for (final limitation
                      in quality['limitations'] as List? ?? [])
                    Text(
                      limitation == 'no_heic_or_raw_decoder' &&
                              asset['processing_derivative'] is Map
                          ? 'Quality measurements use the decoded preview. This measurement stage does not decode HEIC or RAW itself.'
                          : labelOf(limitation.toString()),
                    ),
                  EvidenceDetails(
                    title: 'Image measurements and orientation',
                    value: quality,
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
                    'Classification and pinned profile',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  if (classification.isNotEmpty) ...[
                    Text(
                      '${labelOf(textOf(classification['status']))} · ${labelOf(textOf(classification['reason']))}',
                    ),
                    Text(
                      classification['synthetic'] == true
                          ? 'Synthetic classifier output'
                          : 'Classifier output',
                    ),
                    Text(
                      classification['calibration_version'] == null
                          ? 'Scores are uncalibrated; they do not establish correctness.'
                          : 'Calibration ${classification['calibration_version']}',
                    ),
                    for (final candidate in objects(
                      classification['candidates'],
                    ))
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        child: Text(
                          '${candidate['collection_id']} · Score ${candidate['score']}\n${(candidate['reasons'] as List? ?? []).map((v) => labelOf(v.toString())).join('; ')}',
                        ),
                      ),
                    EvidenceDetails(
                      title: 'Classification provenance',
                      value: classification,
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
                          : 'Institutional policy approval missing',
                    ),
                    Text(
                      profile['semantics_confirmed'] == true
                          ? 'Field semantics confirmed in this environment'
                          : 'Required field semantics remain unconfirmed',
                    ),
                    EvidenceDetails(
                      title: 'Pinned profile dependencies and field rules',
                      value: profile,
                    ),
                  ],
                  if (run['classification_selection'] != null)
                    EvidenceDetails(
                      title: 'Recorded classification decision',
                      value: run['classification_selection'],
                    ),
                  const Text(
                    'Classification corrections create a new run and supersede affected downstream results. Prior records remain in history.',
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
      title: const Text('Confirm collection classification'),
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
                  'Select the classification used to resolve a published profile. This decision does not transfer the record to another collection.',
                ),
                const SizedBox(height: 12),
                if (nodes.isEmpty)
                  const Text(
                    'No classification choices were returned. Refresh collection access or contact your administrator.',
                  ),
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
                    'No published profile is shown for this classification. The server will require review if mapping is unavailable.',
                  ),
                const SizedBox(height: 12),
                const Text(
                  'Saving starts a new run and invalidates profile-dependent results. Previous evidence and decisions remain retained.',
                ),
                TextFormField(
                  controller: _reason,
                  minLines: 2,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    labelText: 'Classification reason',
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
          child: const Text('Select profile and rerun'),
        ),
      ],
    );
  }
}
