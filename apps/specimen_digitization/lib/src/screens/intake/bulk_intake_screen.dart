/// Source acquisition, visual batch review, and the separate intake queue.
library;

import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';
import 'package:desktop_drop/desktop_drop.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../../capture/capture_camera.dart';
import '../../capture/capture_screen.dart';
import '../../models.dart';
import '../../workspace.dart' show WorkspaceBranchScope;
import '../../region_editor.dart' show uiFullScreenRoute;
import '../../widgets/product_modal.dart';
import 'bulk_intake_controller.dart';
import 'bulk_intake_repository.dart';
import 'intake_file_types.dart';
import 'intake_import_workspace.dart';

String intakeStateLabel(String state) => switch (state) {
  'ready' => 'Saved',
  'waiting' => 'Waiting',
  'transferring' => 'Transferring',
  'checking' => 'Checking',
  'sent' => 'Sent to pipeline',
  'duplicate' => 'Already added',
  'held' => 'Held · sensitive',
  'needs_attention' => 'Needs attention',
  'cancelled' => 'Cancelled',
  _ => 'Waiting',
};

class BulkIntakeScreen extends StatefulWidget {
  const BulkIntakeScreen({
    super.key,
    required this.repository,
    required this.scope,
    required this.userId,
    required this.onViewSpecimens,
    this.controller,
    this.pickFiles,
    this.cameraFactory,
    this.initialProvider,
    this.initialSourceId,
  });
  final BulkIntakeRepository repository;
  final CollectionScope scope;
  final String userId;
  final VoidCallback onViewSpecimens;
  final BulkIntakeController? controller;
  final Future<List<XFile>> Function()? pickFiles;
  final CaptureCameraFactory? cameraFactory;
  final String? initialProvider, initialSourceId;
  @override
  State<BulkIntakeScreen> createState() => _BulkIntakeScreenState();
}

