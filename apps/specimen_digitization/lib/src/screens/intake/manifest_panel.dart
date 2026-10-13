/// The upload manifest (07 section 5).
///
/// Every file the operator chose is a row, including the ones this client
/// refused, so the manifest is the complete account PRD 9.1.5 asks for. A
/// rejection is a Skipped row carrying its own reason (heuristics audit, H1.6
/// and H9.4), not a banner somewhere else on the screen.
library;

import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../administrator_contact.dart';
import '../../capture_quality.dart';
import '../../models.dart';
import '../../review_context.dart';
import '../../vocabulary.dart';
import '../../widgets/caveat_text.dart';
import '../../widgets/empty_state.dart';
import '../../widgets/evidence_drawer.dart';
import '../../widgets/motion_reveal.dart';
import '../../widgets/upload_item.dart';
import 'manifest_entry.dart';
import 'intake_transfer_session.dart';
import 'stage_progress.dart';

/// The manifest header and its rows.
class IntakeManifest extends StatefulWidget {
  const IntakeManifest({
    super.key,
    required this.entries,
    required this.busy,
    required this.stopping,
    required this.onStop,
    required this.onRemove,
    required this.onServerCheck,
    this.onRetry,
    this.padding,
    this.scrollable = true,
    this.onExitsSettled,
    this.hostHandlesEmptyFocus = false,
  });

  /// True when the host moves focus itself once the list is empty, because
  /// it closes the manifest then. The manifest then hands focus over only
  /// between rows; when false, an emptied list's focus goes to its summary.
  final bool hostHandlesEmptyFocus;

  /// Called after a frame in which no row is leaving, so a host that kept
  /// the manifest mounted for a final exit knows it may let it go.
  final VoidCallback? onExitsSettled;

  /// Every row, in the order the operator chose them.
  final List<ManifestEntry> entries;

  /// True while a batch is in flight.
  final bool busy;

  /// True once Stop has been pressed and the in-flight file is finishing.
  final bool stopping;

  /// Cancels rows that have not started.
  final VoidCallback? onStop;

  /// Takes one row out of the batch.
  final void Function(ManifestEntry) onRemove;

  /// Sends one row to the server's decode check.
  final void Function(ManifestEntry) onServerCheck;

  /// Retries one failed or interrupted transfer without resending the batch.
  final void Function(ManifestEntry)? onRetry;

  /// Outer padding, so the compact and two column layouts can differ.
  final EdgeInsetsGeometry? padding;

  /// True where the manifest scrolls itself, which is the pane beside the
  /// capture column from 600 dp up.
  ///
  /// False on a phone, where 13 section 4.4 makes the whole screen one scroll
  /// and this is one section of it. It used to be a shrink wrapped `ListView`
  /// with its physics turned off, which is the pair 13 section 2.1 names:
  /// both exist only to put a scroll inside a scroll.
  final bool scrollable;

  /// The pane's own title.
  static const String title = 'Intake queue';

  /// What an empty manifest is called.
  static const String emptyTitle = 'No photographs yet';

  /// What would fill an empty manifest.
  static const String emptyBody =
      'Photographs appear here as you choose or take them.';

  @override
  State<IntakeManifest> createState() => _IntakeManifestState();
}

class _IntakeManifestState extends State<IntakeManifest> {
  /// Every file this manifest has already drawn, by checksum.
  ///
  /// A card that was already there is not new, and an entrance animation on
  /// a row that already existed is on the blocklist. Only a card the
  /// operator has just added animates, and only when there was already a
  /// manifest for it to join (motion catalog, row 62).
  final Set<String> _drawn = <String>{};

  /// The rows drawn last frame, in order, including any still leaving.
  List<ManifestEntry> _shown = const <ManifestEntry>[];

  /// Rows the main Queue has taken that are collapsing out of the list.
  /// Drawn in place, out of the semantics tree and out of focus traversal,
  /// until their exit finishes (motion catalog, section 2.4: permanent exits
  /// are `quick` on the `exit` curve, and nothing under reduced motion).
  final Set<String> _leaving = <String>{};

