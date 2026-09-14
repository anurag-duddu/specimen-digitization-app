/// The upload manifest (screen blueprints, section 5).
///
/// Every file the operator chose is a row, including the ones this client
/// refused, so the manifest is the complete account PRD 9.1.5 asks for. A
/// rejection is a Skipped row carrying its own reason (heuristics audit, H1.6
/// and H9.4), not a banner somewhere else on the screen.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../capture_quality.dart';
import '../../administrator_contact.dart';
import '../../models.dart';
import '../../review_context.dart';
import '../../theme/icons.dart';
import '../../theme/motion.dart';
import '../../vocabulary.dart';
import '../../widgets/caveat_text.dart';
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
    this.padding,
    this.nested = false,
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

  /// Outer padding, so the compact and two column layouts can differ.
  final EdgeInsetsGeometry? padding;

  /// True when the manifest sits inside another scrollable, which is the
  /// compact layout. It then shrink wraps and leaves scrolling to its parent.
  final bool nested;

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
    final ThemeData theme = Theme.of(context);
    final List<ManifestEntry> entries = widget.entries;
    final bool hadCards = _drawn.isNotEmpty;
    final Set<String> arriving = <String>{
      for (final ManifestEntry entry in entries)
        if (hadCards && !_drawn.contains(entry.digest)) entry.digest,
    };
    _drawn.addAll(entries.map((ManifestEntry e) => e.digest));

    return ListView(
      padding: widget.padding ?? EdgeInsets.all(context.space.space6),
      shrinkWrap: widget.nested,
      primary: widget.nested ? false : null,
      physics: widget.nested ? const NeverScrollableScrollPhysics() : null,
      children: <Widget>[
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text('Upload manifest', style: theme.textTheme.titleLarge),
                  SizedBox(height: context.space.space1),
                  Semantics(
                    liveRegion: true,
                    child: Text(
                      batchProgressLine(entries),
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            if (widget.busy)
              OutlinedButton.icon(
                key: const ValueKey<String>('intake-stop'),
                onPressed: widget.stopping ? null : widget.onStop,
                icon: const Icon(Symbols.stop_circle),
                label: Text(widget.stopping ? 'Stopping' : 'Stop'),
                style: OutlinedButton.styleFrom(
                  minimumSize: Size(
                    context.sizes.targetMin,
                    context.sizes.targetMin,
                  ),
                ),
              ),
          ],
        ),
        // The one summary line the whole batch earns, arriving with height
        // and opacity beside the one light impact (motion catalog, row 67).
        MotionReveal(
          visible: batchComplete(entries) && !widget.busy,
          child: Padding(
            padding: EdgeInsets.only(top: context.space.space2),
            child: Semantics(
              liveRegion: true,
              child: Row(
                children: <Widget>[
                  Icon(
                    Symbols.check_circle,
                    size: context.sizes.iconInline,
                    color: context.tokens.clearedContent,
                  ),
                  SizedBox(width: context.space.space2),
                  Flexible(
                    child: Text(
                      batchCompleteLine(entries),
                      style: theme.textTheme.bodyMedium,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        MotionReveal(
          visible: widget.stopping,
          child: Padding(
            padding: EdgeInsets.only(top: context.space.space2),
            child: Semantics(
              liveRegion: true,
              child: Text(
                'Stopping. The file already sending finishes first.',
                style: theme.textTheme.bodySmall,
              ),
            ),
          ),
        ),
        SizedBox(height: context.space.space3),
        const CaveatText(
          label: 'After a restart, select the same files again to resume.',
          why:
              'Checksums match your files to the uploads already on the '
              'server. Records that were accepted are not created twice.',
        ),
        SizedBox(height: context.space.space4),
        if (entries.isEmpty)
          Padding(
            padding: EdgeInsets.symmetric(vertical: context.space.space8),
            child: Text(
              'Nothing here yet. Photographs appear as you add them.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        for (final ManifestEntry entry in entries)
          Padding(
            key: ValueKey<String>('manifest-slot-${entry.digest}'),
            padding: EdgeInsets.only(bottom: context.space.space4),
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
              ),
            ),
          ),
      ],
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

/// One manifest row: the shared `UploadItem`, the local measurements, and the
/// server check that reports into this same row.
class IntakeManifestRow extends StatelessWidget {
  const IntakeManifestRow({
    super.key,
    required this.entry,
    required this.busy,
    required this.onRemove,
    required this.onServerCheck,
  });

  /// The row's data.
  final ManifestEntry entry;

  /// True while a batch is in flight anywhere on the screen.
  final bool busy;

  /// Takes this row out of the batch.
  final VoidCallback onRemove;

  /// Asks the server to try decoding this file.
  final VoidCallback onServerCheck;

  /// States whose reason is a failure a screen reader should hear at once.
  static bool announces(UploadState state) =>
      state == UploadState.failed ||
      state == UploadState.interrupted ||
      state == UploadState.skipped;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final MotionTokens motion = MotionTokens.of(context);
    // A determinate value is information, so it keeps its motion and its
    // linear curve under reduced motion (motion, rows 65 and 2.5).
    final Widget item = TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: entry.progress, end: entry.progress),
      duration: motion.meaningful(MotionTokens.standardRaw),
      curve: MotionTokens.progressCurve,
      builder: (BuildContext context, double value, Widget? _) => UploadItem(
        name: entry.label,
        state: entry.displayState,
        thumbnail: entry.file?.bytes,
        sizeBytes: entry.file?.bytes.length,
        pixelWidth: entry.file?.width,
        pixelHeight: entry.file?.height,
        progress: value,
        reason: entry.why == null ? entry.reason : null,
        onRemove: entry.removable && !busy ? onRemove : null,
        removeBlockedReason: entry.removable
            ? null
            : 'The server has taken this file, so it cannot be removed from '
                  'the batch.',
        // The per-row action and the per-row evidence live inside the
        // component rather than in a column around it, so a manifest row is
        // one thing a reviewer learns once.
        details: _details(context, theme),
      ),
    );

    return Card(
      child: Padding(
        padding: EdgeInsets.all(context.space.space4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Semantics(liveRegion: announces(entry.state), child: item),
            if (entry.why != null)
              CaveatText(label: entry.reason ?? '', why: entry.why!),
            Text(
              entry.session != null
                  ? 'Existing upload, classification unchanged'
                  : entry.file?.sensitive == false
                  ? 'Not sensitive'
                  : 'Sensitive',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            SizedBox(height: context.space.space2),
            SelectableText(
              'Checksum (SHA-256) ${entry.digest}',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// The local measurements, the server check result, and the two caveats
  /// that keep either from reading as a verdict. Rendered inside the
  /// component through its `details` slot.
  Widget? _details(BuildContext context, ThemeData theme) {
    if (entry.file == null) return null;
    final Json? preflight = entry.preflight;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        CaptureQualitySummary(quality: entry.quality),
        SizedBox(height: context.space.space3),
        const CaveatText(
          label: 'Focus, glare and label coverage are not measured.',
          why:
              'These three values describe exposure and detail in a '
              'thumbnail. Compare the photograph with the specimen '
              'yourself before you confirm this batch.',
        ),
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            onPressed: entry.checking || busy ? null : onServerCheck,
            icon: const Icon(Symbols.cloud_sync),
            label: Text(entry.checking ? 'Checking' : 'Send for server check'),
            style: OutlinedButton.styleFrom(
              minimumSize: Size(
                context.sizes.targetMin,
                context.sizes.targetMin,
              ),
            ),
          ),
        ),
        const CaveatText(
          label: 'The server check creates nothing.',
          why:
              'Nothing is created and no outside service is called. '
              'Your local measurements stay on this device until you '
              'choose an action.',
        ),
        if (entry.preflightError != null)
          Semantics(
            liveRegion: true,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(
                  Symbols.error,
                  size: context.sizes.iconInline,
                  color: theme.colorScheme.error,
                ),
                SizedBox(width: context.space.space2),
                Expanded(
                  child: Text(
                    entry.preflightError!,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.error,
                    ),
                  ),
                ),
              ],
            ),
          ),
        if (preflight != null) ...<Widget>[
          if (objectOf(preflight['decode'])['reason'] ==
              'memory_limit_unavailable')
            const CaveatText(
              label:
                  'The server check is not available. Memory-limit '
                  'enforcement has to be turned on for this collection.',
              why:
                  'Changing the image format will not help. Ordinary '
                  'image intake is checked separately and is '
                  'unaffected.',
            ),
          if (objectOf(preflight['decode'])['reason'] ==
              'memory_limit_unavailable')
            const AdministratorContactLine(),
          Text(
            'Server check: '
            '${vocabularyLabel(textOf(preflight['status']))}. '
            'Check quality yourself as well.',
          ),
          for (final dynamic issue
              in preflight['issues'] as List<dynamic>? ?? const <dynamic>[])
            Text(vocabularyLabel(issue.toString())),
          Text('Not measured: ${preflight['unmeasured'] ?? 'Not recorded'}'),
          EvidenceDrawer(
            title: 'Server codec support and check evidence',
            payload: preflight,
          ),
        ],
      ],
    );
  }
}
