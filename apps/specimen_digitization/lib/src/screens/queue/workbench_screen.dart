/// The workbench, as a location (screen blueprints, sections 1.1 and 3).
///
/// This screen owns the route, not the review itself: it resolves the record
/// the location names, guards a back gesture against an in-flight save, and
/// hands the record to `ReviewWorkbench` unchanged.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../app/routes.dart';
import '../../models.dart';
import '../../theme/icons.dart';
import '../../widgets/widgets.dart';
import '../../workbench.dart';
import '../../workspace.dart';

/// One record, opened from the queue.
class WorkbenchScreen extends StatefulWidget {
  const WorkbenchScreen({super.key, required this.specimenId});

  /// The record the location names.
  final String specimenId;

  @override
  State<WorkbenchScreen> createState() => _WorkbenchScreenState();
}

class _WorkbenchScreenState extends State<WorkbenchScreen> {
  /// Held rather than looked up, because `dispose` runs after this element is
  /// detached and can no longer reach an inherited widget.
  WorkspaceController? _held;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _held = WorkspaceScope.read(context);
    _open();
  }

  @override
  void didUpdateWidget(WorkbenchScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.specimenId != widget.specimenId) _open();
  }

  @override
  void dispose() {
    final WorkspaceController? controller = _held;
    if (controller != null) scheduleMicrotask(controller.closeSpecimen);
    super.dispose();
  }

  void _open() {
    final WorkspaceController? controller = _held;
    if (controller == null) return;
    scheduleMicrotask(() {
      controller.openSpecimen(widget.specimenId);
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
    final bool narrow = !WindowClass.of(context).isAtLeast(WindowClass.large);
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
    return PopScope<Object?>(
      canPop: !controller.mutating,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          if (narrow)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: TextButton.icon(
                onPressed: _backToQueue,
                icon: const Icon(Symbols.arrow_back),
                label: const Text('Back to queue'),
              ),
            ),
          Expanded(
            child: specimen == null || scope == null
                ? _Loading(id: widget.specimenId)
                : ReviewWorkbench(
                    key: ValueKey<String>('${scope.key}:${specimen.id}'),
                    specimen: specimen,
                    loadArtifact: (ArtifactRequest artifact) => controller
                        .repository
                        .artifact(scope, specimen, artifact),
                    loadHistoricalArtifact:
                        (Specimen record, ArtifactRequest artifact) =>
                            controller.repository.artifact(
                              scope,
                              record,
                              artifact,
                            ),
                    loadHistoryPage: (int after, int through) =>
                        controller.repository.historyPage(
                          scope,
                          specimen.id,
                          afterRevision: after,
                          throughRevision: through,
                        ),
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
                    onRetry: (String reason) => controller.mutate(null, reason),
                    onRefresh: () => controller.refresh(),
                  ),
          ),
        ],
      ),
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading({required this.id});

  final String id;

  // Scrolls rather than fills: at 200 percent text on a phone the shell hands
  // this pane barely two hundred pixels, and a column of placeholders taller
  // than that lays out past the window (finding V-1, pass criterion 8.5).
  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    padding: EdgeInsets.all(context.space.space6),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        LoadingAnnouncement(thing: 'record $id', visible: true),
        SizedBox(height: context.space.space4),
        const SkeletonBlock(),
        SizedBox(height: context.space.space4),
        const SkeletonRow(),
      ],
    ),
  );
}
