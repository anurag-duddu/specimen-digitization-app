/// Decision history and the version browser (screen blueprints, 6.5).
///
/// The timeline says who did what, in plain words, with their reason, the
/// version it landed on and how long ago. The version browser lists a version
/// with its date, its actor and a one line summary rather than a number and a
/// hash. Raw JSON is one disclosure per event and nothing else.
///
/// Historical snapshots are read-only and never replace the active review
/// model.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'large_record.dart';
import 'models.dart';
import 'screens/workbench/moments.dart';
import 'theme/icons.dart';
import 'theme/motion.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

/// One audit event, in the words a reviewer uses.
///
/// `"Corrected locality"` rather than `field_correction`, and never a raw
/// enum in the first sentence (audit finding H8.1).
String auditActionLabel(Json event) {
  final String action = textOf(event['action'], 'change');
  final String target = textOf(event['target_id'], '');
  final String named = vocabularyLabel(action);
  if (target.isEmpty || target == 'Not recorded') return named;
  return '$named: ${vocabularyLabel(target)}';
}

class AuditHistoryPanel extends StatefulWidget {
  const AuditHistoryPanel({
    super.key,
    required this.specimen,
    this.loadPage,
    this.loadRevision,
    this.loadArtifact,
  });
  final Specimen specimen;
  final Future<Json> Function(Specimen, ArtifactRequest)? loadArtifact;
  final Future<HistoryPage> Function(int afterRevision, int throughRevision)?
  loadPage;
  final Future<Specimen> Function(
    int revision,
    String? runId,
    String? runSha256,
  )?
  loadRevision;
  @override
  State<AuditHistoryPanel> createState() => _AuditHistoryPanelState();
}

class _AuditHistoryPanelState extends State<AuditHistoryPanel> {
  final List<Json> _revisions = <Json>[];
  int? _cursor;
  bool _started = false;
  bool _loadingPage = false;
  bool _loadingRecord = false;
  String? _pageError;
  String? _recordError;
  Specimen? _historical;
  int? _requestedRevision;
  int _generation = 0;
  String? _runId;
  String? _runSha256;

  String _message(Object e) => e is ApiFailure
      ? e.message
      : 'History could not be loaded. Check your connection and retry.';

