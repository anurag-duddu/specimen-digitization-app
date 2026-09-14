/// The review workbench (screen blueprints, section 6).
///
/// Three regions at every window class: the source pane, the evidence pane
/// and the decision bar. The photograph never scrolls away, every correction
/// happens with the pixels on screen, and the corrections a reviewer makes on
/// one record are saved together under one reason.
library;

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'audit_history.dart';
import 'evidence_panel.dart';
import 'large_record.dart';
import 'models.dart';
import 'region_editor.dart';
import 'review_context.dart';
import 'screens/workbench/blockers.dart';
import 'screens/workbench/decision_bar.dart';
import 'screens/workbench/fields_panel.dart';
import 'screens/workbench/pending_changes.dart';
import 'screens/workbench/readings_panel.dart';
import 'screens/workbench/shortcuts.dart';
import 'screens/workbench/source_pane.dart';
import 'screens/workbench/status_strip.dart';
import 'screens/workbench/workbench_layout.dart';
import 'theme/icons.dart';
import 'theme/motion.dart';
import 'operational_panel.dart';
import 'widgets/widgets.dart';

class ReviewWorkbench extends StatefulWidget {
  const ReviewWorkbench({
    super.key,
    required this.specimen,
    required this.onChange,
    required this.onRetry,
    required this.onRefresh,
    this.busy = false,
    this.collections = const [],
    this.canReview = true,
    this.canOperate = true,
    this.loadHistoryPage,
    this.loadArtifact,
    this.loadHistoricalArtifact,
    this.loadHistoricalRevision,
    this.onNext,
    this.onPrevious,
  });
  final Specimen specimen;
  final Future<Json> Function(Specimen, ArtifactRequest)?
  loadHistoricalArtifact;
  final Future<Json> Function(ArtifactRequest)? loadArtifact;

  /// True only after the repository acknowledges this decision.
  final Future<bool> Function(Json change) onChange;
  final Future<void> Function(String reason) onRetry;
  final VoidCallback onRefresh;
  final bool busy;
  final List<CollectionScope> collections;
  final bool canReview;
  final bool canOperate;
  final Future<HistoryPage> Function(int afterRevision, int throughRevision)?
  loadHistoryPage;
  final Future<Specimen> Function(
    int revision,
    String? runId,
    String? runSha256,
  )?
  loadHistoricalRevision;

  /// Opens the next specimen in the queue. Null hides the control and the
  /// shortcut, because a control that does nothing is worse than no control.
  final VoidCallback? onNext;

  /// Opens the previous specimen in the queue.
  final VoidCallback? onPrevious;

  @override
  State<ReviewWorkbench> createState() => _ReviewWorkbenchState();
}

class _ReviewWorkbenchState extends State<ReviewWorkbench> {
  WorkbenchSegment _segment = WorkbenchSegment.readings;
  String? _region;
  bool _sourceCollapsed = false;
  List<PendingFieldChange> _pending = <PendingFieldChange>[];
  List<PendingFieldChange> _stale = <PendingFieldChange>[];
  final List<String> _recentReasons = <String>[];
  int? _conflictVersion;
  bool _savingLocally = false;
  String? _announcement;

  final SourceViewController _view = SourceViewController();
  final ScrollController _evidenceScroll = ScrollController();
  final Map<String, GlobalKey> _regionAnchors = <String, GlobalKey>{};
  final Map<String, GlobalKey> _fieldAnchors = <String, GlobalKey>{};

  List<String> get _serverActions =>
      (widget.specimen.data['available_actions'] as List? ?? <Object?>[])
          .map((Object? a) => a.toString())
          .toList();

  /// Why an action is unavailable, or null when it is available.
  ///
  /// One function per screen, so every gate has a matching sentence and no
  /// button is ever a silent no-op (accessibility, 3.2; pass criterion 5.6).
  String? blockedReason(String action) {
    if (widget.busy) return 'Wait for the save that is in flight to finish';
    if (!widget.canReview) {
      return 'Your role on this collection does not include reviewing';
    }
    if (!_serverActions.contains(action)) {
      return switch (action) {
        'approve' =>
          'The server does not permit approval on this version. Resolve what '
              'blocks clearance first.',
        'coverage' =>
          'The server does not permit confirming label coverage on this '
              'version.',
        'field' =>
          'The server does not permit field corrections on this version.',
        'transcription' =>
          'The server does not permit resolving a transcription on this '
              'version.',
        'regions' =>
          'The server does not permit region corrections on this version.',
        'classification' =>
          'The server does not permit a classification correction on this '
              'version.',
        _ => 'The server does not permit this action on this version.',
      };
    }
    return null;
  }