  /// One focus container per row, so a row that leaves while it holds focus
  /// can hand focus to a neighbour instead of dropping it (06 section 3).
  final Map<String, FocusNode> _rowFocus = <String, FocusNode>{};

  /// Where focus lands when the last row leaves while it held focus.
  final FocusNode _landing = FocusNode(
    debugLabel: 'Intake manifest summary',
    skipTraversal: true,
  );

  @override
  void initState() {
    super.initState();
    // The first manifest did not arrive; it was there when the screen was.
    _drawn.addAll(widget.entries.map((ManifestEntry e) => e.digest));
    _shown = List<ManifestEntry>.of(widget.entries);
  }

  @override
  void dispose() {
    for (final FocusNode node in _rowFocus.values) {
      node.dispose();
    }
    _landing.dispose();
    super.dispose();
  }

  FocusNode _focusFor(String digest) => _rowFocus.putIfAbsent(
    digest,
    () => FocusNode(debugLabel: 'Intake row $digest', skipTraversal: true),
  );

  /// Works out which rows left since the last frame, keeps the ones the main
  /// Queue took on screen while they collapse, and moves focus out of any
  /// row that held it.
  List<ManifestEntry> _reconcile(List<ManifestEntry> entries, bool reduced) {
    final Set<String> present = <String>{
      for (final ManifestEntry entry in entries) entry.digest,
    };
    _leaving.removeAll(present);
    FocusNode? focusTarget;
    for (final (int index, ManifestEntry gone) in _shown.indexed) {
      if (present.contains(gone.digest) || _leaving.contains(gone.digest)) {
        continue;
      }
      if (_rowFocus[gone.digest]?.hasFocus ?? false) {
        focusTarget =
            _neighbourFocus(index, present) ??
            (widget.hostHandlesEmptyFocus ? null : _landing);
      }
      if (!reduced && gone.state == UploadState.inMainQueue) {
        _leaving.add(gone.digest);
      }
    }
    final List<ManifestEntry> display = List<ManifestEntry>.of(entries);
    for (final (int index, ManifestEntry gone) in _shown.indexed) {
      if (!_leaving.contains(gone.digest)) continue;
      var at = 0;
      for (var before = index - 1; before >= 0; before--) {
        final String digest = _shown[before].digest;
        final int found = display.indexWhere(
          (ManifestEntry e) => e.digest == digest,
        );
        if (found >= 0) {
          at = found + 1;
          break;
        }
      }
      display.insert(at, gone);
    }
    _shown = display;
    final Set<String> drawn = <String>{
      for (final ManifestEntry entry in display) entry.digest,
    };
    final List<String> stale = _rowFocus.keys
        .where((String digest) => !drawn.contains(digest))
        .toList();
    final FocusNode? target = focusTarget;
    if (target != null || stale.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        // The departed rows' focus widgets are gone by now, so their nodes
        // can be released without detaching anything still mounted.
        for (final String digest in stale) {
          if (drawn.contains(digest)) continue;
          if (_shown.any((ManifestEntry e) => e.digest == digest)) continue;
          _rowFocus.remove(digest)?.dispose();
        }
        if (!mounted || target == null) return;
        if (!identical(target, _landing) && target.context == null) {
          _landing.requestFocus();
          return;
        }
        (target.traversalDescendants.firstOrNull ?? target).requestFocus();
      });
    }
    return display;
  }

  /// The row after [index] that is still in the list, else the one before.
  FocusNode? _neighbourFocus(int index, Set<String> present) {
    for (final ManifestEntry entry in _shown.skip(index + 1)) {
      if (present.contains(entry.digest)) return _focusFor(entry.digest);
    }
    for (final ManifestEntry entry in _shown.take(index).toList().reversed) {
      if (present.contains(entry.digest)) return _focusFor(entry.digest);
    }
    return null;
  }

  void _gone(String digest) {
    if (!mounted || !_leaving.contains(digest)) return;
    setState(() {
      _leaving.remove(digest);
      _shown = <ManifestEntry>[
        for (final ManifestEntry entry in _shown)
          if (entry.digest != digest) entry,
      ];
    });
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final bool reduced =
        ui.motion.reduced || MediaQuery.disableAnimationsOf(context);
    final List<ManifestEntry> entries = widget.entries;
    final bool hadCards = _drawn.isNotEmpty;
    final Set<String> arriving = <String>{
      for (final ManifestEntry entry in entries)
        if (hadCards && !_drawn.contains(entry.digest)) entry.digest,
    };
    _drawn.addAll(entries.map((ManifestEntry e) => e.digest));
    final List<ManifestEntry> display = _reconcile(entries, reduced);
    if (_leaving.isEmpty && widget.onExitsSettled != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _leaving.isEmpty) widget.onExitsSettled?.call();
      });
    }

    final List<Widget> children = <Widget>[
      Focus(
        focusNode: _landing,
        includeSemantics: false,
        child: _ManifestHeader(
          entries: entries,
          busy: widget.busy,
          stopping: widget.stopping,
          onStop: widget.onStop,
        ),
      ),
      SizedBox(height: ui.space.s4),
      if (entries.isEmpty && _leaving.isEmpty)
        EmptyState(
          icon: UiIcons.intake.defaultGlyph,
          title: IntakeManifest.emptyTitle,
          body: IntakeManifest.emptyBody,
        ),
      for (final ManifestEntry entry in display)
        KeyedSubtree(
          key: ValueKey<String>('manifest-slot-${entry.digest}'),
          // Fade and size, never a slide: the card did not come from
          // anywhere, the operator made it (motion catalog, row 62). Leaving
          // is the same motion in reverse, faster (section 2.4).
          child: _ManifestSlot(
            arriving: arriving.contains(entry.digest),
            leaving: _leaving.contains(entry.digest),
            onGone: () => _gone(entry.digest),
            child: Padding(
              padding: EdgeInsetsDirectional.only(bottom: ui.space.s4),
              child: Focus(
                focusNode: _focusFor(entry.digest),
                includeSemantics: false,
                child: IntakeManifestRow(
                  key: ValueKey<String>(entry.digest),
                  entry: entry,
                  busy: widget.busy,
                  onRemove: () => widget.onRemove(entry),
                  onServerCheck: () => widget.onServerCheck(entry),
                  onRetry: widget.onRetry == null
                      ? null
                      : () => widget.onRetry!(entry),
                ),
              ),
            ),
          ),
        ),
    ];
    final EdgeInsetsGeometry padding =
        widget.padding ?? EdgeInsetsDirectional.all(ui.space.s6);
    // One ticker for every rolling row, however long the manifest is.
    return IntakeStageCycle(
      active: entries.any(IntakeProgress.rolls),
      child: widget.scrollable
          ? ListView(padding: padding, children: children)
          : Padding(
              padding: padding,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: children,
              ),
            ),
    );
  }
}

