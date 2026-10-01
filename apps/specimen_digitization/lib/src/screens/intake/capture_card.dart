/// Device-appropriate ways to add specimen photographs to intake.
library;

import 'package:desktop_drop/desktop_drop.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The screen's own name.
const String intakeTitle = 'Add specimens';

/// What the screen is for, including the possible next step after admission.
const String intakePurpose =
    'Add one photograph per specimen. Eligible uploads may queue for processing.';

/// The capture surface adapts its source choices to the current platform.
class IntakeCaptureCard extends StatefulWidget {
  const IntakeCaptureCard({
    super.key,
    required this.web,
    required this.onChooseFiles,
    required this.onTakePhotograph,
    required this.onDropFiles,
    required this.cameraAvailable,
    this.onBrowseSources,
    this.minDropHeight = 0,
    this.dragActive = false,
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

  /// Opens registered storage, alongside the local file choices.
  final VoidCallback? onBrowseSources;

  /// The available content height allocated to the web drop surface.
  final double minDropHeight;

  /// True while the page-level drop target is receiving a drag.
  final bool dragActive;

  static const String title = intakeTitle;
  static const String dropTitle = 'Drop specimen photos anywhere';
  static const String dropActive = 'Release to add specimen photos';
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (widget.cameraAvailable) ...<Widget>[
          Surface(
            radius: ui.shape.inner,
            hairline: true,
            role: SurfaceRole.ground,
            padding: EdgeInsetsDirectional.all(ui.space.s4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(IntakeCaptureCard.cameraTitle, style: ui.type.label),
                SizedBox(height: ui.space.s2),
                UiButton(
                  key: const ValueKey<String>('intake-take-photograph'),
                  label: 'Take photos',
                  leading: UiIcons.camera,
                  onPressed: widget.onTakePhotograph,
                ),
              ],
            ),
          ),
          SizedBox(height: ui.space.s2),
        ],
        bulk,
      ],
    );
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
          if (!widget.web) ...<Widget>[
            Text(IntakeCaptureCard.bulkTitle, style: ui.type.label),
            SizedBox(height: ui.space.s2),
          ],
          if (widget.web) ...<Widget>[
            Text(
              dragging
                  ? IntakeCaptureCard.dropActive
                  : IntakeCaptureCard.dropTitle,
              style: ui.type.body.copyWith(color: ui.color.ink),
            ),
            SizedBox(height: ui.space.s2),
          ],
          _actions(context),
        ],
      ),
    );
  }

  Widget _actions(BuildContext context) => Wrap(
    spacing: context.ui.space.s2,
    runSpacing: context.ui.space.s2,
    children: [
      UiButton(
        key: const ValueKey<String>('intake-choose-files'),
        label: 'Choose files',
        leading: UiIcons.uploadFile,
        onPressed: widget.onChooseFiles,
        disabledReason: widget.onChooseFiles == null
            ? 'The file picker is already open.'
            : null,
      ),
      if (widget.onBrowseSources != null)
        UiButton(
          label: 'Add from storage',
          variant: UiButtonVariant.secondary,
          leading: UiIcons.sources,
          onPressed: widget.onBrowseSources,
        ),
    ],
  );
}

/// The upload button names the count it will admit.
String intakeUploadLabel({required bool uploading, required int pending}) {
  if (uploading) return 'Uploading';
  if (pending == 1) return 'Upload 1 photograph';
  return 'Upload $pending photographs';
}
