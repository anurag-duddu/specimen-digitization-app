import 'package:flutter/material.dart';
import 'models.dart';
import 'review_context.dart';

class LazyEvidence extends StatefulWidget {
  const LazyEvidence({
    super.key,
    required this.label,
    required this.load,
    required this.render,
  });
  final String label;
  final Future<Json> Function() load;
  final Widget Function(Json) render;
  @override
  State<LazyEvidence> createState() => _LazyEvidenceState();
}

class _LazyEvidenceState extends State<LazyEvidence> {
  Json? _data;
  String? _error;
  bool _busy = false;
  Future<void> _load() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = await widget.load();
      if (mounted) setState(() => _data = result);
    } catch (e) {
      if (mounted) {
        setState(
          () => _error = e is ApiFailure
              ? e.message
              : 'Evidence could not be loaded. Retry or check current collection access.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (_data == null)
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton(
            onPressed: _busy ? null : _load,
            child: Text(
              _busy
                  ? 'Loading evidence…'
                  : _error == null
                  ? widget.label
                  : 'Retry ${widget.label.toLowerCase()}',
            ),
          ),
        ),
      if (_error != null) Semantics(liveRegion: true, child: Text(_error!)),
      if (_data != null) widget.render(_data!),
    ],
  );
}

class EvidencePanel extends StatelessWidget {
  const EvidencePanel({
    super.key,
    required this.specimen,
    required this.load,
    required this.onChange,
    required this.canReview,
  });
  final Specimen specimen;
  final Future<Json> Function(ArtifactRequest) load;
  final Future<void> Function(Json) onChange;
  final bool canReview;
  Future<void> _select(
    BuildContext context,
    Json metadata,
    Json candidate,
  ) async {
    final reason = TextEditingController();
    final form = GlobalKey<FormState>();
    final result = await showDialog<Json>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Select authority candidate'),
        content: SizedBox(
          width: 560,
          child: SingleChildScrollView(
            child: Form(
              key: form,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '${labelOf(textOf(metadata['field_key']))}: ${candidate['name']}',
                  ),
                  SelectableText(textOf(candidate['identifier'])),
                  if (candidate['identity'] != null)
                    EvidenceDetails(
                      title: 'Qualified authority identity',
                      value: candidate['identity'],
                    ),
                  const Text(
                    'This selects a retained authority candidate, preserves the literal field and reruns dependent validation. It does not grant final approval.',
                  ),
                  TextFormField(
                    controller: reason,
                    minLines: 2,
                    maxLines: 4,
                    decoration: const InputDecoration(
                      labelText: 'Reason for selecting this authority',
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
              if (form.currentState!.validate()) {
                Navigator.pop(context, <String, dynamic>{
                  'kind': 'authority_resolution',
                  'target_id': metadata['field_key'],
                  'tool_id': metadata['tool_id'],
                  'identifier': candidate['identifier'],
                  'reason': reason.text.trim(),
                });
              }
            },
            child: const Text('Select and revalidate'),
          ),
        ],
      ),
    );
    await Future<void>.delayed(const Duration(milliseconds: 250));
    reason.dispose();
    if (result != null && context.mounted) await onChange(result);
  }

  Widget _authority(BuildContext context, Json metadata, Json result) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(
        '${labelOf(textOf(result['status']))} · Source ${result['source_id']} · ${result['source_version']}',
      ),
      Text(
        'Retrieved ${result['retrieved_at']} · Adapter ${result['adapter_version']}',
      ),
      Text('Literal input: ${textOf(result['literal'])}'),
      if (result['retry_after_seconds'] != null)
        Text(
          'Provider retry instruction: ${result['retry_after_seconds']} seconds',
        ),
      for (final reason in result['reasons'] as List? ?? [])
        Text('• ${labelOf(reason.toString())}'),
      for (final candidate in objects(result['candidates']))
        Card.outlined(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  textOf(candidate['name']),
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                SelectionArea(child: Text(textOf(candidate['identifier']))),
                Text(
                  '${labelOf(textOf(candidate['relation']))}: ${textOf(candidate['reason'])}',
                ),
                EvidenceDetails(
                  title: 'Candidate identity, context and support',
                  value: candidate,
                ),
                if (canReview &&
                    ['success', 'ambiguous'].contains(result['status']) &&
                    (metadata['tool_id'] != 'parties' ||
                        candidate['identity'] != null))
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton(
                      onPressed: () => _select(context, metadata, candidate),
                      child: const Text('Select this candidate'),
                    ),
                  ),
              ],
            ),
          ),
        ),
      if (objects(result['candidates']).isEmpty)
        const Text('No retained candidate is available for selection.'),
      EvidenceDetails(
        title: 'Authority query and captured evidence',
        value: result,
      ),
      if (result['raw_ref'] != null)
        LazyEvidence(
          key: ValueKey(
            'raw:${specimen.id}:${specimen.revision}:${metadata['tool_id']}:${metadata['field_key']}',
          ),
          label: 'Read raw authority response',
          load: () => load(
            ArtifactRequest(
              ArtifactKind.authorityRaw,
              textOf(metadata['tool_id']),
              fieldKey: textOf(metadata['field_key']),
              sha256: result['response_sha256'] as String?,
            ),
          ),
          render: (raw) =>
              EvidenceDetails(title: 'Raw authority response', value: raw),
        ),
    ],
  );
  @override
  Widget build(BuildContext context) {
    final run = objectOf(specimen.data['run']);
    final phases = objectOf(run['phase_results']);
    final authorities = objectOf(run['authority_results']);
    final risk = objectOf(run['review_risk']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (risk.isNotEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Review risk${risk['calibrated'] == true ? '' : ' (uncalibrated)'}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  Text(
                    risk['composite'] == null
                        ? 'Unmeasured'
                        : '${risk['composite']} / 100',
                  ),
                  const Text(
                    'Prioritization only. Scores never override coverage, evidence or validation gates.',
                  ),
                  for (final component in objects(risk['components']))
                    Builder(
                      builder: (context) {
                        final signal = objectOf(component['signal']);
                        return Text(
                          '${labelOf(textOf(signal['code']))} · ${signal['count'] ?? 'Unmeasured'} · Contribution ${component['contribution'] ?? 'Unmeasured'}\n${textOf(signal['reason'], '')}',
                        );
                      },
                    ),
                  if (risk['unmeasured'] != null)
                    Text('Unmeasured: ${risk['unmeasured']}'),
                  EvidenceDetails(
                    title: 'Risk components, versions and calibration',
                    value: risk,
                  ),
                ],
              ),
            ),
          ),
        if (phases.isNotEmpty)
          Text(
            'Evidence phases',
            style: Theme.of(context).textTheme.titleMedium,
          ),
        for (final name in [
          'parse',
          'plan',
          'lookup',
          'resolve',
          'normalize',
          'validate',
          'finalize',
        ])
          if (phases[name] != null)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Builder(
                  builder: (context) {
                    final metadata = objectOf(phases[name]);
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          '${labelOf(name)} · ${labelOf(textOf(metadata['applicability']))}',
                        ),
                        Text(labelOf(textOf(metadata['reason']))),
                        for (final finding in objects(metadata['findings']))
                          Text(
                            '${finding['severity']}: ${labelOf(textOf(finding['code']))} ${textOf(finding['field_key'], '')}',
                          ),
                        LazyEvidence(
                          key: ValueKey(
                            'phase:${specimen.id}:${specimen.revision}:$name',
                          ),
                          label: 'Read $name evidence',
                          load: () =>
                              load(ArtifactRequest(ArtifactKind.phase, name)),
                          render: (result) => Column(
                            children: [
                              for (final proposal in objects(
                                result['proposals'],
                              ))
                                ListTile(
                                  title: Text(
                                    labelOf(textOf(proposal['field_key'])),
                                  ),
                                  subtitle: Text(
                                    'Literal: ${proposal['literal']}\nCandidate: ${proposal['candidate']}\n${labelOf(textOf(proposal['relation']))}: ${textOf(proposal['reason'])}',
                                  ),
                                ),
                              EvidenceDetails(
                                title: 'Complete $name result',
                                value: result,
                              ),
                            ],
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ),
            ),
        for (final value in authorities.values)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Builder(
                builder: (context) {
                  final metadata = objectOf(value);
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        '${labelOf(textOf(metadata['field_key']))} · ${metadata['tool_id']} · ${labelOf(textOf(metadata['status']))}',
                      ),
                      LazyEvidence(
                        key: ValueKey(
                          'authority:${specimen.id}:${specimen.revision}:${metadata['tool_id']}:${metadata['field_key']}',
                        ),
                        label: 'Read authority alternatives',
                        load: () => load(
                          ArtifactRequest(
                            ArtifactKind.authority,
                            textOf(metadata['tool_id']),
                            fieldKey: textOf(metadata['field_key']),
                          ),
                        ),
                        render: (result) =>
                            _authority(context, metadata, result),
                      ),
                    ],
                  );
                },
              ),
            ),
          ),
      ],
    );
  }
}
