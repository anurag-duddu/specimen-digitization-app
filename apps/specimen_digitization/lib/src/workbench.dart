/// The review workbench (screen blueprints, section 6).
///
/// Three regions at every window class: the source pane, the evidence pane
/// and the decision bar. The photograph never scrolls away, every correction
/// happens with the pixels on screen, and the corrections a reviewer makes on
/// one record are saved together under one reason.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'audit_history.dart';
import 'evidence_panel.dart';
import 'large_record.dart';
import 'models.dart';
import 'reason_codes.dart';
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

/// The evidence pane's own scroll view.
///
/// Named, because "the first `Scrollable` in the tree" is not the evidence
/// pane: the source pane's region chip strip and the segment selector are
/// both scroll views too, and a test that addresses the wrong one proves
/// nothing about whether the pane a reviewer reads actually scrolls.
const Key evidenceScrollKey = ValueKey<String>('workbench-evidence-scroll');

class ReviewWorkbench extends StatefulWidget {
  const ReviewWorkbench({
    super.key,
    required this.specimen,
    required this.onChange,
    this.onChangeBatch,
    required this.onRetry,
    this.reviewerId = '',
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
    this.nextBlockedReason,
    this.previousBlockedReason,
    this.positionLabel,
  });
  final Specimen specimen;
  final Future<Json> Function(Specimen, ArtifactRequest)?
  loadHistoricalArtifact;
  final Future<Json> Function(ArtifactRequest)? loadArtifact;

  /// True only after the repository acknowledges this decision.
  final Future<bool> Function(Json change) onChange;

  /// Saves several corrections as one reviewer action under one reason, and
  /// answers how many the server acknowledged (pass criterion 7.2).
  ///
  /// `stillApplies` is asked before each call, against the record the call
  /// before it produced. It is how the batch keeps the guarantee the one at a
  /// time path gets for free: a draft whose field moved under the reviewer is
  /// never sent automatically against a newer revision. The batch stops there
  /// and reports how many landed.
  ///
  /// Optional, so a component test can pump the workbench with the one change
  /// callback alone; where it is absent the corrections go one at a time and
  /// the screen moves once per correction, which is what shipped before.
  final Future<int> Function(
    List<Json> changes,
    String reason,
    bool Function(Specimen current, Json change) stillApplies,
  )?
  onChangeBatch;

  final Future<void> Function(String reason) onRetry;

  /// The account whose recent reasons this workbench offers.
  ///
  /// Per reviewer rather than per device: an imaging station is shared, and
  /// one reviewer's reasons are not a suggestion for the next one
  /// (pass criterion 7.6).
  final String reviewerId;
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

  /// Why there is no next specimen: the end of the loaded queue.
  ///
  /// When this is set the control is drawn and disabled with the reason on
  /// it, and `J` says the reason aloud rather than doing nothing
  /// (pass criterion 5.6).
  final String? nextBlockedReason;

  /// Why there is no previous specimen: the head of the queue.
  final String? previousBlockedReason;

  /// Where this record sits in the loaded queue, as "3 of 38"
  /// (pass criterion 6.5).
  final String? positionLabel;

  @override
  State<ReviewWorkbench> createState() => _ReviewWorkbenchState();
}

class _ReviewWorkbenchState extends State<ReviewWorkbench> {
  WorkbenchSegment _segment = WorkbenchSegment.readings;

  /// Which way the last segment change moved along the chip row.
  ///
  /// Forward, meaning left to right in the chip row on LTR, sends the
  /// incoming panel in from the leading side and the outgoing one out the
  /// other way. Read from the chip order, never hard-coded, and mirrored
  /// under RTL by `Directionality` (motion catalog, row 41; choreography 5.3).
  bool _segmentForward = true;
  String? _region;
  bool _sourceCollapsed = false;
  List<PendingFieldChange> _pending = <PendingFieldChange>[];
  List<PendingFieldChange> _stale = <PendingFieldChange>[];
  List<String> _recentReasons = <String>[];
  late RecentReasonStore _reasonStore = RecentReasonStore(widget.reviewerId);
  int? _conflictVersion;
  bool _savingLocally = false;
  String? _announcement;

