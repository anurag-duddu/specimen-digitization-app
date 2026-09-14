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
    scheduleMicrotask(() => controller.openSpecimen(widget.specimenId));
  }

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
                    onChange: (Json change) => controller.mutate(change, null),
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

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.all(context.space.space6),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
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
