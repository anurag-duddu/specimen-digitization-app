/// A photo preview with separate inspection and bulk-selection targets.
library;

import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';
import '../../primitives/surface.dart';
import '../inputs/checkbox.dart';

/// An image-first tile whose selection control does not open the inspector.
class UiPhotoTile extends StatelessWidget {
  /// Builds the preview, caption, save state, and separate editing checkbox.
  const UiPhotoTile({
    super.key,
    required this.preview,
    required this.name,
    required this.status,
    required this.selected,
    required this.onSelected,
    required this.onOpen,
    this.included = true,
    this.showStatus = true,
  });

  /// Image content, normally fitted with `BoxFit.contain`.
  final Widget preview;

  /// The photograph's display name.
  final String name;

  /// A factual saving or attention state.
  final String status;

  /// Shows the status caption. A host may hide a settled baseline it already
  /// reports for the batch; the inspection target still announces it.
  /// Excluded photos always retain their visible exception.
  final bool showStatus;

  /// Whether this tile belongs to the current bulk editing selection.
  final bool selected;

  /// Whether the photograph is included in the eventual submission.
  final bool included;

  /// Changes the bulk editing selection only.
  final ValueChanged<bool> onSelected;

  /// Opens the photo inspector without changing selection.
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: Surface(
            role: SurfaceRole.matte,
            radius: ui.shape.inner,
            boundary: selected,
            clip: true,
            child: Pressable(
              semanticsLabel:
                  'Review $name. ${included ? status : 'Excluded from submission'}',
              onPressed: onOpen,
              radius: ui.shape.inner,
              builder: (context, states) =>
                  Padding(padding: EdgeInsets.all(ui.space.s2), child: preview),
            ),
          ),
        ),
        Row(
          children: [
            UiCheckbox(
              label: 'Select $name for editing',
              value: selected,
              showLabel: false,
              onChanged: onSelected,
            ),
            Expanded(
              child: Text(
                name,
                style: ui.type.labelSmall,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
        if (showStatus || !included)
          Padding(
            padding: EdgeInsets.symmetric(horizontal: ui.space.s2),
            child: Text(
              included ? status : 'Excluded from submission',
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
      ],
    );
  }
}
