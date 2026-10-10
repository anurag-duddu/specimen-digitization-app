/// Retained versions form an append-only timeline. A restore creates a version.
library;

import 'dart:convert';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart' hide FieldLayer;

import 'blocker_words.dart';
import 'large_record.dart';
import 'history_timeline.dart';
import 'models.dart';
import 'screens/workbench/moments.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

String auditActionLabel(Json event) {
  final action = textOf(event['action'], '');
  final named = switch (action) {
    '' => 'Action not recorded',
    'review_restore_version' =>
      'Restored version ${event['source_revision'] ?? (event['after'] as Map?)?['source_revision'] ?? ''}',
    'review_reset_initial' => 'Reset to initial version',
    'initial_record' => 'Initial record',
    'ingest' => 'Added photograph',
    'intake' => 'Added photograph',
    'transcribe' => 'Transcribed labels',
    'review_field' => 'Edited specimen data',
    'review_transcription' => 'Edited label transcription',
    'review_approve' => 'Approved review',
    'review_coverage' => 'Checked label coverage',
    'review_reading_metadata' => 'Updated reading declaration',
    'review_regions' => 'Corrected label regions',
    'review_classification' => 'Corrected classification',
    'review_authority' => 'Resolved authority match',
    'review_capability_defer' => 'Deferred review',
    'workflow_step' => 'Processing step',
    'process' => 'Requested processing',
    'retry' => 'Requested processing retry',
    'reprocess' => 'Requested reprocessing',
    'reconcile' => 'Reconciled an unknown request',
    'pause' => 'Paused processing',
    'resume' => 'Resumed processing',
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
  static const _archiveBatchSize = 2;
  static const _eventPageSize = 20;
  int _visibleEventCount = _eventPageSize;
  late HistoryTimeline _timeline;
  int? _olderRevision;
  final Set<int> _visitedArchives = {};
  int _eventsGeneration = 0;
  bool _loadingEvents = false;
  bool _archiveIncomplete = false;
  String? _eventsError;
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
    _resetTimeline();
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
      ++_eventsGeneration;
      _resetTimeline();
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

  void _resetTimeline() {
    _timeline = HistoryTimeline(widget.specimen);
    _olderRevision = historyArchiveRevision(widget.specimen);
    _visitedArchives.clear();
    _loadingEvents = false;
    _visibleEventCount = _eventPageSize;
    _eventsError = null;
    _archiveIncomplete =
        (historyAuditOffset(widget.specimen) > 0 && _olderRevision == null) ||
        (widget.specimen.data['artifact_receipt'] is Map &&
            widget.specimen.audit.isEmpty);
  }

  void _retainEvents(Specimen record) {
    _timeline.add(record);
    if (record.revision != _olderRevision) return;
    _visitedArchives.add(record.revision);
    _olderRevision = historyArchiveRevision(record);
    _archiveIncomplete =
        record.data['artifact_receipt'] is Map ||
        (_olderRevision == null && _timeline.missingArchivedEvents > 0);
  }

  /// Each request recovers at most two immutable compaction boundaries.
  /// A hundred processing snapshots are not a hundred reviewer edits.
  Future<void> _olderEvents() async {
    final load = widget.loadRevision;
    if (load == null || _loadingEvents || _olderRevision == null || _mutating) {
      return;
    }
    final generation = ++_eventsGeneration;
    setState(() {
      _loadingEvents = true;
      _eventsError = null;
    });
    try {
      for (var count = 0; count < _archiveBatchSize; count++) {
        if (!mounted ||
            generation != _eventsGeneration ||
            _olderRevision == null) {
          return;
        }
        final revision = _olderRevision!;
        if (_visitedArchives.contains(revision)) {
          throw const ApiFailure(
            'The earlier event boundary could not be verified.',
          );
        }
        final record = await load(revision, null, null);
        if (!mounted || generation != _eventsGeneration) return;
        if (record.id != widget.specimen.id ||
            record.revision != revision ||
            revision > _timeline.throughRevision) {
          throw const ApiFailure(
            'The requested history snapshot could not be verified.',
          );
        }
        setState(() => _retainEvents(record));
        if (_timeline.newestFirst.length > _visibleEventCount) break;
      }
    } catch (e) {
      if (mounted && generation == _eventsGeneration) {
        setState(() => _eventsError = _message(e));
      }
    } finally {
      if (mounted && generation == _eventsGeneration) {
        setState(() => _loadingEvents = false);
      }
    }
  }

  String _message(Object e) =>
      e is ApiFailure ? e.message : 'History could not be loaded. Retry.';
  TextStyle get _line =>
      context.ui.type.bodySmall.copyWith(color: context.ui.color.inkSecondary);

  Future<void> _more() async {
    if (_loadingPage || widget.loadPage == null) return;
    final through = _started ? (_cursor ?? 0) : _timeline.throughRevision;
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
      if (page.throughRevision != through) {
        throw const ApiFailure(
          'The requested history boundary could not be verified.',
        );
      }
      setState(() {
        final known = _revisions.map((item) => item['revision']).toSet();
        _revisions.addAll(
          page.items.reversed.where(
            (item) =>
                item['revision'] is int &&
                item['revision'] > after &&
                item['revision'] <= through &&
                known.add(item['revision']),
          ),
        );
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
        _retainEvents(record);
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

  String _eventLabel(Json event) {
    final after = event['after'];
    final target = textOf(
      event['target_id'] ?? (after is Map ? after['field_key'] : null),
      '',
    );
    final action = auditActionLabel({...event, 'target_id': ''});
    if (target.isEmpty) return action;
    for (final field in widget.specimen.fields) {
      if (field['field_key'] == target) {
        return '$action: ${textOf(field['display_name'], vocabularyLabel(target))}';
      }
    }
    final labelIndex = widget.specimen.regions.indexWhere(
      (region) => (region['region_id'] ?? region['id']) == target,
    );
    return labelIndex >= 0
        ? '$action: Label ${labelIndex + 1}'
        : '$action: ${vocabularyLabel(target)}';
  }

  List<String> _eventChanges(Json event) {
    Map payload(String side) {
      final value = event[side];
      final record = value is Map ? value : const {};
      final after = event['after'];
      final target =
          event['target_id'] ?? (after is Map ? after['field_key'] : null);
      final fields = record['fields'];
      if (target != null && event['action'] == 'review_field') {
        if (fields is Map && fields[target] is Map) {
          return fields[target] as Map;
        }
        if (fields is List) {
          for (final field in fields.whereType<Map>()) {
            if (field['field_key'] == target) return field;
          }
        }
      }
      final transcripts = record['transcripts'] ?? record['transcriptions'];
      if (target != null &&
          event['action'] == 'review_transcription' &&
          transcripts is List) {
        for (final transcript in transcripts.whereType<Map>()) {
          if (transcript['region_id'] == target) return transcript;
        }
      }
      return record;
    }

    final before = payload('before');
    final after = payload('after');
    const labels = {
      'literal': 'As written',
      'literal_value': 'As written',
      'parsed': 'Read as',
      'parsed_value': 'Read as',
      'normalized': 'Standardized',
      'text': 'Transcription',
      'verbatim_text': 'Transcription',
      'value_state': 'Status',
      'state': 'Status',
      'resolved': 'Resolution',
      'confirmed': 'Label coverage checked',
      'human_approved': 'Review approval',
      'stage': 'Processing state',
      'blocker': 'Processing blocker',
    };
    final changes = <String>[];
    final seen = <String>{};
    String display(Object? value, String key) {
      if (value is bool) {
        return switch (key) {
          'resolved' => value ? 'Resolved' : 'Unresolved',
          'confirmed' => value ? 'Confirmed' : 'Not confirmed',
          'human_approved' => value ? 'Approved' : 'Not approved',
          _ => 'Recorded as $value',
        };
      }
      final text = textOf(value, 'Not recorded');
      // A blocker is a machine code. It reads as its cause, or generically,
      // and an absent one stays "Not recorded".
      if (key == 'blocker') return value == null ? text : blockerLabel(text);
      return {'state', 'value_state', 'stage'}.contains(key)
          ? vocabularyLabel(text)
          : text;
    }

    for (final entry in labels.entries) {
      final key = entry.key;
      if ((!before.containsKey(key) && !after.containsKey(key)) ||
          before[key] == after[key] ||
          !seen.add(entry.value)) {
        continue;
      }
      if (before[key] is Map ||
          before[key] is List ||
          after[key] is Map ||
          after[key] is List) {
        continue;
      }
      changes.add(
        '${entry.value}: ${display(before[key], key)} → ${display(after[key], key)}',
      );
    }
    return changes;
  }

  Widget _event(Json event, {int? retainedRevision}) {
    final before = event['before'];
    final referencedRevision =
        before is Map && before['specimen_id'] == widget.specimen.id
        ? before['revision']
        : null;
    final revision = event['base_revision'] is int
        ? event['base_revision']
        : referencedRevision;
    final resulting = event['resulting_revision'];
    final named = _eventLabel(event);
    final time = DateTime.tryParse(textOf(event['created_at'], '')) == null
        ? 'Time not recorded'
        : citedInstant(event['created_at']);
    return Padding(
      padding: EdgeInsets.only(bottom: context.ui.space.s2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(named, style: context.ui.type.label),
          Text(
            '${textOf(event['actor_id'], textOf(event['actor'], 'Actor not recorded'))} · $time',
            style: _line,
          ),
          if (resulting is int &&
              resulting > 0 &&
              resulting <= _timeline.throughRevision)
            Text('Version $resulting', style: _line)
          else if (retainedRevision != null)
            Text(
              'Retained in version $retainedRevision · event version not recorded',
              style: _line,
            ),
          if (textOf(event['reason'], '').isNotEmpty)
            Text(
              'Reason: ${textOf(event['reason'])}',
              style: context.ui.type.body,
            ),
          for (final change in _eventChanges(event))
            Text(change, style: context.ui.type.body),
          if (event['action'] == 'review_field' &&
              textOf(
                event['target_id'] ??
                    (event['after'] is Map
                        ? event['after']['field_key']
                        : null),
                '',
              ).isEmpty)
            Text('Field name not recorded in this event.', style: _line),
          if (revision is int &&
              revision > 0 &&
              revision <= _timeline.throughRevision &&
              (before is! Map ||
                  before['specimen_id'] == null ||
                  before['specimen_id'] == widget.specimen.id))
            UiButton(
              label: 'Open version $revision',
              variant: UiButtonVariant.ghost,
              onPressed: widget.loadRevision == null || _mutating
                  ? null
                  : () => _open(
                      revision,
                      runId: before is Map && before['run_sha256'] is String
                          ? before['run_id'] as String?
                          : null,
                      runSha256: before is Map
                          ? before['run_sha256'] as String?
                          : null,
                    ),
            ),
          EvidenceDrawer(payload: event, section: named),
        ],
      ),
    );
  }

  Widget _timelineView() {
    final recovered = _timeline.newestFirst;
    final entries = recovered.take(_visibleEventCount).toList();
    final moreRetained = recovered.length > entries.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (entries.isEmpty)
          Text(
            widget.specimen.data['artifact_receipt'] is Map
                ? 'Audit events are not included in this summary. Open a saved version to inspect its retained evidence.'
                : 'No audit events are recorded in this snapshot.',
            style: _line,
          ),
        for (var index = 0; index < entries.length; index++)
          CustomPaint(
            key: ValueKey('history-event:${entries[index].key}'),
            painter: _HistoryRail(
              line: context.ui.color.boundary,
              dot: context.ui.color.inkTertiary,
              direction: Directionality.of(context),
              first: index == 0,
              last: index == entries.length - 1,
            ),
            child: Padding(
              padding: EdgeInsetsDirectional.only(start: context.ui.space.s5),
              child: _event(
                entries[index].event,
                retainedRevision: entries[index].retainedRevision,
              ),
            ),
          ),
        if (_timeline.hasLegacyEvents)
          Text(
            'Some older events do not record the version where they occurred. Their retained record is shown instead.',
            style: _line,
          ),
        if (_timeline.missingArchivedEvents > 0 && _olderRevision != null)
          Text(
            'Earlier events are retained in older saved versions.',
            style: _line,
          ),
        if (_archiveIncomplete)
          Text(
            'Some earlier event details could not be recovered from these snapshots. Saved versions remain available for inspection.',
            style: _line,
          ),
        if (_eventsError != null)
          Semantics(
            liveRegion: true,
            child: Text(_eventsError!, style: context.ui.type.body),
          ),
        if (_loadingEvents)
          Semantics(
            liveRegion: true,
            child: Text('Loading earlier events', style: _line),
          ),
        if (!_loadingEvents && (moreRetained || _olderRevision != null))
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiButton(
              label: _eventsError == null
                  ? 'Load older history'
                  : 'Retry older history',
              variant: UiButtonVariant.ghost,
              disabledReason:
                  'Earlier events cannot be loaded on this connection.',
              onPressed:
                  _mutating || (!moreRetained && widget.loadRevision == null)
                  ? null
                  : () {
                      if (moreRetained) {
                        setState(() => _visibleEventCount += _eventPageSize);
                      } else {
                        _olderEvents();
                      }
                    },
            ),
          ),
      ],
    );
  }

  Widget _savedVersions() => UiDisclosure(
    key: ValueKey(
      'saved-versions:${widget.specimen.id}:${_timeline.throughRevision}',
    ),
    title: 'Saved versions',
    summary:
        'Read-only snapshots, including processing updates without an audit event.',
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final item in _revisions)
          UiListRow(
            title:
                'Version ${item['revision']}${item['revision'] == _timeline.throughRevision ? ' · current' : ''}',
            // The history index records only version and checksum. It cannot
            // establish who changed a record, when, or what they did.
            subtitle: 'Retained snapshot',
            trailing: const UiRowTrailing(label: 'View', icon: UiIcons.next),
            disabledReason:
                'Past versions cannot be loaded on this connection.',
            onPressed: widget.loadRevision == null || _mutating
                ? null
                : () => _open(item['revision'] as int),
          ),
        if (_pageError != null) Text(_pageError!, style: context.ui.type.body),
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
        if (widget.loadPage == null)
          Text(
            'Past versions cannot be loaded on this connection.',
            style: _line,
          ),
      ],
    ),
  );

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
      Text('Latest retained event', style: context.ui.type.label),
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
          SizedBox(height: ui.space.s3),
          Text('Saved audit events, newest first', style: _line),
          SizedBox(height: ui.space.s2),
          _timelineView(),
          SizedBox(height: ui.space.s3),
          _savedVersions(),
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

/// Decorative continuity only; the event text carries all meaning.
class _HistoryRail extends CustomPainter {
  const _HistoryRail({
    required this.line,
    required this.dot,
    required this.direction,
    required this.first,
    required this.last,
  });

  final Color line;
  final Color dot;
  final TextDirection direction;
  final bool first;
  final bool last;

  @override
  void paint(Canvas canvas, Size size) {
    final x = direction == TextDirection.rtl ? size.width - 6 : 6.0;
    const y = 7.0;
    canvas.drawLine(
      Offset(x, first ? y : 0),
      Offset(x, last ? y : size.height),
      Paint()
        ..color = line
        ..strokeWidth = 1,
    );
    canvas.drawCircle(Offset(x, y), 3, Paint()..color = dot);
  }

  @override
  bool shouldRepaint(_HistoryRail oldDelegate) =>
      oldDelegate.line != line ||
      oldDelegate.dot != dot ||
      oldDelegate.direction != direction ||
      oldDelegate.first != first ||
      oldDelegate.last != last;
}
