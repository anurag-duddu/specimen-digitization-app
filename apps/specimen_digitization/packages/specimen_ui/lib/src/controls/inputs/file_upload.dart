/// File selection and transfer presentation; ingestion belongs to the host.
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../actions/button.dart';
import '../actions/icon_button.dart';
import '../data/progress.dart';
import 'field.dart';

/// Presentation of reported transfer progress.
enum UiFileUploadProgressStyle {
  /// A separate linear progress indicator beneath the file details.
  bar,

  /// A fraction of the row's background, with a readable percentage.
  fill,
}

/// The state reported by the application for one selected file.
enum UiFileUploadStatus {
  /// Selected but not yet transferring.
  queued,

  /// Transfer is in progress.
  uploading,

  /// Transfer completed; this does not imply domain processing completed.
  complete,

  /// The application reports a failure.
  error,
}

/// Immutable presentation data; never contains file bytes or a filesystem path.
@immutable
class UiUploadFile {
  /// One file with a stable identity and caller-provided status text.
  const UiUploadFile({
    required this.id,
    required this.name,
    required this.statusLabel,
    this.status = UiFileUploadStatus.queued,
    this.detail,
    this.progress,
    this.errorText,
    this.attempt = 0,
    this.leading,
  }) : assert(progress == null || (progress >= 0 && progress <= 1));

  /// Stable unique identity for callbacks and rendering.
  final String id;

  /// Display filename, including extension.
  final String name;

  /// Human-readable, localized status: for example “Uploading · 40%”.
  final String statusLabel;

  /// Current reported state.
  final UiFileUploadStatus status;

  /// Optional size, file type or other supporting information.
  final String? detail;

  /// Reported transfer fraction, or null for indeterminate progress.
  final double? progress;

  /// Actionable failure detail, displayed only in the error state.
  final String? errorText;

  /// Increment for each retry so progress may restart from zero.
  final int attempt;

  /// Decorative file-type identity; must not contain interactive controls.
  final Widget? leading;
}

/// A controlled chooser/drop surface with transfer rows and recovery actions.
///
/// [onChooseFiles] asks the host to open its picker. [dropTargetBuilder] wraps
/// the selection surface in the host's native/web drop adapter. That adapter
/// owns MIME/size validation, accepted files, permissions and actual transfer.
/// Set [dragActive] only for files the adapter accepts, and supply [dropLabel]
/// only when a working drop adapter is present. This widget never reads files,
/// sends data, starts uploads or invents progress.
class UiFileUpload extends StatelessWidget {
  /// Builds a controlled file selection area and a list of reported files.
  const UiFileUpload({
    super.key,
    required this.label,
    required this.files,
    this.onChooseFiles,
    this.onRemove,
    this.onRetry,
    this.chooseLabel = 'Choose files',
    this.dropLabel,
    this.helpText,
    this.errorText,
    this.disabledReason,
    this.enabled = true,
    this.isChoosing = false,
    this.dragActive = false,
    this.dropTargetBuilder,
    this.removeLabelBuilder,
    this.retryLabelBuilder,
    this.progressStyle = UiFileUploadProgressStyle.bar,
  }) : assert(!dragActive || dropTargetBuilder != null),
       assert(dropLabel == null || dropTargetBuilder != null);

  /// Transfer indicator anatomy; both variants use caller-reported progress.
  final UiFileUploadProgressStyle progressStyle;

  /// Name of the file collection.
  final String label;

  /// Host-owned transfer state. File IDs must be unique.
  final List<UiUploadFile> files;

  /// Opens the host's file picker; null disables choosing.
  final VoidCallback? onChooseFiles;

  /// Requests removal. The host decides whether to cancel an active transfer.
  final ValueChanged<UiUploadFile>? onRemove;

  /// Requests another attempt for a failed file.
  final ValueChanged<UiUploadFile>? onRetry;

  /// Visible chooser command.
  final String chooseLabel;

  /// Drop instructions, only when [dropTargetBuilder] supplies real support.
  final String? dropLabel;

  /// Accepted formats, limits or supporting instructions supplied by the host.
  final String? helpText;

  /// Collection-level validation failure.
  final String? errorText;

  /// Explains why editing is disabled.
  final String? disabledReason;

  /// False disables choosing, removing and retrying.
  final bool enabled;

  /// While true, prevents opening a second chooser.
  final bool isChoosing;

  /// Whether the host currently hovers an accepted drag over the target.
  final bool dragActive;

  /// Native/web adapter around the chooser surface. Must honor [enabled].
  final Widget Function(BuildContext context, Widget child)? dropTargetBuilder;

  /// Localized accessible remove command for one file.
  final String Function(UiUploadFile file)? removeLabelBuilder;

  /// Localized accessible retry command for one file.
  final String Function(UiUploadFile file)? retryLabelBuilder;

