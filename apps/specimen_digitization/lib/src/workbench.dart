/// The review workbench (13 section 4.1; screen blueprints, section 6).
///
/// One screen, composed rather than stacked. On a phone and a tablet in
/// portrait it is one `CustomScrollView`: the photograph is a
/// `UiCollapsingHeader` pinned between 55 and 40 percent of the viewport, the
/// status strip and the evidence scroll beneath it, and the segments stick
/// under the header. From the expanded class up the two and three pane
/// arrangements stay, each pane one scroll and none inside another.
///
/// The chrome is the frame's. The record names itself in the top bar, hides
/// the navigation pill, asks for the one line environment band and fills the
/// action bar with its decision bar, all four through `UiScaffoldSlots`, so
/// the shell owns the top and the bottom of the window and the chrome budget
/// with them (13 sections 2.3 and 3.4). What is left is the work: the
/// photograph never scrolls away, every correction happens with the pixels on
/// screen, and the corrections a reviewer makes on one record are saved
/// together under one reason.
library;

import 'dart:async';

import 'package:flutter/foundation.dart' show listEquals;
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

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

/// The command that puts the identifier on the clipboard.
const String copyIdentifierLabel = 'Copy the specimen identifier';

/// The control that reloads the record.
const String refreshLabel = 'Refresh this record';

/// What the toast says once the identifier is on the clipboard.
const String copiedMessage = 'Specimen identifier copied';

/// What the screen says when collection access has not been answered.
const String noCollectionMessage =
    'Collection configuration is unavailable. Refresh collection access.';

/// The two occasional actions of the fields panel, named once.
const String classificationLabel = 'Correct classification';

/// The control that asks the server to process the record again.
const String retryLabel = 'Retry processing';

/// What the evidence strip calls itself to a screen reader.
const String evidenceTabsLabel = 'Evidence panels';

/// The command that shows the photograph's checksum and coordinate basis.
const String sourceDetailsLabel = 'Source details';

/// What the top bar's back control is called, wherever a record is open.
const String backToQueueLabel = 'Back to queue';

/// What a step along the queue says when this record is not in the loaded
/// list at all, so there is neither a neighbour nor a reason there is none.
///
/// `UiDecisionBar` draws its two edge controls from `medium` up whether or
/// not the screen gave it somewhere to go, so the record answers every press
/// rather than leaving one of them a control that does nothing (pass
/// criterion 5.6, finding V-2). The same sentence answers the `J` and `K`
/// keys and the compact swipe.
///
/// fe/polish-3: `UiDecisionBar` should draw no edge control where there is no
/// move, and should take the reason for its absence where there is one, the
/// way every other control in the system carries a `disabledReason`.
const String notInQueueMessage = 'This record is not in the loaded queue.';

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
    this.onBack,
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

  /// Leaves the record for the list it came from.
  ///
  /// The way out of a record is the top bar's back, which this record
  /// publishes into the frame itself: the navigation pill is hidden inside a
  /// record and a screen with neither is a screen a reviewer is stuck on
  /// (13 sections 2.3 and 2.4). Null where the host offers no way back, which
  /// is a component test pumping the workbench on its own.
  final VoidCallback? onBack;

  @override
  State<ReviewWorkbench> createState() => _ReviewWorkbenchState();
}

class _ReviewWorkbenchState extends State<ReviewWorkbench> {
  WorkbenchSegment _segment = WorkbenchSegment.readings;

  /// Which tab the strip is on, as the index into [WorkbenchSegment.values].
  ///
  /// `UiTabs` owns the selection and writes into this, so the strip and the
  /// panel below it cannot disagree. The index into the visible list is the
  /// same number as the index into the enum, because the only list the regime
  /// shortens drops the last entry (`WorkbenchSegment.forRegime`).
  final ValueNotifier<int> _tab = ValueNotifier<int>(0);

  /// How the record is arranged this frame, so a shortcut and a blocker can
  /// tell whether History is a tab or a pane of its own.
  WorkbenchRegime _regime = WorkbenchRegime.stacked;

