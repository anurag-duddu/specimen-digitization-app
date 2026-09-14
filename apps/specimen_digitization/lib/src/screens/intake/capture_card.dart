/// The capture card (screen blueprints, section 5).
///
/// One card, one job: choose how photographs arrive, say how sensitive they
/// are, and confirm that this batch was looked at. The manifest is a separate
/// card, so the card an operator presses repeatedly never scrolls away from
/// the list it fills (responsive, section 3.4).
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../theme/icons.dart';
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
  /// button is not rendered at all rather than rendered dead.
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

  /// The upload button's word, which names the count it authorises
  /// (pass criterion 5.2).
  static String uploadLabel({required bool uploading, required int pending}) {
    if (uploading) return 'Uploading';
    if (pending == 1) return 'Upload 1 photograph';
    return 'Upload $pending photographs';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: EdgeInsets.all(context.space.space6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text('Add photographs', style: theme.textTheme.headlineSmall),
            SizedBox(height: context.space.space2),
            Text('One photograph per specimen.'),
            SizedBox(height: context.space.space4),
            Wrap(
              spacing: context.space.space3,
              runSpacing: context.space.space3,
              children: <Widget>[
                if (cameraAvailable)
                  FilledButton.icon(
                    key: const ValueKey<String>('intake-take-photograph'),
                    onPressed: onTakePhotograph,
                    icon: const Icon(Symbols.photo_camera),
                    label: const Text('Take photograph'),
                    style: FilledButton.styleFrom(
                      minimumSize: Size(
                        context.sizes.targetMin,
                        context.sizes.targetMin,
                      ),
                    ),
                  ),
                OutlinedButton.icon(
                  key: const ValueKey<String>('intake-choose-files'),
                  onPressed: onChooseFiles,
                  icon: const Icon(Symbols.upload_file),
                  label: const Text('Choose files'),
                  style: OutlinedButton.styleFrom(
                    minimumSize: Size(
                      context.sizes.targetMin,
                      context.sizes.targetMin,
                    ),
                  ),
                ),
              ],
            ),
            if (!cameraAvailable) ...<Widget>[
              SizedBox(height: context.space.space3),
              Text(
                'Camera capture runs in the Android and iOS apps. Here, '
                'choose a file.',
                style: theme.textTheme.bodySmall,
              ),
            ],
            SizedBox(height: context.space.space6),
            SizedBox(
              width: double.infinity,
              child: SegmentedButton<bool>(
                key: const ValueKey<String>('intake-sensitivity'),
                segments: const <ButtonSegment<bool>>[
                  ButtonSegment<bool>(
                    value: true,
                    label: Text('Sensitive'),
                    icon: Icon(Symbols.lock),
                  ),
                  ButtonSegment<bool>(
                    value: false,
                    label: Text('Not sensitive'),
                    icon: Icon(Symbols.lock_open),
                  ),
                ],
                selected: <bool>{sensitive},
                showSelectedIcon: false,
                onSelectionChanged: onSensitivityChanged == null
                    ? null
                    : (Set<bool> selection) =>
                          onSensitivityChanged!(selection.first),
              ),
            ),
            SizedBox(height: context.space.space2),
            Text(
              'Applies to photographs you add next.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const CaveatText(
              label: 'Sensitivity cannot be changed after an upload starts.',
              why:
                  'Choose Not sensitive only if these photographs and their '
                  'labels are suitable for ordinary collection access. A '
                  'photograph already sent keeps the classification its '
                  'upload was created with.',
            ),
            SizedBox(height: context.space.space4),
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
            SizedBox(height: context.space.space4),
            Text(
              'Before you upload, check:',
              style: theme.textTheme.titleSmall,
            ),
            SizedBox(height: context.space.space2),
            for (final String check in preUploadChecklist)
              Padding(
                padding: EdgeInsets.only(bottom: context.space.space1),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Icon(
                      Symbols.check_box_outline_blank,
                      size: context.sizes.iconInline,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    SizedBox(width: context.space.space2),
                    Expanded(child: Text(check)),
                  ],
                ),
              ),
            CheckboxListTile(
              key: const ValueKey<String>('intake-confirm'),
              contentPadding: EdgeInsets.zero,
              value: confirmed,
              onChanged: onConfirmedChanged == null
                  ? null
                  : (bool? value) => onConfirmedChanged!(value ?? false),
              title: const Text(batchConfirmationLabel),
              subtitle: Text(
                'Clears whenever you add a photograph.',
                style: theme.textTheme.bodySmall,
              ),
            ),
            SizedBox(height: context.space.space3),
            FilledButton.icon(
              key: const ValueKey<String>('intake-upload'),
              onPressed: onUpload,
              icon: const Icon(Symbols.cloud_upload),
              label: Text(
                uploadLabel(uploading: uploading, pending: pendingCount),
              ),
              style: FilledButton.styleFrom(
                minimumSize: Size(
                  context.sizes.targetMin,
                  context.sizes.targetMin,
                ),
              ),
            ),
            SizedBox(height: context.space.space2),
            Text(
              'The server runs its own checks.',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}
