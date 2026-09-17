/// Browse a registered source and add photographs to the queue (screen
/// blueprints, section 13).
///
/// The screen exists because the collection's images were invisible to the
/// application: intake was upload-only, so a thousand slides already sitting
/// in storage could not be seen, let alone chosen between. This is the surface
/// that makes them visible and lets a reviewer pick one, several, or all of
/// them.
///
/// **Adding is not running.** The import path creates records and dispatches
/// no processing, in any mode. Running a selection is a separate decision that
/// needs an estimate, an allowance and a reservation, and the endpoint for it
/// does not exist yet: it is workstream C of
/// `docs/execution/SOURCE_BROWSE_AND_RUN.md`, blocked on an ongoing budget the
/// owner has not set. So this screen offers no run control. An affordance the
/// server cannot serve is hidden rather than disabled (blueprint 3), and the
/// one place the distinction matters to a reviewer, the confirmation, says in
/// words that nothing is run and nothing is spent.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../selection.dart';
import '../../sources.dart';
import '../../widgets/source_import_sheet.dart';
import '../../widgets/source_object_row.dart';
import '../../widgets/widgets.dart';
import 'source_controller.dart';

/// How many rows stand in for the first page while it loads.
const int sourceSkeletonRows = 6;

/// What the recaptured-snapshot band's dismiss control is called.
///
/// A band's dismiss draws a glyph rather than a word, so the name it
/// publishes is the only handle a reviewer or a test has on it.
const String sourceRefreshedDismissLabel = 'Dismiss this notice';

/// What a long press does on a narrow window, in this screen's noun.
///
/// The only way into a selection where the checkbox column is closed, so a
/// reader that announces custom actions has to hear the right word for what
/// it is picking.
const String sourceLongPressHint = 'Select this photograph';

/// Browsing one registered source.
class SourceBrowsePane extends StatefulWidget {
  const SourceBrowsePane({
    super.key,
    required this.controller,
    required this.source,
    this.onOpenSpecimen,
  });

  /// The paging controller for this source.
  final SourceBrowseController controller;

  /// The source being browsed, for its name and its snapshot header.
  final RegisteredSource source;

  /// Opens the record a photograph already became.
  ///
  /// Passed in rather than read from the router here, so the pane knows what
  /// it draws and not where it sits.
  final void Function(String specimenId)? onOpenSpecimen;

  @override
  State<SourceBrowsePane> createState() => _SourceBrowsePaneState();
}

class _SourceBrowsePaneState extends State<SourceBrowsePane> {
  final PagedSelection<SourceObject> _selection = PagedSelection<SourceObject>(
    identify: (SourceObject object) => object.objectName,
  );
  final ScrollController _scroll = ScrollController();

  /// A context inside the toast layer.
  ///
  /// `UiToasts.show` walks up from the context it is given, and this pane's
  /// own context is above the layer it installs, so a toast raised from here
  /// would find no host at all.
  final GlobalKey _toastScope = GlobalKey(debugLabel: 'Source toast scope');

