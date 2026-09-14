/// Authority evidence and phase results (screen blueprints, 6.4).
///
/// Authority candidates are cards with a name, an identifier, a relation and
/// one action; phase results are a stepped list with a lazy "View evidence"
/// that renders typed proposals. Raw JSON stays behind the shared disclosure
/// (audit finding H8.1, severity 4).
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'models.dart';
import 'review_context.dart';
import 'risk_assessment.dart';
import 'screens/workbench/moments.dart';
import 'theme/icons.dart';
import 'theme/motion.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

/// The phases the server runs, in the order it runs them.
const List<String> evidencePhases = <String>[
  'parse',
  'plan',
  'lookup',
  'resolve',
  'normalize',
  'validate',
  'finalize',
];

/// A payload fetched only when the reviewer asks for it.
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
      final Json result = await widget.load();
      if (mounted) setState(() => _data = result);
    } catch (e) {
      if (mounted) {
        setState(
          () => _error = e is ApiFailure
              ? e.message
              : 'Evidence could not be loaded. Retry or check current '
                    'collection access.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final MotionTokens motion = context.motion;
    final Widget content = _data == null
        ? const SizedBox(width: double.infinity)
        : widget.render(_data!);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (_data == null)
          Align(
            alignment: AlignmentDirectional.centerStart,
            // The footprint does not move while the request is out: the label
            // swaps for an inline indicator of the same height (motion 44).
            child: OutlinedButton.icon(
              onPressed: _busy ? null : _load,
              icon: _busy
                  ? SizedBox.square(
                      dimension: context.sizes.iconInline,
                      child: CircularProgressIndicator(
                        strokeWidth: context.shape.strokeEmphasis,
                      ),
                    )
                  : Icon(
                      _error == null ? Symbols.visibility : Symbols.refresh,
                      size: context.sizes.iconInline,
                    ),
              label: Text(
                _busy
                    ? 'Loading evidence'
                    : _error == null
                    ? widget.label
                    : 'Retry ${widget.label.toLowerCase()}',
              ),
            ),
          ),
        if (_error != null)
          Semantics(
            liveRegion: true,
            child: Text(
              _error!,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Theme.of(context).colorScheme.error,
              ),
            ),
          ),
        if (motion.reduced)
          content
        else
          AnimatedSize(
            duration: motion.standard,
            curve: MotionTokens.enterCurve,
            alignment: Alignment.topLeft,
            child: content,
          ),
      ],
    );
  }
}