  String? get _retryBlockedReason {
    if (widget.busy) return 'Wait for the save that is in flight to finish';
    if (!widget.canOperate) {
      return 'Your role on this collection does not include operating runs';
    }
    final DateTime? lease = DateTime.tryParse(
      textOf(objectOf(widget.specimen.data['run'])['lease_until'], ''),
    );
    if (lease != null && lease.isAfter(DateTime.now())) {
      return 'The processing service holds this run until its reservation '
          'ends';
    }
    if (!_serverActions.contains('retry')) {
      return 'The server does not permit a retry on this version.';
    }
    return null;
  }

  @override
  void didUpdateWidget(covariant ReviewWorkbench oldWidget) {
    super.didUpdateWidget(oldWidget);
    final bool newRecord = oldWidget.specimen.id != widget.specimen.id;
    if (newRecord ||
        oldWidget.specimen.data['active_run_id'] !=
            widget.specimen.data['active_run_id'] ||
        (_region != null &&
            !widget.specimen.regions.any(
              (Json r) => r['region_id'] == _region,
            ))) {
      _region = null;
    }
    if (newRecord) {
      _pending = <PendingFieldChange>[];
      _stale = <PendingFieldChange>[];
      _conflictVersion = null;
      return;
    }
    if (oldWidget.specimen.revision != widget.specimen.revision &&
        !_savingLocally) {
      _reapplyPending();
      _conflictVersion = widget.specimen.revision;
    }
  }

  void _reapplyPending() {
    final split = reapply(_pending, widget.specimen);
    _pending = split.keep;
    if (split.stale.isNotEmpty) {
      _stale = split.stale;
      _conflictVersion = widget.specimen.revision;
    }
  }

  @override
  void dispose() {
    _view.dispose();
    _evidenceScroll.dispose();
    super.dispose();
  }

