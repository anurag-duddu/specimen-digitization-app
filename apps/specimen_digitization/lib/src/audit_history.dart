/// Retained versions form an append-only timeline. A restore creates a version.
library;

import 'dart:convert';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart' hide FieldLayer;

import 'large_record.dart';
import 'models.dart';
import 'screens/workbench/moments.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

String auditActionLabel(Json event) {
  final action = textOf(event['action'], 'change');
  final named = switch (action) {
    'review_restore_version' =>
      'Restored version ${event['source_revision'] ?? (event['after'] as Map?)?['source_revision'] ?? ''}',
    'review_reset_initial' => 'Reset to initial version',
    'initial_record' => 'Initial record',
    'ingest' => 'Added photograph',
    'transcribe' => 'Transcribed labels',
    'review_field' => 'Edited specimen data',
    'review_transcription' => 'Edited label transcription',
    'review_approve' => 'Approved review',
    _ => vocabularyLabel(action),
  };
  final target = textOf(event['target_id'], '');
  return target.isEmpty ? named : '$named: ${vocabularyLabel(target)}';
}

class AuditHistoryPanel extends StatefulWidget {
  const AuditHistoryPanel({
    super.key,
    required this.specimen,
    this.loadPage,
    this.loadRevision,
    this.loadArtifact,
    this.onRestore,
    this.mutationDisabledReason,
    this.embedded = false,
    this.active = true,
  });
  final Specimen specimen;
  final bool embedded;

  /// A retained hidden panel can finish loading without moving another view.
  final bool active;
  final Future<Json> Function(Specimen, ArtifactRequest)? loadArtifact;
  final Future<HistoryPage> Function(int afterRevision, int throughRevision)?
  loadPage;
  final Future<Specimen> Function(
    int revision,
    String? runId,
    String? runSha256,
  )?
  loadRevision;
  final Future<void> Function(
    int sourceRevision,
    bool resetToInitial,
    String reason,
  )?
  onRestore;
  final String? mutationDisabledReason;

  @override
  State<AuditHistoryPanel> createState() => _AuditHistoryPanelState();
}