  Future<void> _more() async {
    if (_loadingPage || widget.loadPage == null) return;
    setState(() {
      _loadingPage = true;
      _pageError = null;
    });
    try {
      final HistoryPage page = await widget.loadPage!(
        _cursor ?? 0,
        widget.specimen.revision,
      );
      if (!mounted) return;
      setState(() {
        _revisions.addAll(page.items);
        _cursor = page.nextCursor;
        _started = true;
        _loadingPage = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _loadingPage = false;
          _pageError = _message(e);
        });
      }
    }
  }

  Future<void> _open(int revision, {String? runId, String? runSha256}) async {
    if (widget.loadRevision == null ||
        revision < 1 ||
        revision > widget.specimen.revision) {
      return;
    }
    final int generation = ++_generation;
    setState(() {
      _requestedRevision = revision;
      _runId = runId;
      _runSha256 = runSha256;
      _historical = null;
      _recordError = null;
      _loadingRecord = true;
    });
    try {
      final Specimen record = await widget.loadRevision!(
        revision,
        runId,
        runSha256,
      );
      if (mounted && generation == _generation) {
        setState(() {
          _historical = record;
          _loadingRecord = false;
        });
      }
    } catch (e) {
      if (mounted && generation == _generation) {
        setState(() {
          _recordError = _message(e);
          _loadingRecord = false;
        });
      }
    }
  }

  /// One decision, as a timeline entry.
  Widget _event(Json event, int sequence) {
    final ThemeData theme = Theme.of(context);
    final Object? before = event['before'];
    final int? reference =
        before is Map &&
            before['specimen_id'] == widget.specimen.id &&
            before['revision'] is int
        ? before['revision'] as int
        : null;
    final String reason = textOf(event['reason'], '');
    final String actor = textOf(
      event['actor_id'],
      textOf(event['actor'], 'Not recorded'),
    );

    return Semantics(
      container: true,
      child: Padding(
        padding: EdgeInsets.only(bottom: context.space.space3),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Padding(
              padding: EdgeInsets.only(top: context.space.space1),
              child: Icon(
                event['actor_id'] == null
                    ? SpecimenIconography.processing
                    : SpecimenIconography.humanDecision,
                size: context.sizes.iconInline,
                color: context.tokens.evidenceHumanContent,
              ),
            ),
            SizedBox(width: context.space.space2),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    '$sequence · ${auditActionLabel(event)}',
                    style: theme.textTheme.titleSmall,
                  ),
                  Text(
                    '$actor · ${citedInstant(event['created_at'])}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  if (reason.isNotEmpty && reason != 'Not recorded')
                    Text('Reason: $reason'),
                  if (event['revision'] != null)
                    Text(
                      'Version ${event['revision']}',
                      style: theme.textTheme.bodySmall,
                    ),
                  if (reference != null &&
                      reference > 0 &&
                      reference <= widget.specimen.revision)
                    Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: TextButton.icon(
                        onPressed: widget.loadRevision == null
                            ? null
                            : () => _open(
                                reference,
                                runId: textOf((before! as Map)['run_id']),
                                runSha256: textOf(
                                  (before as Map)['run_sha256'],
                                ),
                              ),
                        icon: const Icon(Symbols.history),
                        label: Text('Open version $reference'),
                      ),
                    ),
                  EvidenceDrawer(payload: event),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _card(String title, List<Widget> children) => Card(
    child: Padding(
      padding: EdgeInsets.all(context.space.space4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          SizedBox(height: context.space.space2),
          ...children,
        ],
      ),
    ),
  );

  Widget _historicalRecord(Specimen record) =>
      _card('Version ${record.revision} · read only', <Widget>[
        const Text('This is a past version. It is read only.'),
        SizedBox(height: context.space.space1),
        Text(
          'Your current review is on version ${widget.specimen.revision}. '
          'This version: ${record.status}.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        Text(
          'Profile ${record.profile} · Record '
          '${textOf(record.data['record_version_id'])}',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        if (record.data['history_through_revision'] != null)
          Text(
            'Earlier history through version '
            '${record.data['history_through_revision']} is in the version '
            'browser below.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        if (record.data['artifact_receipt'] is Map)
          LargeRecordEvidence(
            key: ValueKey<String>('historical:${record.id}:${record.revision}'),
            specimen: record,
            load: widget.loadArtifact == null
                ? null
                : (ArtifactRequest request) =>
                      widget.loadArtifact!(record, request),
          )
        else ...<Widget>[
          EvidenceDrawer(
            title: 'Source asset and pinned run evidence',
            payload: <String, dynamic>{
              'asset': record.data['asset'],
              'run': record.data['run'],
            },
          ),
          EvidenceDrawer(
            title: 'Independent readings and transcriptions',
            payload: <String, dynamic>{
              'observations': record.observations,
              'transcriptions': record.data['transcriptions'],
            },
          ),
          EvidenceDrawer(
            title: 'Fields, authority evidence and validation',
            payload: <String, dynamic>{
              'fields': record.fields,
              'evidence': record.evidence,
              'validations': record.findings,
            },
          ),
          EvidenceDrawer(
            title: 'Complete retained workspace',
            payload: record.data,
          ),
        ],
        SizedBox(height: context.space.space3),
        Text(
          'Audit events · version ${record.revision}',
          style: Theme.of(context).textTheme.titleSmall,
        ),
        if (record.audit.isEmpty)
          const Text(
            'No events in this version. Open earlier versions to see more '
            'history.',
          ),
        ...record.audit.indexed.map(
          ((int, Json) entry) => _event(
            entry.$2,
            (record.data['audit_offset'] as int? ?? 0) + entry.$1 + 1,
          ),
        ),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: TextButton(
            onPressed: () => setState(() {
              _historical = null;
              _requestedRevision = null;
              ++_generation;
            }),
            child: const Text('Close past version'),
          ),
        ),
      ]);

  /// One line saying what a version changed, built from the event the server
  /// already returned rather than from the hash.
  String _revisionSummary(Json item) {
    final String actor = textOf(
      item['actor_id'],
      textOf(item['actor'], 'Not recorded'),
    );
    final String action = item['action'] == null
        ? 'Saved'
        : auditActionLabel(item);
    return '$action · $actor';
  }

  @override
  Widget build(BuildContext context) {
    final MotionTokens motion = context.motion;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _card('Current decision history', <Widget>[
          Text(
            'Current review version ${widget.specimen.revision}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (widget.specimen.data['history_through_revision'] != null)
            Text(
              'Earlier audit and run evidence through version '
              '${widget.specimen.data['history_through_revision']} is kept in '
              'record history. Browse versions below for the complete earlier '
              'record.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          SizedBox(height: context.space.space2),
          if (widget.specimen.audit.isEmpty)
            const Text('No audit events in the current snapshot.'),
          ...widget.specimen.audit.indexed.map(
            ((int, Json) entry) => _event(
              entry.$2,
              (widget.specimen.data['audit_offset'] as int? ?? 0) +
                  entry.$1 +
                  1,
            ),
          ),
        ]),
        if (_loadingRecord)
          Semantics(
            liveRegion: true,
            child: Padding(
              padding: EdgeInsets.all(context.space.space4),
              child: Text('Loading version $_requestedRevision'),
            ),
          ),
        if (_recordError != null)
          _card('Past version unavailable', <Widget>[
            Semantics(liveRegion: true, child: Text(_recordError!)),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: TextButton(
                onPressed: _requestedRevision == null
                    ? null
                    : () => _open(
                        _requestedRevision!,
                        runId: _runId,
                        runSha256: _runSha256,
                      ),
                child: const Text('Retry loading version'),
              ),
            ),
          ]),
        // Moving back through time is not a peer relationship, so the panel
        // cross-fades rather than sliding (motion catalog row 57).
        AnimatedSwitcher(
          duration: motion.standard,
          switchInCurve: MotionTokens.standardCurve,
          child: _historical == null
              ? const SizedBox(width: double.infinity)
              : KeyedSubtree(
                  key: ValueKey<int>(_historical!.revision),
                  child: _historicalRecord(_historical!),
                ),
        ),
        _card('Record versions', <Widget>[
          Text(
            'History goes up to your current review version '
            '${widget.specimen.revision}. Opening a version rechecks your '
            'access.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          SizedBox(height: context.space.space2),
          if (widget.loadPage == null || widget.loadRevision == null)
            const Text('Past versions cannot be loaded on this connection.'),
          ..._revisions.map(
            (Json item) => ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text('Version ${item['revision']}'),
              subtitle: Text(
                <String>[
                  citedInstant(item['created_at']),
                  _revisionSummary(item),
                ].join(' · '),
              ),
              trailing: const Icon(Symbols.chevron_right),
              onTap: () => _open(item['revision'] as int),
            ),
          ),
          if (_pageError != null)
            Semantics(liveRegion: true, child: Text(_pageError!)),
          if (_started && _cursor == null)
            Text(
              'All versions through this snapshot are listed.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          if (!_started || _cursor != null)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: OutlinedButton.icon(
                onPressed: _loadingPage || widget.loadPage == null
                    ? null
                    : _more,
                icon: const Icon(Symbols.history),
                label: Text(
                  _loadingPage
                      ? 'Loading versions'
                      : _pageError != null
                      ? 'Retry history page'
                      : _started
                      ? 'Load more versions'
                      : 'Browse record versions',
                ),
              ),
            ),
        ]),
      ],
    );
  }
}