  bool _adding = false;
  int _added = 0;
  int _addingTotal = 0;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onControllerChanged);
    _selection.addListener(_onSelectionChanged);
    _scroll.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) widget.controller.load();
    });
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onControllerChanged);
    _selection
      ..removeListener(_onSelectionChanged)
      ..dispose();
    _scroll.dispose();
    super.dispose();
  }

  /// Keeps the selection a subset of what is loaded.
  ///
  /// Driven from the controller's listener rather than from `build`, because a
  /// widget must not push a change back into the thing it is drawing. On an
  /// immutable snapshot this only ever appends, so nothing already picked is
  /// dropped by a later page arriving.
  void _onControllerChanged() {
    _selection.syncLoaded(
      widget.controller.items,
      moreToLoad: widget.controller.moreToLoad,
    );
    if (mounted) setState(() {});
  }

  void _onSelectionChanged() {
    if (mounted) setState(() {});
  }

  void _onScroll() {
    final SourceBrowseController controller = widget.controller;
    if (!_scroll.hasClients ||
        controller.loadingMore ||
        !controller.moreToLoad) {
      return;
    }
    final double remaining =
        _scroll.position.maxScrollExtent - _scroll.position.pixels;
    if (remaining < _loadMoreThreshold) controller.loadMore();
  }

  /// How close to the end of the list a scroll gets before the next page is
  /// asked for.
  static const double _loadMoreThreshold = 600;

  /// Picks every photograph in the current filter, loading the rest first.
  ///
  /// The count is stated on the control before this runs, so a reviewer who
  /// presses it has already been told how far it reaches.
  Future<void> _selectAll() async {
    final SourceBrowseController controller = widget.controller;
    if (!controller.allLoaded) await controller.loadAll();
    if (!mounted) return;
    _selection.selectAllLoaded();
  }

  /// Confirms, then adds the selection in as many requests as the server's
  /// bound takes.
  Future<void> _addSelection() async {
    final SourceBrowseController controller = widget.controller;
    final List<SourceObject> chosen = _selection.items;
    if (chosen.isEmpty || _adding) return;
    final int alreadyInQueue = chosen
        .where((SourceObject o) => o.state == SourceObjectState.imported)
        .length;
    final bool go = await confirmSourceImport(
      context,
      count: chosen.length,
      alreadyInQueue: alreadyInQueue,
    );
    if (!go || !mounted) return;
    setState(() {
      _adding = true;
      _added = 0;
      _addingTotal = chosen.length;
    });
    final SourceImportProgress progress = await controller.importSelection(
      chosen,
      onProgress: (SourceImportProgress p) {
        if (mounted) setState(() => _added = p.settled);
      },
    );
    if (!mounted) return;
    setState(() => _adding = false);
    _selection.clear();
    // The rows' imported state is resolved server side, so the list has to be
    // asked again rather than patched here.
    await controller.load();
    if (!mounted) return;
    if (progress.complete && progress.unchanged.isEmpty) {
      _toast('${photographsLabel(progress.imported)} added to the queue');
      return;
    }
    // Anything less than whole is something the reviewer has to act on, so it
    // is a surface they dismiss rather than one that times out.
    await showSourceImportOutcome(context, progress: progress);
  }

  /// Raises [message] on the nearest toast layer.
  void _toast(String message) {
    final BuildContext? scope = _toastScope.currentContext;
    if (scope == null) return;
    UiToasts.show(scope, message: message, icon: UiIcons.cleared);
  }

  @override
  Widget build(BuildContext context) => _ToastLayer(
    child: KeyedSubtree(key: _toastScope, child: _pane(context)),
  );

  Widget _pane(BuildContext context) {
    final UiThemeData ui = context.ui;
    final SourceBrowseController controller = widget.controller;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Padding(
          padding: EdgeInsetsDirectional.fromSTEB(
            ui.space.s4,
            ui.space.s4,
            ui.space.s4,
            ui.space.s2,
          ),
          child: _Header(controller: controller, source: widget.source),
        ),
        Padding(
          padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s4),
          child: _Controls(
            controller: controller,
            selection: _selection,
            onSelectAll: _selectAll,
          ),
        ),
        if (controller.refreshed)
          Padding(
            padding: EdgeInsetsDirectional.only(
              top: ui.space.s2,
              bottom: ui.space.s0,
            ),
            child: _RefreshedNotice(onDismiss: controller.acknowledgeRefresh),
          ),
        // The import has a denominator, so its progress is drawn rather than
        // described (02 section 4.8). It is one bar for one gesture, however
        // many requests the server's bound takes.
        MotionReveal(
          visible: _adding,
          child: Padding(
            padding: EdgeInsetsDirectional.fromSTEB(
              ui.space.s4,
              ui.space.s2,
              ui.space.s4,
              ui.space.s0,
            ),
            child: UiProgress.bar(
              value: _addingTotal == 0 ? null : _added / _addingTotal,
              semanticsLabel: _addingLabel(),
            ),
          ),
        ),
        Expanded(child: _body(context, controller)),
        MotionReveal(
          visible: _selection.isNotEmpty,
          child: SelectionBar(
            count: _selection.count,
            loadedCount: _selection.loadedCount,
            moreToLoad: _selection.moreToLoad,
            allLoadedSelected: _selection.allLoadedSelected,
            onSelectAllLoaded: _selection.selectAllLoaded,
            onClear: _selection.clear,
            busy: _adding,
            countLabel: photographsLabel,
            moreMatchLabel: _moreMatchLabel,
            actions: <SelectionAction>[
              (
                label: _adding
                    ? 'Adding ${photographsLabel(_added)}'
                    : addToQueueLabel,
                icon: UiIcons.addToBatch.defaultGlyph,
                onPressed: _addSelection,
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// What the import bar reads as, counted rather than a bare percentage
  /// (02 section 4.8).
  String _addingLabel() =>
      'Adding ${photographsLabel(_added)} of ${photographsLabel(_addingTotal)}';

  /// The sentence under a select all that stopped at the loaded page, in this
  /// screen's noun.
  static const String _moreMatchLabel =
      'More photographs match this filter. Load more to select them.';

  /// What the selection bar's one action is called.
  static const String addToQueueLabel = 'Add to queue';

  Widget _body(BuildContext context, SourceBrowseController controller) {
    final UiThemeData ui = context.ui;
    final ApiFailure? failure = controller.error;
    if (failure != null && controller.items.isEmpty) {
      return _Failure(failure: failure, onRetry: controller.load);
    }
    if (controller.loading && controller.items.isEmpty) {
      return ListView(
        padding: EdgeInsetsDirectional.all(ui.space.s4),
        children: <Widget>[
          const LoadingAnnouncement(thing: 'this source'),
          for (int row = 0; row < sourceSkeletonRows; row++)
            Padding(
              padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
              child: const SkeletonRow(),
            ),
        ],
      );
    }
    if (controller.loaded && controller.items.isEmpty) {
      return EmptyState(
        icon: UiIcons.noResults.defaultGlyph,
        title: controller.filter == SourceFilter.all
            ? 'No photographs here'
            : 'No photographs match',
        body: controller.filter == SourceFilter.all
            ? 'This source holds nothing the collection can read yet.'
            : 'Choose another filter to see the rest of this source.',
      );
    }

    final List<SourceObject> items = controller.items;
    // A checkbox column stays open on a window wide enough to keep one, so a
    // reviewer on a pointer never has to discover a gesture. A narrow one
    // reveals it on a long press. The window decides, never the platform.
    final bool column =
        WindowClass.of(context).isAtLeast(WindowClass.medium) ||
        _selection.active;

    return ListView.builder(
      controller: _scroll,
      padding: EdgeInsetsDirectional.all(ui.space.s4),
      // One extra row carries the paging footer.
      itemCount: items.length + 1,
      itemBuilder: (BuildContext context, int index) {
        if (index == items.length) {
          return _Footer(controller: controller);
        }
        final SourceObject object = items[index];
        final Widget row = SourceObjectRow(
          object: object,
          onOpen: object.specimenId == null || widget.onOpenSpecimen == null
              ? null
              : () => widget.onOpenSpecimen!(object.specimenId!),
        );
        return Padding(
          key: ValueKey<String>('source-row-${object.objectName}'),
          padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s1),
          child: SelectableRow(
            selected: _selection.isSelected(object),
            label: object.displayName,
            showCheckbox: column,
            // Drawn and unavailable rather than absent: a photograph this
            // source does not admit cannot be added, and a reader hearing
            // nothing at all could not tell it from a row they missed.
            enabled: object.state.selectable,
            longPressHint: sourceLongPressHint,
            onToggle: () => _selection.toggle(object),
            onExtend: () => _selection.selectRange(object),
            onLongPress: column ? null : () => _selection.select(object),
            child: row,
          ),
        );
      },
    );
  }
}

/// Installs a toast layer only where there is not one already.
///
/// `UiScaffold` hosts the layer for a page built on it, which is what the
/// shell gives this pane in the application. A component test that pumps the
/// pane on its own has no frame above it, and a result nobody can read is
/// worse than one drawn in a bare host.
class _ToastLayer extends StatelessWidget {
  const _ToastLayer({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) =>
      UiToastHost.maybeOf(context) == null ? UiToastHost(child: child) : child;
}

/// The source's name and what its snapshot holds.
class _Header extends StatelessWidget {
  const _Header({required this.controller, required this.source});

  final SourceBrowseController controller;
  final RegisteredSource source;

  /// What the header says under the name.
  ///
  /// The count is the snapshot's, which is a number the server made, and the
  /// moment is when it made it. A source that has never been captured says so
  /// rather than showing a zero (writing guidelines, rule 14).
  String summary() {
    if (!controller.loaded) return 'Loading this source';
    final DateTime? captured = controller.capturedAt;
    final String count = photographsLabel(controller.objectCount);
    return captured == null
        ? count
        : '$count · listed ${absoluteTime(captured)}';
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Semantics(
          container: true,
          header: true,
          child: Text(
            source.displayName,
            style: ui.type.headline.copyWith(color: ui.color.ink),
          ),
        ),
        SizedBox(height: ui.space.s1),
        Semantics(
          container: true,
          liveRegion: true,
          child: Text(
            summary(),
            style: ui.type.body.copyWith(color: ui.color.inkSecondary),
          ),
        ),
      ],
    );
  }
}

/// The filter and the select all.
class _Controls extends StatelessWidget {
  const _Controls({
    required this.controller,
    required this.selection,
    required this.onSelectAll,
  });

  final SourceBrowseController controller;
  final PagedSelection<SourceObject> selection;
  final Future<void> Function() onSelectAll;

  /// The name the filter's options are offered under on a column too narrow
  /// for the track (11 section 3.3).
  static const String filterLabel = 'Photographs';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final int? reach = controller.reachableCount;
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: ui.space.s3,
      runSpacing: ui.space.s2,
      children: <Widget>[
        UiSegmented<SourceFilter>(
          label: filterLabel,
          value: controller.filter,
          onChanged: (SourceFilter chosen) =>
              controller.applyFilter(filter: chosen),
          segments: <UiSegment<SourceFilter>>[
            for (final SourceFilter filter in SourceFilter.values)
              UiSegment<SourceFilter>(value: filter, label: filter.label),
          ],
        ),
        // Offered only where the reach can be named. Under the in-queue
        // filters the server does not count the snapshot, because that would
        // cost a checksum lookup per object, so until everything is loaded
        // there is no honest number to put on the control and it is absent
        // rather than vague.
        if (reach != null && reach > 0 && !selection.allLoadedSelected)
          UiButton(
            label: 'Select all ${groupedCount(reach)}',
            variant: UiButtonVariant.ghost,
            leading: UiIcons.selectAll,
            onPressed: controller.loading ? null : onSelectAll,
          ),
      ],
    );
  }
}