class _AuditHistoryPanelState extends State<AuditHistoryPanel> {
  final List<Json> _revisions = [];
  final GlobalKey _previewKey = GlobalKey(
    debugLabel: 'history-version-preview',
  );
  int? _cursor;
  bool _started = false;
  bool _loadingPage = false;
  bool _loadingRecord = false;
  bool _mutating = false;
  bool _submitting = false;
  bool _resetPreview = false;
  String? _pageError;
  String? _recordError;
  Specimen? _historical;
  int? _requestedRevision;
  int _generation = 0;
  int _pageGeneration = 0;
  String? _runId;
  String? _runSha256;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _more();
    });
  }

  @override
  void didUpdateWidget(AuditHistoryPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.specimen.id != widget.specimen.id ||
        oldWidget.specimen.revision != widget.specimen.revision) {
      ++_generation;
      ++_pageGeneration;
      _revisions.clear();
      _cursor = null;
      _started = _loadingPage = _loadingRecord = _resetPreview = false;
      _historical = null;
      _recordError = _pageError = null;
      _requestedRevision = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _more();
      });
    }
  }

  String _message(Object e) =>
      e is ApiFailure ? e.message : 'History could not be loaded. Retry.';
  TextStyle get _line =>
      context.ui.type.bodySmall.copyWith(color: context.ui.color.inkSecondary);

  Future<void> _more() async {
    if (_loadingPage || widget.loadPage == null) return;
    final through = _started ? (_cursor ?? 0) : widget.specimen.revision;
    if (through < 1) return;
    final after = through > 10 ? through - 10 : 0;
    final generation = ++_pageGeneration;
    setState(() {
      _loadingPage = true;
      _pageError = null;
    });
    try {
      final page = await widget.loadPage!(after, through);
      if (!mounted || generation != _pageGeneration) return;
      setState(() {
        _revisions.addAll(page.items.reversed);
        _cursor = after == 0 ? null : after;
        _started = true;
        _loadingPage = false;
      });
    } catch (e) {
      if (mounted && generation == _pageGeneration) {
        setState(() {
          _loadingPage = false;
          _pageError = _message(e);
        });
      }
    }
  }

  Future<void> _open(
    int revision, {
    String? runId,
    String? runSha256,
    bool reset = false,
  }) async {
    if (widget.loadRevision == null ||
        revision < 1 ||
        revision > widget.specimen.revision ||
        _mutating) {
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
      _resetPreview = reset;
    });
    try {
      final record = await widget.loadRevision!(revision, runId, runSha256);
      if (!mounted || generation != _generation) return;
      if (record.id != widget.specimen.id || record.revision != revision) {
        throw const ApiFailure('The requested version could not be verified.');
      }
      setState(() {
        _historical = record;
        _loadingRecord = false;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final preview = _previewKey.currentContext;
        if (mounted &&
            widget.active &&
            generation == _generation &&
            preview != null) {
          Scrollable.ensureVisible(preview, alignment: 0);
        }
      });
    } catch (e) {
      if (mounted && generation == _generation) {
        setState(() {
          _recordError = _message(e);
          _loadingRecord = false;
        });
      }
    }
  }

  Future<void> _restore(Specimen record) async {
    if (_mutating ||
        widget.onRestore == null ||
        widget.mutationDisabledReason != null) {
      return;
    }
    final generation = _generation;
    final reset = _resetPreview;
    setState(() {
      _mutating = true;
      _recordError = null;
    });
    try {
      final reason = await showReasonSheet(
        context,
        title: reset
            ? 'Reset specimen to its initial version?'
            : 'Restore version ${record.revision}?',
        action: reset ? 'Reset specimen' : 'Restore version',
        consequence:
            'Replace the current label and specimen data with version ${record.revision}. Approval and authority matches will need review; processing stays paused.',
        retained: 'The photograph and every saved version remain in history.',
        reversal:
            'This creates a new version. You can restore another saved version later.',
      );
      if (reason == null ||
          !mounted ||
          generation != _generation ||
          widget.mutationDisabledReason != null) {
        return;
      }
      setState(() {
        _submitting = true;
      });
      await widget.onRestore!(record.revision, reset, reason);
    } catch (e) {
      if (mounted && generation == _generation) {
        setState(() {
          _recordError = e is ApiFailure
              ? e.message
              : 'This version could not be restored. Retry.';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _mutating = false;
          _submitting = false;
        });
      }
    }
  }

  Widget _card(String title, List<Widget> children) {
    final ui = context.ui;
    final section = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(header: true, child: Text(title, style: ui.type.title)),
        SizedBox(height: ui.space.s2),
        ...children,
      ],
    );
    return Padding(
      padding: EdgeInsets.only(bottom: ui.space.s4),
      child: widget.embedded
          ? section
          : Surface(
              radius: ui.shape.tile,
              hairline: true,
              padding: EdgeInsets.all(ui.space.s3),
              child: section,
            ),
    );
  }

  Widget _event(Json event) {
    final before = event['before'];
    final revision =
        before is Map && before['specimen_id'] == widget.specimen.id
        ? before['revision']
        : null;
    return Padding(
      padding: EdgeInsets.only(bottom: context.ui.space.s2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(auditActionLabel(event), style: context.ui.type.label),
          Text(
            '${textOf(event['actor_id'], textOf(event['actor'], 'Unknown actor'))} · ${citedInstant(event['created_at'])}',
            style: _line,
          ),
          if (textOf(event['reason'], '').isNotEmpty)
            Text(textOf(event['reason']), style: context.ui.type.body),
          if (revision is int &&
              revision > 0 &&
              revision <= widget.specimen.revision)
            UiButton(
              label: 'Open version $revision',
              variant: UiButtonVariant.ghost,
              onPressed: widget.loadRevision == null || _mutating
                  ? null
                  : () => _open(
                      revision,
                      runId: before['run_sha256'] is String
                          ? before['run_id'] as String?
                          : null,
                      runSha256: before['run_sha256'] as String?,
                    ),
            ),
          EvidenceDrawer(payload: event, section: auditActionLabel(event)),
        ],
      ),
    );
  }

  String? _value(dynamic value) {
    final text = textOf(value, '');
    return text.isEmpty ? null : text;
  }

  String? _fieldLayer(Json? field, FieldLayer layer) => _value(switch (layer) {
    FieldLayer.asWritten =>
      field?['literal_value'] ?? field?['literal'] ?? field?['value'],
    FieldLayer.readAs => field?['parsed_value'] ?? field?['parsed'],
    // resolved_value is a display fallback across layers, not standardized data.
    FieldLayer.standardized => field?['normalized'],
  });

  String? _status(Json? record) {
    final state = _value(record?['value_state'] ?? record?['state']);
    return state == null ? null : vocabularyLabel(state);
  }

  String? _resolution(Json? transcript) => switch (transcript?['resolved']) {
    true => 'Resolved',
    false => 'Unresolved',
    _ => null,
  };

  void _addDifference(
    List<Widget> lines,
    String label,
    String? current,
    String? past, {
    required bool currentPresent,
    required bool pastPresent,
  }) {
    if (current == past) return;
    final from = current ?? (currentPresent ? 'Not recorded' : 'Not present');
    final to = past ?? (pastPresent ? 'Not recorded' : 'Not present');
    lines.add(
      Padding(
        padding: EdgeInsets.only(top: context.ui.space.s2),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: _line),
            Text('$from → $to', style: context.ui.type.body),
          ],
        ),
      ),
    );
  }

  Widget _differenceGroup(String title, List<Widget> lines) => Padding(
    padding: EdgeInsets.only(bottom: context.ui.space.s2),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: context.ui.type.label),
        ...lines,
      ],
    ),
  );

  List<Widget> _differences(Specimen record) {
    final current = {
      for (final f in widget.specimen.fields) textOf(f['field_key']): f,
    };
    final past = {for (final f in record.fields) textOf(f['field_key']): f};
    final keys = {...current.keys, ...past.keys}.toList()..sort();
    final changes = <Widget>[];
    for (final key in keys) {
      final before = current[key];
      final after = past[key];
      final lines = <Widget>[];
      if (before == null || after == null) {
        lines.add(
          Text(before == null ? 'Field added' : 'Field removed', style: _line),
        );
      }
      for (final layer in FieldLayer.values) {
        _addDifference(
          lines,
          layer.label,
          _fieldLayer(before, layer),
          _fieldLayer(after, layer),
          currentPresent: before != null,
          pastPresent: after != null,
        );
      }
      _addDifference(
        lines,
        'Status',
        _status(before),
        _status(after),
        currentPresent: before != null,
        pastPresent: after != null,
      );
      if (lines.isEmpty) continue;
      changes.add(
        _differenceGroup(
          textOf(
            after?['display_name'],
            textOf(before?['display_name'], vocabularyLabel(key)),
          ),
          lines,
        ),
      );
    }
    final currentTranscripts = {
      for (final transcript in objects(widget.specimen.data['transcriptions']))
        textOf(transcript['region_id']): transcript,
    };
    final pastTranscripts = {
      for (final transcript in objects(record.data['transcriptions']))
        textOf(transcript['region_id']): transcript,
    };
    for (final id in {...currentTranscripts.keys, ...pastTranscripts.keys}) {
      final before = currentTranscripts[id];
      final after = pastTranscripts[id];
      final lines = <Widget>[];
      _addDifference(
        lines,
        'Transcription',
        _value(before?['verbatim_text'] ?? before?['text']),
        _value(after?['verbatim_text'] ?? after?['text']),
        currentPresent: before != null,
        pastPresent: after != null,
      );
      _addDifference(
        lines,
        'Status',
        _status(before),
        _status(after),
        currentPresent: before != null,
        pastPresent: after != null,
      );
      _addDifference(
        lines,
        'Resolution',
        _resolution(before),
        _resolution(after),
        currentPresent: before != null,
        pastPresent: after != null,
      );
      if (lines.isEmpty && (before == null || after == null)) {
        lines.add(
          Text(
            before == null ? 'Transcription added' : 'Transcription removed',
            style: _line,
          ),
        );
      }
      if (lines.isEmpty) continue;
      var index = record.regions.indexWhere(
        (r) => (r['region_id'] ?? r['id']) == id,
      );
      if (index < 0) {
        index = widget.specimen.regions.indexWhere(
          (r) => (r['region_id'] ?? r['id']) == id,
        );
      }
      changes.add(
        _differenceGroup(index < 0 ? 'Label $id' : 'Label ${index + 1}', lines),
      );
    }
    if (jsonEncode(record.regions) != jsonEncode(widget.specimen.regions)) {
      changes.insert(
        0,
        Text(
          record.regions.length != widget.specimen.regions.length
              ? '${widget.specimen.regions.length} labels → ${record.regions.length} labels'
              : 'Label regions changed',
          style: context.ui.type.body,
        ),
      );
    }
    return changes.isEmpty
        ? [Text('No label or field changes in this comparison.', style: _line)]
        : changes;
  }

  Widget _preview(
    Specimen record,
  ) => _card(_resetPreview ? 'Initial version · 1' : 'Version ${record.revision}', [
    Text(
      'Status: ${SpecimenStatus.ofRecord(disposition: record.disposition, state: record.state).label}',
      style: _line,
    ),
    Text(
      'Changes from current version ${widget.specimen.revision}',
      style: _line,
    ),
    SizedBox(height: context.ui.space.s2),
    ..._differences(record),
    if (record.data['artifact_receipt'] is Map)
      LargeRecordEvidence(
        key: ValueKey('historical:${record.id}:${record.revision}'),
        specimen: record,
        load: widget.loadArtifact == null
            ? null
            : (request) => widget.loadArtifact!(record, request),
      ),
    if (record.revision != widget.specimen.revision || _resetPreview) ...[
      SizedBox(height: context.ui.space.s2),
      Text(
        _resetPreview
            ? 'Version 1 is the initial retained record. It may precede label processing.'
            : 'Restores label and specimen data. Approval and authority matches need review; processing stays paused.',
        style: _line,
      ),
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: UiButton(
          label: _resetPreview
              ? 'Reset to initial version'
              : 'Restore this version',
          loading: _submitting,
          disabledReason:
              widget.mutationDisabledReason ??
              'Version restoration is not available on this connection.',
          onPressed:
              widget.onRestore == null ||
                  widget.mutationDisabledReason != null ||
                  _mutating
              ? null
              : () => _restore(record),
        ),
      ),
    ],
    if (record.audit.isNotEmpty) ...[
      SizedBox(height: context.ui.space.s3),
      Text('Changes saved in this version', style: context.ui.type.label),
      ...record.audit.reversed.take(1).map(_event),
    ],
    EvidenceDrawer(title: 'Retained version data', payload: record.data),
    Align(
      alignment: AlignmentDirectional.centerStart,
      child: UiButton(
        label: 'Close past version',
        variant: UiButtonVariant.ghost,
        onPressed: _mutating
            ? null
            : () => setState(() {
                _historical = null;
                _requestedRevision = null;
                ++_generation;
              }),
      ),
    ),
  ]);

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _card('History', [
          Wrap(
            spacing: ui.space.s2,
            runSpacing: ui.space.s1,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text('Current version ${widget.specimen.revision}', style: _line),
              UiButton(
                label: 'Start over',
                variant: UiButtonVariant.ghost,
                disabledReason:
                    widget.mutationDisabledReason ??
                    'Version restoration is not available on this connection.',
                onPressed:
                    widget.loadRevision == null ||
                        widget.onRestore == null ||
                        _mutating ||
                        widget.mutationDisabledReason != null
                    ? null
                    : () => _open(1, reset: true),
              ),
            ],
          ),
          if (widget.loadPage == null)
            ...widget.specimen.audit.reversed.map(_event),
          for (final item in _revisions)
            UiListRow(
              title:
                  'Version ${item['revision']}${item['revision'] == widget.specimen.revision ? ' · current' : ''}',
              subtitle:
                  '${auditActionLabel(item)} · ${textOf(item['actor_id'], textOf(item['actor'], 'Unknown actor'))}\n${citedInstant(item['created_at'])}',
              trailing: const UiRowTrailing(label: 'View', icon: UiIcons.next),
              disabledReason:
                  'Past versions cannot be loaded on this connection.',
              onPressed: widget.loadRevision == null || _mutating
                  ? null
                  : () => _open(item['revision'] as int),
            ),
          if (_pageError != null) Text(_pageError!, style: ui.type.body),
          if (_loadingPage) Text('Loading versions', style: _line),
          if (!_loadingPage &&
              widget.loadPage != null &&
              (!_started || _cursor != null))
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiButton(
                label: _pageError != null
                    ? 'Retry history page'
                    : 'Load earlier versions',
                variant: UiButtonVariant.ghost,
                onPressed: _more,
              ),
            ),
          if (widget.loadPage == null && widget.specimen.audit.isEmpty)
            Text(
              'Past versions cannot be loaded on this connection.',
              style: _line,
            ),
        ]),
        if (_loadingRecord)
          Semantics(
            liveRegion: true,
            child: Text('Loading version $_requestedRevision', style: _line),
          ),
        if (_recordError != null)
          _card('Version unavailable', [
            Semantics(
              liveRegion: true,
              child: Text(_recordError!, style: ui.type.body),
            ),
            if (_historical == null)
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: UiButton(
                  label: 'Retry loading version',
                  variant: UiButtonVariant.ghost,
                  onPressed: _requestedRevision == null
                      ? null
                      : () => _open(
                          _requestedRevision!,
                          runId: _runId,
                          runSha256: _runSha256,
                          reset: _resetPreview,
                        ),
                ),
              ),
          ]),
        if (_historical != null)
          KeyedSubtree(key: _previewKey, child: _preview(_historical!)),
      ],
    );
  }
}