class _BulkIntakeScreenState extends State<BulkIntakeScreen>
    with WidgetsBindingObserver {
  late final BulkIntakeController c;
  String? inspecting, submission;
  bool dragging = false;
  bool _routeActive = true, _branchActive = true, _background = false;
  @override
  void initState() {
    super.initState();
    c =
        widget.controller ??
        BulkIntakeController(
          repository: widget.repository,
          scope: widget.scope,
          userId: widget.userId,
        );
    WidgetsBinding.instance.addObserver(this);
    _background = _isBackground(WidgetsBinding.instance.lifecycleState);
    unawaited(() async {
      if (widget.controller == null) await c.initialize();
      if (mounted && widget.initialProvider != null) {
        await _source(widget.initialProvider!);
      }
    }());
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final branch = WorkspaceBranchScope.maybeOf(context);
    _branchActive =
        branch == null ||
        (branch.active && branch.collectionKey == widget.scope.key);
    _routeActive = ModalRoute.isCurrentOf(context) ?? true;
    _updateActivity();
  }

  static bool _isBackground(AppLifecycleState? state) =>
      state == AppLifecycleState.hidden ||
      state == AppLifecycleState.paused ||
      state == AppLifecycleState.detached;

  void _updateActivity() =>
      c.setViewActive(_branchActive && _routeActive && !_background);

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _background = _isBackground(state);
    _updateActivity();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    c.setViewActive(false);
    if (widget.controller == null) c.dispose();
    super.dispose();
  }

  Future<void> _files() async {
    try {
      final files =
          await (widget.pickFiles?.call() ??
              openFiles(acceptedTypeGroups: const [intakePhotoTypes]));
      await c.addFiles(files);
    } catch (e) {
      c.error = c.message(e);
      c.changed();
    }
  }

  Future<void> _camera() async {
    final result = await Navigator.of(context).push(
      CaptureScreen.route(
        widget.cameraFactory ?? () async => PlatformCaptureCamera(),
        bulkDraft: true,
        onCapturedDurably: (photo) => c.addFiles(
          [photo.file],
          camera: true,
          sensitive: photo.sensitive,
          captureAttempt: photo.admissionAttempt,
        ),
        batchTray: (context) => SizedBox(
          height: context.ui.space.s16,
          child: ListView.builder(
            scrollDirection: Axis.horizontal,
            reverse: true,
            itemCount: c.visible.length,
            itemBuilder: (context, index) => Padding(
              padding: EdgeInsets.all(context.ui.space.s1),
              child: SizedBox(
                width: context.ui.space.s16 - context.ui.space.s2,
                child: BulkPhotoPreview(
                  controller: c,
                  item: c.visible[c.visible.length - 1 - index],
                ),
              ),
            ),
          ),
        ),
        activity: c,
        activitySnapshot: () => CaptureActivity(
          label:
              '${c.visible.length} ${c.visible.length == 1 ? 'photo' : 'photos'} in your batch · ${c.saveLabel}',
        ),
      ),
    );
    if (!mounted) return;
    if (result?.needsFallback == true) await _files();
  }

  Future<void> _add() => showProductModal<void>(
    context: context,
    title: 'Add photos',
    body: (context) => Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final entry in <(String, IconSpec, Future<void> Function())>[
          ('Take photos', UiIcons.camera, _camera),
          ('Choose files', UiIcons.uploadFile, _files),
          ('Google Drive', UiIcons.source, () => _source('google_drive')),
          ('Dropbox', UiIcons.source, () => _source('dropbox')),
          (
            'Registered storage',
            UiIcons.sourceImport,
            () => _source('storage'),
          ),
          ('Import links', UiIcons.sourceImport, () => _source('url')),
        ])
          Padding(
            padding: EdgeInsets.only(bottom: context.ui.space.s2),
            child: UiButton(
              label: entry.$1,
              leading: entry.$2,
              variant: UiButtonVariant.secondary,
              onPressed: () {
                Navigator.of(context).pop();
                unawaited(entry.$3());
              },
            ),
          ),
        Text(
          'Every source joins this batch for review before submission.',
          style: context.ui.type.bodySmall,
        ),
      ],
    ),
  );

  Future<void> _source(String provider) => IntakeImportWorkspace.show(
    context: context,
    controller: c,
    provider: provider,
    initialSourceId: widget.initialSourceId,
  );

  Future<void> _open(IntakeDraftItem item, bool wide) async {
    if (wide) {
      setState(() => inspecting = item.id);
      return;
    }
    await Navigator.of(context).push(
      uiFullScreenRoute<void>(
        context,
        builder: (_) => Surface(
          child: SafeArea(
            child: BulkPhotoInspector(
              controller: c,
              cameraFactory: widget.cameraFactory,
              pickReplacementFile: widget.pickFiles == null
                  ? null
                  : () async => (await widget.pickFiles!()).firstOrNull,
              initialId: item.id,
              onClose: () => Navigator.of(context).pop(),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    final result = await c.submit();
    if (mounted && result != null) {
      setState(() {
        submission = result.id;
        inspecting = null;
      });
    }
  }

  Future<void> _editSelected() => showProductModal<void>(
    context: context,
    title: '${c.selected.length} selected for editing',
    body: (modal) => _selectionActions(
      modal,
      onAction: () {
        Navigator.of(modal).pop();
      },
    ),
  );

  Widget _selectionActions(BuildContext context, {VoidCallback? onAction}) {
    final ui = context.ui;
    void edit(String action, {bool? value}) {
      onAction?.call();
      unawaited(c.edit(action, value: value));
    }

    return Wrap(
      spacing: ui.space.s2,
      runSpacing: ui.space.s2,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        UiButton(
          label: 'Remove selected',
          leading: UiIcons.remove,
          variant: UiButtonVariant.ghost,
          onPressed: () => edit('remove'),
        ),
        UiButton(
          label: 'Mark sensitive',
          variant: UiButtonVariant.ghost,
          onPressed: () => edit('sensitive', value: true),
        ),
        UiButton(
          label: 'Mark non-sensitive',
          variant: UiButtonVariant.ghost,
          onPressed: () => edit('sensitive', value: false),
        ),
        UiButton(
          label: 'Exclude selected',
          variant: UiButtonVariant.ghost,
          onPressed: () => edit('exclude'),
        ),
      ],
    );
  }

  Future<void> _discard() async {
    final confirmed = await showProductModal<bool>(
      context: context,
      title: 'Discard this draft?',
      body: (_) => const Text(
        'Remove the saved draft and its local recovery files. Provider originals and submitted specimens are kept.',
      ),
      primaryAction: (modal) => UiButton(
        label: 'Discard draft',
        onPressed: () => Navigator.of(modal).pop(true),
      ),
      secondaryAction: (modal) => UiButton(
        label: 'Keep draft',
        variant: UiButtonVariant.secondary,
        onPressed: () => Navigator.of(modal).pop(false),
      ),
    );
    if (confirmed == true) {
      try {
        await c.discardDraft();
      } catch (e) {
        c.error = c.message(e);
        c.changed();
      }
    }
  }

  Future<void> _history() => showProductModal<void>(
    context: context,
    title: 'Your batches',
    body: (_) => AnimatedBuilder(
      animation: c,
      builder: (context, _) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (c.visible.isNotEmpty && submission == null)
            UiButton(
              label: 'Discard current draft',
              variant: UiButtonVariant.ghost,
              onPressed: () {
                Navigator.of(context).pop();
                unawaited(_discard());
              },
            ),
          UiButton(
            label: 'Start a new batch',
            leading: UiIcons.add,
            onPressed: () {
              Navigator.of(context).pop();
              setState(() => submission = null);
              unawaited(c.newDraft());
            },
          ),
          for (final batch in c.savedDrafts.where((d) => d['state'] == 'draft'))
            UiButton(
              label: 'Resume ${textOf(batch['name'], 'draft')}',
              variant: UiButtonVariant.secondary,
              onPressed: () {
                Navigator.of(context).pop();
                setState(() => submission = null);
                unawaited(c.openDraft(batch));
              },
            ),
          for (final batch in c.submissions)
            UiButton(
              label: 'View ${batch.total} submitted photos',
              variant: UiButtonVariant.secondary,
              onPressed: () {
                Navigator.of(context).pop();
                setState(() => submission = batch.id);
              },
            ),
          if (c.savedDrafts.isEmpty && c.submissions.isEmpty)
            const Text('Your saved drafts and submissions appear here.'),
        ],
      ),
    ),
  );

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: c,
    builder: (context, _) {
      if (submission != null) {
        return BulkIntakeProgress(
          controller: c,
          submissionId: submission!,
          onAdd: () => setState(() => submission = null),
          onViewSpecimens: widget.onViewSpecimens,
        );
      }
      return Surface(
        role: SurfaceRole.ground,
        child: SafeArea(
          child: DropTarget(
            onDragEntered: (_) => setState(() => dragging = true),
            onDragExited: (_) => setState(() => dragging = false),
            onDragDone: (details) {
              setState(() => dragging = false);
              unawaited(c.addFiles(details.files));
            },
            child: LayoutBuilder(
              builder: (context, constraints) {
                final ui = context.ui;
                final wide = constraints.maxWidth >= 1050;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(
                            child: Align(
                              alignment: Alignment.topCenter,
                              child: ConstrainedBox(
                                constraints: BoxConstraints(
                                  maxWidth: ui.space.importWorkspaceMax,
                                ),
                                child: _workspace(context, wide),
                              ),
                            ),
                          ),
                          if (wide && inspecting != null)
                            SizedBox(
                              width: constraints.maxWidth * .38,
                              child: BulkPhotoInspector(
                                key: ValueKey(inspecting),
                                controller: c,
                                cameraFactory: widget.cameraFactory,
                                pickReplacementFile: widget.pickFiles == null
                                    ? null
                                    : () async => (await widget.pickFiles!())
                                          .firstOrNull,
                                initialId: inspecting!,
                                onClose: () =>
                                    setState(() => inspecting = null),
                              ),
                            ),
                        ],
                      ),
                    ),
                    if (c.visible.isNotEmpty) _submissionBar(context, wide),
                  ],
                );
              },
            ),
          ),
        ),
      );
    },
  );

  Widget _workspace(BuildContext context, bool wide) {
    final ui = context.ui;
    return CustomScrollView(
      key: const ValueKey('bulk-photo-grid'),
      slivers: [
        SliverPadding(
          padding: EdgeInsets.all(ui.space.s4),
          sliver: SliverToBoxAdapter(child: _header(context)),
        ),
        if (c.loading)
          const SliverFillRemaining(
            hasScrollBody: false,
            child: Center(
              child: UiProgress.ring(semanticsLabel: 'Loading your drafts'),
            ),
          )
        else if (c.visible.isEmpty)
          SliverPadding(
            padding: EdgeInsets.fromLTRB(
              ui.space.s4,
              0,
              ui.space.s4,
              ui.space.s6,
            ),
            sliver: SliverToBoxAdapter(child: _empty(context, dragging)),
          )
        else
          SliverPadding(
            padding: EdgeInsets.fromLTRB(
              ui.space.s4,
              0,
              ui.space.s4,
              ui.space.s6,
            ),
            sliver: _grid(context, wide),
          ),
      ],
    );
  }

  List<IntakeDraftItem> get _attentionPhotos => c.visible
      .where(
        (item) =>
            item.included &&
            (item.state == 'needs_attention' || item.error != null),
      )
      .toList();

  String get _batchStatus => _attentionPhotos.isEmpty
      ? c.saveLabel
      : '${_attentionPhotos.length} ${_attentionPhotos.length == 1 ? 'needs' : 'need'} attention';

  Widget _header(BuildContext context) {
    final ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (c.visible.isEmpty)
          Align(
            alignment: AlignmentDirectional.centerEnd,
            child: UiButton(
              label: 'Your batches',
              variant: UiButtonVariant.ghost,
              onPressed: _history,
            ),
          )
        else
          UiSectionHeader(
            title: 'Your batch',
            role: UiSectionHeaderRole.section,
            supporting:
                '${c.visible.length} ${c.visible.length == 1 ? 'photo' : 'photos'} · $_batchStatus',
            supportingLiveRegion: true,
            actions: [
              UiButton(
                label: 'Batches',
                semanticsLabel: 'Your batches',
                size: UiSize.sm,
                variant: UiButtonVariant.ghost,
                onPressed: _history,
              ),
              UiButton(
                label: 'Add photos',
                size: UiSize.sm,
                variant: UiButtonVariant.secondary,
                onPressed: _add,
              ),
            ],
          ),
        if (c.preparingFiles || c.addingSources) ...[
          SizedBox(height: ui.space.s2),
          Semantics(
            liveRegion: true,
            child: Text(
              c.preparingFiles ? c.preparationLabel : c.sourceAddLabel,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          ),
        ],
        if (c.error != null) ...[
          SizedBox(height: ui.space.s2),
          Wrap(
            spacing: ui.space.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(c.error!, style: ui.type.bodySmall),
              UiButton(
                label: 'Retry saving',
                variant: UiButtonVariant.ghost,
                onPressed: c.retrySaving,
              ),
            ],
          ),
        ],
        if (c.needsOpenWorkspace) ...[
          SizedBox(height: ui.space.s2),
          Text(
            'Keep this workspace open until photos are saved. If you leave early, choose the original files again to resume.',
            style: ui.type.bodySmall,
          ),
        ],
        if (c.selected.isNotEmpty) ...[
          SizedBox(height: ui.space.s4),
          DecoratedBox(
            decoration: BoxDecoration(color: ui.brand.secondary.fill),
            child: Padding(
              padding: EdgeInsets.all(ui.space.s2),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${c.selected.length} selected for editing',
                    style: ui.type.labelSmall.copyWith(
                      color: ui.brand.secondary.content,
                    ),
                  ),
                  _selectionActions(context),
                ],
              ),
            ),
          ),
        ],
        if (c.lastRemoved.isNotEmpty) ...[
          SizedBox(height: ui.space.s2),
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                '${c.lastRemoved.length} removed from this batch',
                style: ui.type.bodySmall,
              ),
              UiButton(
                label: 'Undo removal',
                leading: UiIcons.undo,
                variant: UiButtonVariant.ghost,
                onPressed: () => c.edit('restore', ids: c.lastRemoved),
              ),
            ],
          ),
        ],
      ],
    );
  }

  Widget _submissionBar(BuildContext context, bool wide) {
    final ui = context.ui;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: ui.color.paper,
        border: Border(top: BorderSide(color: ui.color.hairline)),
      ),
      child: Padding(
        padding: EdgeInsets.all(ui.space.s4),
        child: Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: ui.space.s4,
          runSpacing: ui.space.s2,
          children: [
            if (c.selected.isNotEmpty)
              UiButton(
                label: 'Edit ${c.selected.length} selected',
                variant: UiButtonVariant.secondary,
                onPressed: _editSelected,
              )
            else if (_attentionPhotos.isNotEmpty)
              UiButton(
                label:
                    'Review ${_attentionPhotos.length} ${_attentionPhotos.length == 1 ? 'photo' : 'photos'}',
                variant: c.readyCount == 0
                    ? UiButtonVariant.primary
                    : UiButtonVariant.secondary,
                onPressed: () => _open(_attentionPhotos.first, wide),
              )
            else
              Text(
                c.readyCount == c.visible.length
                    ? 'Submit starts processing.'
                    : '${c.visible.length - c.readyCount} ${c.visible.length - c.readyCount == 1 ? 'photo' : 'photos'} will remain in your draft.',
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
            if (c.readyCount > 0 || _attentionPhotos.isEmpty)
              UiButton(
                label:
                    'Submit ${c.readyCount} ${c.readyCount == 1 ? 'photo' : 'photos'}',
                leading: UiIcons.cloudUpload,
                loading: c.submitting,
                onPressed:
                    c.readyCount == 0 || c.preparingFiles || c.addingSources
                    ? null
                    : _submit,
                disabledReason: c.preparingFiles || c.addingSources
                    ? 'Wait for the selected photos to be added.'
                    : c.readyCount == 0
                    ? 'Add readable photos to submit.'
                    : null,
              ),
          ],
        ),
      ),
    );
  }

  Widget _empty(BuildContext context, bool dragging) {
    final ui = context.ui;
    final cameraFirst = WindowClass.of(context).isCompact;
    return Align(
      alignment: AlignmentDirectional.topStart,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: ui.space.readingMax),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            UiSectionHeader(
              title: dragging ? 'Drop photos into your batch' : 'Add photos',
              role: UiSectionHeaderRole.page,
              supporting:
                  'Add up to 500 photos to a private draft. Review them before submitting.',
            ),
            SizedBox(height: ui.space.s6),
            Wrap(
              spacing: ui.space.s3,
              runSpacing: ui.space.s3,
              children: [
                UiButton(
                  label: cameraFirst ? 'Take photos' : 'Choose files',
                  leading: cameraFirst ? UiIcons.camera : UiIcons.uploadFile,
                  onPressed: cameraFirst ? _camera : _files,
                ),
                UiButton(
                  label: cameraFirst ? 'Choose files' : 'Take photos',
                  leading: cameraFirst ? UiIcons.uploadFile : UiIcons.camera,
                  variant: UiButtonVariant.secondary,
                  onPressed: cameraFirst ? _files : _camera,
                ),
              ],
            ),
            SizedBox(height: ui.space.s6),
            UiDisclosure(
              title: 'Import from a source',
              summary: 'Google Drive, Dropbox, storage or links',
              hideSummaryWhenExpanded: true,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final source in [
                    ('Google Drive', 'google_drive'),
                    ('Dropbox', 'dropbox'),
                    ('Storage', 'storage'),
                    ('Import links', 'url'),
                  ])
                    UiListRow(
                      title: source.$1,
                      trailing: const UiIcon(
                        UiIcons.next,
                        size: UiIconSize.inline,
                      ),
                      onPressed: () => _source(source.$2),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _grid(BuildContext context, bool wide) => SliverLayoutBuilder(
    builder: (context, constraints) {
      final ui = context.ui;
      final available = constraints.crossAxisExtent;
      final textScale =
          UiType.lineHeightOf(ui.type.bodySmall, context) /
          UiType.unscaledLineHeightOf(ui.type.bodySmall);
      final minWidth = ui.space.targetMin * 3 * math.max(1, textScale);
      final columns = ((available + ui.space.s4) / (minWidth + ui.space.s4))
          .floor()
          .clamp(1, 5);
      final width = (available - ui.space.s4 * (columns - 1)) / columns;
      final caption =
          UiType.lineHeightOf(ui.type.bodySmall, context) * 2 +
          math.max(
            ui.space.targetMin,
            UiType.lineHeightOf(ui.type.labelSmall, context),
          ) +
          ui.space.s2;
      final photos = c.visible;
      return SliverGrid.builder(
        itemCount: photos.length,
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: columns,
          crossAxisSpacing: ui.space.s4,
          mainAxisSpacing: ui.space.s6,
          mainAxisExtent: width * .8 + caption,
        ),
        itemBuilder: (context, index) {
          final item = photos[index];
          return UiPhotoTile(
            key: ValueKey(item.id),
            name: item.name,
            selected: c.selected.contains(item.id),
            included: item.included,
            showStatus:
                item.state != 'ready' || item.error != null || item.sensitive,
            status:
                item.error ??
                (item.sensitive
                    ? 'Sensitive · ${intakeStateLabel(item.state)}'
                    : intakeStateLabel(item.state)),
            onSelected: (value) => c.select(item.id, value),
            onOpen: () => _open(item, wide),
            preview: BulkPhotoPreview(controller: c, item: item),
          );
        },
      );
    },
  );
}