  String? _region;
  List<PendingFieldChange> _pending = <PendingFieldChange>[];
  List<PendingFieldChange> _stale = <PendingFieldChange>[];
  List<String> _recentReasons = <String>[];
  late RecentReasonStore _reasonStore = RecentReasonStore(widget.reviewerId);
  int? _conflictVersion;
  bool _savingLocally = false;
  String? _announcement;

  /// What this screen has asked of the frame around it (13 section 3.4).
  ///
  /// Held rather than looked up in `dispose`, which runs after this element is
  /// detached and can no longer reach an inherited widget.
  UiScaffoldSlots? _slots;

  final SourceViewController _view = SourceViewController();
  final ScrollController _evidenceScroll = ScrollController();
  final Map<String, GlobalKey> _regionAnchors = <String, GlobalKey>{};
  final Map<String, GlobalKey> _fieldAnchors = <String, GlobalKey>{};

  @override
  void initState() {
    super.initState();
    _tab.addListener(_tabChanged);
    unawaited(_loadRecentReasons());
  }

  /// The tab strip moved. The panel follows it, and the reviewer feels the
  /// selection tick the catalog gives this one change (row 41).
  void _tabChanged() {
    final List<WorkbenchSegment> segments = WorkbenchSegment.forRegime(_regime);
    final WorkbenchSegment next =
        segments[_tab.value.clamp(0, segments.length - 1)];
    if (next == _visibleSegment) return;
    setState(() {
      _segment = next;
      SpecimenHaptics.selectionChanged();
    });
  }

  /// The segment actually on screen, which is Readings wherever the regime
  /// has taken History out of the strip and made it a pane.
  WorkbenchSegment get _visibleSegment =>
      WorkbenchSegment.forRegime(_regime).contains(_segment)
      ? _segment
      : WorkbenchSegment.readings;

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
  void didChangeDependencies() {
    super.didChangeDependencies();
    _slots = UiScaffoldSlots.of(context);
    _publish(context);
  }

  @override
  void dispose() {
    // Only what this screen still holds: the router builds the screen
    // arriving before it disposes the screen leaving, so clearing the slots
    // outright would take the next screen's chrome with it.
    _slots?.release(this);
    _tab
      ..removeListener(_tabChanged)
      ..dispose();
    _view.dispose();
    _evidenceScroll.dispose();
    super.dispose();
  }

  /// Asks the frame for the chrome a record needs (13 sections 2.3 and 3.4).
  ///
  /// Four asks. The bar across the top carries the identifier, the way out
  /// and the record's own commands, none of which the shell that built the
  /// frame holds. The action bar carries the decision bar, so the two
  /// decisions sit on the frame's one pane rather than on a second one over
  /// it. The navigation pill is hidden, because the way out of a record is
  /// the bar's back and three other destinations are chrome the reviewer did
  /// not ask for. The band drops to its one line form, which is what buys the
  /// action bar its share of the budget on a phone.
  ///
  /// Called from `build`, because every one of the four reads state that
  /// changes under the reviewer: the identifier when the record is replaced,
  /// the two decisions when the server withdraws one, the count when the
  /// queue moves. A publish during a build is announced after it, which is
  /// what `UiScaffoldSlots` promises, and the frame rebuilds the chrome and
  /// not the body, so the two settle rather than chase each other.
  void _publish(BuildContext context) {
    final UiScaffoldSlots? slots = _slots;
    if (slots == null) return;
    final List<Object?> now = _chromeState();
    if (_published != null && listEquals(_published, now)) return;
    _published = now;
    slots
      ..setTopBar(_recordTopBar(context), owner: this)
      ..setActionBar(_decisionBar(context), owner: this)
      ..setNavVisible(false, owner: this)
      ..setBandCompact(true, owner: this);
  }

  /// What the published chrome is built from.
  ///
  /// A widget has no value equality, so a frame rebuilt for any reason would
  /// otherwise publish a new bar, the frame would rebuild to draw it, and
  /// this screen would publish again on the way back: the chrome and the body
  /// chasing each other one frame apart for as long as the record is open.
  /// This is every value the two bars read, compared before publishing, so a
  /// rebuild that changes none of them changes nothing in the frame.
  List<Object?> _chromeState() => <Object?>[
    widget.specimen.id,
    widget.busy,
    _pending.length,
    widget.onBack == null,
    widget.positionLabel,
    widget.onNext == null,
    widget.onPrevious == null,
    widget.nextBlockedReason,
    widget.previousBlockedReason,
    blockedReason('approve'),
    blockedReason('coverage'),
    blockedReason('classification'),
    _regionEditBlockedReason,
    _retryBlockedReason,
  ];

