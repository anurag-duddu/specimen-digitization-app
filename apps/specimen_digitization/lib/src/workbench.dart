/// Image-led review with one evidence inspector and a contextual decision.
/// Narrow constraints retain one page scroll and a reachable bottom decision.
library;

import 'dart:async';

import 'package:flutter/foundation.dart' show listEquals;
import 'package:flutter/scheduler.dart' show SchedulerPhase;
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
import 'research/research_models.dart';
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
const String copyIdentifierLabel = 'Copy full specimen ID';

/// The control that reloads the record.
const String refreshLabel = 'Refresh this record';

/// What the toast says once the identifier is on the clipboard.
const String copiedMessage = 'Full specimen ID copied';

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
const String backToQueueLabel = 'Back to specimens';

/// What a step along the queue says when this record is not in the loaded
/// list at all, so there is neither a neighbour nor a reason there is none.
///
/// The decision bar's edge control is drawn disabled with this on its hint
/// and its tooltip where the host gave neither a move nor a reason of its own
/// (13 section 3.3, polish 3), so a record reached by a deep link still says
/// why it cannot step rather than drawing a control that does nothing (pass
/// criterion 5.6, finding V-2). The same sentence answers the `J` and `K`
/// keys and the compact swipe, which have no control to carry it.
const String notInQueueMessage = 'This record is not in the loaded queue.';

/// One field's research, backed by the host's shared record controller.
typedef FieldResearchBuilder =
    Widget Function(
      String fieldKey,
      ValueChanged<ResearchReviewCandidate>? onSelectCandidate,
    );

/// Wraps the field overview in a single research lifecycle.
typedef FieldReviewHost =
    Widget Function(Widget Function(FieldResearchBuilder) buildFields);

class _PendingBatchReconciliation {
  const _PendingBatchReconciliation({
    required this.specimenId,
    required this.baseRevision,
    required this.baseRecordVersionId,
    required this.reviewerId,
    required this.drafts,
    required this.acknowledgement,
  });

  final String specimenId;
  final int baseRevision;
  final String baseRecordVersionId;
  final String reviewerId;
  final List<PendingFieldChange> drafts;
  final ReviewBatchAcknowledgement? acknowledgement;
}

bool _sameStagedBatchChoice(
  PendingFieldChange current,
  PendingFieldChange original,
) =>
    current == original &&
    current.displayName == original.displayName &&
    current.regionId == original.regionId &&
    current.baseLiteral == original.baseLiteral &&
    current.candidateLabel == original.candidateLabel;

class ReviewWorkbench extends StatefulWidget {
  const ReviewWorkbench({
    super.key,
    required this.specimen,
    required this.onChange,
    this.onChangeBatch,
    this.verifyBatchReadback,
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
    this.onRestoreVersion,
    this.onNext,
    this.onPrevious,
    this.nextBlockedReason,
    this.previousBlockedReason,
    this.positionLabel,
    this.onBack,
    this.onShowQueue,
    this.specimensExpanded = false,
    this.showSidebarToggle = true,
    this.onExitGuardChanged,
    this.onNavigationBlockedChanged,
    this.active = true,
    this.account,
    this.researchPanel,
    this.fieldResearchHost,
  });
  final Widget? researchPanel;
  final FieldReviewHost? fieldResearchHost;
  final Specimen specimen;
  final Future<Json> Function(Specimen, ArtifactRequest)?
  loadHistoricalArtifact;
  final Future<Json> Function(ArtifactRequest)? loadArtifact;

  /// True only after the repository acknowledges this decision.
  final Future<bool> Function(Json change) onChange;

  /// Saves several corrections as one reviewer action under one reason, and
  /// distinguishes acknowledged decisions from a verified current record.
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
  final Future<ReviewBatchSaveOutcome> Function(
    List<Json> changes,
    String reason,
    bool Function(Specimen current, Json change) stillApplies,
  )?
  onChangeBatch;

  /// Verifies a later read against the original scoped batch owner and ACK.
  final bool Function(ReviewBatchAcknowledgement, Specimen)?
  verifyBatchReadback;

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
  final Future<void> Function(
    int sourceRevision,
    bool resetToInitial,
    String reason,
  )?
  onRestoreVersion;

  /// Opens the next specimen in the queue.
  ///
  /// Null draws the bar's next control disabled with [nextBlockedReason] on
  /// it, or with [notInQueueMessage] where the host gave no reason, and the
  /// `J` key says the same sentence aloud: a control that does nothing is
  /// worse than no control, and a control that says why is neither.
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

  /// Reveals the preserved queue over the current record at intermediate widths.
  final VoidCallback? onShowQueue;
  final bool specimensExpanded;
  final bool showSidebarToggle;

  /// Registers the active editor's leave guard with its workspace owner.
  final void Function(Future<bool> Function() guard, bool active)?
  onExitGuardChanged;

  /// Whether an interactive route pop must wait for edits or a pending save.
  /// Event-driven changes are synchronous; build-time changes publish after
  /// the frame so the route owner can safely rebuild its PopScope.
  final ValueChanged<bool>? onNavigationBlockedChanged;

  /// A retained hidden branch keeps its draft state but does not own chrome.
  final bool active;

  /// The account menu the shell puts at the end of its own bars, drawn at the
  /// end of this record's bar too (13 section 4.1, polish 3).
  ///
  /// The shell's, because the session it names and signs out of is the
  /// shell's. Null where the frame's navigation already carries the account,
  /// which is the sidebar's footer at large, and in a host with no shell,
  /// which is a component test.
  final Widget? account;

  @override
  State<ReviewWorkbench> createState() => _ReviewWorkbenchState();
}

class _ReviewWorkbenchState extends State<ReviewWorkbench> {
  final GlobalKey _processingAnchor = GlobalKey();
  final GlobalKey _requirementsAnchor = GlobalKey();
  int _requirementsReveal = 0;
  int _processingReveal = 0;
  int _detailsReveal = 0;
  final FocusNode _showQueueFocus = FocusNode(debugLabel: 'Specimens sidebar');
  final FocusScopeNode _workbenchFocus = FocusScopeNode(
    debugLabel: 'workbench',
    traversalEdgeBehavior: TraversalEdgeBehavior.parentScope,
  );
  WorkbenchSegment _segment = WorkbenchSegment.fields;