class BulkPhotoPreview extends StatefulWidget {
  const BulkPhotoPreview({
    super.key,
    required this.controller,
    required this.item,
    this.full = false,
  });
  final BulkIntakeController controller;
  final IntakeDraftItem item;
  final bool full;
  @override
  State<BulkPhotoPreview> createState() => _BulkPhotoPreviewState();
}

class _BulkPhotoPreviewState extends State<BulkPhotoPreview> {
  late Future<Uint8List> _preview;
  int _previewGeneration = 0;
  String get _identity =>
      '${widget.item.id}:${widget.item.state}:${widget.item.data['revision']}:${widget.full}';
  late String _loadedIdentity;
  void _load() {
    _previewGeneration++;
    _loadedIdentity = _identity;
    _preview = widget.controller.preview(widget.item, full: widget.full);
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(BulkPhotoPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_loadedIdentity != _identity ||
        oldWidget.controller != widget.controller) {
      _load();
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<Uint8List>(
    key: ValueKey(_previewGeneration),
    future: _preview,
    builder: (context, snapshot) {
      if (snapshot.hasData) {
        return Image.memory(
          snapshot.data!,
          fit: BoxFit.contain,
          gaplessPlayback: false,
          excludeFromSemantics: true,
        );
      }
      if (snapshot.hasError && snapshot.error is! IntakePreviewPending) {
        void retry() {
          widget.controller.invalidatePreview(widget.item, full: widget.full);
          setState(_load);
        }

        return Center(
          child: widget.full
              ? UiButton(
                  label: 'Retry preview',
                  variant: UiButtonVariant.ghost,
                  onPressed: retry,
                )
              : UiIconButton(
                  icon: UiIcons.retry,
                  semanticsLabel: 'Retry preview for ${widget.item.name}',
                  onPressed: retry,
                ),
        );
      }
      return const Center(child: UiIcon(UiIcons.image));
    },
  );
}

class BulkPhotoInspector extends StatefulWidget {
  const BulkPhotoInspector({
    super.key,
    required this.controller,
    required this.initialId,
    required this.onClose,
    this.cameraFactory,
    this.pickReplacementFile,
  });
  final BulkIntakeController controller;
  final String initialId;
  final VoidCallback onClose;
  final CaptureCameraFactory? cameraFactory;
  final Future<XFile?> Function()? pickReplacementFile;
  @override
  State<BulkPhotoInspector> createState() => _BulkPhotoInspectorState();
}

class _BulkPhotoInspectorState extends State<BulkPhotoInspector> {
  late String id = widget.initialId;
  final transform = TransformationController();
  bool editing = false;
  Future<void> retakePhoto(IntakeDraftItem item) async {
    var replaced = false;
    try {
      final result = await Navigator.of(context).push(
        CaptureScreen.route(
          widget.cameraFactory ?? () async => PlatformCaptureCamera(),
          bulkDraft: true,
          initialSensitive: item.sensitive,
          onCapturedDurably: (photo) async {
            await widget.controller.addFiles(
              [photo.file],
              camera: true,
              sensitive: photo.sensitive,
              replacesId: item.id,
              captureAttempt: photo.admissionAttempt,
            );
            replaced = true;
            if (mounted) Navigator.of(context).pop();
          },
        ),
      );
      if (!mounted) return;
      if (result?.needsFallback == true) {
        final file =
            await (widget.pickReplacementFile?.call() ??
                openFile(acceptedTypeGroups: const [intakePhotoTypes]));
        if (!mounted || file == null) return;
        await widget.controller.addFiles(
          [file],
          sensitive: item.sensitive,
          replacesId: item.id,
        );
        replaced = true;
      }
      if (mounted && replaced) widget.onClose();
    } catch (error) {
      widget.controller.error = widget.controller.message(error);
      widget.controller.changed();
    }
  }

  Future<void> editPhoto(IntakeDraftItem item) async {
    setState(() => editing = true);
    try {
      final file = await widget.controller.originalForEdit(item);
      if (!mounted) return;
      final result = await Navigator.of(context).push(
        CaptureScreen.route(
          () async => PlatformCaptureCamera(),
          initialReview: file,
          initialSensitive: item.sensitive,
        ),
      );
      if (result != null && result.files.isNotEmpty) {
        await widget.controller.addFiles(
          result.files,
          sensitive: item.sensitive,
          replacesId: item.id,
        );
        widget.onClose();
      }
    } catch (e) {
      widget.controller.error = widget.controller.message(e);
      widget.controller.changed();
    } finally {
      if (mounted) setState(() => editing = false);
    }
  }

  @override
  void dispose() {
    transform.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: widget.controller,
    builder: (context, _) {
      final c = widget.controller;
      final photos = c.visible;
      final index = photos.indexWhere((item) => item.id == id);
      if (index < 0) {
        return Center(
          child: UiButton(label: 'Close review', onPressed: widget.onClose),
        );
      }
      final item = photos[index];
      final ui = context.ui;
      void move(int delta) {
        setState(() {
          id = photos[index + delta].id;
          transform.value = Matrix4.identity();
        });
      }

      return Padding(
        padding: EdgeInsets.all(ui.space.s4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${index + 1} of ${photos.length}',
                    style: ui.type.label,
                  ),
                ),
                UiIconButton(
                  icon: UiIcons.close,
                  semanticsLabel: 'Close photo review',
                  onPressed: widget.onClose,
                ),
              ],
            ),
            Expanded(
              child: InteractiveViewer(
                transformationController: transform,
                minScale: 1,
                maxScale: 8,
                child: SizedBox.expand(
                  child: BulkPhotoPreview(
                    controller: c,
                    item: item,
                    full: true,
                  ),
                ),
              ),
            ),
            Text(
              item.name,
              style: ui.type.label,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            Text(
              item.error ?? intakeStateLabel(item.state),
              style: ui.type.bodySmall,
            ),
            UiCheckbox(
              label: 'Include in submission',
              value: item.included,
              onChanged: (value) =>
                  c.edit(value ? 'include' : 'exclude', ids: [item.id]),
            ),
            UiButton(
              label: 'Rotate or crop',
              variant: UiButtonVariant.ghost,
              loading: editing,
              onPressed: editing || item.id.startsWith('local:')
                  ? null
                  : () => editPhoto(item),
            ),
            UiButton(
              label: 'Retake photo',
              variant: UiButtonVariant.ghost,
              onPressed: item.id.startsWith('local:')
                  ? null
                  : () => retakePhoto(item),
            ),
            UiSwitch(
              label: 'Mark this photo sensitive',
              value: item.sensitive,
              onChanged: (value) =>
                  c.edit('sensitive', value: value, ids: [item.id]),
            ),
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              children: [
                UiIconButton(
                  icon: UiIcons.previous,
                  semanticsLabel: 'Previous photo',
                  onPressed: index > 0 ? () => move(-1) : null,
                ),
                UiButton(
                  label: 'Remove photo',
                  variant: UiButtonVariant.ghost,
                  onPressed: () => c.edit('remove', ids: [item.id]),
                ),
                UiIconButton(
                  icon: UiIcons.next,
                  semanticsLabel: 'Next photo',
                  onPressed: index + 1 < photos.length ? () => move(1) : null,
                ),
              ],
            ),
          ],
        ),
      );
    },
  );
}