  /// The state the chrome on screen was built from.
  List<Object?>? _published;

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
      duration: context.ui.motion.standard,
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
      UiToasts.show(context, message: noCollectionMessage, icon: UiIcons.error);
      return;
    }
    final Json? result = await showClassificationForm(
      context,
      specimen: widget.specimen,
      scope: scope,
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
    UiToasts.show(context, message: copiedMessage, icon: UiIcons.copy);
  }

  /// The record's own bar across the top (13 section 4.1).
  ///
  /// Back, the specimen identifier in `mono.identifier`, and the commands
  /// that belong to the record rather than to any one segment of it. The bar
  /// keeps the first two of them beside the identifier and puts the rest in
  /// its own overflow menu, which is the fit policy 11 section 3.3 gives it,
  /// so a phone reaches every command through one control instead of four
  /// rows of the page.
  ///
  /// The collection switcher is deliberately absent: a reviewer inside a
  /// record is inside one collection, and a control that would take them to
  /// another is the top bar doing a second job (13 sections 2.4 and 4.1).
  Widget _recordTopBar(BuildContext context) {
    final UiThemeData ui = context.ui;
    return UiTopBar(
      leading: widget.onBack == null
          ? null
          : UiIconButton(
              icon: UiIcons.back,
              semanticsLabel: backToQueueLabel,
              tooltip: backToQueueLabel,
              onPressed: widget.onBack,
            ),
      // The centre slot rather than the title, because an identifier is set
      // in `mono.identifier` and a title is set in `type.title`: two records
      // whose identifiers differ by one character have to be told apart at a
      // glance (blueprint 6.1).
      center: UiLabel(
        widget.specimen.id,
        style: ui.type.mono.identifier.copyWith(color: ui.color.ink),
      ),
      actions: <Widget>[
        UiTopBarAction(
          icon: UiIcons.reload,
          label: refreshLabel,
          disabledReason: widget.busy
              ? 'Wait for the save that is in flight to finish'
              : null,
          onPressed: widget.busy ? null : _refresh,
        ),
        UiTopBarAction(
          icon: UiIcons.correctRegions,
          label: SourceRegionEditControl.label,
          disabledReason: _regionEditBlockedReason,
          onPressed: _regionEditBlockedReason != null ? null : _editRegions,
        ),
        UiTopBarAction(
          icon: UiIcons.provenance,
          label: classificationLabel,
          disabledReason: blockedReason('classification'),
          onPressed: blockedReason('classification') != null
              ? null
              : _classification,
        ),
        UiTopBarAction(
          icon: UiIcons.retry,
          label: retryLabel,
          disabledReason: _retryBlockedReason,
          onPressed: _retryBlockedReason != null ? null : _retry,
        ),
        UiTopBarAction(
          icon: UiIcons.copy,
          label: copyIdentifierLabel,
          onPressed: () => _copyIdentifier(context),
        ),
        UiTopBarAction(
          icon: UiIcons.provenance,
          label: sourceDetailsLabel,
          onPressed: () => showSourceDetailsSheet(context, asset: _asset),
        ),
        UiTopBarAction(
          icon: UiIcons.keyboard,
          label: shortcutSheetTitle,
          shortcut: 'Question mark',
          onPressed: () => showShortcutSheet(context),
        ),
      ],
    );
  }

  /// The photograph this record carries, or an empty asset where it has none.
  Json get _asset => widget.specimen.assets.isEmpty
      ? const <String, dynamic>{}
      : widget.specimen.assets.first;

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

  /// Moves to [next], and takes the tab strip with it.
  ///
  /// Call inside `setState`; it assigns, it does not schedule a rebuild. The
  /// notifier's own listener sees the two already agree and does nothing.
  void _moveSegment(WorkbenchSegment next) {
    _segment = next;
    final List<WorkbenchSegment> segments = WorkbenchSegment.forRegime(_regime);
    _tab.value = segments.contains(next) ? next.index : 0;
  }

  Widget _segmentContent(
    BuildContext context,
    WorkbenchSegment segment,
  ) => switch (segment) {
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
        SizedBox(height: context.ui.space.s6),
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
        SizedBox(height: context.ui.space.s6),
        ReviewContext(specimen: widget.specimen),
        SizedBox(height: context.ui.space.s4),
        // The run internals, one closed disclosure, where the blocker that
        // names them sends the reviewer. An operator's concern rather than a
        // reviewer's, which is why it is not on the status strip and not a
        // row of the page (audit finding H8.2; 13 section 4.1).
        ProcessingDisclosure(
          specimen: widget.specimen,
          canOperate: widget.canOperate,
          busy: widget.busy,
          onAction: _send,
        ),
      ],
    ),
    WorkbenchSegment.history => _history(const ValueKey<String>('history')),
  };

  Widget _history(Key key) => AuditHistoryPanel(
    key: key,
    specimen: widget.specimen,
    loadPage: widget.loadHistoryPage,
    loadRevision: widget.loadHistoricalRevision,
    loadArtifact: widget.loadHistoricalArtifact,
  );

  /// The evidence pane of a side by side regime: one scroll, and only one.
  ///
  /// The decision bar is not in it. It is the frame's action bar now, which
  /// is the one place 13 section 3.3 puts it, so the arithmetic that used to
  /// take the bar's height out of the pane before the photograph and the
  /// evidence split what was left is gone with it.
  Widget _evidencePane(BuildContext context, WorkbenchRegime regime) {
    final UiThemeData ui = context.ui;
    return SingleChildScrollView(
      key: evidenceScrollKey,
      controller: _evidenceScroll,
      padding: EdgeInsetsDirectional.symmetric(
        horizontal: ui.space.s4,
      ).add(EdgeInsets.only(bottom: UiScaffold.of(context).bottomInset)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: _evidence(context, regime),
      ),
    );
  }

  /// The evidence, as the rows every regime draws in the same order.
  ///
  /// The status strip, the segments and the chosen segment's content. A box
  /// list rather than a sliver list, because the side by side regimes put it
  /// in a pane's own scroll and the one scroll regime puts each row in a
  /// sliver of its own; both read this and neither restates it.
  List<Widget> _evidence(BuildContext context, WorkbenchRegime regime) {
    final UiThemeData ui = context.ui;
    _syncTabs(regime);
    return <Widget>[
      _statusStrip(context),
      SizedBox(height: ui.space.s3),
      _segments(context, regime),
      SizedBox(height: ui.space.s4),
      _segmentPanel(context, regime),
    ];
  }

  /// Keeps the strip and the panel from disagreeing about which segment is on.
  ///
  /// A window that crosses into the three pane layout takes History out of
  /// the strip. The strip cannot be corrected inside a build, so the frame
  /// that crosses draws the clamped tab and the next one draws the right one.
  void _syncTabs(WorkbenchRegime regime) {
    _regime = regime;
    final int count = WorkbenchSegment.forRegime(regime).length;
    if (_tab.value < count) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _tab.value >= count) _tab.value = 0;
    });
  }

  /// Where the record stands, and what is holding a decision up.
  Widget _statusStrip(BuildContext context) => WorkbenchStatusStrip(
    specimen: widget.specimen,
    blockers: blockersFor(widget.specimen),
    pending: _pending,
    staleChanges: _stale,
    onGoToBlocker: _goToBlocker,
    conflictVersion: _conflictVersion,
    onRefresh: _refresh,
  );

  /// The evidence selector.
  ///
  /// `UiTabs` publishes the tab bar role and its children publish the tab
  /// role, which is what VoiceOver and TalkBack read as "tab, 1 of 3,
  /// selected" and what a rotor jumps between (finding V-3, accessibility
  /// section 4.2 step 6). Below `medium` the strip scrolls with fading edges
  /// rather than breaking its labels.
  Widget _segments(BuildContext context, WorkbenchRegime regime) => UiTabs(
    semanticsLabel: evidenceTabsLabel,
    selected: _tab,
    tabs: <UiTab>[
      for (final WorkbenchSegment s in WorkbenchSegment.forRegime(regime))
        UiTab(label: s.label),
    ],
  );

  /// The chosen segment's content.
  Widget _segmentPanel(BuildContext context, WorkbenchRegime regime) =>
      UiTabView(
        selected: _tab,
        children: <Widget>[
          for (final WorkbenchSegment s in WorkbenchSegment.forRegime(regime))
            _segmentContent(context, s),
        ],
      );

  /// The bar the frame floats above the navigation (13 section 3.3).
  ///
  /// Previous and next are handed through whether or not there is a neighbour
  /// to move to: at the end of the queue the control announces the reason,
  /// which is the answer the `J` and `K` keys already give and is what a
  /// control that would otherwise be a silent no-op owes the reviewer
  /// (pass criterion 5.6, finding V-2).
  Widget _decisionBar(BuildContext context) => WorkbenchDecisionBar(
    busy: widget.busy,
    pendingCount: _pending.length,
    onSavePending: _savePending,
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
    onNext: () => _step(widget.onNext, widget.nextBlockedReason),
    onPrevious: () => _step(widget.onPrevious, widget.previousBlockedReason),
    positionLabel: widget.positionLabel,
  );

  // ------------------------------------------------------- large records

  /// The fallback for a record too large to review field by field.
  ///
  /// It carries no source header and no segments, so it is a page of two
  /// panes rather than a composition: one scroll on a narrow window, two
  /// beside each other on a wide one, each clearing the frame's own chrome.
  Widget _largeRecord(BuildContext context, WorkbenchRegime regime) {
    final Specimen s = widget.specimen;
    final UiThemeData ui = context.ui;
    final double bottom = UiScaffold.of(context).bottomInset;
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

    if (regime.isStacked) {
      return SingleChildScrollView(
        key: evidenceScrollKey,
        controller: _evidenceScroll,
        padding: EdgeInsets.all(ui.space.s4).copyWith(bottom: bottom),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[evidence, side],
        ),
      );
    }
    return Padding(
      padding: EdgeInsets.all(ui.space.s4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Expanded(
            flex: 3,
            child: SingleChildScrollView(
              padding: EdgeInsets.only(bottom: bottom),
              child: evidence,
            ),
          ),
          SizedBox(width: ui.space.s4),
          Expanded(
            flex: 2,
            child: SingleChildScrollView(
              padding: EdgeInsets.only(bottom: bottom),
              child: side,
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
      // The frame's chrome is published from here rather than from
      // `didChangeDependencies` alone, because every part of it reads state
      // that moves under the reviewer.
      _publish(context);
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
    _announce(reason ?? notInQueueMessage);
  }

  Widget _workbench(BuildContext context, WorkbenchRegime regime) =>
      regime.isStacked ? _oneScroll(context, regime) : _panes(context, regime);

  /// The record as one scroll (13 sections 2.1 and 4.1).
  ///
  /// Four slivers and nothing nested: the source header, the status strip,
  /// the segments, and the chosen segment's content. The header is the only
  /// region that pins, and it pins by scroll position rather than by an
  /// arithmetic that had to be told the height of everything else on the
  /// screen first.
  Widget _oneScroll(BuildContext context, WorkbenchRegime regime) {
    final UiThemeData ui = context.ui;
    _syncTabs(regime);
    final EdgeInsetsGeometry gutter = EdgeInsetsDirectional.symmetric(
      horizontal: ui.space.s4,
    );
    final Widget scroll = CustomScrollView(
      key: evidenceScrollKey,
      controller: _evidenceScroll,
      slivers: <Widget>[
        WorkbenchSourcePane.header(
          specimen: widget.specimen,
          controller: _view,
          selectedRegionId: _region,
          onSelectRegion: _selectRegion,
          onExpand: () => showSourceFullScreen(
            context,
            specimen: widget.specimen,
            selectedRegionId: _region,
            onSelectRegion: _selectRegion,
          ),
        ),
        SliverPadding(
          padding: gutter.add(
            EdgeInsets.only(top: ui.space.s3, bottom: ui.space.s3),
          ),
          sliver: SliverToBoxAdapter(child: _statusStrip(context)),
        ),
        _segmentBar(context, regime),
        SliverPadding(
          padding: gutter.add(
            EdgeInsets.only(
              top: ui.space.s4,
              bottom: ui.space.s4 + UiScaffold.of(context).bottomInset,
            ),
          ),
          sliver: SliverToBoxAdapter(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                // Why the photograph carries no region boxes, where it does
                // not. It is the first row of the evidence rather than a
                // region above the strip: at 200 percent text it is three
                // lines, and three lines between the header and the strip is
                // the disposition below the fold (13 section 2.5).
                if (SourceOrientationCaveat.unverified(_asset)) ...<Widget>[
                  const SourceOrientationCaveat.text(),
                  SizedBox(height: ui.space.s4),
                ],
                _segmentPanel(context, regime),
              ],
            ),
          ),
        ),
      ],
    );
    if (!WindowClass.of(context).isCompact) return scroll;
    // Previous and next are a swipe on the phone, where the decision bar
    // draws no edge buttons, and both moves reach a screen reader as named
    // custom actions (13 section 3.3).
    return UiDecisionSwipe(
      previousLabel: WorkbenchDecisionBar.previousLabel,
      nextLabel: WorkbenchDecisionBar.nextLabel,
      onPrevious: () => _step(widget.onPrevious, widget.previousBlockedReason),
      onNext: () => _step(widget.onNext, widget.nextBlockedReason),
      child: scroll,
    );
  }

  /// The segments, stuck under the header while the chrome budget holds them.
  ///
  /// `UiStickyBar` pins the row once it has scrolled up to the header, so the
  /// reviewer never loses which evidence is showing (13 sections 3.5 and
  /// 4.1). It is pinned chrome while it is stuck, which is what
  /// [segmentsStick] weighs: above the reviewer's default type size, and
  /// from `expanded` up at any size, the frame's own chrome has already spent
  /// the budget of 13 section 2.3, and a screen over the budget gives a pinned
  /// region up.
  Widget _segmentBar(BuildContext context, WorkbenchRegime regime) {
    final UiThemeData ui = context.ui;
    final Widget bar = Padding(
      padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s4),
      child: _segments(context, regime),
    );
    if (!segmentsStick(
      MediaQuery.textScalerOf(context),
      WindowClass.of(context),
    )) {
      return SliverToBoxAdapter(child: bar);
    }
    return UiStickyBar(
      // The control's own height and nothing around it: the bar is pinned
      // chrome while it is stuck, and every dp of padding on it is a dp the
      // budget of 13 section 2.3 does not have. The space above and below it
      // belongs to the regions it separates, which is 13 section 2.6's rule
      // that a region's own padding replaces the page's rather than adding
      // to it. Derived from the type the row holds rather than declared
      // (11 section 2.2).
      extent: UiSegmentedStyle.resolve(
        ui,
        UiSize.lg,
        textScaler: MediaQuery.textScalerOf(context),
      ).outerHeight,
      child: bar,
    );
  }

  /// The record beside itself: source, evidence, and history where the window
  /// is wide enough to hold all three (05 section 3.5).
  ///
  /// Each pane is one scroll and no pane is inside another. The decision bar
  /// is the frame's action bar here too, so every pane clears it.
  Widget _panes(BuildContext context, WorkbenchRegime regime) {
    final UiThemeData ui = context.ui;
    return Padding(
      padding: EdgeInsets.all(ui.space.s4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Expanded(flex: regime.sourceFlex, child: _sourcePane(context)),
          SizedBox(width: ui.space.s4),
          Expanded(
            flex: regime.evidenceFlex,
            child: _evidencePane(context, regime),
          ),
          if (regime == WorkbenchRegime.threePane) ...<Widget>[
            SizedBox(width: ui.space.s4),
            SizedBox(
              width: historyPaneWidth,
              child: Semantics(
                container: true,
                label: 'History',
                child: SingleChildScrollView(
                  padding: EdgeInsets.only(
                    bottom: UiScaffold.of(context).bottomInset,
                  ),
                  child: _history(const ValueKey<String>('history-pane')),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