/// Risk, the phase stepper, and the authority results.
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
    final String? reason = await showReasonSheet(
      context,
      title: 'Use this match?',
      action: AuthorityCandidateCard.useLabel,
      consequence:
          'The saved authority match is applied to '
          '${vocabularyLabel(textOf(metadata['field_key']))} and the checks '
          'that depend on it run again.',
      retained:
          'The text as written is unchanged and the record is not approved.',
    );
    if (reason == null || !context.mounted) return;
    await onChange(<String, dynamic>{
      'kind': 'authority_resolution',
      'target_id': metadata['field_key'],
      'tool_id': metadata['tool_id'],
      'identifier': candidate['identifier'],
      'reason': reason,
    });
  }

  Widget _authority(BuildContext context, Json metadata, Json result) {
    final ThemeData theme = Theme.of(context);
    final List<Json> candidates = objects(result['candidates']);
    final bool usable =
        canReview &&
        <String>['success', 'ambiguous'].contains(result['status']);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          '${vocabularyLabel(textOf(result['status']))} · Source '
          '${textOf(result['source_id'])} · ${textOf(result['source_version'])}',
          style: theme.textTheme.bodySmall,
        ),
        Text(
          'Retrieved ${relativeInstant(result['retrieved_at'])} · Adapter '
          '${textOf(result['adapter_version'])}',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        Text('As written: ${textOf(result['literal'])}'),
        if (result['retry_after_seconds'] != null)
          Text(
            'Provider retry instruction: ${result['retry_after_seconds']} '
            'seconds',
            style: theme.textTheme.bodySmall,
          ),
        for (final Object? reason in result['reasons'] as List? ?? <Object?>[])
          Text(vocabularyLabel(reason.toString())),
        SizedBox(height: context.space.space2),
        for (final Json candidate in candidates)
          Padding(
            padding: EdgeInsets.only(bottom: context.space.space2),
            child: AuthorityCandidateCard(
              name: textOf(candidate['name']),
              identifier: textOf(candidate['identifier']),
              relation: vocabularyLabel(textOf(candidate['relation'])),
              reason: textOf(candidate['reason'], 'No reason recorded'),
              authorityName: textOf(metadata['tool_id'], 'Authority'),
              raw: candidate,
              onUse:
                  usable &&
                      (metadata['tool_id'] != 'parties' ||
                          candidate['identity'] != null)
                  ? () => _select(context, metadata, candidate)
                  : null,
            ),
          ),
        if (candidates.isEmpty)
          const Text('No saved match is available to use.'),
        EvidenceDrawer(
          title: 'Authority query and captured evidence',
          payload: result,
        ),
        if (result['raw_ref'] != null)
          LazyEvidence(
            key: ValueKey<String>(
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
            render: (Json raw) =>
                EvidenceDrawer(title: 'Raw authority response', payload: raw),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Json run = objectOf(specimen.data['run']);
    final Json phases = objectOf(run['phase_results']);
    final Json authorities = objectOf(run['authority_results']);
    final Json risk = objectOf(run['review_risk']);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (risk.isNotEmpty)
          ReviewRiskPanel(
            risk: risk,
            policy: objectOf(run['risk_policy_snapshot']),
          ),
        if (phases.isNotEmpty) ...<Widget>[
          SizedBox(height: context.space.space4),
          Text('Evidence steps', style: theme.textTheme.titleMedium),
          SizedBox(height: context.space.space2),
          for (final (int i, String name) in evidencePhases.indexed)
            if (phases[name] != null)
              _PhaseStep(
                position: i + 1,
                name: name,
                metadata: objectOf(phases[name]),
                last: name == evidencePhases.last,
                evidence: LazyEvidence(
                  key: ValueKey<String>(
                    'phase:${specimen.id}:${specimen.revision}:$name',
                  ),
                  label: 'View evidence',
                  load: () => load(ArtifactRequest(ArtifactKind.phase, name)),
                  render: (Json result) =>
                      _Proposals(name: name, result: result),
                ),
              ),
        ],
        if (authorities.isNotEmpty) ...<Widget>[
          SizedBox(height: context.space.space4),
          Text('Authority evidence', style: theme.textTheme.titleMedium),
          SizedBox(height: context.space.space2),
          for (final Object? value in authorities.values)
            Builder(
              builder: (BuildContext context) {
                final Json metadata = objectOf(value);
                return Card.outlined(
                  child: Padding(
                    padding: EdgeInsets.all(context.space.space4),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        Text(
                          '${vocabularyLabel(textOf(metadata['field_key']))} · '
                          '${metadata['tool_id']} · '
                          '${vocabularyLabel(textOf(metadata['status']))}',
                          style: theme.textTheme.titleSmall,
                        ),
                        LazyEvidence(
                          key: ValueKey<String>(
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
                          render: (Json result) =>
                              _authority(context, metadata, result),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
        ],
      ],
    );
  }
}

/// One step of the seven phase run, drawn as a step rather than a card so the
/// order and the completion read at a glance.
class _PhaseStep extends StatelessWidget {
  const _PhaseStep({
    required this.position,
    required this.name,
    required this.metadata,
    required this.last,
    required this.evidence,
  });

  final int position;
  final String name;
  final Json metadata;
  final bool last;
  final Widget evidence;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String applicability = textOf(metadata['applicability']);
    final bool blocked = applicability == 'blocked';
    final Color accent = blocked
        ? context.tokens.blockedContent
        : context.tokens.clearedContent;

    return Semantics(
      container: true,
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Column(
              children: <Widget>[
                SizedBox.square(
                  dimension: context.sizes.iconAction,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: accent,
                        width: context.shape.strokeEmphasis,
                      ),
                    ),
                    child: Center(
                      child: Text(
                        '$position',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: accent,
                        ),
                      ),
                    ),
                  ),
                ),
                if (!last)
                  Expanded(
                    child: Container(
                      width: context.shape.strokeEmphasis,
                      color: theme.colorScheme.outlineVariant,
                    ),
                  ),
              ],
            ),
            SizedBox(width: context.space.space3),
            Expanded(
              child: Padding(
                padding: EdgeInsets.only(bottom: context.space.space4),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text(
                      '${vocabularyLabel(name)} · '
                      '${vocabularyLabel(applicability)}',
                      style: theme.textTheme.titleSmall,
                    ),
                    Text(vocabularyLabel(textOf(metadata['reason']))),
                    for (final Json finding in objects(metadata['findings']))
                      Text(
                        '${finding['severity']}: '
                        '${vocabularyLabel(textOf(finding['code']))} '
                        '${textOf(finding['field_key'], '')}',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.error,
                        ),
                      ),
                    evidence,
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The typed rendering of a phase payload.
class _Proposals extends StatelessWidget {
  const _Proposals({required this.name, required this.result});

  final String name;
  final Json result;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<Json> proposals = objects(result['proposals']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (proposals.isEmpty)
          Text(
            'This step proposed nothing.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        for (final Json proposal in proposals)
          Padding(
            padding: EdgeInsets.only(bottom: context.space.space2),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  vocabularyLabel(textOf(proposal['field_key'])),
                  style: theme.textTheme.titleSmall,
                ),
                Text(
                  'As written: ${textOf(proposal['literal'])}',
                  style: context.mono.literalDense,
                ),
                Text('Suggested match: ${textOf(proposal['candidate'])}'),
                Text(
                  '${vocabularyLabel(textOf(proposal['relation']))}: '
                  '${textOf(proposal['reason'])}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        EvidenceDrawer(
          title: 'Complete ${vocabularyLabel(name)} result',
          payload: result,
        ),
      ],
    );
  }
}