/// The pane above the rows: what the batch is, how far it got, and the one
/// way to stop it.
class _ManifestHeader extends StatelessWidget {
  const _ManifestHeader({
    required this.entries,
    required this.busy,
    required this.stopping,
    required this.onStop,
  });

  final List<ManifestEntry> entries;
  final bool busy;
  final bool stopping;
  final VoidCallback? onStop;

  /// What Stop does and what it does not, stated beside the control rather
  /// than after it has been pressed (02 section 4.4).
  static const String stopConsequence =
      'Stop cancels the files that have not started. The file already '
      'sending finishes first.';

  /// What a reviewer is told once Stop has been pressed.
  static const String stoppingLine =
      'Stopping. The file already sending finishes first.';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final bool hasProcessingRows = entries.any(
      (ManifestEntry entry) =>
          entry.state == UploadState.processing ||
          entry.state == UploadState.processingBlocked ||
          entry.state == UploadState.inMainQueue,
    );
    final String summary = entries.isEmpty
        ? batchProgressLine(entries)
        : hasProcessingRows
        ? ingestionQueueLine(entries)
        : batchComplete(entries) && !busy
        ? batchCompleteLine(entries)
        : batchProgressLine(entries);
    return Padding(
      padding: EdgeInsetsDirectional.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          // One account of the batch, read in place but never announced:
          // each row's stage status is the one live region for a photo's
          // change, so one transition is heard once (06 section 2.1).
          Semantics(
            key: const ValueKey<String>('intake-batch-summary'),
            container: true,
            child: Text(
              summary,
              style: ui.type.body.copyWith(color: ui.color.inkSecondary),
            ),
          ),
          if (busy &&
              entries.any(
                (ManifestEntry entry) =>
                    entry.state == UploadState.uploading ||
                    (entry.checking && entry.file != null),
              )) ...<Widget>[
            SizedBox(height: ui.space.s4),
            Align(
              alignment: AlignmentDirectional.centerStart,
              // The label is the present participle and the control is
              // disabled, which is what 02 section 4.3 asks of a control in
              // flight. No indeterminate ring: the batch's own progress is
              // the determinate ring on the row that is sending.
              child: UiButton(
                key: const ValueKey<String>('intake-stop'),
                label: stopping ? 'Stopping' : 'Stop',
                variant: UiButtonVariant.danger,
                leading: UiIcons.stop,
                onPressed: stopping ? null : onStop,
              ),
            ),
            SizedBox(height: ui.space.s2),
            Semantics(
              container: true,
              liveRegion: true,
              child: Text(
                stopping
                    ? _ManifestHeader.stoppingLine
                    : _ManifestHeader.stopConsequence,
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// One manifest card, revealed on the frame it is added, static after that
/// (motion catalog, row 62), and collapsed when the main Queue takes it.
class _ManifestSlot extends StatefulWidget {
  const _ManifestSlot({
    required this.arriving,
    required this.leaving,
    required this.onGone,
    required this.child,
  });

  final bool arriving;

  /// True once the row has left the Intake list and is only collapsing.
  final bool leaving;

  /// Called when the collapse has finished.
  final VoidCallback onGone;
  final Widget child;

  @override
  State<_ManifestSlot> createState() => _ManifestSlotState();
}

class _ManifestSlotState extends State<_ManifestSlot>
    with SingleTickerProviderStateMixin {
  late bool _revealed = !widget.arriving;
  final GlobalKey _content = GlobalKey();

  /// 1 while the row is in the list, running to 0 as it leaves.
  late final AnimationController _exit;
  late final Animation<double> _exitCurve;

  @override
  void initState() {
    super.initState();
    _exit = AnimationController(
      vsync: this,
      value: 1,
      duration: MotionTokens.quickRaw,
    );
    _exitCurve = CurvedAnimation(parent: _exit, curve: MotionTokens.exitCurve);
    if (!_revealed) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() => _revealed = true);
      });
    }
    if (widget.leaving) _leave();
  }

  @override
  void didUpdateWidget(covariant _ManifestSlot oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.leaving && !oldWidget.leaving) _leave();
    if (!widget.leaving && oldWidget.leaving) _exit.value = 1;
  }

