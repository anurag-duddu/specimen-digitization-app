/// Compact Intake rows, batch progress and photo diagnostics.
///
/// Local refusals stay as rows with a short reason. A photo already in this
/// list is reported once without adding another row; handed-off photos leave
/// the list while their cumulative result remains in the header.
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
import 'intake_status.dart';
import '../../widgets/product_modal.dart';
import '../../widgets/specimen_status.dart';
import '../../widgets/intake_photo.dart';

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
    this.onChooseFile,
    this.onSensitivityChanged,
    this.onViewSpecimens,
    this.sent = 0,
    this.duplicates = 0,
    this.activity,
    this.padding,
    this.scrollable = true,
    this.onExitsSettled,
    this.hostHandlesEmptyFocus = false,
  });

  /// True when the host moves focus itself once the list is empty, because
  /// it closes the manifest then. The manifest then hands focus over only
  /// between rows; when false, an emptied list's focus goes to its summary.
  final bool hostHandlesEmptyFocus;
  final VoidCallback? onChooseFile, onViewSpecimens;
  final void Function(ManifestEntry, bool)? onSensitivityChanged;
  final int sent, duplicates;
  final Listenable? activity;

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
  static const String title = 'Photos';

  /// What an empty manifest is called.
  static const String emptyTitle = 'No photos yet';

  /// What would fill an empty manifest.
  static const String emptyBody = 'Choose or take a photo to begin.';

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

  /// Rows handed off to Specimens that are collapsing out of the list.
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
  void didUpdateWidget(covariant IntakeManifest oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Stop disappears on completion; keep its keyboard focus on the summary.
    if (oldWidget.busy &&
        !widget.busy &&
        widget.entries.isEmpty &&
        _landing.hasFocus &&
        !widget.hostHandlesEmptyFocus) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _landing.requestFocus();
      });
    }
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

  /// Works out which rows left since the last frame, keeps handed-off rows on screen while they collapse, and moves focus out of any
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
          sent: widget.sent,
          duplicates: widget.duplicates,
          onViewSpecimens: widget.onViewSpecimens,
          busy: widget.busy,
          stopping: widget.stopping,
          onStop: widget.onStop,
        ),
      ),
      SizedBox(height: ui.space.s4),
      if (entries.isEmpty &&
          _leaving.isEmpty &&
          widget.sent + widget.duplicates == 0)
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
                  activity: widget.activity,
                  onRemove: () => widget.onRemove(entry),
                  onChooseFile: widget.onChooseFile,
                  onSensitivityChanged: widget.onSensitivityChanged == null
                      ? null
                      : (value) => widget.onSensitivityChanged!(entry, value),
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
    return widget.scrollable
        ? SingleChildScrollView(
            padding: padding,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: children,
            ),
          )
        : Padding(
            padding: padding,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: children,
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
    required this.sent,
    required this.duplicates,
    this.onViewSpecimens,
  });
  final List<ManifestEntry> entries;
  final bool busy, stopping;
  final VoidCallback? onStop, onViewSpecimens;
  final int sent, duplicates;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final complete = entries.isEmpty && sent > 0 && duplicates == 0;
    final summary = complete
        ? 'All $sent sent'
        : intakeBatchSummary(entries, sent: sent, duplicates: duplicates);
    final active = entries.indexWhere(
      (entry) =>
          entry.state == UploadState.uploading ||
          (entry.checking && !entry.settled),
    );
    final total = sent + duplicates + entries.length;
    final position = sent + duplicates + (active < 0 ? 0 : active + 1);
    final progressLabel = 'Sending $position of $total';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(
          key: const ValueKey<String>('intake-batch-summary'),
          container: true,
          child: Text(
            summary,
            style: ui.type.body.copyWith(color: ui.color.inkSecondary),
          ),
        ),
        if (sent + duplicates > 0 && onViewSpecimens != null)
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiButton(
              label: 'View in Specimens',
              variant: UiButtonVariant.ghost,
              onPressed: onViewSpecimens,
            ),
          ),
        if (busy && active >= 0) ...[
          SizedBox(height: ui.space.s2),
          Text(progressLabel, style: ui.type.bodySmall),
          UiProgress.bar(
            value: ((position - 1 + entries[active].progress) / total).clamp(
              0,
              1,
            ),
            semanticsLabel: progressLabel,
          ),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiButton(
              key: const ValueKey<String>('intake-stop'),
              label: stopping ? 'Stopping' : 'Stop sending',
              variant: UiButtonVariant.secondary,
              leading: UiIcons.stop,
              onPressed: stopping ? null : onStop,
            ),
          ),
          if (stopping)
            Semantics(
              liveRegion: true,
              child: const Text('Stopping. Current photo finishes.'),
            ),
        ],
      ],
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
    this.onChooseFile,
    this.onSensitivityChanged,
    this.activity,
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
  final VoidCallback? onChooseFile;
  final ValueChanged<bool>? onSensitivityChanged;
  final Listenable? activity;

  /// What the server check control is called.
  static const String serverCheckLabel = 'Send for server check';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final status = intakeStatus(entry);
    final triple = switch (status.tone) {
      IntakeTone.error => ui.color.status.blocked,
      IntakeTone.operational => ui.color.status.needsReview,
      IntakeTone.processing => ui.color.status.processing,
      IntakeTone.none || IntakeTone.neutral => ui.color.status.deferred,
    };
    final icon = switch (status.tone) {
      IntakeTone.error => UiIcons.error,
      IntakeTone.operational => UiIcons.deferred,
      IntakeTone.processing => UiIcons.processing,
      _ => UiIcons.time,
    };
    final serverSensitive = entry.session?['sensitive'];
    final sensitive =
        entry.file?.sensitive ??
        (serverSensitive is bool ? serverSensitive : null);
    return UploadItem(
      name: entry.label,
      state: entry.displayState,
      thumbnail: entry.file?.bytes,
      reason: status.reason,
      sensitive: sensitive,
      intakePresentation: StatusPresentation(
        content: triple.content,
        fill: triple.fill,
        onFill: triple.onFill,
        icon: icon.resolve(),
        spec: icon,
        label: status.status,
        semanticsLabel: status.status,
        progress: entry.state == UploadState.uploading ? entry.progress : null,
      ),
      onOpen: () => showProductModal<void>(
        context: context,
        title: entry.label,
        body: (context) => activity == null
            ? _sheet(context)
            : ListenableBuilder(
                listenable: activity!,
                builder: (context, _) => _sheet(context),
              ),
      ),
      action: _action(status),
    );
  }

  Widget? _action(IntakeStatus status) {
    // A server handle locks the declaration even after sign-in interruption.
    final editable =
        entry.state == UploadState.ready &&
        !entry.checking &&
        entry.session == null &&
        entry.file != null;
    if (status.action == IntakeAction.menu) {
      final wasSensitive = entry.file?.sensitive == true;
      return UiMenuTrigger(
        semanticsLabel: 'Photo options for ${entry.label}',
        items: [
          if (editable && onSensitivityChanged != null)
            UiMenuItem(
              label: wasSensitive ? 'Mark not sensitive' : 'Mark sensitive',
              icon: UiIcons.locked,
              onSelected: () => onSensitivityChanged!(!wasSensitive),
            ),
          UiMenuItem(
            label: 'Remove',
            icon: UiIcons.close,
            onSelected: onRemove,
          ),
        ],
      );
    }
    final action = switch (status.action) {
      IntakeAction.dismiss || IntakeAction.remove => onRemove,
      IntakeAction.chooseFile => onChooseFile,
      IntakeAction.start ||
      IntakeAction.retry ||
      IntakeAction.retryNow => busy || entry.checking ? null : onRetry,
      _ => null,
    };
    if (status.action?.label == null) return null;
    return UiButton(
      key: ValueKey<String>('intake-action-${entry.digest}'),
      label: status.action!.label!,
      variant: UiButtonVariant.ghost,
      onPressed: action,
    );
  }

  Widget _sheet(BuildContext context) {
    final ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (entry.file != null)
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: IntakePhoto(
              bytes: entry.file!.bytes,
              side: ui.space.s10 * 4,
            ),
          ),
        Text(
          entry.file?.sensitive == false
              ? 'Not sensitive'
              : entry.file?.sensitive == true
              ? 'Sensitive'
              : 'Existing upload, classification unchanged',
          style: ui.type.body,
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
        if (entry.reason != null) Text(entry.reason!, style: ui.type.bodySmall),
        if (entry.why != null) Text(entry.why!, style: ui.type.bodySmall),
        if (entry.transferError != null)
          Text(
            entry.transferError is ApiFailure
                ? (entry.transferError! as ApiFailure).message
                : entry.transferError.toString(),
            style: ui.type.bodySmall,
          ),
        if (entry.file != null) ...[
          CaptureQualitySummary(quality: entry.quality),
          if (entry.preflight == null &&
              entry.preflightError == null &&
              !entry.checking)
            _checkButton(context),
          const CaveatText(
            label: 'Thumbnail measurements do not assess readability.',
            why: 'Check focus, glare and whether every label is in frame.',
          ),
          const CaveatText(
            label: 'The server check creates nothing.',
            why:
                'Nothing is created and no outside service is called. '
                'Local measurements stay on this device until you choose an action.',
          ),
        ],
        if (_details(context, ui) case final Widget details) details,
        if (entry.preflight != null)
          EvidenceDrawer(
            title: 'Server codec support and check evidence',
            payload: entry.preflight,
          ),
      ],
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
