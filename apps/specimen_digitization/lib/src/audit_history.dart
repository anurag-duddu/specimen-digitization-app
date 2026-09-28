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

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'large_record.dart';
import 'models.dart';
import 'screens/workbench/moments.dart';
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
    final UiThemeData ui = context.ui;
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

    final bool machine = event['actor_id'] == null;
    return Semantics(
      container: true,
      child: Padding(
        padding: EdgeInsetsDirectional.only(bottom: ui.space.s3),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Padding(
              padding: EdgeInsetsDirectional.only(top: ui.space.s1),
              child: UiIcon(
                // Slate for a machine event and green for a reviewer's, which
                // is the evidence family 09 section 3.5 gives each: the
                // glyph already said which, and now the colour agrees.
                machine ? UiIcons.processing : UiIcons.reviewer,
                size: UiIconSize.inline,
                color: machine
                    ? ui.color.status.model.content
                    : ui.color.status.human.content,
              ),
            ),
            SizedBox(width: ui.space.s2),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    '$sequence · ${auditActionLabel(event)}',
                    style: ui.type.label,
                  ),
                  Text(
                    '$actor · ${citedInstant(event['created_at'])}',
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                  if (reason.isNotEmpty && reason != 'Not recorded')
                    Text('Reason: $reason', style: ui.type.body),
                  if (event['revision'] != null)
                    Text(
                      'Version ${event['revision']}',
                      style: ui.type.mono.identifier.copyWith(
                        color: ui.color.inkSecondary,
                      ),
                    ),
                  if (reference != null &&
                      reference > 0 &&
                      reference <= widget.specimen.revision)
                    Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: UiButton(
                        label: 'Open version $reference',
                        variant: UiButtonVariant.ghost,
                        leading: UiIcons.history,
                        disabledReason: widget.loadRevision == null
                            ? unavailableReason
                            : null,
                        onPressed: widget.loadRevision == null
                            ? null
                            : () => _open(
                                reference,
                                runId: textOf((before! as Map)['run_id']),
                                runSha256: textOf(
                                  (before as Map)['run_sha256'],
                                ),
                              ),
                      ),
                    ),
                  EvidenceDrawer(
                    payload: event,
                    section: auditActionLabel(event),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _card(String title, List<Widget> children) {
    final UiThemeData ui = context.ui;
    return Padding(
      padding: EdgeInsetsDirectional.only(bottom: ui.space.s4),
      child: Surface(
        radius: ui.shape.tile,
        hairline: true,
        padding: EdgeInsetsDirectional.all(ui.space.s4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Semantics(
              container: true,
              header: true,
              child: Text(title, style: ui.type.title),
            ),
            SizedBox(height: ui.space.s2),
            ...children,
          ],
        ),
      ),
    );
  }

  Widget _historicalRecord(
    Specimen record,
  ) => _card('Version ${record.revision} · read only', <Widget>[
    Text(
      'This is a past version. It is read only.',
      style: context.ui.type.body,
    ),
    SizedBox(height: context.ui.space.s1),
    Text(
      'Your current review is on version ${widget.specimen.revision}. '
      'This version: ${SpecimenStatus.ofRecord(disposition: record.disposition, state: record.state).label}.',
      style: _line,
    ),
    Text(
      'Profile ${record.profile} · Record '
      '${textOf(record.data['record_version_id'])}',
      style: _line,
    ),
    if (record.data['history_through_revision'] != null)
      Text(
        'Earlier history through version '
        '${record.data['history_through_revision']} is in the version '
        'browser below.',
        style: _line,
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
    SizedBox(height: context.ui.space.s3),
    Text(
      'Audit events · version ${record.revision}',
      style: context.ui.type.label,
    ),
    if (record.audit.isEmpty)
      Text(
        'No events in this version. Open earlier versions to see more '
        'history.',
        style: context.ui.type.body,
      ),
    ...record.audit.indexed.map(
      ((int, Json) entry) => _event(
        entry.$2,
        (record.data['audit_offset'] as int? ?? 0) + entry.$1 + 1,
      ),
    ),
    Align(
      alignment: AlignmentDirectional.centerStart,
      child: UiButton(
        label: closeVersionLabel,
        variant: UiButtonVariant.ghost,
        leading: UiIcons.close,
        onPressed: () => setState(() {
          _historical = null;
          _requestedRevision = null;
          ++_generation;
        }),
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

  /// The style every secondary line in this panel is set in.
  TextStyle get _line =>
      context.ui.type.bodySmall.copyWith(color: context.ui.color.inkSecondary);

  /// The controls this panel names, fixed so the panel and its tests agree.
  static const String closeVersionLabel = 'Close past version';
  static const String retryVersionLabel = 'Retry loading version';
  static const String browseLabel = 'Browse record versions';
  static const String loadMoreLabel = 'Load more versions';
  static const String loadingLabel = 'Loading versions';
  static const String retryPageLabel = 'Retry history page';
  static const String openVersionLabel = 'Open';

  /// Why a control is unavailable on a connection that cannot reach history.
  static const String unavailableReason =
      'Past versions cannot be loaded on this connection.';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final MotionTokens motion = ui.motion;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _card('Current decision history', <Widget>[
          Text(
            'Current review version ${widget.specimen.revision}',
            style: _line,
          ),
          if (widget.specimen.data['history_through_revision'] != null)
            Text(
              'Earlier audit and run evidence through version '
              '${widget.specimen.data['history_through_revision']} is kept in '
              'record history. Browse versions below for the complete earlier '
              'record.',
              style: _line,
            ),
          SizedBox(height: ui.space.s2),
          if (widget.specimen.audit.isEmpty)
            Text(
              'No audit events in the current snapshot.',
              style: ui.type.body,
            ),
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
              padding: EdgeInsetsDirectional.all(ui.space.s4),
              child: Text(
                'Loading version $_requestedRevision',
                style: ui.type.body,
              ),
            ),
          ),
        if (_recordError != null)
          _card('Past version unavailable', <Widget>[
            Semantics(
              liveRegion: true,
              child: Text(_recordError!, style: ui.type.body),
            ),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiButton(
                label: retryVersionLabel,
                variant: UiButtonVariant.ghost,
                leading: UiIcons.retry,
                disabledReason: unavailableReason,
                onPressed: _requestedRevision == null
                    ? null
                    : () => _open(
                        _requestedRevision!,
                        runId: _runId,
                        runSha256: _runSha256,
                      ),
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
            style: _line,
          ),
          SizedBox(height: ui.space.s2),
          if (widget.loadPage == null || widget.loadRevision == null)
            Text(unavailableReason, style: ui.type.body),
          ..._revisions.map(
            (Json item) => UiListRow(
              title: 'Version ${item['revision']}',
              subtitle: <String>[
                citedInstant(item['created_at']),
                _revisionSummary(item),
              ].join(' · '),
              trailing: const UiRowTrailing(
                label: openVersionLabel,
                icon: UiIcons.next,
              ),
              disabledReason: unavailableReason,
              onPressed: widget.loadRevision == null
                  ? null
                  : () => _open(item['revision'] as int),
            ),
          ),
          if (_pageError != null)
            Semantics(
              liveRegion: true,
              child: Text(_pageError!, style: ui.type.body),
            ),
          if (_started && _cursor == null)
            Text(
              'All versions through this snapshot are listed.',
              style: _line,
            ),
          if (!_started || _cursor != null)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiButton(
                label: _loadingPage
                    ? loadingLabel
                    : _pageError != null
                    ? retryPageLabel
                    : _started
                    ? loadMoreLabel
                    : browseLabel,
                variant: UiButtonVariant.secondary,
                leading: UiIcons.history,
                loading: _loadingPage,
                disabledReason: unavailableReason,
                onPressed: widget.loadPage == null ? null : _more,
              ),
            ),
        ]),
      ],
    );
  }
}