  void _leave() {
    _exit.reverse().whenCompleteOrCancel(() {
      if (mounted && widget.leaving) widget.onGone();
    });
  }

  @override
  void dispose() {
    _exit.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bool leaving = widget.leaving;
    final Widget content = KeyedSubtree(
      key: _content,
      child: ExcludeFocus(
        excluding: leaving,
        child: ExcludeSemantics(
          excluding: leaving,
          child: IgnorePointer(
            ignoring: leaving,
            child: MotionReveal(visible: _revealed, child: widget.child),
          ),
        ),
      ),
    );
    // The collapse wraps the row only while it leaves: a size transition
    // loosens its child's width, which a settled row must never feel. The
    // global key carries the row's state across, so it does not redraw.
    if (!leaving) return content;
    return SizeTransition(
      sizeFactor: _exitCurve,
      axisAlignment: -1,
      child: FadeTransition(opacity: _exitCurve, child: content),
    );
  }
}

/// One manifest row: transfer state and server-check outcomes stay visible;
/// file metadata and descriptive measurements are available on request.
class IntakeManifestRow extends StatelessWidget {
  const IntakeManifestRow({
    super.key,
    required this.entry,
    required this.busy,
    required this.onRemove,
    required this.onServerCheck,
    this.onRetry,
  });