/// The end of the list: a loading row, a way to load more, or nothing.
class _Footer extends StatelessWidget {
  const _Footer({required this.controller});

  final SourceBrowseController controller;

  /// What the control that asks for the next page is called.
  static const String loadMoreLabel = 'Load more';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    if (controller.loadingMore) {
      return Padding(
        padding: EdgeInsetsDirectional.all(ui.space.s4),
        child: const Center(
          child: UiProgress.ring(
            semanticsLabel: 'Loading more photographs',
            size: UiProgressSize.medium,
          ),
        ),
      );
    }
    if (!controller.moreToLoad) return const SizedBox.shrink();
    return Padding(
      padding: EdgeInsetsDirectional.all(ui.space.s4),
      child: Center(
        child: UiButton(
          label: loadMoreLabel,
          variant: UiButtonVariant.ghost,
          onPressed: controller.loadMore,
        ),
      ),
    );
  }
}

/// Said once, when the source was recaptured under the reviewer.
class _RefreshedNotice extends StatelessWidget {
  const _RefreshedNotice({required this.onDismiss});

  final VoidCallback onDismiss;

  /// What a reviewer is told when the snapshot changed while they were
  /// choosing.
  static const String body =
      'This source was listed again, so the photographs start from the top.';

  @override
  Widget build(BuildContext context) => UiBanner(
    message: body,
    dismissLabel: sourceRefreshedDismissLabel,
    onDismiss: onDismiss,
  );
}

/// A listing that did not answer.
class _Failure extends StatelessWidget {
  const _Failure({required this.failure, required this.onRetry});

  final ApiFailure failure;
  final VoidCallback onRetry;

  /// What a member without the sensitive-image permission is told.
  ///
  /// A snapshot is retained sensitive, because the names of objects under a
  /// collection's prefix are collection information. Refusal names who can
  /// resolve it rather than restating the denial (writing guidelines, rule 9).
  static const String denied =
      'This source needs permission for sensitive images. Ask your '
      'administrator for access.';

  @override
  Widget build(BuildContext context) => EmptyState(
    icon: failure.status == 403
        ? UiIcons.locked.defaultGlyph
        : UiIcons.syncProblem.defaultGlyph,
    title: failure.status == 403 ? 'Source not available' : 'Source not loaded',
    body: failure.status == 403 ? denied : failure.message,
    actionLabel: failure.status == 403 ? null : 'Retry',
    onAction: failure.status == 403 ? null : onRetry,
  );
}
