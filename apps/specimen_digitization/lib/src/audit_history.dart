import 'dart:convert';
import 'package:flutter/material.dart';
import 'models.dart';
import 'large_record.dart';

/// Historical snapshots are read-only and never replace the active review model.
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
  final _revisions = <Json>[];
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
      final page = await widget.loadPage!(
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
    final generation = ++_generation;
    setState(() {
      _requestedRevision = revision;
      _runId = runId;
      _runSha256 = runSha256;
      _historical = null;
      _recordError = null;
      _loadingRecord = true;
    });
    try {
      final record = await widget.loadRevision!(revision, runId, runSha256);
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

  Widget _json(Json value) => SelectionArea(
    child: Text(
      const JsonEncoder.withIndent('  ').convert(value),
      style: Theme.of(
        context,
      ).textTheme.bodySmall?.copyWith(fontFamily: 'monospace'),
    ),
  );

  Widget _event(Json event, int sequence) {
    final before = event['before'];
    final reference =
        before is Map &&
            before['specimen_id'] == widget.specimen.id &&
            before['revision'] is int
        ? before['revision'] as int
        : null;
    return ExpansionTile(
      title: Text('$sequence · ${labelOf(textOf(event['action']))}'),
      subtitle: Text(
        '${textOf(event['created_at'])} · ${textOf(event['actor_id'], textOf(event['actor']))}',
      ),
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _json(event),
              if (reference != null &&
                  reference > 0 &&
                  reference <= widget.specimen.revision)
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: widget.loadRevision == null
                        ? null
                        : () => _open(
                            reference,
                            runId: textOf(before['run_id']),
                            runSha256: textOf(before['run_sha256']),
                          ),
                    icon: const Icon(Icons.history),
                    label: Text('Read prior record · revision $reference'),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _card(String title, List<Widget> children) => Card(
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    ),
  );

  Widget _historicalRecord(
    Specimen record,
  ) => _card('Historical revision ${record.revision} · read only', [
    const Text(
      'This retained record is historical evidence. It cannot be edited or used as the current review revision.',
    ),
    const SizedBox(height: 8),
    Text(
      'Current review remains revision ${widget.specimen.revision}. Historical status: ${record.status}.',
    ),
    Text(
      'Profile ${record.profile} · Record ${textOf(record.data['record_version_id'])}',
    ),
    if (record.data['history_through_revision'] != null)
      Text(
        'Earlier history through revision ${record.data['history_through_revision']} is retained in the revision browser below.',
      ),
    if (record.data['artifact_receipt'] is Map)
      LargeRecordEvidence(
        key: ValueKey('historical:${record.id}:${record.revision}'),
        specimen: record,
        load: widget.loadArtifact == null
            ? null
            : (request) => widget.loadArtifact!(record, request),
      )
    else ...[
      ExpansionTile(
        title: const Text('Source asset and pinned run evidence'),
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: _json({
              'asset': record.data['asset'],
              'run': record.data['run'],
            }),
          ),
        ],
      ),
      ExpansionTile(
        title: const Text('Independent readings and transcriptions'),
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: _json({
              'observations': record.observations,
              'transcriptions': record.data['transcriptions'],
            }),
          ),
        ],
      ),
      ExpansionTile(
        title: const Text('Fields, authority evidence and validation'),
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: _json({
              'fields': record.fields,
              'evidence': record.evidence,
              'validations': record.findings,
            }),
          ),
        ],
      ),
      ExpansionTile(
        title: const Text('Complete retained workspace'),
        children: [
          Padding(padding: const EdgeInsets.all(12), child: _json(record.data)),
        ],
      ),
    ],
    const SizedBox(height: 12),
    Text(
      'Retained audit events · revision ${record.revision}',
      style: Theme.of(context).textTheme.titleSmall,
    ),
    if (record.audit.isEmpty)
      const Text(
        'No inline events in this revision. Use earlier revisions to inspect retained history.',
      ),
    ...record.audit.indexed.map(
      (entry) => _event(
        entry.$2,
        (record.data['audit_offset'] as int? ?? 0) + entry.$1 + 1,
      ),
    ),
    TextButton(
      onPressed: () => setState(() {
        _historical = null;
        _requestedRevision = null;
        ++_generation;
      }),
      child: const Text('Close historical record'),
    ),
  ]);

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      _card('Current decision history', [
        Text('Current review revision ${widget.specimen.revision}'),
        if (widget.specimen.data['history_through_revision'] != null)
          Text(
            'Earlier audit and run evidence through revision ${widget.specimen.data['history_through_revision']} is retained in immutable record history. Browse revisions below for the complete prior record.',
          ),
        if (widget.specimen.audit.isEmpty)
          const Text('No inline audit events in the current snapshot.'),
        ...widget.specimen.audit.indexed.map(
          (entry) => _event(
            entry.$2,
            (widget.specimen.data['audit_offset'] as int? ?? 0) + entry.$1 + 1,
          ),
        ),
      ]),
      if (_loadingRecord)
        Semantics(
          liveRegion: true,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Text('Loading historical revision $_requestedRevision…'),
          ),
        ),
      if (_recordError != null)
        _card('Historical record unavailable', [
          Semantics(liveRegion: true, child: Text(_recordError!)),
          TextButton(
            onPressed: _requestedRevision == null
                ? null
                : () => _open(
                    _requestedRevision!,
                    runId: _runId,
                    runSha256: _runSha256,
                  ),
            child: const Text('Retry historical record'),
          ),
        ]),
      if (_historical != null) _historicalRecord(_historical!),
      _card('Browse retained record revisions', [
        Text(
          'History is bounded through the current review revision ${widget.specimen.revision}. Opening a revision rechecks your current access.',
        ),
        const SizedBox(height: 12),
        if (widget.loadPage == null || widget.loadRevision == null)
          const Text(
            'Historical retrieval is unavailable in this client connection.',
          ),
        ..._revisions.map(
          (item) => ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text('Revision ${item['revision']}'),
            subtitle: Text('Snapshot SHA-256 ${item['sha256']}'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => _open(item['revision'] as int),
          ),
        ),
        if (_pageError != null)
          Semantics(liveRegion: true, child: Text(_pageError!)),
        if (_started && _cursor == null)
          const Text('All revisions through this review snapshot are listed.'),
        if (!_started || _cursor != null)
          Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton.icon(
              onPressed: _loadingPage || widget.loadPage == null ? null : _more,
              icon: const Icon(Icons.history),
              label: Text(
                _loadingPage
                    ? 'Loading revisions…'
                    : _pageError != null
                    ? 'Retry history page'
                    : _started
                    ? 'Load more revisions'
                    : 'Browse record revisions',
              ),
            ),
          ),
      ]),
    ],
  );
}