  /// The row's data.
  final ManifestEntry entry;

  /// True while a batch is in flight anywhere on the screen.
  final bool busy;

  /// Takes this row out of the batch.
  final VoidCallback onRemove;

  /// Asks the server to try decoding this file.
  final VoidCallback onServerCheck;
  final VoidCallback? onRetry;

  /// What the server check control is called.
  static const String serverCheckLabel = 'Send for server check';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final bool canDismiss =
        !entry.checking && (entry.removable || entry.dismissible);
    final bool canRetryTransfer =
        (entry.state == UploadState.failed ||
            entry.state == UploadState.interrupted) &&
        entry.file != null;
    final String? processingAction = intakeProcessingRetryAction(entry);
    final bool canRetryProcessing = processingAction != null;
    final bool showProcessingGuidance =
        entry.state == UploadState.processingBlocked ||
        canRetryProcessing ||
        (entry.state == UploadState.processing && entry.specimen == null);
    // The stage track owns progress interpolation and status announcements.
    final Widget item = UploadItem(
      name: entry.label,
      concise: true,
      stageProgress: IntakeStageProgress(entry: entry),
      state: entry.displayState,
      thumbnail: entry.file?.bytes,
      sizeBytes: entry.file?.bytes.length,
      pixelWidth: entry.file?.width,
      pixelHeight: entry.file?.height,
      progress: entry.progress,
      reason: entry.why == null ? entry.reason : null,
      onRemove: canDismiss ? onRemove : null,
      removeBlockedReason: canDismiss
          ? null
          : entry.state == UploadState.processing
          ? 'This photograph stays here while processing is active.'
          : 'The server has taken this file, so it cannot be removed from '
                'the batch.',
      // The per-row action and the per-row evidence live inside the
      // component rather than in a column around it, so a manifest row is
      // one thing a reviewer learns once.
      details: _details(context, ui),
    );