  void _announce(String message) {
    _announcement = message;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final String? pending = _announcement;
      _announcement = null;
      if (pending == null || !mounted) return;
      if (!MediaQuery.supportsAnnounceOf(context)) return;
      SemanticsService.sendAnnouncement(
        View.of(context),
        pending,
        TextDirection.ltr,
      );
    });
  }

  GlobalKey _anchor(Map<String, GlobalKey> anchors, String id) =>
      anchors.putIfAbsent(id, GlobalKey.new);

  void _selectRegion(String? id) {
    setState(() {
      _region = id;
      if (id != null) _segment = WorkbenchSegment.readings;
    });
    if (id == null) return;
    // The readings scroll to the region the photograph just moved to.
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => _scrollTo(_regionAnchors[id]),
    );
  }

  void _scrollTo(GlobalKey? key) {
    final BuildContext? target = key?.currentContext;
    if (target == null) return;
    Scrollable.ensureVisible(
      target,
      duration: context.motion.standard,
      curve: MotionTokens.standardCurve,
      alignment: 0.1,
    );
    Focus.maybeOf(target)?.requestFocus();
  }

  void _goToBlocker(ClearanceBlocker blocker) {
    setState(() => _segment = blocker.segment);
    final String? region = blocker.regionId;
    if (region != null) _region = region;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final String? field = blocker.fieldKey;
      _scrollTo(
        field != null
            ? _fieldAnchors[field]
            : region != null
            ? _regionAnchors[region]
            : null,
      );
    });
  }

  void _rememberReason(String reason) {
    _recentReasons
      ..remove(reason)
      ..insert(0, reason);
    if (_recentReasons.length > _recentReasonLimit) {
      _recentReasons.removeRange(_recentReasonLimit, _recentReasons.length);
    }
  }

  /// Waits for this decision's acknowledgement, independently of widget
  /// identity or another request refreshing the record in the meantime.
  Future<bool> _send(Json change) async {
    if (_savingLocally || widget.busy) return false;
    _savingLocally = true;
    bool acknowledged = false;
    try {
      acknowledged = await widget.onChange(change);
      // Let the acknowledged record reach this widget before the next item
      // in a batch reads its version or available actions.
      if (mounted) await WidgetsBinding.instance.endOfFrame;
      return mounted && acknowledged;
    } catch (_) {
      return false;
    } finally {
      _savingLocally = false;
      if (mounted) {
        setState(() {
          // The fresh readback can include this acknowledged correction and
          // unrelated concurrent edits. Remove only the acknowledged field
          // before checking whether the remaining drafts are still current.
          if (acknowledged && change['kind'] == 'field_correction') {
            _pending.removeWhere((p) => p.fieldKey == change['target_id']);
            _stale.removeWhere((p) => p.fieldKey == change['target_id']);
          }
          _reapplyPending();
        });
      }
    }
  }

  Future<void> _savePending() async {
    final List<PendingFieldChange> batch = List<PendingFieldChange>.of(
      _pending,
    );
    if (batch.isEmpty || _savingLocally || blockedReason('field') != null) {
      return;
    }
    final List<ClearanceBlocker> outstanding = blockersFor(widget.specimen);
    final String? reason = await showReasonSheet(
      context,
      title: 'Save ${pendingChangesLabel(batch.length)}?',
      action: 'Save ${pendingChangesLabel(batch.length)}',
      consequence:
          'Each correction is recorded on this record under this one reason, '
          'and the checks that depend on it run again.',
      retained: 'The model readings and earlier versions stay in history.',
      outstanding: <String>[
        for (final PendingFieldChange change in batch) change.summary,
        for (final ClearanceBlocker blocker in outstanding) blocker.message,
      ],
      recentReasons: _recentReasons,
    );
    if (reason == null || !mounted) return;
    _rememberReason(reason);

    int saved = 0;
    for (final PendingFieldChange change in batch) {
      // A preceding readback may have invalidated a later draft. Never send
      // it from the original batch against a newer revision automatically.
      if (!_pending.contains(change) || blockedReason('field') != null) break;
      final bool landed = await _send(change.toChange(reason));
      if (!mounted) return;
      if (!landed) break;
      saved++;
    }

    if (!mounted) return;
    if (saved == batch.length) {
      _announce(
        '${pendingChangesLabel(saved)} saved. '
        'Version ${widget.specimen.revision}.',
      );
      return;
    }
    await _reportFailedSave(batch.length - saved);
  }

  Future<void> _reportFailedSave(int keptCount) async {
    final bool refresh = await showConflictDialog(
      context,
      version: _conflictVersion ?? widget.specimen.revision,
      anotherReviewer: _conflictVersion != null,
      pendingCount: keptCount,
    );
    if (refresh && mounted) _refresh();
  }

  void _refresh() {
    setState(() => _conflictVersion = null);
    widget.onRefresh();
  }

  Future<void> _decide(String kind, String title, String action) async {
    if (blockedReason(kind) != null) return;
    final List<ClearanceBlocker> outstanding = blockersFor(widget.specimen);
    final String? reason = await showReasonSheet(
      context,
      title: title,
      action: action,
      consequence:
          'This is recorded on version ${widget.specimen.revision} with your '
          'name. The server decides clearance.',
      retained: 'Every reading, finding and earlier version stays in history.',
      outstanding: <String>[
        for (final ClearanceBlocker blocker in outstanding) blocker.message,
      ],
      recentReasons: _recentReasons,
    );
    if (reason == null || !mounted) return;
    _rememberReason(reason);
    final bool landed = await _send(<String, dynamic>{
      'kind': kind,
      'reason': reason,
    });
    if (!mounted) return;
    if (!landed) {
      await _reportFailedSave(_pending.length);
    } else {
      _announce('$action saved. Version ${widget.specimen.revision}.');
    }
  }

  Future<void> _classification() async {
    final CollectionScope? scope = widget.collections
        .where(
          (CollectionScope c) =>
              c.collectionId == widget.specimen.data['collection_id'],
        )
        .firstOrNull;
    if (scope == null) {
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        const SnackBar(
          content: Text(
            'Collection configuration is unavailable. Refresh collection '
            'access.',
          ),
        ),
      );
      return;
    }
    final Json? result = await showDialog<Json>(
      context: context,
      builder: (_) =>
          ClassificationDialog(specimen: widget.specimen, scope: scope),
    );
    if (result != null && mounted) await _send(result);
  }

  Future<void> _retry() async {
    if (_retryBlockedReason != null) return;
    final String blocker = textOf(
      objectOf(widget.specimen.data['run'])['blocker'],
      '',
    );
    final String? reason = await showReasonSheet(
      context,
      title: 'Retry from the checkpoint?',
      action: 'Retry from the checkpoint',
      consequence:
          'The server repeats the processing it allows from the last '
          'checkpoint.',
      retained: 'Earlier evidence and decisions stay in history.',
      outstanding: <String>[
        if (blocker.contains('external_outcome_unknown'))
          'The last external request may already have run and its result is '
              'unknown. Reconcile it first. This app never retries it for you.',
      ],
      recentReasons: _recentReasons,
    );
    if (reason == null || !mounted) return;
    _rememberReason(reason);
    await widget.onRetry(reason);
  }

  Future<void> _editRegions() async {
    final Json? result = await showRegionEditor(
      context,
      regions: widget.specimen.regions,
      asset: widget.specimen.assets.isEmpty
          ? const <String, dynamic>{}
          : widget.specimen.assets.first,
    );
    if (result != null && mounted) await _send(result);
  }

  String? get _regionEditBlockedReason => !_regionsEditable
      ? 'This photograph has no verified orientation, so region editing is '
            'unavailable'
      : blockedReason('regions');

  bool get _regionsEditable {
    final Json asset = widget.specimen.assets.isEmpty
        ? const <String, dynamic>{}
        : widget.specimen.assets.first;
    return !(asset['media_type'] != null &&
        asset['preview_is_derivative'] != true);
  }

  // ---------------------------------------------------------------- panes

  Future<void> _copyIdentifier(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: widget.specimen.id));
    if (!context.mounted) return;
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      const SnackBar(content: Text('Specimen identifier copied')),
    );
  }

  Widget _header(BuildContext context) => Padding(
    padding: EdgeInsets.only(bottom: context.space.space2),
    child: Row(
      children: <Widget>[
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                widget.specimen.title,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              // Plain text, not selectable: a selectable paragraph exposes a
              // long press action, which makes a 20 dp line a tap target the
              // guideline rightly refuses. The copy control beside it is the
              // 48 dp way to take the identifier.
              Text(widget.specimen.id, style: context.mono.identifier),
            ],
          ),
        ),
        IconButton(
          onPressed: () => _copyIdentifier(context),
          tooltip: 'Copy the specimen identifier',
          icon: const Icon(Symbols.content_copy),
        ),
        IconButton(
          onPressed: widget.busy ? null : _refresh,
          tooltip: 'Refresh this record',
          icon: const Icon(Symbols.refresh),
        ),
        IconButton(
          onPressed: () => showShortcutSheet(context),
          tooltip: 'Keyboard shortcuts',
          icon: const Icon(Symbols.keyboard),
        ),
      ],
    ),
  );

  Widget _sourcePane(BuildContext context, {bool compact = false}) =>
      WorkbenchSourcePane(
        specimen: widget.specimen,
        compact: compact,
        controller: _view,
        selectedRegionId: _region,
        onSelectRegion: _selectRegion,
        onEditRegions: !_regionsEditable || blockedReason('regions') != null
            ? null
            : _editRegions,
        editRegionsBlockedReason: _regionEditBlockedReason,
        onExpand: () => showSourceFullScreen(
          context,
          specimen: widget.specimen,
          selectedRegionId: _region,
          onSelectRegion: _selectRegion,
        ),
      );

  Widget _segmentContent(BuildContext context) => switch (_segment) {
    WorkbenchSegment.readings => WorkbenchReadings(
      key: const ValueKey<String>('readings'),
      specimen: widget.specimen,
      anchors: <String, GlobalKey>{
        for (final Json r in widget.specimen.regions)
          textOf(r['region_id'], ''): _anchor(
            _regionAnchors,
            textOf(r['region_id'], ''),
          ),
      },
      selectedRegionId: _region,
      onSelectRegion: _selectRegion,
      onChange: _send,
      transcriptionBlockedReason: blockedReason('transcription'),
      declarationsBlocked: blockedReason('reading_metadata') != null,
      loadArtifact: widget.loadArtifact,
    ),
    WorkbenchSegment.fields => Column(
      key: const ValueKey<String>('fields'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        WorkbenchFields(
          specimen: widget.specimen,
          anchors: <String, GlobalKey>{
            for (final Json f in widget.specimen.fields)
              textOf(f['field_key'], ''): _anchor(
                _fieldAnchors,
                textOf(f['field_key'], ''),
              ),
          },
          pending: _pending,
          onPendingChanged: (List<PendingFieldChange> next) =>
              setState(() => _pending = next),
          onFocusRegion: (String? id) {
            if (id != null) setState(() => _region = id);
          },
          fieldBlockedReason: blockedReason('field'),
        ),
        SizedBox(height: context.space.space6),
        if (widget.loadArtifact != null)
          EvidencePanel(
            key: ValueKey<String>(
              'evidence:${widget.specimen.id}:${widget.specimen.revision}',
            ),
            specimen: widget.specimen,
            load: widget.loadArtifact!,
            onChange: _send,
            canReview: blockedReason('authority_resolution') == null,
          ),
        SizedBox(height: context.space.space6),
        ReviewContext(specimen: widget.specimen),
        SizedBox(height: context.space.space4),
        Wrap(
          spacing: context.space.space2,
          runSpacing: context.space.space2,
          children: <Widget>[
            _reasoned(
              blockedReason('classification'),
              OutlinedButton.icon(
                onPressed: blockedReason('classification') != null
                    ? null
                    : _classification,
                icon: const Icon(Symbols.account_tree),
                label: const Text('Correct classification'),
              ),
            ),
            _reasoned(
              _retryBlockedReason,
              OutlinedButton.icon(
                onPressed: _retryBlockedReason != null ? null : _retry,
                icon: const Icon(Symbols.replay),
                label: const Text('Retry processing'),
              ),
            ),
          ],
        ),
      ],
    ),
    WorkbenchSegment.history => _history(const ValueKey<String>('history')),
  };

  Widget _reasoned(String? reason, Widget child) => Tooltip(
    message: reason ?? '',
    child: Semantics(hint: reason ?? '', child: child),
  );

  Widget _history(Key key) => AuditHistoryPanel(
    key: key,
    specimen: widget.specimen,
    loadPage: widget.loadHistoryPage,
    loadRevision: widget.loadHistoricalRevision,
    loadArtifact: widget.loadHistoricalArtifact,
  );

  Widget _evidencePane(BuildContext context, WorkbenchRegime regime) {
    final List<WorkbenchSegment> segments = WorkbenchSegment.forRegime(regime);
    final WorkbenchSegment selected = segments.contains(_segment)
        ? _segment
        : WorkbenchSegment.readings;
    final MotionTokens motion = context.motion;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Expanded(
          child: SingleChildScrollView(
            controller: _evidenceScroll,
            padding: EdgeInsets.symmetric(horizontal: context.space.space4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                if (regime.isStacked) ...<Widget>[
                  SourceRegionEditControl(
                    onEditRegions:
                        !_regionsEditable || blockedReason('regions') != null
                        ? null
                        : _editRegions,
                    blockedReason: _regionEditBlockedReason,
                  ),
                  SourceDetails(
                    asset: widget.specimen.assets.isEmpty
                        ? const <String, dynamic>{}
                        : widget.specimen.assets.first,
                  ),
                  SizedBox(height: context.space.space2),
                ],
                WorkbenchStatusStrip(
                  specimen: widget.specimen,
                  blockers: blockersFor(widget.specimen),
                  pending: _pending,
                  staleChanges: _stale,
                  canOperate: widget.canOperate,
                  busy: widget.busy,
                  onAction: _send,
                  onGoToBlocker: _goToBlocker,
                  onReviewPending: _savePending,
                  conflictVersion: _conflictVersion,
                  onRefresh: _refresh,
                ),
                SizedBox(height: context.space.space3),
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: SegmentedButton<WorkbenchSegment>(
                      segments: <ButtonSegment<WorkbenchSegment>>[
                        for (final WorkbenchSegment s in segments)
                          ButtonSegment<WorkbenchSegment>(
                            value: s,
                            label: Text(s.label),
                          ),
                      ],
                      selected: <WorkbenchSegment>{selected},
                      showSelectedIcon: false,
                      onSelectionChanged: (Set<WorkbenchSegment> next) =>
                          setState(() => _segment = next.first),
                    ),
                  ),
                ),
                SizedBox(height: context.space.space4),
                // A 30 px slide beside a stationary photograph, so the image
                // does not read as having moved (motion catalog row 41).
                AnimatedSwitcher(
                  duration: motion.reduced ? motion.quick : motion.standard,
                  switchInCurve: MotionTokens.standardCurve,
                  layoutBuilder: (Widget? current, List<Widget> previous) =>
                      Stack(
                        alignment: AlignmentDirectional.topStart,
                        children: <Widget>[...previous, ?current],
                      ),
                  transitionBuilder: (Widget child, Animation<double> value) =>
                      FadeTransition(
                        opacity: value,
                        child: motion.reduced
                            ? child
                            : SlideTransition(
                                position: Tween<Offset>(
                                  begin: const Offset(_panelSlide, 0),
                                  end: Offset.zero,
                                ).animate(value),
                                child: child,
                              ),
                      ),
                  child: _segmentContent(context),
                ),
                SizedBox(height: context.space.space8),
              ],
            ),
          ),
        ),
        WorkbenchDecisionBar(
          compact: regime.isStacked,
          onConfirmCoverage: () => _decide(
            'coverage',
            'Confirm label coverage?',
            WorkbenchDecisionBar.coverageLabel,
          ),
          onApprove: () => _decide(
            'approve',
            'Approve this record?',
            WorkbenchDecisionBar.approveLabel,
          ),
          coverageBlockedReason: blockedReason('coverage'),
          approveBlockedReason: blockedReason('approve'),
          pendingCount: _pending.length,
          onSavePending: _savePending,
          onNext: widget.onNext,
          onPrevious: widget.onPrevious,
        ),
      ],
    );
  }

  /// The pinned source header of a stacked layout.
  ///
  /// The height is the blueprint's 40 percent of the viewport, offered
  /// through a loose `Flexible` so that a window too short to give it that
  /// much takes it from the photograph rather than pushing the decision bar
  /// off the screen.
  List<Widget> _stackedSource(BuildContext context) => <Widget>[
    Row(
      children: <Widget>[
        Expanded(
          child: Text(
            'Source photograph',
            style: Theme.of(context).textTheme.titleSmall,
          ),
        ),
        IconButton(
          tooltip: _sourceCollapsed
              ? 'Show the photograph'
              : 'Collapse the photograph',
          onPressed: () => setState(() => _sourceCollapsed = !_sourceCollapsed),
          icon: Icon(
            _sourceCollapsed ? Symbols.expand_more : Symbols.expand_less,
          ),
        ),
      ],
    ),
    if (!_sourceCollapsed)
      Flexible(
        fit: FlexFit.loose,
        child: SizedBox(
          height: pinnedSourceHeight(context),
          child: _sourcePane(context, compact: true),
        ),
      ),
  ];

  // ------------------------------------------------------- large records

  Widget _largeRecord(BuildContext context, WorkbenchRegime regime) {
    final Specimen s = widget.specimen;
    final Widget evidence = LargeRecordEvidence(
      key: ValueKey<String>('graph:${s.id}:${s.revision}'),
      specimen: s,
      load: widget.loadArtifact,
    );
    final Widget side = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        OperationalPanel(
          specimen: s,
          canOperate: widget.canOperate,
          busy: widget.busy,
          onAction: _send,
        ),
        _history(ValueKey<String>('history:${s.id}:${s.revision}')),
      ],
    );

    return Padding(
      padding: EdgeInsets.all(context.space.space4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _header(context),
          Expanded(
            child: regime.isStacked
                ? ListView(children: <Widget>[evidence, side])
                : Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Expanded(
                        flex: 3,
                        child: SingleChildScrollView(child: evidence),
                      ),
                      SizedBox(width: context.space.space4),
                      Expanded(
                        flex: 2,
                        child: SingleChildScrollView(child: side),
                      ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }

  // -------------------------------------------------------------- build

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) {
      final WorkbenchRegime regime = WorkbenchRegime.fromWidth(
        constraints.maxWidth,
      );
      final Widget body = widget.specimen.data['artifact_receipt'] is Map
          ? _largeRecord(context, regime)
          : _workbench(context, regime);
      return Shortcuts(
        shortcuts: workbenchShortcuts(),
        child: Actions(
          actions: _actions(context),
          // The map only fires while focus is inside this subtree, which is
          // also what keeps it inert while a reason sheet owns the focus
          // (responsive 4).
          child: FocusScope(
            autofocus: true,
            debugLabel: 'workbench',
            child: body,
          ),
        ),
      );
    },
  );

  Map<Type, Action<Intent>> _actions(BuildContext context) =>
      <Type, Action<Intent>>{
        NextSpecimenIntent: CallbackAction<NextSpecimenIntent>(
          onInvoke: (_) {
            widget.onNext?.call();
            return null;
          },
        ),
        PreviousSpecimenIntent: CallbackAction<PreviousSpecimenIntent>(
          onInvoke: (_) {
            widget.onPrevious?.call();
            return null;
          },
        ),
        SelectRegionIntent: CallbackAction<SelectRegionIntent>(
          onInvoke: (SelectRegionIntent intent) {
            final List<Json> regions = widget.specimen.regions;
            if (intent.index <= regions.length) {
              _selectRegion(textOf(regions[intent.index - 1]['region_id'], ''));
            }
            return null;
          },
        ),
        ShowSegmentIntent: CallbackAction<ShowSegmentIntent>(
          onInvoke: (ShowSegmentIntent intent) {
            final List<WorkbenchSegment> all = WorkbenchSegment.values;
            if (intent.index < all.length) {
              setState(() => _segment = all[intent.index]);
            }
            return null;
          },
        ),
        ZoomInIntent: CallbackAction<ZoomInIntent>(
          onInvoke: (_) {
            _view.zoomIn();
            return null;
          },
        ),
        ZoomOutIntent: CallbackAction<ZoomOutIntent>(
          onInvoke: (_) {
            _view.zoomOut();
            return null;
          },
        ),
        FitViewIntent: CallbackAction<FitViewIntent>(
          onInvoke: (_) {
            _view.fit();
            return null;
          },
        ),
        RotateViewIntent: CallbackAction<RotateViewIntent>(
          onInvoke: (_) {
            _view.rotate();
            return null;
          },
        ),
        ApproveIntent: CallbackAction<ApproveIntent>(
          onInvoke: (_) {
            if (blockedReason('approve') == null) {
              _decide(
                'approve',
                'Approve this record?',
                WorkbenchDecisionBar.approveLabel,
              );
            }
            return null;
          },
        ),
        ConfirmCoverageIntent: CallbackAction<ConfirmCoverageIntent>(
          onInvoke: (_) {
            if (blockedReason('coverage') == null) {
              _decide(
                'coverage',
                'Confirm label coverage?',
                WorkbenchDecisionBar.coverageLabel,
              );
            }
            return null;
          },
        ),
        ShowShortcutsIntent: CallbackAction<ShowShortcutsIntent>(
          onInvoke: (_) {
            showShortcutSheet(context);
            return null;
          },
        ),
      };

  Widget _workbench(BuildContext context, WorkbenchRegime regime) {
    if (regime.isStacked) {
      return Padding(
        padding: EdgeInsets.symmetric(
          horizontal: context.space.space4,
        ).copyWith(top: context.space.space4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _header(context),
            ..._stackedSource(context),
            SizedBox(height: context.space.space2),
            Expanded(child: _evidencePane(context, regime)),
          ],
        ),
      );
    }

    return Padding(
      padding: EdgeInsets.all(context.space.space4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _header(context),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Expanded(flex: regime.sourceFlex, child: _sourcePane(context)),
                SizedBox(width: context.space.space4),
                Expanded(
                  flex: regime.evidenceFlex,
                  child: _evidencePane(context, regime),
                ),
                if (regime == WorkbenchRegime.threePane) ...<Widget>[
                  SizedBox(width: context.space.space4),
                  SizedBox(
                    width: historyPaneWidth,
                    child: Semantics(
                      container: true,
                      label: 'History',
                      child: SingleChildScrollView(
                        child: _history(const ValueKey<String>('history-pane')),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  static const int _recentReasonLimit = 5;
  static const double _panelSlide = 0.06;
}
