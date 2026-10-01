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
  });

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
  static const String title = 'Upload manifest';

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

  @override
  void initState() {
    super.initState();
    // The first manifest did not arrive; it was there when the screen was.
    _drawn.addAll(widget.entries.map((ManifestEntry e) => e.digest));
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final List<ManifestEntry> entries = widget.entries;
    final bool hadCards = _drawn.isNotEmpty;
    final Set<String> arriving = <String>{
      for (final ManifestEntry entry in entries)
        if (hadCards && !_drawn.contains(entry.digest)) entry.digest,
    };
    _drawn.addAll(entries.map((ManifestEntry e) => e.digest));

    final List<Widget> children = <Widget>[
      _ManifestHeader(
        entries: entries,
        busy: widget.busy,
        stopping: widget.stopping,
        onStop: widget.onStop,
      ),
      SizedBox(height: ui.space.s4),
      if (entries.isEmpty)
        EmptyState(
          icon: UiIcons.intake.defaultGlyph,
          title: IntakeManifest.emptyTitle,
          body: IntakeManifest.emptyBody,
        ),
      for (final ManifestEntry entry in entries)
        Padding(
          key: ValueKey<String>('manifest-slot-${entry.digest}'),
          padding: EdgeInsetsDirectional.only(bottom: ui.space.s4),
          // Fade and size, never a slide: the card did not come from
          // anywhere, the operator made it (motion catalog, row 62).
          child: _ArrivingCard(
            arriving: arriving.contains(entry.digest),
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
    ];
    final EdgeInsetsGeometry padding =
        widget.padding ?? EdgeInsetsDirectional.all(ui.space.s6);
    return widget.scrollable
        ? ListView(padding: padding, children: children)
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
    final String summary = batchComplete(entries) && !busy
        ? batchCompleteLine(entries)
        : batchProgressLine(entries);
    return Padding(
      padding: EdgeInsetsDirectional.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          // One account of the batch, visually and in announcements.
          Semantics(
            container: true,
            liveRegion: true,
            child: Text(
              summary,
              style: ui.type.body.copyWith(color: ui.color.inkSecondary),
            ),
          ),
          if (busy) ...<Widget>[
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

/// One manifest card, revealed on the frame it is added and static after
/// that (motion catalog, row 62).
class _ArrivingCard extends StatefulWidget {
  const _ArrivingCard({required this.arriving, required this.child});

  final bool arriving;
  final Widget child;

  @override
  State<_ArrivingCard> createState() => _ArrivingCardState();
}

class _ArrivingCardState extends State<_ArrivingCard> {
  late bool _revealed = !widget.arriving;

  @override
  void initState() {
    super.initState();
    if (_revealed) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) setState(() => _revealed = true);
    });
  }

  @override
  Widget build(BuildContext context) =>
      MotionReveal(visible: _revealed, child: widget.child);
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

  /// States whose reason is a failure a screen reader should hear at once.
  static bool announces(UploadState state) =>
      state == UploadState.failed ||
      state == UploadState.interrupted ||
      state == UploadState.skipped;

  /// What the server check control is called.
  static const String serverCheckLabel = 'Send for server check';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    // A determinate value is information, so it keeps its motion and its
    // linear curve under reduced motion (motion, rows 65 and 2.5).
    final Widget item = TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: entry.progress, end: entry.progress),
      duration: ui.motion.meaningful(MotionTokens.standardRaw),
      curve: MotionTokens.progressCurve,
      builder: (BuildContext context, double value, Widget? _) => UploadItem(
        name: entry.label,
        concise: true,
        state: entry.displayState,
        thumbnail: entry.file?.bytes,
        sizeBytes: entry.file?.bytes.length,
        pixelWidth: entry.file?.width,
        pixelHeight: entry.file?.height,
        progress: value,
        reason: entry.why == null ? entry.reason : null,
        onRemove: entry.removable ? onRemove : null,
        removeBlockedReason: entry.removable
            ? null
            : 'The server has taken this file, so it cannot be removed from '
                  'the batch.',
        // The per-row action and the per-row evidence live inside the
        // component rather than in a column around it, so a manifest row is
        // one thing a reviewer learns once.
        details: _details(context, ui),
      ),
    );

    return Padding(
      padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const UiHairline(),
          SizedBox(height: ui.space.s2),
          Semantics(liveRegion: announces(entry.state), child: item),
          if ((entry.state == UploadState.failed ||
                  entry.state == UploadState.interrupted) &&
              entry.file != null &&
              onRetry != null)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiButton(
                label: 'Retry this file',
                variant: UiButtonVariant.secondary,
                onPressed: busy ? null : onRetry,
              ),
            ),
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