  final SourceViewController _view = SourceViewController();
  final ScrollController _evidenceScroll = ScrollController();
  final Map<String, GlobalKey> _regionAnchors = <String, GlobalKey>{};
  final Map<String, GlobalKey> _fieldAnchors = <String, GlobalKey>{};

  @override
  void initState() {
    super.initState();
    unawaited(_loadRecentReasons());
  }

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
    if (oldWidget.reviewerId != widget.reviewerId) {
      // A different account is a different list of recent reasons, never a
      // merge of the two (pass criterion 7.6).
      _reasonStore = RecentReasonStore(widget.reviewerId);
      _recentReasons = <String>[];
      unawaited(_loadRecentReasons());
    }
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
      if (id != null) _moveSegment(WorkbenchSegment.readings);
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
    setState(() => _moveSegment(blocker.segment));
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

  /// Records [reason] for next time, on the device, for this reviewer.
  ///
  /// In memory at once, so the next sheet offers it whatever the store does,
  /// and written behind the save so the reason survives a restart
  /// (pass criterion 7.6).
  void _rememberReason(String reason) {
    final List<String> next = <String>[
      reason,
      for (final String existing in _recentReasons)
        if (existing != reason) existing,
    ];
    setState(
      () => _recentReasons = next.length <= RecentReasonStore.limit
          ? next
          : next.sublist(0, RecentReasonStore.limit),
    );
    // The write happens behind the save. A preferences store that is slow, or
    // absent on this platform, must never hold up a decision the reviewer has
    // already confirmed.
    unawaited(
      _reasonStore.remember(reason).then((List<String> stored) {
        if (!mounted || stored.isEmpty) return;
        setState(() => _recentReasons = stored);
      }),
    );
  }

  Future<void> _loadRecentReasons() async {
    final List<String> stored = await _reasonStore.load();
    if (!mounted || stored.isEmpty) return;
    setState(() => _recentReasons = stored);
  }

  /// The decision reasons this record's collection or profile published.
  ///
  /// Empty against every collection document and profile this client has
  /// seen, which is why pass criterion 7.6 records what the API would have
  /// to publish rather than claiming the group ships full.
  List<String> get _configuredReasons => configuredReasonCodes(<Json?>[
    widget.collections
        .where(
          (CollectionScope c) =>
              c.collectionId == widget.specimen.data['collection_id'],
        )
        .firstOrNull
        ?.configuration,
    objectOf(widget.specimen.data['profile']),
  ]);

  /// The machine's reasons this record is in the queue, in plain words.
  List<String> get _recordReasons => recordReasonCodes(widget.specimen);