    return Padding(
      padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const UiHairline(),
          SizedBox(height: ui.space.s2),
          item,
          UiDisclosure(
            key: ValueKey<String>('intake-progress-details-${entry.digest}'),
            title: 'Progress details',
            child: IntakeProgressDetails(entry: entry),
          ),
          if ((canRetryTransfer || canRetryProcessing) && onRetry != null)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiButton(
                key: ValueKey<String>('intake-retry-${entry.digest}'),
                label: entry.checking
                    ? 'Retrying…'
                    : processingAction == 'start_processing'
                    ? 'Retry start'
                    : canRetryProcessing
                    ? 'Retry processing'
                    : 'Retry this file',
                variant: UiButtonVariant.primary,
                onPressed: busy || entry.checking ? null : onRetry,
                disabledReason: busy && !entry.checking
                    ? 'Finish the current upload or retry first.'
                    : null,
              ),
            ),
          if (showProcessingGuidance) ...<Widget>[
            SizedBox(height: ui.space.s2),
            Text(
              intakeProcessingRecoveryGuidance(entry),
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
            if (entry.specimen != null &&
                !canRetryProcessing &&
                const <String>{
                  'processing_blocked',
                  'paused',
                }.contains(entry.specimen!.state))
              AdministratorContactLine(specimenId: entry.specimenId),
          ],
          if (entry.why != null)
            CaveatText(label: entry.reason ?? '', why: entry.why!),
          UiDisclosure(
            title: 'File details',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Text(
                  entry.session != null
                      ? 'Existing upload, classification unchanged'
                      : entry.file?.sensitive == false
                      ? 'Not sensitive'
                      : 'Sensitive',
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
                if (entry.file != null)
                  Text(
                    UploadItem.measurements(
                      sizeBytes: entry.file!.bytes.length,
                      width: entry.file!.width,
                      height: entry.file!.height,
                    ),
                    style: ui.type.bodySmall,
                  ),
                _ChecksumLine(digest: entry.digest),
                if (entry.file != null) ...<Widget>[
                  SizedBox(height: ui.space.s3),
                  CaptureQualitySummary(quality: entry.quality),
                  if (entry.preflight == null &&
                      entry.preflightError == null &&
                      !entry.checking)
                    _checkButton(context),
                  if (entry.quality != null)
                    const CaveatText(
                      label:
                          'Thumbnail measurements do not assess readability.',
                      why:
                          'Check focus, glare and whether every label is in frame.',
                    ),
                  const CaveatText(
                    label: 'The server check creates nothing.',
                    why:
                        'Nothing is created and no outside service is called. '
                        'Local measurements stay on this device until you choose an action.',
                  ),
                ],
                if (entry.preflight != null)
                  EvidenceDrawer(
                    title: 'Server codec support and check evidence',
                    payload: entry.preflight,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// The server-check action, result and actionable failures stay beside the
  /// file they concern. Descriptive diagnostics live in File details.
  Widget? _details(BuildContext context, UiThemeData ui) {
    if (entry.file == null) return null;
    final Json? preflight = entry.preflight;
    if (preflight == null && entry.preflightError == null && !entry.checking) {
      return null;
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _checkButton(context),
        if (entry.preflightError != null)
          Semantics(
            container: true,
            liveRegion: true,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                UiIcon(
                  UiIcons.error,
                  size: UiIconSize.inline,
                  color: ui.color.status.blocked.content,
                ),
                SizedBox(width: ui.space.s2),
                Expanded(
                  child: Text(
                    entry.preflightError!,
                    style: ui.type.body.copyWith(
                      color: ui.color.status.blocked.content,
                    ),
                  ),
                ),
              ],
            ),
          ),
        if (preflight != null) ...<Widget>[
          if (objectOf(preflight['decode'])['reason'] ==
              'memory_limit_unavailable') ...<Widget>[
            const CaveatText(
              label:
                  'The server check is not available. Memory-limit '
                  'enforcement has to be turned on for this collection.',
              why:
                  'Changing the image format will not help. Ordinary '
                  'image intake is checked separately and is '
                  'unaffected.',
            ),
            const AdministratorContactLine(),
          ],
          Text(
            'Server check: '
            '${vocabularyLabel(textOf(preflight['status']))}.',
            style: ui.type.body.copyWith(color: ui.color.ink),
          ),
          for (final dynamic issue
              in preflight['issues'] as List<dynamic>? ?? const <dynamic>[])
            Text(
              vocabularyLabel(issue.toString()),
              style: ui.type.body.copyWith(color: ui.color.ink),
            ),
        ],
      ],
    );
  }

  Widget _checkButton(BuildContext context) => Align(
    alignment: AlignmentDirectional.centerStart,
    child: UiButton(
      label: entry.checking ? 'Checking' : serverCheckLabel,
      variant: UiButtonVariant.secondary,
      leading: UiIcons.sourceImport,
      onPressed: entry.checking || busy ? null : onServerCheck,
    ),
  );
}

/// The file's checksum, truncated with a copy control (02 section 4.14).
///
/// The v1 line was a `SelectableText`, which is a Material component and a
/// drag a touch reviewer has to discover. The whole value goes to the
/// clipboard; the line shows the first twelve characters, which is what the
/// guideline asks of a checksum outside a details sheet.
class _ChecksumLine extends StatelessWidget {
  const _ChecksumLine({required this.digest});

  final String digest;

  /// How many characters of a checksum are shown.
  static const int shown = 12;

  /// What the copy control is called.
  static const String copyLabel = 'Copy the checksum';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String head = digest.length <= shown
        ? digest
        : '${digest.substring(0, shown)}…';
    return MergeSemantics(
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              'Checksum (SHA-256) $head',
              style: ui.type.mono.digest.copyWith(color: ui.color.inkSecondary),
            ),
          ),
          UiIconButton(
            icon: UiIcons.copy,
            semanticsLabel: copyLabel,
            tooltip: copyLabel,
            onPressed: () =>
                unawaited(Clipboard.setData(ClipboardData(text: digest))),
          ),
        ],
      ),
    );
  }
}
