/// The workbench, as a location (screen blueprints, sections 1.1 and 3).
///
/// This screen owns the route, not the review itself: it resolves the record
/// the location names, guards a back gesture against an in-flight save, and
/// hands the record to `ReviewWorkbench` unchanged.
library;

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../app/routes.dart';
import '../../app/shell.dart';
import '../../models.dart';
import '../../api_repository.dart';
import '../../research/research_host.dart';
import '../workbench/source_pane.dart';
import '../workbench/workbench_layout.dart';
import '../../widgets/widgets.dart';
import '../../workbench.dart';
import '../../workspace.dart';

/// One record, opened from the queue.
class WorkbenchScreen extends StatefulWidget {
  const WorkbenchScreen({
    super.key,
    required this.specimenId,
    this.collectionKey,
  });

  /// The record the location names.
  final String specimenId;

  /// The decoded route collection. Standalone hosts can omit it.
  final String? collectionKey;

  @override
  State<WorkbenchScreen> createState() => _WorkbenchScreenState();
}

class _WorkbenchScreenState extends State<WorkbenchScreen> {
  /// Held rather than looked up, because `dispose` runs after this element is
  /// detached and can no longer reach an inherited widget.
  WorkspaceController? _held;
  CollectionScope? _openedScope;
  String? _openedId;
  Future<bool> Function()? _reviewGuard;
  bool _active = true;
  bool _navigationBlocked = false;
  bool _handlingBlockedPop = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _held = WorkspaceScope.read(context);
    _updateActivity();
    _open();
  }

  @override
  void didUpdateWidget(WorkbenchScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.specimenId != widget.specimenId ||
        oldWidget.collectionKey != widget.collectionKey) {
      _updateActivity();
      _open();
    }
  }

  @override
  void dispose() {
    final WorkspaceController? controller = _held;
    _releaseGuard();
    if (controller != null) {
      scheduleMicrotask(() {
        if (identical(controller.recordRouteOwner, this)) {
          controller.recordRouteOwner = null;
          controller.closeSpecimen();
        }
      });
    }
    super.dispose();
  }

  bool get _ownsCollection =>
      widget.collectionKey == null || widget.collectionKey == _held?.scope?.key;

  void _updateActivity() {
    final branch = WorkspaceBranchScope.maybeOf(context);
    _active =
        (branch?.active ?? true) &&
        (branch == null || branch.collectionKey == _held?.scope?.key) &&
        (ModalRoute.of(context)?.isCurrent ?? true) &&
        _ownsCollection;
    if (_active) {
      _held?.recordRouteOwner = this;
      if (_reviewGuard != null) _held?.reviewExitGuard = _reviewGuard;
    } else {
      _releaseGuard();
    }
  }

  void _releaseGuard() {
    if (identical(_held?.reviewExitGuard, _reviewGuard)) {
      _held?.reviewExitGuard = null;
    }
  }

  void _onExitGuardChanged(Future<bool> Function() guard, bool mounted) {
    if (mounted) {
      _reviewGuard = guard;
      if (_active) _held?.reviewExitGuard = guard;
    } else {
      if (identical(_held?.reviewExitGuard, guard)) {
        _held?.reviewExitGuard = null;
      }
      if (identical(_reviewGuard, guard)) _reviewGuard = null;
    }
  }

  void _onNavigationBlockedChanged(bool blocked) {
    if (!mounted || _navigationBlocked == blocked) return;
    setState(() => _navigationBlocked = blocked);
  }

  /// Android/framework Back can request a blocked pop. iOS checks canPop
  /// before starting its edge gesture; explicit Back remains available.
  Future<void> _onBlockedPop(bool didPop, Object? result) async {
    final controller = _held;
    if (didPop ||
        !_active ||
        !_navigationBlocked ||
        _handlingBlockedPop ||
        controller == null ||
        controller.mutating) {
      return;
    }
    _handlingBlockedPop = true;
    final id = widget.specimenId;
    final scope = controller.scope;
    try {
      if (!await controller.mayLeaveReview()) return;
      // Discard updates the synchronous block state; let PopScope receive it
      // before asking the navigator to pop again.
      await WidgetsBinding.instance.endOfFrame;
      if (!mounted ||
          !_active ||
          _navigationBlocked ||
          controller.mutating ||
          widget.specimenId != id ||
          !identical(controller.scope, scope)) {
        return;
      }
      _backToQueue();
    } finally {
      _handlingBlockedPop = false;
    }
  }

  void _open() {
    final WorkspaceController? controller = _held;
    if (controller == null || !_active || !_ownsCollection) return;
    final CollectionScope? scope = controller.scope;
    if (scope == null) return;
    final String id = widget.specimenId;
    // Loading, success and failure all notify this inherited dependency.
    // Only a new route/scope starts a request; retry belongs to the explicit
    // error action, otherwise an unsuccessful response would loop forever.
    if (identical(_openedScope, scope) &&
        _openedId == id &&
        controller.selectedId == id) {
      return;
    }
    _openedScope = scope;
    _openedId = id;
    scheduleMicrotask(() {
      if (!mounted ||
          !_active ||
          !_ownsCollection ||
          !identical(controller.scope, scope) ||
          widget.specimenId != id) {
        return;
      }
      controller.openSpecimen(id);
      // A deep link opens a record without ever passing through the queue,
      // so the list this screen reads next and previous from may never have
      // been asked for. Asking for it here is what gives `J` and `K` a
      // neighbour to move to (finding V-2). It is a no-op once the list has
      // been answered, so it adds no request to the ordinary path.
      controller.ensureListLoaded();
    });
  }

  /// Opens [record], replacing this location rather than stacking one record
  /// on top of another: a reviewer stepping through thirty specimens must not
  /// have to press back thirty times.
  void _goTo(CollectionScope scope, Specimen record) => context.go(
    AppRoutes.specimenOf(encodeCollectionKey(scope.key), record.id),
  );

  void _backToQueue() {
    final WorkspaceController controller = WorkspaceScope.read(context);
    final CollectionScope? scope = controller.scope;
    if (context.canPop()) {
      context.pop();
    } else if (scope != null) {
      context.go(AppRoutes.queueOf(encodeCollectionKey(scope.key)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final WorkspaceController controller = WorkspaceScope.of(context);
    final Specimen? specimen = controller.selected;
    final CollectionScope? scope = controller.scope;
    // Next and previous come from the list the queue already holds, in the
    // order it holds it. Null at each end rather than wrapping: a queue that
    // loops has no end, and a reviewer working it cannot tell when they are
    // finished (pass criteria 6.5 and 7.1).
    final Specimen? next = controller.nextSpecimen;
    final Specimen? previous = controller.previousSpecimen;
    final int? position = controller.selectedPosition;
    final bool listed = position != null;

    // A back gesture must not abandon a save that is in flight
    // (motion catalog, row 19).
    // The way out is the top bar's back, which the workbench publishes into
    // the frame with the record's identifier and its commands (13 sections
    // 2.4 and 4.1). The row that used to hold a back control and nothing else
    // is gone: it repeated what the bar's leading slot is for, which is the
    // third row of 13 section 0's table.
    return PopScope<Object?>(
      canPop: !controller.mutating && !_navigationBlocked,
      onPopInvokedWithResult: _onBlockedPop,
      child:
          specimen == null ||
              scope == null ||
              !_ownsCollection ||
              specimen.id != widget.specimenId
          ? _Loading(id: widget.specimenId)
          : ReviewWorkbench(
              key: ValueKey<String>('${scope.key}:${specimen.id}'),
              specimen: specimen,
              onShowQueue: QueueWorkspaceScope.maybeOf(context)?.showQueue,
              showSidebarToggle:
                  !(AppSidebarScope.maybeOf(context)?.docked ?? false),
              specimensExpanded:
                  QueueWorkspaceScope.maybeOf(context)?.expanded ?? false,
              active: _active,
              onExitGuardChanged: _onExitGuardChanged,
              onNavigationBlockedChanged: _onNavigationBlockedChanged,
              loadArtifact: (ArtifactRequest artifact) =>
                  controller.repository.artifact(scope, specimen, artifact),
              loadHistoricalArtifact:
                  (Specimen record, ArtifactRequest artifact) =>
                      controller.repository.artifact(scope, record, artifact),
              loadHistoryPage: (int after, int through) =>
                  controller.repository.historyPage(
                    scope,
                    specimen.id,
                    afterRevision: after,
                    throughRevision: through,
                  ),
              onRestoreVersion:
                  controller.repository is SpecimenHistoryRepository
                  ? controller.restoreVersion
                  : null,
              fieldResearchHost: controller.repository is ApiSpecimenRepository
                  ? (buildFields) => ResearchHost(
                      repository:
                          controller.repository as ApiSpecimenRepository,
                      collection: scope,
                      specimen: specimen,
                      refreshRecord: () => controller.refreshSelected(),
                      refreshEpoch: controller.selectedRefreshEpoch,
                      refreshEnabled:
                          _active &&
                          controller.foreground &&
                          !controller.mutating,
                      onPollingPaused: (owner, paused) =>
                          controller.setPollingPaused(owner, paused),
                      builder: (context, researchForField) =>
                          buildFields(researchForField),
                    )
                  : null,
              loadHistoricalRevision:
                  (int revision, String? runId, String? runSha256) =>
                      controller.repository.historicalSpecimen(
                        scope,
                        specimen.id,
                        revision,
                        runId: runId,
                        runSha256: runSha256,
                      ),
              collections: controller.scopes,
              canReview: scope.permissions.any(
                (String p) =>
                    <String>['reviewer', 'manager', 'admin'].contains(p),
              ),
              canOperate: scope.permissions.any(
                (String p) => <String>[
                  'operator',
                  'reviewer',
                  'manager',
                  'admin',
                ].contains(p),
              ),
              busy:
                  controller.mutating ||
                  (specimen.disposition != null &&
                      !<String>[
                        'cleared',
                        'needs_human_review',
                        'deferred',
                      ].contains(specimen.disposition)),
              onNext: next == null ? null : () => _goTo(scope, next),
              onPrevious: previous == null
                  ? null
                  : () => _goTo(scope, previous),
              nextBlockedReason: !listed || next != null
                  ? null
                  : 'This is the last record loaded. Load more in the '
                        'queue to carry on.',
              previousBlockedReason: !listed || previous != null
                  ? null
                  : 'This is the first record in the queue.',
              positionLabel: listed
                  ? '$position of ${controller.items.length}'
                  : null,
              reviewerId: controller.session.userId,
              onChange: (Json change) => controller.mutate(change, null),
              onChangeBatch:
                  (
                    List<Json> changes,
                    String reason,
                    bool Function(Specimen, Json) stillApplies,
                  ) => controller.mutateBatch(
                    changes,
                    reason,
                    stillApplies: stillApplies,
                  ),
              verifyBatchReadback: controller.isAcknowledgedBatchReadback,
              onRetry: (String reason) => controller.mutate(null, reason),
              onRefresh: () => controller.refresh(),
              onBack: _backToQueue,
              // The shell's account menu, at the end of the record's bar in
              // the slot every list screen's bar gives it, below large; at
              // large the sidebar's footer carries the account (13 section
              // 4.1, polish 3).
              account: AppShell.accountOnRecordBar(WindowClass.of(context))
                  ? RecordAccountActions(controller: controller)
                  : null,
            ),
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading({required this.id});

  final String id;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final ui = context.ui;
      final stacked = WorkbenchRegime.fromConstraints(
        constraints,
        textScaler: MediaQuery.textScalerOf(context),
      ).isStacked;
      final toolbarScrolls =
          stacked &&
          paneScrollsAtThisTextScale(MediaQuery.textScalerOf(context));
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          if (!toolbarScrolls) _toolbar(context),
          Expanded(
            child: stacked
                ? _stacked(context, toolbarScrolls: toolbarScrolls)
                : _panes(context),
          ),
          if (stacked)
            SafeArea(
              top: false,
              child: Padding(
                padding: EdgeInsets.all(ui.space.s3),
                child: _decision(context),
              ),
            ),
        ],
      );
    },
  );

  Widget _toolbar(BuildContext context) => Semantics(
    liveRegion: true,
    label: 'Loading record $id',
    child: UiTopBar(
      key: const ValueKey<String>('loading-record-toolbar'),
      leading: AppSidebarScope.maybeOf(context)?.mobileNavigation == true
          ? UiIconButton(
              icon: UiIcons.back,
              semanticsLabel: AppShell.backLabel,
              onPressed: () {
                if (context.canPop()) {
                  context.pop();
                } else {
                  final key = WorkspaceScope.read(context).defaultRouteKey;
                  if (key != null) context.go(AppRoutes.queueOf(key));
                }
              },
            )
          : AppSidebarScope.maybeOf(context)?.docked == false
          ? UiIconButton(
              icon: UiIcons.sidebar,
              semanticsLabel: 'Open sidebar',
              onPressed: AppSidebarScope.maybeOf(context)?.toggle,
            )
          : null,
      center: UiLabel('Loading record…', style: context.ui.type.bodySmall),
    ),
  );

  Widget _decision(BuildContext context) => SizedBox(
    key: const ValueKey<String>('loading-decision'),
    height: UiDecisionBarStyle.resolve(context.ui, context).height,
    child: const Align(
      alignment: AlignmentDirectional.centerEnd,
      child: SkeletonBar(widthFactor: .45),
    ),
  );

  Widget _canvas(
    BuildContext context, {
    required bool stacked,
    double? toolsHeight,
  }) {
    final ui = context.ui;
    final style = UiCollapsingHeaderStyle.resolve(ui, context);
    // The record's header keeps its whole photo-and-controls allocation even
    // before the number of labels is known. Large phone text reserves a second
    // control row; the placeholders make no claim about those labels or zoom.
    final rows =
        stacked && paneScrollsAtThisTextScale(MediaQuery.textScalerOf(context))
        ? 2
        : 1;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) =>
                SkeletonBlock(height: constraints.maxHeight),
          ),
        ),
        Padding(
          padding: EdgeInsets.zero,
          child: SizedBox(
            height: toolsHeight ?? style.chromeRowHeight * rows,
            child: const Row(
              children: <Widget>[
                Expanded(child: SkeletonBar(widthFactor: .55)),
                Expanded(child: SkeletonBar(widthFactor: .7)),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _readingLines(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[
      const SkeletonRow(),
      SizedBox(height: context.ui.space.s6),
      const SkeletonRow(),
      SizedBox(height: context.ui.space.s6),
      const SkeletonRow(),
    ],
  );

  Widget _panes(BuildContext context) => LayoutBuilder(
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
      return Padding(
        padding: EdgeInsets.all(metrics.gutter),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Expanded(
              child: SizedBox.expand(
                key: const ValueKey<String>('loading-canvas'),
                child: _canvas(context, stacked: false),
              ),
            ),
            SizedBox(width: metrics.gap),
            SizedBox(
              width: inspectorWidth,
              child: Column(
                key: const ValueKey<String>('loading-inspector'),
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  const SkeletonRow(),
                  const UiHairline(),
                  Expanded(
                    child: SingleChildScrollView(
                      padding: EdgeInsets.symmetric(vertical: metrics.gap),
                      child: _readingLines(context),
                    ),
                  ),
                  const UiHairline(),
                  Padding(
                    padding: EdgeInsets.symmetric(vertical: metrics.gap),
                    child: _decision(context),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
    },
  );

  Widget _stacked(BuildContext context, {required bool toolbarScrolls}) {
    final ui = context.ui;
    return CustomScrollView(
      slivers: <Widget>[
        if (toolbarScrolls) SliverToBoxAdapter(child: _toolbar(context)),
        SliverLayoutBuilder(
          builder: (context, constraints) {
            final toolsHeight = inlineToolsHeight(
              context,
              constraints.crossAxisExtent,
            );
            return SliverToBoxAdapter(
              child: SizedBox(
                key: const ValueKey<String>('loading-canvas'),
                height:
                    reviewInlinePhotoHeight(
                      constraints.viewportMainAxisExtent,
                      constraints.crossAxisExtent,
                      reservedHeight: inlineSourceReservedHeight(
                        context,
                        constraints.crossAxisExtent,
                      ),
                    ) +
                    toolsHeight,
                child: _canvas(
                  context,
                  stacked: true,
                  toolsHeight: toolsHeight,
                ),
              ),
            );
          },
        ),
        SliverPadding(
          padding: EdgeInsets.symmetric(
            horizontal: ui.space.s4,
          ).add(EdgeInsets.only(top: ui.space.s3, bottom: ui.space.s4)),
          sliver: SliverToBoxAdapter(
            child: SizedBox(
              key: const ValueKey<String>('loading-inspector'),
              child: _readingLines(context),
            ),
          ),
        ),
      ],
    );
  }
}
