/// Device-appropriate ways to add specimen photographs to intake.
library;

import 'package:desktop_drop/desktop_drop.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The screen's own name.
const String intakeTitle = 'Intake';

/// What the screen is for, including the possible next step after admission.
const String intakePurpose = 'One photo per specimen.';

const String cameraSendImmediatelyLabel = 'Send now';
const String cameraReviewFirst = 'Review';
const String cameraSendImmediatelyBody =
    'Camera photos skip review and send as soon as you take them.';
const String _sourceBusyMessage = 'Camera or photo picker is already open.';

/// The capture surface adapts its source choices to the current platform.
class IntakeCaptureCard extends StatefulWidget {
  const IntakeCaptureCard({
    super.key,
    required this.web,
    required this.onChooseFiles,
    required this.onTakePhotograph,
    required this.onDropFiles,
    required this.cameraAvailable,
    this.autoIngest = false,
    this.onAutoIngestChanged,
    this.onBrowseSources,
    this.onImportFromLink,
    this.minDropHeight = 0,
    this.dragActive = false,
    this.hasPhotos = false,
  });

  /// Whether this is the browser client.
  final bool web;

  /// Opens the system file picker. Null while a picker is already open.
  final VoidCallback? onChooseFiles;

  /// Opens capture. On mobile web this uses the browser camera picker.
  final VoidCallback? onTakePhotograph;

  /// Adds operating-system files dropped onto the web surface.
  final ValueChanged<List<XFile>>? onDropFiles;

  /// Whether the native app can offer camera capture.
  final bool cameraAvailable;

  /// Whether taking a photograph skips review and enters Intake immediately.
  final bool autoIngest;

  /// Changes and persists the camera-only submission preference.
  final ValueChanged<bool>? onAutoIngestChanged;

  /// Opens registered storage, alongside the local file choices.
  final VoidCallback? onBrowseSources;

  final VoidCallback? onImportFromLink;

  /// The available content height allocated to the web drop surface.
  final double minDropHeight;

  /// True while the page-level drop target is receiving a drag.
  final bool dragActive;

  final bool hasPhotos;

  static const String title = intakeTitle;
  static const String dropTitle = 'Drop photos anywhere';
  static const String dropActive = 'Release to add photos';
  static const String cameraTitle = 'Camera';
  static const String bulkTitle = 'Files';

  @override
  State<IntakeCaptureCard> createState() => _IntakeCaptureCardState();
}

class _IntakeCaptureCardState extends State<IntakeCaptureCard> {
  bool _dragging = false;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Widget files = Surface(
      radius: ui.shape.inner,
      hairline: true,
      role: SurfaceRole.ground,
      padding: EdgeInsetsDirectional.all(ui.space.s4),
      child: ConstrainedBox(
        constraints: BoxConstraints(minHeight: widget.minDropHeight),
        child: _fileContent(context),
      ),
    );
    final Widget bulk = !widget.web || widget.onDropFiles == null
        ? files
        : DropTarget(
            key: const ValueKey<String>('intake-file-drop-target'),
            enable: widget.onDropFiles != null,
            onDragEntered: (_) => setState(() => _dragging = true),
            onDragExited: (_) => setState(() => _dragging = false),
            onDragDone: (DropDoneDetails details) {
              setState(() => _dragging = false);
              widget.onDropFiles?.call(
                details.files.whereType<DropItemFile>().cast<XFile>().toList(),
              );
            },
            child: files,
          );
    return bulk;
  }

  Widget _fileContent(BuildContext context) {
    final UiThemeData ui = context.ui;
    final bool dragging = widget.dragActive || _dragging;
    return Semantics(
      container: true,
      label: dragging ? IntakeCaptureCard.dropActive : null,
      liveRegion: dragging,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          if (widget.web && dragging) ...<Widget>[
            Text(
              IntakeCaptureCard.dropActive,
              style: ui.type.body.copyWith(color: ui.color.ink),
            ),
            SizedBox(height: ui.space.s2),
          ],
          _actions(context),
          if (widget.cameraAvailable) ...[
            SizedBox(height: ui.space.s2),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiSegmented<bool>(
                key: const ValueKey<String>('intake-auto-ingest'),
                segments: const <UiSegment<bool>>[
                  UiSegment(value: false, label: cameraReviewFirst),
                  UiSegment(value: true, label: cameraSendImmediatelyLabel),
                ],
                value: widget.autoIngest,
                onChanged: widget.onAutoIngestChanged,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _actions(BuildContext context) => Wrap(
    spacing: context.ui.space.s2,
    runSpacing: context.ui.space.s2,
    children: [
      if (widget.cameraAvailable)
        UiButton(
          key: const ValueKey<String>('intake-take-photograph'),
          label: 'Take photos',
          leading: UiIcons.camera,
          variant: widget.web
              ? UiButtonVariant.secondary
              : UiButtonVariant.primary,
          onPressed: widget.onTakePhotograph,
          disabledReason: widget.onTakePhotograph == null
              ? _sourceBusyMessage
              : null,
        ),
      // Keep the overflow source beside Choose files when they fit. At larger
      // text sizes the pair stacks without clipping either label.
      OverflowBar(
        spacing: context.ui.space.s2,
        overflowSpacing: context.ui.space.s2,
        children: [
          UiButton(
            key: const ValueKey<String>('intake-choose-files'),
            label: 'Choose files',
            leading: UiIcons.uploadFile,
            variant: widget.cameraAvailable && !widget.web
                ? UiButtonVariant.secondary
                : UiButtonVariant.primary,
            onPressed: widget.onChooseFiles,
            disabledReason: widget.onChooseFiles == null
                ? _sourceBusyMessage
                : null,
          ),
          if (widget.onImportFromLink != null || widget.onBrowseSources != null)
            UiMenuTrigger(
              key: const ValueKey<String>('intake-more'),
              label: 'More',
              semanticsLabel: 'More photo sources',
              items: <UiMenuItem>[
                if (widget.onImportFromLink != null)
                  UiMenuItem(
                    label: 'Import from link',
                    icon: UiIcons.sourceImport,
                    onSelected: widget.onImportFromLink,
                  ),
                if (widget.onBrowseSources != null)
                  UiMenuItem(
                    label: 'Add from storage',
                    icon: UiIcons.sources,
                    onSelected: widget.onBrowseSources,
                  ),
              ],
            ),
        ],
      ),
    ],
  );
}

/// The action names the processing handoff rather than its transport detail.
String intakeUploadLabel({required bool uploading, required int pending}) {
  if (uploading) return 'Sending';
  if (pending == 1) return 'Send 1 photo';
  return 'Send $pending photos';
}