  /// Which tab the strip is on, as the index into the visible segment list.
  ///
  /// `UiTabs` owns the selection and writes into this, so the strip and the
  /// panel below it cannot disagree. Keyboard shortcuts keep their logical
  /// segment indices independently of the order of the visible tabs.
  final ValueNotifier<int> _tab = ValueNotifier<int>(0);

  /// How the record is arranged this frame, so a shortcut and a blocker can
  /// keep the same evidence selection through a constraint change.
  WorkbenchRegime _regime = WorkbenchRegime.stacked;

  String? _region;
  List<PendingFieldChange> _pending = <PendingFieldChange>[];
  List<PendingFieldChange> _stale = <PendingFieldChange>[];
  List<String> _recentReasons = <String>[];
  late RecentReasonStore _reasonStore = RecentReasonStore(widget.reviewerId);
  int? _conflictVersion;
  bool _savingLocally = false;
  int? _acknowledgedRevision;
  String? _reconciliationMessage;
  _PendingBatchReconciliation? _pendingBatchReconciliation;
  String? _announcement;

  /// What this screen has asked of the frame around it (13 section 3.4).
  ///
  /// Held rather than looked up in `dispose`, which runs after this element is
  /// detached and can no longer reach an inherited widget.
  UiScaffoldSlots? _slots;

  final GlobalKey _readingsKey = GlobalKey(debugLabel: 'label-comparison');
  final GlobalKey _historyKey = GlobalKey(
    debugLabel: 'retained-review-history',
  );
  bool _historyVisited = false;
  bool _labelDraft = false;
  final LabelDraftController _labelDrafts = LabelDraftController();
  late final Future<bool> Function() _exitGuard = _confirmUnsaved;
  bool get _hasUnsaved =>
      _labelDrafts.hasChanges || _pending.isNotEmpty || _stale.isNotEmpty;
  bool? _reportedNavigationBlocked;
  bool _navigationNotificationPending = false;

