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
import '../../models.dart';
import '../../review_context.dart';
import '../../theme/icons.dart';
import '../../theme/motion.dart';
import '../../vocabulary.dart';
import '../../widgets/caveat_text.dart';
import '../../widgets/upload_item.dart';
import 'manifest_entry.dart';

/// The manifest header and its rows.
class IntakeManifest extends StatelessWidget {
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
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return ListView(
      padding: padding ?? EdgeInsets.all(context.space.space6),
      shrinkWrap: nested,
      primary: nested ? false : null,
      physics: nested ? const NeverScrollableScrollPhysics() : null,
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
            if (busy)
              OutlinedButton.icon(
                key: const ValueKey<String>('intake-stop'),
                onPressed: stopping ? null : onStop,
                icon: const Icon(Symbols.stop_circle),
                label: Text(stopping ? 'Stopping' : 'Stop'),
                style: OutlinedButton.styleFrom(
                  minimumSize: Size(
                    context.sizes.targetMin,
                    context.sizes.targetMin,
                  ),
                ),
              ),
          ],
        ),
        if (stopping) ...<Widget>[
          SizedBox(height: context.space.space2),
          Semantics(
            liveRegion: true,
            child: Text(
              'Stopping. The file already sending finishes first.',
              style: theme.textTheme.bodySmall,
            ),
          ),
        ],
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
            padding: EdgeInsets.only(bottom: context.space.space4),
            child: IntakeManifestRow(
              key: ValueKey<String>(entry.digest),
              entry: entry,
              busy: busy,
              onRemove: () => onRemove(entry),
              onServerCheck: () => onServerCheck(entry),
            ),
          ),
      ],
    );
  }
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
    final Json? preflight = entry.preflight;
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
            if (entry.file != null) ...<Widget>[
              SizedBox(height: context.space.space3),
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
                  label: Text(
                    entry.checking ? 'Checking' : 'Send for server check',
                  ),
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
                        'The server check is not available. Ask the service '
                        'administrator to enable memory-limit enforcement.',
                    why:
                        'Changing the image format will not help. Ordinary '
                        'image intake is checked separately and is '
                        'unaffected.',
                  ),
                Text(
                  'Server check: '
                  '${vocabularyLabel(textOf(preflight['status']))}. '
                  'Check quality yourself as well.',
                ),
                for (final dynamic issue
                    in preflight['issues'] as List<dynamic>? ??
                        const <dynamic>[])
                  Text(vocabularyLabel(issue.toString())),
                Text(
                  'Not measured: ${preflight['unmeasured'] ?? 'Not recorded'}',
                ),
                EvidenceDetails(
                  title: 'Server codec support and check evidence',
                  value: preflight,
                ),
              ],
            ],
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
}