  @override
  Widget build(BuildContext context) {
    assert(
      files.map((UiUploadFile file) => file.id).toSet().length == files.length,
      'Upload file IDs must be unique.',
    );
    final UiThemeData ui = context.ui;
    final bool dragging = enabled && dragActive;
    Widget target = Container(
      width: double.infinity,
      padding: EdgeInsets.all(ui.space.s4),
      decoration: BoxDecoration(
        color: dragging ? ui.color.status.processing.fill : ui.color.paper,
        borderRadius: BorderRadius.circular(ui.shape.tile),
        border: Border.all(
          color: errorText != null
              ? ui.color.status.blocked.content
              : dragging
              ? ui.color.accent
              : ui.color.boundary,
          width: dragging ? ui.shape.stroke.emphasis : ui.shape.stroke.hairline,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          UiIcon(
            UiIcons.uploadFile,
            color: enabled ? ui.color.inkSecondary : ui.color.disabledContent,
          ),
          SizedBox(height: ui.space.s2),
          UiButton(
            label: chooseLabel,
            variant: UiButtonVariant.secondary,
            loading: isChoosing,
            onPressed: enabled && !isChoosing ? onChooseFiles : null,
            disabledReason: disabledReason,
          ),
          if (dropLabel != null)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s2),
              child: Text(
                dropLabel!,
                textAlign: TextAlign.center,
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
            ),
        ],
      ),
    );
    if (dropTargetBuilder != null) target = dropTargetBuilder!(context, target);
    return UiFieldFrame(
      style: UiInputStyle.resolve(ui, UiFieldShape.box),
      states: <WidgetState>{
        if (!enabled) WidgetState.disabled,
        if (errorText != null) WidgetState.error,
      },
      label: label,
      message: errorText ?? disabledReason ?? helpText,
      isError: errorText != null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          target,
          for (final UiUploadFile file in files)
            Padding(
              key: ValueKey<String>(file.id),
              padding: EdgeInsets.only(top: ui.space.s2),
              child: _row(context, file),
            ),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, UiUploadFile file) {
    final UiThemeData ui = context.ui;
    final bool failed = file.status == UiFileUploadStatus.error;
    final fillProgress =
        progressStyle == UiFileUploadProgressStyle.fill &&
        file.status == UiFileUploadStatus.uploading &&
        file.progress != null;
    return Container(
      padding: EdgeInsets.all(ui.space.s3),
      decoration: BoxDecoration(
        color: ui.color.paper,
        gradient: !fillProgress
            ? null
            : LinearGradient(
                begin: Directionality.of(context) == TextDirection.rtl
                    ? Alignment.centerRight
                    : Alignment.centerLeft,
                end: Directionality.of(context) == TextDirection.rtl
                    ? Alignment.centerLeft
                    : Alignment.centerRight,
                colors: [
                  ui.brand.secondary.fill,
                  ui.brand.secondary.fill,
                  ui.color.paper,
                  ui.color.paper,
                ],
                stops: [0, file.progress!, file.progress!, 1],
              ),
        borderRadius: BorderRadius.circular(ui.shape.inner),
        border: Border.all(
          color: failed ? ui.color.status.blocked.content : ui.color.hairline,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Padding(
                padding: EdgeInsetsDirectional.only(
                  end: ui.space.s2,
                  top: ui.space.s1,
                ),
                child: file.leading == null
                    ? UiIcon(
                        failed
                            ? UiIcons.error
                            : file.status == UiFileUploadStatus.complete
                            ? UiIcons.check
                            : UiIcons.record,
                        color: failed
                            ? ui.color.status.blocked.content
                            : ui.color.inkSecondary,
                      )
                    : ExcludeSemantics(child: file.leading!),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text(file.name, style: ui.type.label),
                    if (file.detail != null)
                      Text(
                        file.detail!,
                        style: ui.type.bodySmall.copyWith(
                          color: ui.color.inkSecondary,
                        ),
                      ),
                    if (fillProgress)
                      Text(
                        '${(file.progress! * 100).round()}%',
                        style: ui.type.labelSmall,
                      ),
                    Text(
                      file.statusLabel,
                      style: ui.type.bodySmall.copyWith(
                        color: failed
                            ? ui.color.status.blocked.content
                            : ui.color.inkSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (file.status == UiFileUploadStatus.uploading && !fillProgress)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s3),
              child: UiProgress.bar(
                key: ValueKey<String>('${file.id}:${file.attempt}'),
                semanticsLabel: '${file.name}: ${file.statusLabel}',
                value: file.progress,
                color: ui.color.accent,
              ),
            ),
          if (failed && file.errorText != null)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s2),
              child: Semantics(
                liveRegion: true,
                child: Text(
                  file.errorText!,
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.status.blocked.content,
                  ),
                ),
              ),
            ),
          if (onRemove != null || (failed && onRetry != null))
            Padding(
              padding: EdgeInsets.only(top: ui.space.s2),
              child: Wrap(
                alignment: WrapAlignment.end,
                spacing: ui.space.s2,
                children: <Widget>[
                  if (failed && onRetry != null)
                    UiIconButton(
                      icon: UiIcons.retry,
                      semanticsLabel:
                          retryLabelBuilder?.call(file) ?? 'Retry ${file.name}',
                      onPressed: enabled ? () => onRetry!(file) : null,
                      disabledReason: disabledReason,
                    ),
                  if (onRemove != null)
                    UiIconButton(
                      icon: UiIcons.remove,
                      semanticsLabel:
                          removeLabelBuilder?.call(file) ??
                          'Remove ${file.name}',
                      onPressed: enabled ? () => onRemove!(file) : null,
                      disabledReason: disabledReason,
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