  void _reportNavigationBlocked() {
    if (!mounted) return;
    if (WidgetsBinding.instance.schedulerPhase ==
        SchedulerPhase.persistentCallbacks) {
      if (_navigationNotificationPending) return;
      _navigationNotificationPending = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _navigationNotificationPending = false;
        _reportNavigationBlocked();
      });
      return;
    }
    final blocked =
        widget.busy || _savingLocally || _labelDrafts.isSaving || _hasUnsaved;
    if (_reportedNavigationBlocked == blocked) return;
    _reportedNavigationBlocked = blocked;
    widget.onNavigationBlockedChanged?.call(blocked);
  }

  void _setSavingLocally(bool saving) {
    _savingLocally = saving;
    _reportNavigationBlocked();
  }

  Future<bool> _confirmUnsaved() async {
    if (widget.busy || _savingLocally || _labelDrafts.isSaving) return false;
    if (!_hasUnsaved) return true;
    final bool discard =
        await showProductModal<bool>(
          context: context,
          title: 'Discard unsaved corrections?',
          body: (context) => const Text(
            'Your corrections have not been saved. Stay to finish them, or discard them before leaving this record.',
          ),
          primaryAction: (context) => UiButton(
            label: 'Keep editing',
            onPressed: () => Navigator.of(context).pop(false),
          ),
          secondaryAction: (context) => UiButton(
            label: 'Discard changes',
            variant: UiButtonVariant.ghost,
            onPressed: () => Navigator.of(context).pop(true),
          ),
        ) ??
        false;
    if (!discard || !mounted || !_labelDrafts.discardAll()) return false;
    setState(() {
      _labelDraft = false;
      _pending = <PendingFieldChange>[];
      _stale = <PendingFieldChange>[];
      _pendingBatchReconciliation = null;
      _reconciliationMessage = null;
      _conflictVersion = null;
    });
    _reportNavigationBlocked();
    return true;
  }

  final SourceViewController _view = SourceViewController();
  final ScrollController _evidenceScroll = ScrollController();
  final Map<String, GlobalKey> _regionAnchors = <String, GlobalKey>{};
  final Map<String, GlobalKey> _fieldAnchors = <String, GlobalKey>{};

  @override
  void initState() {
    super.initState();
    _region = null;
    _tab.addListener(_tabChanged);
    _labelDrafts.addListener(_reportNavigationBlocked);
    widget.onExitGuardChanged?.call(_exitGuard, true);
    _reportNavigationBlocked();
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
      : WorkbenchSegment.fields;

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
    if (_hasUnsaved && (action == 'approve' || action == 'coverage')) {
      return 'Save or discard your corrections first.';
    }
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
    if (oldWidget.active != widget.active) {
      if (!widget.active) _slots?.release(this);
      _published = null;
    }
    if (oldWidget.onNavigationBlockedChanged == null &&
        widget.onNavigationBlockedChanged != null) {
      _reportedNavigationBlocked = null;
    }
    if (oldWidget.reviewerId != widget.reviewerId) {
      // A different account is a different list of recent reasons, never a
      // merge of the two (pass criterion 7.6).
      _reasonStore = RecentReasonStore(widget.reviewerId);
      _recentReasons = <String>[];
      unawaited(_loadRecentReasons());
      _pending = <PendingFieldChange>[];
      _stale = <PendingFieldChange>[];
      _pendingBatchReconciliation = null;
      _reconciliationMessage = null;
      _acknowledgedRevision = null;
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
      _moveSegment(WorkbenchSegment.fields);
      _historyVisited = false;
      _acknowledgedRevision = null;
      _reconciliationMessage = null;
      _pendingBatchReconciliation = null;
      _pending = <PendingFieldChange>[];
      _stale = <PendingFieldChange>[];
      _conflictVersion = null;
      _reportNavigationBlocked();
      return;
    }
    if ((oldWidget.specimen.revision != widget.specimen.revision ||
            oldWidget.specimen.recordVersionId !=
                widget.specimen.recordVersionId ||
            _hasVerifiedBatchReadback()) &&
        !_savingLocally) {
      final bool acknowledged = _reconcileRefreshedBatch();
      _reapplyPending();
      _conflictVersion = acknowledged && _pending.isEmpty && _stale.isEmpty
          ? null
          : widget.specimen.revision;
    }
    _reportNavigationBlocked();
  }

  void _reapplyPending() {
    final split = reapply(_pending, widget.specimen);
    _pending = split.keep;
    if (split.stale.isNotEmpty) {
      for (final draft in split.stale) {
        _retainStale(draft);
      }
      _conflictVersion = widget.specimen.revision;
    }
    _reportNavigationBlocked();
  }

  void _retainStale(PendingFieldChange draft) {
    if (!_stale.any((existing) => _sameStagedBatchChoice(existing, draft))) {
      _stale.add(draft);
    }
  }

  bool _hasVerifiedBatchReadback() {
    final ticket = _pendingBatchReconciliation;
    final ack = ticket?.acknowledgement;
    return ticket != null &&
        ack != null &&
        ticket.reviewerId == widget.reviewerId &&
        ack.specimenId == ticket.specimenId &&
        ack.baseRevision == ticket.baseRevision &&
        ack.baseRecordVersionId == ticket.baseRecordVersionId &&
        widget.verifyBatchReadback?.call(ack, widget.specimen) == true;
  }

  bool _reconcileRefreshedBatch() {
    final ticket = _pendingBatchReconciliation;
    if (ticket == null) return false;
    final bool proven = _hasVerifiedBatchReadback();
    for (final original in ticket.drafts) {
      final current = _pending
          .where((draft) => draft.fieldKey == original.fieldKey)
          .firstOrNull;
      if (current != null) {
        _pending.remove(current);
        if (!proven || !_sameStagedBatchChoice(current, original)) {
          _retainStale(current);
        }
      }
      if (proven) {
        _stale.removeWhere((draft) => _sameStagedBatchChoice(draft, original));
      }
    }
    _pendingBatchReconciliation = null;
    if (proven) {
      _acknowledgedRevision = widget.specimen.revision;
      _reconciliationMessage = null;
      _announce(
        'The earlier ${ticket.drafts.length} decisions were confirmed in '
        'version ${widget.specimen.revision}.',
      );
    } else {
      _acknowledgedRevision = null;
      _reconciliationMessage =
          'The refreshed record did not confirm this save. Old choices were '
          'moved aside; compare the current sources before selecting again.';
    }
    return proven;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _slots = UiScaffoldSlots.of(context);
  }

  @override
  void dispose() {
    _showQueueFocus.dispose();
    _workbenchFocus.dispose();
    // Only what this screen still holds: the router builds the screen
    // arriving before it disposes the screen leaving, so clearing the slots
    // outright would take the next screen's chrome with it.
    widget.onExitGuardChanged?.call(_exitGuard, false);
    _slots?.release(this);
    _tab
      ..removeListener(_tabChanged)
      ..dispose();
    _labelDrafts
      ..removeListener(_reportNavigationBlocked)
      ..dispose();
    _view.dispose();
    _evidenceScroll.dispose();
    super.dispose();
  }

  /// The frame owns navigation. Decisions stay with the review content.
  void _publish(BuildContext context, {required bool actionBar}) {
    if (!widget.active) return;
    final UiScaffoldSlots? slots = _slots;
    if (slots == null) return;
    final List<Object?> now = _chromeState(actionBar: actionBar);
    if (_published != null && listEquals(_published, now)) return;
    _published = now;
    slots
      ..setTopBar(null, owner: this)
      ..setActionBar(null, owner: this)
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
  List<Object?> _chromeState({required bool actionBar}) => <Object?>[
    actionBar,
    widget.specimen.id,
    widget.busy,
    _pending.length,
    widget.onBack == null,
    widget.account == null,
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

  /// Says [message] to a screen reader once, after the frame.
  ///
  /// After the frame so that two announcements in one build collapse into
  /// the last, and so that the tree the message is about is the one on
  /// screen. A post frame callback runs only once a frame does, and a key
  /// press that moves nowhere schedules none: `J` at the end of the queue
  /// changes nothing on screen, so without [ensureVisualUpdate] its reason
  /// waited for the next repaint, which on a still screen is never. A tap
  /// never met this, because a pressed control repaints (found at polish 3,
  /// when the layout test pressed the key rather than the control).
  void _announce(String message) {
    _announcement = message;
    WidgetsBinding.instance
      ..addPostFrameCallback((_) {
        final String? pending = _announcement;
        _announcement = null;
        if (pending == null || !mounted) return;
        if (!MediaQuery.supportsAnnounceOf(context)) return;
        SemanticsService.sendAnnouncement(
          View.of(context),
          pending,
          TextDirection.ltr,
        );
      })
      ..ensureVisualUpdate();
  }

  GlobalKey _anchor(Map<String, GlobalKey> anchors, String id) =>
      anchors.putIfAbsent(id, GlobalKey.new);

  void _selectRegion(String? id) {
    setState(() {
      if (id != null) _moveSegment(WorkbenchSegment.readings);
      _region = id;
    });
    if (id != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _region == id) _view.frameSelection();
      });
    }
  }

  void _focusFieldRegion(String? id) {
    setState(() => _region = id);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _region != id) return;
      if (id == null) {
        _view.fit();
      } else {
        _view.frameSelection();
      }
    });
  }

  void _scrollTo(GlobalKey? key) {
    final BuildContext? target = key?.currentContext;
    if (target == null) return;
    Scrollable.ensureVisible(
      target,
      duration: context.ui.motion.standard,
      curve: MotionTokens.standardCurve,
      alignment: 0,
    );
  }

  void _goToBlocker(ClearanceBlocker blocker) {
    setState(() {
      _moveSegment(
        blocker.isTargeted ? blocker.segment : WorkbenchSegment.fields,
      );
      if (blocker.isOperational) {
        _processingReveal++;
        _detailsReveal++;
      } else if (!blocker.isTargeted) {
        _requirementsReveal++;
      }
    });
    final String? region = blocker.regionId;
    if (region != null) _region = region;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final String? field = blocker.fieldKey;
      _scrollTo(
        blocker.isOperational
            ? _processingAnchor
            : field != null
            ? _fieldAnchors[field]
            : region != null
            ? _regionAnchors[region]
            : _requirementsAnchor,
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
    _setSavingLocally(true);
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
      _setSavingLocally(false);
      if (mounted) {
        setState(() {
          if (acknowledged) _acknowledgedRevision = widget.specimen.revision;
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

    final ReviewBatchSaveOutcome outcome = await _sendBatch(batch, reason);
    if (!mounted) return;
    if (outcome.requiresReconciliation) {
      _announce(_reconciliationMessage ?? 'Refresh and compare this save.');
      return;
    }
    if (outcome.saved == batch.length && outcome.confirmed != null) {
      _announce(
        '${pendingChangesLabel(outcome.saved)} saved. '
        'Version ${widget.specimen.revision}.',
      );
      return;
    }
    await _reportFailedSave(batch.length - outcome.saved);
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
  /// Clears only a verified prefix. Uncertain candidate groups retain every
  /// draft and stable retry key, even when the server acknowledged a commit.
  Future<ReviewBatchSaveOutcome> _sendBatch(
    List<PendingFieldChange> batch,
    String reason,
  ) async {
    final Future<ReviewBatchSaveOutcome> Function(
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
        if (!mounted) return const ReviewBatchSaveOutcome(saved: 0);
        if (!landed) break;
        saved++;
      }
      return ReviewBatchSaveOutcome(
        saved: saved,
        confirmed: saved > 0 ? widget.specimen : null,
      );
    }

    if (_savingLocally || widget.busy) {
      return const ReviewBatchSaveOutcome(saved: 0);
    }
    final Specimen original = widget.specimen;
    final Map<String, PendingFieldChange> drafts = <String, PendingFieldChange>{
      for (final PendingFieldChange change in batch) change.fieldKey: change,
    };
    _setSavingLocally(true);
    ReviewBatchSaveOutcome outcome = const ReviewBatchSaveOutcome(saved: 0);
    try {
      outcome = await send(
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
      if (!mounted) {
        outcome = const ReviewBatchSaveOutcome(saved: 0);
      } else {
        final Specimen? confirmed = outcome.confirmed;
        if (confirmed != null &&
            outcome.saved > 0 &&
            (confirmed.id != original.id ||
                confirmed.revision <= original.revision ||
                widget.specimen.id != confirmed.id ||
                widget.specimen.revision != confirmed.revision ||
                widget.specimen.recordVersionId != confirmed.recordVersionId)) {
          outcome = ReviewBatchSaveOutcome(
            saved: outcome.saved,
            requiresReconciliation: true,
          );
        }
      }
    } catch (_) {
      outcome = const ReviewBatchSaveOutcome(saved: 0);
    } finally {
      _setSavingLocally(false);
      if (mounted) {
        setState(() {
          final bool verified =
              outcome.confirmed != null && !outcome.requiresReconciliation;
          if (verified && outcome.saved > 0) {
            _acknowledgedRevision = widget.specimen.revision;
            _reconciliationMessage = null;
            _pendingBatchReconciliation = null;
          } else if (outcome.requiresReconciliation) {
            _acknowledgedRevision = null;
            _pendingBatchReconciliation = _PendingBatchReconciliation(
              specimenId: original.id,
              baseRevision: original.revision,
              baseRecordVersionId: original.recordVersionId,
              reviewerId: widget.reviewerId,
              drafts: List<PendingFieldChange>.of(batch),
              acknowledgement: outcome.acknowledgement,
            );
            _reconciliationMessage = outcome.saved > 0
                ? 'The server recorded ${outcome.saved} '
                      '${outcome.saved == 1 ? 'decision' : 'decisions'}, '
                      'but the current record could not be reopened. Your '
                      'choices remain staged. Refresh and compare, or retry '
                      'with the same choices.'
                : 'The batch result could not be confirmed. Your choices '
                      'remain staged. Refresh and compare, or retry with '
                      'the same choices.';
          }
          final Set<String> landed = <String>{
            for (final PendingFieldChange change
                in verified
                    ? batch.take(outcome.saved)
                    : <PendingFieldChange>[])
              change.fieldKey,
          };
          _pending.removeWhere(
            (PendingFieldChange p) => landed.contains(p.fieldKey),
          );
          _stale.removeWhere(
            (PendingFieldChange p) => landed.contains(p.fieldKey),
          );
          // A quiet refresh can replace this record while the save's own GET
          // is still in flight. Its widget update is ignored during the save.
          // Once the ticket exists, confirm only an exact scoped ACK; move
          // unproven choices aside if the current version differs from their
          // base. An unchanged base retains the original retry identity.
          final bool currentMovedFromBase =
              widget.specimen.id == original.id &&
              (widget.specimen.revision != original.revision ||
                  widget.specimen.recordVersionId != original.recordVersionId);
          if (outcome.requiresReconciliation &&
              (currentMovedFromBase || _hasVerifiedBatchReadback())) {
            final bool reconciled = _reconcileRefreshedBatch();
            if (reconciled) {
              outcome = ReviewBatchSaveOutcome(
                saved: outcome.saved,
                confirmed: widget.specimen,
              );
            }
          }
          _reapplyPending();
          if (outcome.confirmed != null && _pending.isEmpty && _stale.isEmpty) {
            _conflictVersion = null;
          }
        });
      }
    }
    return outcome;
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

  void _refresh() async {
    if (!await _confirmUnsaved() || !mounted) return;
    setState(() => _conflictVersion = null);
    widget.onRefresh();
  }

  void _refreshForReconciliation() {
    if (widget.busy || _savingLocally) return;
    // A verification refresh must not ask the reviewer to discard the exact
    // drafts and keys needed to compare or retry an uncertain batch.
    widget.onRefresh();
  }

  void _reviewCurrentFields() => _moveSegment(WorkbenchSegment.fields);

  Future<void> _decide(String kind, String title, String action) async {
    if (blockedReason(kind) != null) return;
    final List<ClearanceBlocker> outstanding = blockersFor(widget.specimen);
    final String? reason = await showReasonSheet(
      context,
      title: title,
      action: action,
      consequence: kind == 'coverage'
          ? 'Confirm that every visible label in the photograph has been included. This records your check; it does not approve the specimen.'
          : 'Approve the accepted label text and record details. Your decision is recorded with your name; remaining checks still apply.',
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

  /// Record identity and commands; the review decision belongs to the inspector.
  Widget _recordTopBar(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final UiThemeData ui = context.ui;
      final metrics = UiLayoutMetrics.fromConstraints(
        constraints,
        textScaler: MediaQuery.textScalerOf(context),
      );
      final showRefresh =
          constraints.maxWidth >=
          measureLabel(
                context,
                widget.specimen.displayReference,
                ui.type.mono.identifier,
              ).width +
              6 * UiDensity.hitBox +
              2 * metrics.gutter;
      final refresh = UiTopBarAction(
        icon: UiIcons.reload,
        label: refreshLabel,
        disabledReason: widget.busy
            ? 'Wait for the save that is in flight to finish'
            : null,
        onPressed: widget.busy ? null : _refresh,
      );
      // The centre slot rather than the title, because an identifier is set in
      // `mono.identifier` and a title is set in `type.title`: two records whose
      // identifiers differ by one character have to be told apart at a glance
      // (blueprint 6.1).
      final Widget identifier = UiLabel(
        widget.specimen.displayReference,
        style: ui.type.mono.identifier.copyWith(color: ui.color.ink),
      );
      return UiTopBar(
        leading: !widget.showSidebarToggle
            ? null
            : widget.onShowQueue != null
            ? widget.specimensExpanded
                  ? null
                  : UiIconButton(
                      icon: UiIcons.sidebar,
                      semanticsLabel: widget.specimensExpanded
                          ? 'Close sidebar'
                          : 'Open sidebar',
                      tooltip: widget.specimensExpanded
                          ? 'Close sidebar'
                          : 'Open sidebar',
                      focusNode: _showQueueFocus,
                      onPressed: () {
                        _showQueueFocus.requestFocus();
                        FocusManager.instance.applyFocusChangesIfNeeded();
                        widget.onShowQueue?.call();
                      },
                    )
            : widget.onBack == null
            ? null
            : UiIconButton(
                icon: UiIcons.back,
                semanticsLabel: backToQueueLabel,
                tooltip: backToQueueLabel,
                onPressed: () async {
                  if (await _confirmUnsaved() && mounted) widget.onBack?.call();
                },
              ),
        center: identifier,
        actions: <Widget>[
          if (showRefresh) refresh,
          UiMenuTrigger(
            semanticsLabel: UiTopBarStyle.overflowLabel,
            icon: UiIcons.more,
            items: <UiMenuItem>[
              if (!showRefresh) refresh.menuItem,
              for (final UiTopBarAction command in _recordCommands(context))
                command.menuItem,
            ],
          ),
          // The account is the shell's, handed in where its rule says the bar
          // carries it (`AppShell.accountOnRecordBar`): below large and not at
          // compact, where the identifier is the bar's one fact.
          ?widget.account,
        ],
      );
    },
  );

  /// The record's own commands, declared once and drawn as menu rows.
  ///
  /// Declared as `UiTopBarAction`s rather than as menu items so that each
  /// carries the glyph, the label, the shortcut and the reason in the one
  /// form the bar reads, and so a test reads a command rather than hunting
  /// for the row that draws it. Every glyph is its own: classification is the
  /// provenance tree, and the source details sheet, which is the checksum and
  /// the coordinate basis of the photograph, is supporting information.
  List<UiTopBarAction> _recordCommands(BuildContext context) =>
      <UiTopBarAction>[
        if (WindowClass.of(context).isCompact) ...<UiTopBarAction>[
          UiTopBarAction(
            icon: UiIcons.back,
            label: WorkbenchDecisionBar.previousLabel,
            disabledReason: widget.onPrevious == null
                ? widget.previousBlockedReason ?? notInQueueMessage
                : null,
            onPressed: widget.onPrevious == null
                ? null
                : () => _step(widget.onPrevious, widget.previousBlockedReason),
          ),
          UiTopBarAction(
            icon: UiIcons.next,
            label: WorkbenchDecisionBar.nextLabel,
            disabledReason: widget.onNext == null
                ? widget.nextBlockedReason ?? notInQueueMessage
                : null,
            onPressed: widget.onNext == null
                ? null
                : () => _step(widget.onNext, widget.nextBlockedReason),
          ),
        ],
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
          icon: UiIcons.info,
          label: sourceDetailsLabel,
          onPressed: () => showSourceDetailsSheet(context, asset: _asset),
        ),
        UiTopBarAction(
          icon: UiIcons.keyboard,
          label: shortcutSheetTitle,
          shortcut: 'Question mark',
          onPressed: () => showShortcutSheet(context),
        ),
      ];

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
    labelReviewActive: _visibleSegment == WorkbenchSegment.readings,
    onSelectRegion: _selectRegion,
    onEditRegions: !_regionsEditable || blockedReason('regions') != null
        ? null
        : _editRegions,
    editRegionsBlockedReason: _regionEditBlockedReason,
    onExpand: () => showSourceFullScreen(
      context,
      specimen: widget.specimen,
      viewController: _view,
      selectedRegionId: _region,
      labelReviewActive: _visibleSegment == WorkbenchSegment.readings,
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
    _tab.value = segments.contains(next) ? segments.indexOf(next) : 0;
  }

  Widget _segmentContent(
    BuildContext context,
    WorkbenchSegment segment, {
    bool compact = false,
  }) => switch (segment) {
    WorkbenchSegment.readings => WorkbenchReadings(
      key: _readingsKey,
      presentationIdentity: _regime,
      compact: compact,
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
      onCommit: _send,
      draftController: _labelDrafts,
      onDraftChanged: (bool dirty) {
        if (mounted && _labelDraft != dirty) {
          setState(() => _labelDraft = dirty);
        }
      },
      transcriptionBlockedReason: blockedReason('transcription'),
      declarationsBlocked: blockedReason('reading_metadata') != null,
      loadArtifact: widget.loadArtifact,
    ),
    WorkbenchSegment.fields =>
      widget.fieldResearchHost?.call(
            (researchForField) => _fieldsContent(context, researchForField),
          ) ??
          _fieldsContent(context, null),
    WorkbenchSegment.history => _history(
      _historyKey,
      active: _visibleSegment == WorkbenchSegment.history,
    ),
  };

  Widget _fieldsContent(
    BuildContext context,
    FieldResearchBuilder? researchForField,
  ) {
    final issues = blockersFor(widget.specimen);
    final recordIssues = issues.where((issue) => !issue.isTargeted).toList();
    return Column(
      key: const ValueKey<String>('fields'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (recordIssues.isNotEmpty)
          Padding(
            padding: EdgeInsets.only(bottom: context.ui.space.s2),
            child: KeyedSubtree(
              key: _requirementsAnchor,
              child: UiDisclosure(
                key: ValueKey('record-requirements:$_requirementsReveal'),
                initiallyExpanded: _requirementsReveal > 0,
                title: 'Record review requirements',
                summary:
                    'Some requirements still need attention before clearance.',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (final issue in recordIssues)
                      Padding(
                        padding: EdgeInsets.only(bottom: context.ui.space.s2),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(issue.message, style: context.ui.type.body),
                            if (issue.detail != null)
                              Text(
                                issue.detail!,
                                style: context.ui.type.bodySmall,
                              ),
                          ],
                        ),
                      ),
                    if (recordIssues.any((issue) => issue.isOperational))
                      UiButton(
                        label: 'View processing details',
                        variant: UiButtonVariant.ghost,
                        onPressed: () {
                          setState(() {
                            _processingReveal++;
                            _detailsReveal++;
                          });
                          WidgetsBinding.instance.addPostFrameCallback((_) {
                            if (mounted) _scrollTo(_processingAnchor);
                          });
                        },
                      ),
                  ],
                ),
              ),
            ),
          ),
        WorkbenchFields(
          specimen: widget.specimen,
          issues: issues,
          researchForField: (fieldKey, onSelectCandidate) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (researchForField != null)
                researchForField(fieldKey, onSelectCandidate),
              if (widget.loadArtifact != null)
                EvidencePanel(
                  key: ValueKey(
                    'field-evidence:${widget.specimen.id}:${widget.specimen.revision}:$fieldKey',
                  ),
                  specimen: widget.specimen,
                  load: widget.loadArtifact!,
                  onChange: _send,
                  canReview: blockedReason('authority_resolution') == null,
                  fieldKey: fieldKey,
                  includeReviewDetails: false,
                ),
            ],
          ),
          anchors: <String, GlobalKey>{
            for (final Json f in widget.specimen.fields)
              textOf(f['field_key'], ''): _anchor(
                _fieldAnchors,
                textOf(f['field_key'], ''),
              ),
          },
          pending: _pending,
          onFocusRegion: _focusFieldRegion,
          onPendingChanged: (List<PendingFieldChange> next) {
            setState(() {
              _pending = next;
              if (_pendingBatchReconciliation == null) {
                final fields = next.map((draft) => draft.fieldKey).toSet();
                _stale.removeWhere((draft) => fields.contains(draft.fieldKey));
                if (_stale.isEmpty && _reconciliationMessage != null) {
                  _reconciliationMessage = null;
                }
              }
            });
            _reportNavigationBlocked();
          },
          fieldBlockedReason: blockedReason('field'),
        ),
        SizedBox(height: context.ui.space.s6),
        if (widget.researchPanel != null) ...[
          UiDisclosure(
            title: 'Additional field research',
            child: widget.researchPanel!,
          ),
          SizedBox(height: context.ui.space.s6),
        ],
        UiDisclosure(
          key: ValueKey('review-details:$_detailsReveal'),
          title: 'Review details',
          summary: 'Processing and audit information',
          initiallyExpanded: _detailsReveal > 0,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (widget.loadArtifact != null)
                EvidencePanel(
                  key: ValueKey<String>(
                    'evidence:${widget.specimen.id}:${widget.specimen.revision}',
                  ),
                  specimen: widget.specimen,
                  load: widget.loadArtifact!,
                  onChange: _send,
                  canReview: blockedReason('authority_resolution') == null,
                  excludedFieldKeys: {
                    for (final field in widget.specimen.fields)
                      textOf(field['field_key'], ''),
                  },
                ),
              SizedBox(height: context.ui.space.s6),
              if (issues.isNotEmpty)
                EvidenceDrawer(
                  title: 'Technical review details',
                  payload: {
                    'validation_findings': widget.specimen.findings,
                    'reason_codes': widget.specimen.data['reason_codes'],
                    'issues': [
                      for (final issue in issues)
                        {
                          'reason_code': issue.rawCode,
                          'rule_id': issue.diagnosticRuleId,
                          'field_key': issue.fieldKey,
                          'region_id': issue.regionId,
                          'message': issue.message,
                        },
                    ],
                  },
                ),
              UiDisclosure(
                title: 'Image and processing details',
                child: ReviewContext(specimen: widget.specimen),
              ),
              SizedBox(height: context.ui.space.s4),
              // The run internals, one closed disclosure, where the blocker that
              // names them sends the reviewer. An operator's concern rather than a
              // reviewer's, which is why it is not on the status strip and not a
              // row of the page (audit finding H8.2; 13 section 4.1).
              KeyedSubtree(
                key: _processingAnchor,
                child: ProcessingDisclosure(
                  key: ValueKey('processing:$_processingReveal'),
                  initiallyExpanded: _processingReveal > 0,
                  specimen: widget.specimen,
                  canOperate: widget.canOperate,
                  busy: widget.busy,
                  onAction: _send,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _history(Key key, {bool active = true}) => AuditHistoryPanel(
    key: key,
    embedded: true,
    active: widget.active && active,
    specimen: widget.specimen,
    loadPage: widget.loadHistoryPage,
    loadRevision: widget.loadHistoricalRevision,
    loadArtifact: widget.loadHistoricalArtifact,
    onRestore: widget.onRestoreVersion == null
        ? null
        : (revision, reset, reason) async {
            if (widget.busy ||
                _savingLocally ||
                !widget.canReview ||
                _hasUnsaved) {
              throw const ApiFailure(
                'Save or discard current edits before restoring a version.',
                code: 'restore_unavailable',
              );
            }
            final before = widget.specimen;
            final reviewer = widget.reviewerId;
            var acknowledged = false;
            setState(() => _setSavingLocally(true));
            try {
              await widget.onRestoreVersion!(revision, reset, reason);
              // As with a normal correction, keep this save local until its
              // readback reaches didUpdateWidget. Otherwise our own restored
              // revision is mistaken for another reviewer's edit.
              if (mounted) await WidgetsBinding.instance.endOfFrame;
              acknowledged =
                  mounted &&
                  widget.specimen.id == before.id &&
                  widget.reviewerId == reviewer &&
                  widget.specimen.revision > before.revision;
            } finally {
              _setSavingLocally(false);
              if (mounted &&
                  widget.specimen.id == before.id &&
                  widget.reviewerId == reviewer) {
                setState(() {
                  if (acknowledged) {
                    _acknowledgedRevision = widget.specimen.revision;
                    _conflictVersion = _hasUnsaved
                        ? widget.specimen.revision
                        : null;
                  } else if (widget.specimen.revision != before.revision) {
                    // A failed restore may overlap a real incoming update.
                    _conflictVersion = widget.specimen.revision;
                  }
                  _reapplyPending();
                });
              }
            }
          },
    mutationDisabledReason: widget.busy || _savingLocally
        ? 'Wait for the current operation to finish.'
        : !widget.canReview
        ? 'Reviewer access is required to restore a version.'
        : _hasUnsaved
        ? 'Save or discard your current edits before restoring a version.'
        : null,
  );

  /// Flat review content with intrinsic navigation and a single scroll region.
  Widget _evidencePane(BuildContext context, WorkbenchRegime regime) {
    _syncTabs(regime);
    return LayoutBuilder(
      builder: (context, constraints) {
        final metrics = UiLayoutMetrics.fromConstraints(
          constraints,
          textScaler: MediaQuery.textScalerOf(context),
        );
        final keyboard = MediaQuery.viewInsetsOf(context).bottom;
        final scale = MediaQuery.textScalerOf(context).scale(16) / 16;
        final chromeScrolls = constraints.maxHeight - keyboard < 320 * scale;
        final decision = Padding(
          padding: EdgeInsets.symmetric(vertical: metrics.gap),
          child: _decisionBar(context),
        );
        final content = _segmentPanel(context, regime, compact: chromeScrolls);
        // UiScaffold keeps the body full-height and publishes keyboard
        // geometry. Reserve it here so both the editor's scroll extent and
        // the local decision bar end above the software keyboard.
        return Padding(
          padding: EdgeInsets.only(bottom: keyboard),
          child: SizedBox(
            key: const ValueKey<String>('review-inspector'),
            child: chromeScrolls
                ? SingleChildScrollView(
                    key: evidenceScrollKey,
                    controller: _evidenceScroll,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        _contextHeader(context, regime),
                        SizedBox(height: context.ui.space.s1),
                        content,
                        const UiHairline(),
                        decision,
                      ],
                    ),
                  )
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      _contextHeader(context, regime),
                      const UiHairline(),
                      Expanded(
                        child: SingleChildScrollView(
                          key: evidenceScrollKey,
                          controller: _evidenceScroll,
                          padding: EdgeInsets.symmetric(vertical: metrics.gap),
                          child: content,
                        ),
                      ),
                      const UiHairline(),
                      decision,
                    ],
                  ),
          ),
        );
      },
    );
  }

  /// Keeps selection shared by keyboard commands and the inspector tabs.
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
    saved:
        _reconciliationMessage == null &&
        _acknowledgedRevision == widget.specimen.revision &&
        !_hasUnsaved &&
        _stale.isEmpty,
    blockers: blockersFor(widget.specimen),
    pending: _pending,
    staleChanges: _stale,
    onGoToBlocker: _goToBlocker,
    conflictVersion: _conflictVersion,
    reconciliationMessage: _reconciliationMessage,
    reconciliationActionLabel:
        _reconciliationMessage != null && _pendingBatchReconciliation == null
        ? 'Review current fields'
        : ConflictBanner.action,
    onRefresh: _reconciliationMessage == null
        ? _refresh
        : _pendingBatchReconciliation == null
        ? _reviewCurrentFields
        : _refreshForReconciliation,
  );

  Widget _contextHeader(BuildContext context, WorkbenchRegime regime) {
    final hasNotice =
        _pending.isNotEmpty ||
        _stale.isNotEmpty ||
        _conflictVersion != null ||
        _reconciliationMessage != null ||
        _acknowledgedRevision == widget.specimen.revision;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _segments(context, regime),
        if (hasNotice) _statusStrip(context),
      ],
    );
  }

  /// One navigation pattern remains stable across all record contexts.
  Widget _segments(BuildContext context, WorkbenchRegime regime) => UiTabs(
    key: const ValueKey<String>('review-context-tabs'),
    selected: _tab,
    semanticsLabel: 'Record view',
    tabs: const <UiTab>[
      UiTab(label: 'Specimen data', semanticsLabel: 'Structured specimen data'),
      UiTab(label: 'Labels', semanticsLabel: 'Label review'),
      UiTab(label: 'History', semanticsLabel: 'Review history'),
    ],
    onSelected: (index) =>
        setState(() => _moveSegment(WorkbenchSegment.forRegime(regime)[index])),
  );

  /// Retain label drafts and visited history without exposing hidden controls.
  Widget _segmentPanel(
    BuildContext context,
    WorkbenchRegime regime, {
    bool compact = false,
  }) {
    _historyVisited |= _visibleSegment == WorkbenchSegment.history;
    Widget retained(WorkbenchSegment segment) {
      final visible = _visibleSegment == segment;
      return TickerMode(
        enabled: visible,
        child: ExcludeFocus(
          excluding: !visible,
          child: ExcludeSemantics(
            excluding: !visible,
            child: Offstage(
              offstage: !visible,
              child: _segmentContent(context, segment, compact: compact),
            ),
          ),
        ),
      );
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        retained(WorkbenchSegment.readings),
        if (_historyVisited) retained(WorkbenchSegment.history),
        if (_visibleSegment == WorkbenchSegment.fields)
          _segmentContent(context, WorkbenchSegment.fields),
      ],
    );
  }

  /// One decision binding, used in the inspector or compact bottom bar.
  Widget _decisionBar(BuildContext context) => WorkbenchDecisionBar(
    busy: widget.busy,
    pendingCount: _pending.length,
    onSavePending: _savePending,
    saveBlockedReason: blockedReason('field'),
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
    onNext: widget.onNext == null
        ? null
        : () => _step(widget.onNext, widget.nextBlockedReason),
    onPrevious: widget.onPrevious == null
        ? null
        : () => _step(widget.onPrevious, widget.previousBlockedReason),
    nextDisabledReason: widget.onNext == null
        ? widget.nextBlockedReason ?? notInQueueMessage
        : null,
    previousDisabledReason: widget.onPrevious == null
        ? widget.previousBlockedReason ?? notInQueueMessage
        : null,
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
        padding: EdgeInsets.all(
          ui.space.s4,
        ).copyWith(bottom: _stackedTailInset(context)),
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
      final keyboard = MediaQuery.viewInsetsOf(context).bottom;
      final availableHeight = (constraints.maxHeight - keyboard).clamp(
        0.0,
        double.infinity,
      );
      final scale = MediaQuery.textScalerOf(context).scale(16) / 16;
      final WorkbenchRegime regime = WorkbenchRegime.fromConstraints(
        BoxConstraints(
          maxWidth: constraints.maxWidth,
          maxHeight: availableHeight,
        ),
        textScaler: MediaQuery.textScalerOf(context),
      );
      final chromeScrolls =
          widget.specimen.data['artifact_receipt'] is! Map &&
          regime.isStacked &&
          availableHeight < reviewMinimumPaneHeight * scale;
      _publish(
        context,
        actionBar:
            regime.isStacked || widget.specimen.data['artifact_receipt'] is Map,
      );
      final Widget body = widget.specimen.data['artifact_receipt'] is Map
          ? _largeRecord(context, regime)
          : _workbench(context, regime, chromeScrolls: chromeScrolls);
      return Shortcuts(
        shortcuts: workbenchShortcuts(),
        child: Actions(
          actions: _actions(context),
          // The map only fires while focus is inside this subtree, which is
          // also what keeps it inert while a reason sheet owns the focus
          // (responsive 4).
          child: FocusScope(
            autofocus: true,
            node: _workbenchFocus,
            // UiScaffold publishes keyboard geometry without shrinking its
            // body. Contract the actual stacked scroll viewport and footer so
            // EditableText.showOnScreen can reveal the caret above the IME.
            // A short keyboard viewport can change the composition. The
            // retained reading/history keys and source controller carry the
            // draft, selection and deliberate pan through that transition.
            // The two-pane inspector consumes its inset in _evidencePane.
            child: Padding(
              padding: EdgeInsets.only(
                bottom: regime.isStacked
                    ? MediaQuery.viewInsetsOf(context).bottom
                    : 0,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  if (!chromeScrolls &&
                      (!regime.isStacked ||
                          !paneScrollsAtThisTextScale(
                            MediaQuery.textScalerOf(context),
                          )))
                    _recordTopBar(context),
                  Expanded(child: body),
                  if (regime.isStacked &&
                      !chromeScrolls &&
                      widget.specimen.data['artifact_receipt'] is! Map)
                    SafeArea(
                      top: false,
                      child: Padding(
                        padding: EdgeInsets.all(context.ui.space.s3),
                        child: _decisionBar(context),
                      ),
                    ),
                ],
              ),
            ),
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
  void _step(VoidCallback? move, String? reason) async {
    if (!await _confirmUnsaved() || !mounted) return;
    if (move != null) {
      move();
      return;
    }
    _announce(reason ?? notInQueueMessage);
  }

  Widget _workbench(
    BuildContext context,
    WorkbenchRegime regime, {
    bool chromeScrolls = false,
  }) => regime.isStacked
      ? _oneScroll(context, regime, chromeScrolls: chromeScrolls)
      : _panes(context, regime);

  /// The stacked viewport already clears the keyboard. Keep any remaining
  /// scaffold chrome/safe-area tail without reserving the IME a second time.
  double _stackedTailInset(BuildContext context) =>
      (UiScaffold.of(context).bottomInset -
              MediaQuery.viewInsetsOf(context).bottom)
          .clamp(0.0, double.infinity)
          .toDouble();

  /// The record as one scroll (13 sections 2.1 and 4.1).
  ///
  /// The photograph, tools and evidence all scroll in the same ordinary page.
  /// Detailed image gestures belong to the explicitly opened viewer.
  Widget _oneScroll(
    BuildContext context,
    WorkbenchRegime regime, {
    bool chromeScrolls = false,
  }) {
    final UiThemeData ui = context.ui;
    _syncTabs(regime);
    final EdgeInsetsGeometry gutter = EdgeInsetsDirectional.symmetric(
      horizontal: ui.space.s4,
    );
    return CustomScrollView(
      key: evidenceScrollKey,
      controller: _evidenceScroll,
      slivers: <Widget>[
        if (chromeScrolls ||
            paneScrollsAtThisTextScale(MediaQuery.textScalerOf(context)))
          SliverToBoxAdapter(child: _recordTopBar(context)),
        WorkbenchSourcePane.header(
          specimen: widget.specimen,
          controller: _view,
          selectedRegionId: _region,
          labelReviewActive: _visibleSegment == WorkbenchSegment.readings,
          onSelectRegion: _selectRegion,
          onExpand: () => showSourceFullScreen(
            context,
            specimen: widget.specimen,
            viewController: _view,
            selectedRegionId: _region,
            labelReviewActive: _visibleSegment == WorkbenchSegment.readings,
            onSelectRegion: _selectRegion,
          ),
        ),
        _segmentBar(context, regime),
        SliverPadding(
          padding: gutter.add(
            EdgeInsets.only(
              top: ui.space.s4,
              bottom: ui.space.s4 + _stackedTailInset(context),
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
                  const UiDisclosure(
                    title: 'Label overlays unavailable',
                    child: SourceOrientationCaveat.text(),
                  ),
                  SizedBox(height: ui.space.s2),
                ],
                _segmentPanel(context, regime),
              ],
            ),
          ),
        ),
        if (chromeScrolls)
          SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.all(ui.space.s3),
              child: _decisionBar(context),
            ),
          ),
      ],
    );
  }

  /// Record-context navigation scrolls with the narrow review page.
  Widget _segmentBar(BuildContext context, WorkbenchRegime regime) =>
      SliverPadding(
        padding: EdgeInsets.symmetric(horizontal: context.ui.space.s4),
        sliver: SliverToBoxAdapter(child: _contextHeader(context, regime)),
      );

  /// Columns share the available width while keeping text at a readable measure.
  Widget _panes(BuildContext context, WorkbenchRegime regime) => LayoutBuilder(
    builder: (context, constraints) {
      final metrics = UiLayoutMetrics.fromConstraints(
        constraints,
        textScaler: MediaQuery.textScalerOf(context),
      );
      final available = metrics.contentWidth - metrics.gap;
      final inspectorWidth = (available * .45).clamp(
        metrics.minColumnWidth,
        metrics.readableMax,
      );
      final short =
          constraints.maxHeight <
          400 * MediaQuery.textScalerOf(context).scale(16) / 16;
      return Padding(
        padding: EdgeInsets.symmetric(
          horizontal: metrics.gutter,
          vertical: short ? context.ui.space.s1 : metrics.gutter,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Expanded(child: _sourcePane(context)),
            SizedBox(width: metrics.gap),
            SizedBox(
              width: inspectorWidth,
              child: _evidencePane(context, regime),
            ),
          ],
        ),
      );
    },
  );
}