class BulkIntakeProgress extends StatefulWidget {
  const BulkIntakeProgress({
    super.key,
    required this.controller,
    required this.submissionId,
    required this.onAdd,
    required this.onViewSpecimens,
  });
  final BulkIntakeController controller;
  final String submissionId;
  final VoidCallback onAdd, onViewSpecimens;
  @override
  State<BulkIntakeProgress> createState() => _BulkIntakeProgressState();
}

class _BulkIntakeProgressState extends State<BulkIntakeProgress> {
  IntakeSubmissionProgress? get snapshot =>
      widget.controller.progressFor(widget.submissionId);
  IntakeSubmission? get batch => snapshot?.batch;
  List<IntakeSubmissionItem> get items => snapshot?.items ?? const [];
  String? error;
  bool reselecting = false, retrying = false;
  @override
  void initState() {
    super.initState();
    unawaited(refresh());
  }

  @override
  void didUpdateWidget(BulkIntakeProgress oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller ||
        oldWidget.submissionId != widget.submissionId) {
      oldWidget.controller.stopObservingSubmission(oldWidget.submissionId);
      unawaited(refresh());
    }
  }

  @override
  void dispose() {
    widget.controller.stopObservingSubmission(widget.submissionId);
    super.dispose();
  }

  Future<void> refresh() async {
    await widget.controller.observeSubmission(widget.submissionId);
    if (mounted) setState(() => error = null);
  }

  Future<void> action(String path, {Json? body}) async {
    try {
      await widget.controller.call(
        'POST',
        '/submissions/${widget.submissionId}/$path',
        body: body,
      );
      await refresh();
    } catch (e) {
      if (mounted) setState(() => error = widget.controller.message(e));
    }
  }

  Future<void> retry({String? state, bool finalization = false}) async {
    final controller = widget.controller, id = widget.submissionId;
    setState(() => retrying = true);
    try {
      final candidates = await controller.progressItemsForAction(id);
      if (!mounted ||
          widget.controller != controller ||
          widget.submissionId != id) {
        return;
      }
      final ids = candidates
          .where(
            (item) =>
                (state == null || item.state == state) &&
                (!finalization || item.data['needs_finalization'] == true),
          )
          .map((item) => item.itemId)
          .toList();
      if (ids.isNotEmpty) await action('retry', body: {'item_ids': ids});
    } catch (failure) {
      if (mounted) setState(() => error = widget.controller.message(failure));
    } finally {
      if (mounted) setState(() => retrying = false);
    }
  }

  Future<void> reselect() async {
    setState(() => reselecting = true);
    try {
      final files = await openFiles(
        acceptedTypeGroups: const [intakePhotoTypes],
      );
      if (files.isEmpty) return;
      await widget.controller.reselectSubmission(widget.submissionId, files);
      await refresh();
      if (mounted) setState(() => error = widget.controller.error);
    } catch (e) {
      if (mounted) setState(() => error = widget.controller.message(e));
    } finally {
      if (mounted) setState(() => reselecting = false);
    }
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: widget.controller,
    builder: (context, _) => _content(context),
  );

  Widget _content(BuildContext context) {
    final ui = context.ui;
    final counts = batch?.counts ?? {};
    int count(String state) => ((counts[state] as num?) ?? 0).toInt();
    final done =
        count('sent') + count('duplicate') + count('held') + count('cancelled');
    return Surface(
      child: SafeArea(
        child: Padding(
          padding: EdgeInsets.all(ui.space.s4),
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Wrap(
                      alignment: WrapAlignment.spaceBetween,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Text('Intake progress', style: ui.type.titleLarge),
                        UiButton(
                          label: 'Add more photos',
                          leading: UiIcons.add,
                          variant: UiButtonVariant.secondary,
                          onPressed: widget.onAdd,
                        ),
                      ],
                    ),
                    SizedBox(height: ui.space.s3),
                    Text(
                      batch == null
                          ? 'Loading your submission…'
                          : '$done of ${batch!.total} finished · ${count('sent')} sent to pipeline',
                      style: ui.type.body,
                    ),
                    SizedBox(height: ui.space.s2),
                    UiProgress.bar(
                      value: batch == null
                          ? null
                          : done / math.max(1, batch!.total),
                      semanticsLabel: 'Photos finished',
                    ),
                    SizedBox(height: ui.space.s2),
                    Text(
                      'The specimen pipeline takes over after each successful handoff.',
                      style: ui.type.bodySmall,
                    ),
                    if (error ??
                            widget.controller.progressErrorFor(
                              widget.submissionId,
                            )
                        case final String problem)
                      Text(problem, style: ui.type.bodySmall),
                    if (items.any(
                      (item) => item.data['needs_original'] == true,
                    )) ...[
                      Text(
                        'Some photos still need their original files. Keep this workspace open until transfer finishes; after reopening, choose the originals here to resume this submission.',
                        style: ui.type.bodySmall,
                      ),
                      UiButton(
                        label: reselecting
                            ? 'Resuming original files'
                            : 'Choose original files to resume',
                        variant: UiButtonVariant.secondary,
                        onPressed: reselecting ? null : reselect,
                      ),
                    ],
                    if (batch?.data['worker_error'] is Map)
                      Text(
                        textOf((batch!.data['worker_error'] as Map)['message']),
                        style: ui.type.bodySmall,
                      ),
                    Wrap(
                      spacing: ui.space.s2,
                      children: [
                        if (items.any(
                          (item) => item.data['needs_finalization'] == true,
                        ))
                          UiButton(
                            label: 'Finish saved transfers',
                            variant: UiButtonVariant.secondary,
                            onPressed: retrying
                                ? null
                                : () => retry(finalization: true),
                          ),
                        if (batch?.data['worker_error'] != null)
                          UiButton(
                            label: 'Retry batch',
                            variant: UiButtonVariant.secondary,
                            onPressed: retrying || items.isEmpty ? null : retry,
                          ),
                        if (count('needs_attention') > 0)
                          UiButton(
                            label: 'Retry failed photos',
                            variant: UiButtonVariant.secondary,
                            onPressed: retrying
                                ? null
                                : () => retry(state: 'needs_attention'),
                          ),
                        if (batch?.active == true)
                          UiButton(
                            label: 'Cancel remaining',
                            variant: UiButtonVariant.ghost,
                            onPressed: () => action('cancel'),
                          ),
                        if (count('sent') + count('held') + count('duplicate') >
                            0)
                          UiButton(
                            label: 'View specimens',
                            variant: UiButtonVariant.secondary,
                            onPressed: widget.onViewSpecimens,
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              SliverList.builder(
                itemCount: items.length,
                itemBuilder: (context, index) {
                  final item = items[index];
                  return Padding(
                    padding: EdgeInsets.symmetric(vertical: ui.space.s3),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          item.name,
                          style: ui.type.label,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        Text(
                          intakeStateLabel(item.state),
                          style: ui.type.bodySmall,
                        ),
                        if (item.progress != null)
                          UiProgress.bar(
                            value: item.progress,
                            semanticsLabel: 'Transferring ${item.name}',
                          ),
                        if (item.data['error'] is Map)
                          Text(
                            textOf((item.data['error'] as Map)['message']),
                            style: ui.type.bodySmall,
                          ),
                      ],
                    ),
                  );
                },
              ),
              if (snapshot?.hasMore == true)
                SliverToBoxAdapter(
                  child: UiButton(
                    label: 'Load more photos',
                    variant: UiButtonVariant.secondary,
                    onPressed: () =>
                        widget.controller.loadMoreProgress(widget.submissionId),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