  /// True when [draft] is still against the value the record now holds.
  ///
  /// The same rule `reapply` uses, asked about one draft, so the batch path
  /// and the one at a time path agree on what "still applies" means.
  bool _draftStillApplies(Specimen current, PendingFieldChange draft) =>
      reapply(<PendingFieldChange>[draft], current).keep.isNotEmpty;

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
      configuredReasons: _configuredReasons,
      recordReasons: _recordReasons,
      recentReasons: _recentReasons,
    );
    if (reason == null || !mounted) return;
    _rememberReason(reason);

    final int saved = await _sendBatch(batch, reason);
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

  /// Sends every pending correction under one reason.
  ///
  /// Pass criterion 7.2. Where the host gave the workbench a batch callback,
  /// the whole set goes out under one idempotency key prefix and the screen
  /// moves once, at the end, rather than once per correction. Where it did
  /// not, this is the one at a time loop, kept so a component test can still
  /// drive the workbench with the one change callback alone.
  ///
  /// Both paths obey the same rule: a draft whose field moved under the
  /// reviewer is never sent automatically against a newer revision. The one
  /// at a time path checks between calls, because a readback has already
  /// reached this widget by then; the batch path hands the same check to the
  /// repository, which applies it against the record each call produced.
  ///
  /// Returns how many corrections the server acknowledged, and clears exactly
  /// those from the pending list.
  Future<int> _sendBatch(List<PendingFieldChange> batch, String reason) async {
    final Future<int> Function(
      List<Json>,
      String,
      bool Function(Specimen, Json),
    )?
    send = widget.onChangeBatch;

    if (send == null) {
      int saved = 0;
      for (final PendingFieldChange change in batch) {
        // A preceding readback may have invalidated a later draft. Never send
        // it from the original batch against a newer revision automatically.
        if (!_pending.contains(change) || blockedReason('field') != null) break;
        final bool landed = await _send(change.toChange(reason));
        if (!mounted) return saved;
        if (!landed) break;
        saved++;
      }
      return saved;
    }

    if (_savingLocally || widget.busy) return 0;
    final Map<String, PendingFieldChange> drafts = <String, PendingFieldChange>{
      for (final PendingFieldChange change in batch) change.fieldKey: change,
    };
    _savingLocally = true;
    int saved = 0;
    try {
      saved = await send(
        <Json>[
          for (final PendingFieldChange change in batch)
            change.toChange(reason),
        ],
        reason,
        (Specimen current, Json change) {
          final PendingFieldChange? draft = drafts[change['target_id']];
          return draft != null && _draftStillApplies(current, draft);
        },
      );
      // Let the acknowledged record reach this widget before anything reads
      // its version, exactly as the one at a time path does.
      if (mounted) await WidgetsBinding.instance.endOfFrame;
      return mounted ? saved : 0;
    } catch (_) {
      return 0;
    } finally {
      _savingLocally = false;
      if (mounted) {
        setState(() {
          final Set<String> landed = <String>{
            for (final PendingFieldChange change in batch.take(saved))
              change.fieldKey,
          };
          _pending.removeWhere(
            (PendingFieldChange p) => landed.contains(p.fieldKey),
          );
          _stale.removeWhere(
            (PendingFieldChange p) => landed.contains(p.fieldKey),
          );
          _reapplyPending();
        });
      }
    }
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
      configuredReasons: _configuredReasons,
      recordReasons: _recordReasons,
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
      configuredReasons: _configuredReasons,
      recordReasons: _recordReasons,
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

  Widget _sourcePane(
    BuildContext context, {
    bool compact = false,
    double? imageHeight,
  }) => WorkbenchSourcePane(
    specimen: widget.specimen,
    compact: compact,
    imageHeight: imageHeight,
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

  /// Moves to [next], remembering which way along the chip row it went.
  ///
  /// Call inside `setState`; it assigns, it does not schedule a rebuild.
  void _moveSegment(WorkbenchSegment next) {
    _segmentForward = next.index >= _segment.index;
    _segment = next;
  }

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

  /// A control, plus the reason it cannot be used.
  ///
  /// `MergeSemantics` is what makes the reason audible. Without it the hint
  /// lands on a node of its own and the disabled button becomes a separate
  /// child node beneath it, so a screen reader focusing the control hears
  /// "Approve record, dimmed" and never the sentence saying why
  /// (accessibility, section 3.2 and the section 4.2 VoiceOver script,
  /// step 4).
  ///
  /// The enabled state is repeated on the merged node rather than left to the
  /// button underneath it, because a merge boundary keeps its own flags and a
  /// node that does not say it is disabled is read, and checked, as if it
  /// were live.
  Widget _reasoned(String? reason, Widget child) => Tooltip(
    message: reason ?? '',
    child: MergeSemantics(
      child: Semantics(
        hint: reason ?? '',
        enabled: reason == null,
        child: child,
      ),
    ),
  );

  Widget _history(Key key) => AuditHistoryPanel(
    key: key,
    specimen: widget.specimen,
    loadPage: widget.loadHistoryPage,
    loadRevision: widget.loadHistoricalRevision,
    loadArtifact: widget.loadHistoricalArtifact,
  );

  /// The evidence pane: the scrolling evidence, with the decision bar pinned
  /// beneath it.
  ///
  /// The two are separate widgets rather than one column, because on a phone
  /// the bar's height has to come out of the layout before the photograph and
  /// the evidence split what is left. Taking it out of the evidence pane's
  /// own share is what left the pane with no viewport, and a scroll view with
  /// no viewport does not scroll.
  Widget _evidencePane(BuildContext context, WorkbenchRegime regime) {
    // At a large text scale the decision bar wraps to three rows of large
    // type and is taller than what is left of the pane, so pinning it lays
    // the pane out past its box. The pane then scrolls as one, bar included,
    // rather than clipping the last row (finding V-1, pass criterion 8.5).
    if (paneScrollsAtThisTextScale(MediaQuery.textScalerOf(context))) {
      return SingleChildScrollView(
        key: evidenceScrollKey,
        controller: _evidenceScroll,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            _evidenceContent(context, regime, scrollable: false),
            _decisionBar(context, regime),
          ],
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Expanded(child: _evidenceContent(context, regime)),
        _decisionBar(context, regime),
      ],
    );
  }

  /// The evidence pane's content.
  ///
  /// [scrollable] is false in the one case where the record is too short for
  /// a pinned photograph and a scrolling pane beneath it: the whole record
  /// then scrolls as one, so this returns the content without a scroll view
  /// of its own rather than nesting one inside another (finding V-1).
  Widget _evidenceContent(
    BuildContext context,
    WorkbenchRegime regime, {
    bool scrollable = true,
    Widget? leading,
  }) {
    final List<WorkbenchSegment> segments = WorkbenchSegment.forRegime(regime);
    final WorkbenchSegment selected = segments.contains(_segment)
        ? _segment
        : WorkbenchSegment.readings;
    final MotionTokens motion = context.motion;

    final Widget content = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        // The record's own header scrolls with the evidence on a stacked
        // layout, so the photograph is what stays. The title and the
        // identifier are worth reading once; the pixels are what every
        // correction is checked against (blueprint 6.1, pass criterion 6.1).
        ?leading,
        if (regime.isStacked) ...<Widget>[
          SourceOrientationCaveat(
            asset: widget.specimen.assets.isEmpty
                ? const <String, dynamic>{}
                : widget.specimen.assets.first,
          ),
          SourceRegionEditControl(
            onEditRegions: !_regionsEditable || blockedReason('regions') != null
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
            // The roles are what VoiceOver and TalkBack read as "tab, 1 of 3,
            // selected", and what a rotor jumps between. Without them
            // Material's own `checked` and `inMutuallyExclusiveGroup` are read
            // as a radio button, which is finding V-3 and accessibility
            // section 4.2 step 6.
            child: Semantics(
              role: SemanticsRole.tabBar,
              explicitChildNodes: true,
              child: SegmentedButton<WorkbenchSegment>(
                segments: <ButtonSegment<WorkbenchSegment>>[
                  for (final WorkbenchSegment s in segments)
                    ButtonSegment<WorkbenchSegment>(
                      value: s,
                      label: Semantics(
                        role: SemanticsRole.tab,
                        child: Text(s.label),
                      ),
                    ),
                ],
                selected: <WorkbenchSegment>{selected},
                showSelectedIcon: false,
                onSelectionChanged: (Set<WorkbenchSegment> next) =>
                    setState(() {
                      _moveSegment(next.first);
                      SpecimenHaptics.selectionChanged();
                    }),
              ),
            ),
          ),
        ),
        SizedBox(height: context.space.space4),
        // A 30 px slide beside a stationary photograph, so the image
        // does not read as having moved (motion catalog row 41).
        AnimatedSwitcher(
          duration: motion.reduced ? motion.quick : motion.standard,
          switchInCurve: MotionTokens.standardCurve,
          layoutBuilder: (Widget? current, List<Widget> previous) => Stack(
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
                          begin: Offset(_panelOffset(context), 0),
                          end: Offset.zero,
                        ).animate(value),
                        child: child,
                      ),
              ),
          child: _segmentContent(context),
        ),
        // The decision bar is pinned below this pane and a phone puts
        // a gesture bar below that. The content ends clear of both,
        // so the last row is reachable rather than sitting under
        // them.
        SizedBox(
          height:
              context.space.space8 + MediaQuery.viewPaddingOf(context).bottom,
        ),
      ],
    );

    if (!scrollable) {
      return Padding(
        padding: EdgeInsets.symmetric(horizontal: context.space.space4),
        child: content,
      );
    }
    return SingleChildScrollView(
      key: evidenceScrollKey,
      controller: _evidenceScroll,
      padding: EdgeInsets.symmetric(horizontal: context.space.space4),
      child: content,
    );
  }

  /// Records a measured piece of the stacked layout's fixed chrome.
  ///
  /// Four parts: the record header, the source pane's title row, the source
  /// pane's own chrome, and the decision bar. Every one of them is measured
  /// rather than guessed, because each grows with the text scale and with the
  /// window, and the photograph's band is what is left after all four.
  void _measureChrome(String part, double height) {
    final double clamped = height < 0 ? 0 : height;
    final double? previous = _chromeParts[part];
    if (previous != null && (previous - clamped).abs() < 0.5) return;
    if (!mounted) return;
    setState(() => _chromeParts[part] = clamped);
  }

  final Map<String, double> _chromeParts = <String, double>{};

  /// How the stacked layout is arranged this frame.
  ///
  /// The record's own header is not counted: on a stacked layout it scrolls
  /// with the evidence, so that the photograph is what stays on the screen.
  ///
  /// [band] is the height the photograph's own pixels get, zero when the
  /// reviewer has collapsed the pane. [scrolls] is true when the record is
  /// too short to pin the photograph above a scrolling evidence pane, in
  /// which case the whole record scrolls as one and the photograph is still
  /// on the screen rather than replaced by an overflow stripe. [pinBar] is
  /// false in the last resort, where the decision bar alone is taller than
  /// the height this pane was given, and pinning it would push everything
  /// else past the window (finding V-1, pass criteria 6.1 and 8.5).
  ({double band, bool scrolls, bool pinBar}) _stackedPlan(
    BuildContext context,
    double available,
  ) {
    final double? bar = _chromeParts['bar'];
    final double? title = _chromeParts['sourceTitle'];
    final double? pane = _chromeParts['sourcePane'];
    if (bar == null || title == null || (pane == null && !_sourceCollapsed)) {
      // Nothing has been measured yet. The scrolling form cannot lay out past
      // the window whatever the measurements turn out to be, so the first
      // frame takes it and the pinned form starts once the numbers are in.
      return (
        band: _sourceCollapsed ? 0 : sourceImageMinHeight,
        scrolls: true,
        pinBar: false,
      );
    }
    // The bar is pinned only while there is still a pane left underneath it.
    // At 200 percent text on a phone the shell can hand the record barely
    // two hundred pixels, and a bar that wraps to three rows of large type is
    // taller than that on its own.
    final bool pinBar = available - bar >= evidencePaneHardMinHeight;
    final double fixed =
        bar + title + (_sourceCollapsed ? 0 : pane!) + context.space.space2;
    final double free = available - fixed;
    if (_sourceCollapsed) {
      return (
        band: 0,
        scrolls: !pinBar || free < evidencePaneHardMinHeight,
        pinBar: pinBar,
      );
    }
    final double band = pinBar ? pinnedSourceHeight(available, free) : 0;
    return band > 0
        ? (band: band, scrolls: false, pinBar: true)
        : (band: sourceImageMinHeight, scrolls: true, pinBar: pinBar);
  }

  Widget _decisionBar(BuildContext context, WorkbenchRegime regime) =>
      WorkbenchDecisionBar(
        compact: regime.isStacked,
        busy: widget.busy,
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
        nextBlockedReason: widget.nextBlockedReason,
        previousBlockedReason: widget.previousBlockedReason,
        positionLabel: widget.positionLabel,
      );

  /// The pinned source header of a stacked layout (blueprint 6.1).
  ///
  /// The title row is always drawn and always measured, so the collapse and
  /// expand control is reachable whether or not the photograph is on screen.
  /// The pane below it is handed a band for its pixels rather than a height
  /// for the whole pane, so its controls and its region chips are never
  /// squeezed by a box that was sized without them.
  List<Widget> _stackedSource(BuildContext context, double band) => <Widget>[
    MeasuredHeight(
      onHeight: (double h) => _measureChrome('sourceTitle', h),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              'Source photograph',
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
          if (band <= 0)
            IconButton(
              tooltip: 'Open the photograph full screen',
              onPressed: () => showSourceFullScreen(
                context,
                specimen: widget.specimen,
                selectedRegionId: _region,
                onSelectRegion: _selectRegion,
              ),
              icon: const Icon(Symbols.open_in_full),
            ),
          IconButton(
            tooltip: _sourceCollapsed
                ? 'Show the photograph'
                : 'Collapse the photograph',
            onPressed: () =>
                setState(() => _sourceCollapsed = !_sourceCollapsed),
            icon: Icon(
              _sourceCollapsed ? Symbols.expand_more : Symbols.expand_less,
            ),
          ),
        ],
      ),
    ),
    if (band > 0)
      // The pane reports its own chrome by subtracting the band it was given
      // from the height it ended up at, which is the one measurement the
      // photograph's share cannot be computed without.
      MeasuredHeight(
        onHeight: (double h) => _measureChrome('sourcePane', h - band),
        child: _sourcePane(context, compact: true, imageHeight: band),
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
            _step(widget.onNext, widget.nextBlockedReason);
            return null;
          },
        ),
        PreviousSpecimenIntent: CallbackAction<PreviousSpecimenIntent>(
          onInvoke: (_) {
            _step(widget.onPrevious, widget.previousBlockedReason);
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
              setState(() => _moveSegment(all[intent.index]));
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

  /// Moves along the queue, or says why it cannot.
  ///
  /// A key bound to a callback that is null is exactly the silent no-op pass
  /// criterion 5.6 forbids, and it is what finding V-2 found `J` and `K`
  /// doing. At the ends of the queue the reason is announced instead.
  void _step(VoidCallback? move, String? reason) {
    if (move != null) {
      move();
      return;
    }
    if (reason != null) _announce(reason);
  }

  Widget _workbench(BuildContext context, WorkbenchRegime regime) {
    if (regime.isStacked) {
      return Padding(
        padding: EdgeInsets.symmetric(
          horizontal: context.space.space4,
        ).copyWith(top: context.space.space4),
        // The photograph's share is measured against the height this pane was
        // actually given, not against the window. On a phone the two differ by
        // the app bar, the navigation bar, the environment band and the system
        // insets, and the difference is the whole evidence pane.
        child: LayoutBuilder(
          builder: (BuildContext context, BoxConstraints box) {
            final double available = box.maxHeight.isFinite
                ? box.maxHeight
                : MediaQuery.sizeOf(context).height;
            final ({double band, bool scrolls, bool pinBar}) plan =
                _stackedPlan(context, available);
            final Widget bar = MeasuredHeight(
              onHeight: (double h) => _measureChrome('bar', h),
              child: _decisionBar(context, regime),
            );
            final Widget header = _header(context);

            if (plan.scrolls) {
              // Too short to pin the photograph above a scrolling pane at this
              // text scale. The record scrolls as one instead, so nothing is
              // clipped and the photograph is still on the screen, and the
              // decision bar stays pinned beneath it where it still fits
              // (finding V-1).
              final Widget scrolled = SingleChildScrollView(
                key: evidenceScrollKey,
                controller: _evidenceScroll,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    header,
                    ..._stackedSource(context, plan.band),
                    SizedBox(height: context.space.space2),
                    _evidenceContent(context, regime, scrollable: false),
                    if (!plan.pinBar) bar,
                  ],
                ),
              );
              return plan.pinBar
                  ? Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        Expanded(child: scrolled),
                        bar,
                      ],
                    )
                  : scrolled;
            }

            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                ..._stackedSource(context, plan.band),
                SizedBox(height: context.space.space2),
                Expanded(
                  child: _evidenceContent(context, regime, leading: header),
                ),
                bar,
              ],
            );
          },
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

  static const double _panelSlide = 0.06;

  /// The incoming panel's starting offset, as a fraction of its own width.
  ///
  /// Capped at a fraction rather than a full width because the panel sits
  /// beside a stationary photograph: a large horizontal slide next to a still
  /// image produces induced motion, and the photograph appears to drift the
  /// other way (choreography 5.4).
  double _panelOffset(BuildContext context) {
    final bool rtl = Directionality.of(context) == TextDirection.rtl;
    final bool fromEnd = _segmentForward != rtl;
    return fromEnd ? _panelSlide : -_panelSlide;
  }
}
