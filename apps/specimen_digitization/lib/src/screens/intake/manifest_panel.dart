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

    return ListView(
      padding: widget.padding ?? EdgeInsetsDirectional.all(ui.space.s6),
      shrinkWrap: widget.nested,
      primary: widget.nested ? false : null,
      physics: widget.nested ? const NeverScrollableScrollPhysics() : null,
      children: <Widget>[
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
              ),
            ),
          ),
      ],
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

  int _count(UploadState state) =>
      entries.where((ManifestEntry e) => e.state == state).length;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Surface(
      radius: ui.shape.tile,
      padding: EdgeInsetsDirectional.all(ui.space.s6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Semantics(
            header: true,
            child: Text(
              IntakeManifest.title,
              style: ui.type.titleLarge.copyWith(color: ui.color.ink),
            ),
          ),
          SizedBox(height: ui.space.s4),
          // One node for the whole account: the three numerals are the
          // headline and the sentence under them names every outcome the
          // batch reached, including the ones with no tile of their own. A
          // reader hears "8 of 12 accepted, 1 skipped" once when it changes
          // rather than three tiles and then the sentence again.
          Semantics(
            container: true,
            liveRegion: true,
            label: batchProgressLine(entries),
            excludeSemantics: true,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                // A batch with nothing in it has nothing to count, and three
                // zeroes over a sentence that says the same is the interface
                // stating an absence three times.
                if (entries.isNotEmpty) ...<Widget>[
                  Wrap(
                    spacing: ui.space.s6,
                    runSpacing: ui.space.s4,
                    children: <Widget>[
                      _CountTile(
                        label: 'Accepted',
                        value: _count(UploadState.accepted),
                        footer: 'of ${entries.length}',
                      ),
                      _CountTile(
                        label: 'Already in collection',
                        value: _count(UploadState.duplicate),
                      ),
                      _CountTile(
                        label: 'Failed',
                        value: _count(UploadState.failed),
                      ),
                    ],
                  ),
                  SizedBox(height: ui.space.s2),
                ],
                Text(
                  batchProgressLine(entries),
                  style: ui.type.body.copyWith(color: ui.color.inkSecondary),
                ),
              ],
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
          // The one summary line the whole batch earns, arriving with height
          // and opacity beside the one light impact (motion catalog, row 67).
          MotionReveal(
            visible: batchComplete(entries) && !busy,
            child: Padding(
              padding: EdgeInsetsDirectional.only(top: ui.space.s4),
              child: Semantics(
                container: true,
                liveRegion: true,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    UiIcon(
                      UiIcons.cleared,
                      size: UiIconSize.inline,
                      color: ui.color.status.cleared.content,
                    ),
                    SizedBox(width: ui.space.s2),
                    Flexible(
                      child: Text(
                        batchCompleteLine(entries),
                        style: ui.type.body.copyWith(color: ui.color.ink),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          SizedBox(height: ui.space.s3),
          const CaveatText(
            label: 'After a restart, select the same files again to resume.',
            why:
                'Checksums match your files to the uploads already on the '
                'server. Records that were accepted are not created twice.',
          ),
        ],
      ),
    );
  }
}

/// One counted outcome in the manifest header.
///
// fe/polish-2: `UiDataTile` is the control this draws, and it cannot be used
// here: it is a `GlassSurface`, which asserts in debug when it is built inside
// a scrolling list, and three of them plus the shell's bar and navigation
// would break the four pane budget of 09 section 3.3. The package needs a
// tile that draws on a `Surface`, or a `UiTileGroup` that is one pane holding
// several numerals.
class _CountTile extends StatelessWidget {
  const _CountTile({required this.label, required this.value, this.footer});

  final String label;
  final int value;
  final String? footer;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String? under = footer;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          label,
          style: ui.type.label.copyWith(color: ui.color.inkSecondary),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        Text(
          '$value',
          style: ui.type.displayMedium.copyWith(color: ui.color.ink),
        ),
        if (under != null)
          Text(
            under,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkTertiary),
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
        details: _details(context, ui),
      ),
    );

    return Surface(
      radius: ui.shape.tile,
      padding: EdgeInsetsDirectional.all(ui.space.s4),
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
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
          SizedBox(height: ui.space.s2),
          _ChecksumLine(digest: entry.digest),
        ],
      ),
    );
  }

  /// The local measurements, the server check result, and the two caveats
  /// that keep either from reading as a verdict. Rendered inside the
  /// component through its `details` slot.
  Widget? _details(BuildContext context, UiThemeData ui) {
    if (entry.file == null) return null;
    final Json? preflight = entry.preflight;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        CaptureQualitySummary(quality: entry.quality),
        SizedBox(height: ui.space.s3),
        const CaveatText(
          label: 'Focus, glare and label coverage are not measured.',
          why:
              'These three values describe exposure and detail in a '
              'thumbnail. Compare the photograph with the specimen '
              'yourself before you confirm this batch.',
        ),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: UiButton(
            label: entry.checking ? 'Checking' : serverCheckLabel,
            variant: UiButtonVariant.secondary,
            leading: UiIcons.sourceImport,
            onPressed: entry.checking || busy ? null : onServerCheck,
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
            '${vocabularyLabel(textOf(preflight['status']))}. '
            'Check quality yourself as well.',
            style: ui.type.body.copyWith(color: ui.color.ink),
          ),
          for (final dynamic issue
              in preflight['issues'] as List<dynamic>? ?? const <dynamic>[])
            Text(
              vocabularyLabel(issue.toString()),
              style: ui.type.body.copyWith(color: ui.color.ink),
            ),
          Text(
            'Not measured: ${preflight['unmeasured'] ?? 'Not recorded'}',
            style: ui.type.body.copyWith(color: ui.color.ink),
          ),
          EvidenceDrawer(
            title: 'Server codec support and check evidence',
            payload: preflight,
          ),
        ],
      ],
    );
  }
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
