/// The capture card (07 section 5).
///
/// One pane, one job: choose how photographs arrive, say how sensitive they
/// are, and confirm that this batch was looked at. The manifest is a separate
/// pane, so the control an operator presses repeatedly never scrolls away from
/// the list it fills (05 section 3.4).
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../widgets/caveat_text.dart';

/// The five checks an operator makes before a batch leaves the device
/// (heuristics audit, H10.5).
const List<String> preUploadChecklist = <String>[
  'Sharp focus',
  'Smallest text readable',
  'Even exposure',
  'No glare',
  'Every label inside the frame',
];

/// The one confirmation this screen asks for, per batch.
///
/// The checkbox resets whenever a file is added, so a tick never authorises
/// photographs the operator had not selected when they ticked it
/// (heuristics audit, H5.3).
const String batchConfirmationLabel = 'I checked framing and readability';

/// Where photographs come from, how they are classified, and the one
/// confirmation that releases the batch.
class IntakeCaptureCard extends StatelessWidget {
  const IntakeCaptureCard({
    super.key,
    required this.sensitive,
    required this.onSensitivityChanged,
    required this.onChooseFiles,
    required this.onTakePhotograph,
    required this.cameraAvailable,
    required this.confirmed,
    required this.onConfirmedChanged,
    required this.onUpload,
    required this.uploading,
    required this.pendingCount,
  });

  /// The classification that will be applied to photographs added next.
  final bool sensitive;

  /// Called when the operator changes that classification.
  final ValueChanged<bool>? onSensitivityChanged;

  /// Opens the file picker. Null while the screen is busy.
  final VoidCallback? onChooseFiles;

  /// Opens the capture route. Null while the screen is busy.
  final VoidCallback? onTakePhotograph;

  /// False on web and desktop, where this client has no camera to offer. The
  /// control is not rendered at all rather than rendered dead.
  final bool cameraAvailable;

  /// Whether this batch has been confirmed.
  final bool confirmed;

  /// Called when the confirmation is ticked or cleared.
  final ValueChanged<bool>? onConfirmedChanged;

  /// Starts the batch. Null when something is missing.
  final VoidCallback? onUpload;

  /// True while a batch is in flight.
  final bool uploading;

  /// How many rows this batch would send.
  final int pendingCount;

  /// The card's own title, which names the screen (02 section 4.1).
  static const String title = 'Add photographs';

  /// What the checklist is called.
  static const String checklistTitle = 'Before you upload, check:';

  /// What the one confirmation says under itself.
  static const String confirmationHelp =
      'Clears whenever you add a photograph.';

  /// What a build with no camera says instead of a control it cannot offer.
  static const String noCameraHelp =
      'Camera capture runs in the Android and iOS apps. Here, choose a file.';

  /// The upload button's word, which names the count it authorises
  /// (pass criterion 5.2).
  static String uploadLabel({required bool uploading, required int pending}) {
    if (uploading) return 'Uploading';
    if (pending == 1) return 'Upload 1 photograph';
    return 'Upload $pending photographs';
  }

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
              title,
              style: ui.type.titleLarge.copyWith(color: ui.color.ink),
            ),
          ),
          SizedBox(height: ui.space.s2),
          Text(
            'One photograph per specimen.',
            style: ui.type.body.copyWith(color: ui.color.ink),
          ),
          SizedBox(height: ui.space.s4),
          UiButtonRow(
            primary: UiButton(
              key: const ValueKey<String>('intake-choose-files'),
              label: 'Choose files',
              leading: UiIcons.uploadFile,
              onPressed: onChooseFiles,
            ),
            secondary: cameraAvailable
                ? UiButton(
                    key: const ValueKey<String>('intake-take-photograph'),
                    label: 'Take photograph',
                    variant: UiButtonVariant.secondary,
                    leading: UiIcons.camera,
                    onPressed: onTakePhotograph,
                  )
                : null,
          ),
          if (!cameraAvailable) ...<Widget>[
            SizedBox(height: ui.space.s3),
            Text(
              noCameraHelp,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          ],
          SizedBox(height: ui.space.s6),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiSegmented<bool>(
              key: const ValueKey<String>('intake-sensitivity'),
              // The name the select rung offers the options under, on a
              // column too narrow for the track (11 section 3.3). The track
              // itself never draws it; the line below the control does.
              label: 'Sensitivity',
              value: sensitive,
              onChanged: onSensitivityChanged,
              segments: const <UiSegment<bool>>[
                UiSegment<bool>(
                  value: true,
                  label: 'Sensitive',
                  icon: UiIcons.locked,
                ),
                UiSegment<bool>(
                  value: false,
                  label: 'Not sensitive',
                  icon: UiIcons.unlocked,
                ),
              ],
            ),
          ),
          SizedBox(height: ui.space.s2),
          Text(
            'Applies to photographs you add next.',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
          SizedBox(height: ui.space.s4),
          const CaveatText(
            label: 'Sensitivity cannot be changed after an upload starts.',
            why:
                'Choose Not sensitive only if these photographs and their '
                'labels are suitable for ordinary collection access. A '
                'photograph already sent keeps the classification its '
                'upload was created with.',
          ),
          SizedBox(height: ui.space.s4),
          const CaveatText(
            label:
                'HEIC, TIFF and DNG may not preview on this device. You can '
                'still upload them.',
            why:
                'Previews depend on this device. The server verifies the '
                'bytes, format and dimensions of the file when the upload '
                'completes. If the server cannot decode it, your upload is '
                'kept so you can retry.',
          ),
          SizedBox(height: ui.space.s4),
          Semantics(
            header: true,
            child: Text(
              checklistTitle,
              style: ui.type.label.copyWith(color: ui.color.inkSecondary),
            ),
          ),
          for (final String check in preUploadChecklist)
            _ChecklistItem(check: check),
          SizedBox(height: ui.space.s2),
          // One confirmation for the whole batch, not one per line: a tick
          // that authorises a batch has to be a single deliberate act
          // (heuristics audit, H5.3).
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiCheckbox(
              key: const ValueKey<String>('intake-confirm'),
              label: batchConfirmationLabel,
              value: confirmed,
              onChanged: onConfirmedChanged,
            ),
          ),
          SizedBox(height: ui.space.s1),
          Text(
            confirmationHelp,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
          SizedBox(height: ui.space.s4),
          UiButtonRow(
            // The label is the present participle while a batch is in
            // flight and the control is disabled, which is what 02 section
            // 4.3 asks for. The measured progress is on the manifest, where
            // the denominator is.
            primary: UiButton(
              key: const ValueKey<String>('intake-upload'),
              label: uploadLabel(uploading: uploading, pending: pendingCount),
              leading: UiIcons.cloudUpload,
              onPressed: onUpload,
            ),
          ),
          SizedBox(height: ui.space.s2),
          Text(
            'The server runs its own checks.',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ],
      ),
    );
  }
}

/// One line of the pre-upload checklist.
///
/// A row rather than a control: the five checks are what an operator looks
/// at, and the one thing on this card that can be ticked is the batch
/// confirmation below them. The row publishes its own words and none of
/// `UiListRow`'s press semantics, because there is nothing here to press.
class _ChecklistItem extends StatelessWidget {
  const _ChecklistItem({required this.check});

  final String check;

  @override
  Widget build(BuildContext context) => Semantics(
    container: true,
    label: check,
    excludeSemantics: true,
    child: UiListRow(
      size: UiSize.sm,
      title: check,
      leading: UiIcon(
        UiIcons.unselected,
        size: UiIconSize.inline,
        color: context.ui.color.inkSecondary,
      ),
    ),
  );
}
