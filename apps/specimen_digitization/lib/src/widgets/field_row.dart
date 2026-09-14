/// One field of the record (design system, 7.3 `FieldRow`; UX writing, 1.13).
///
/// The verbatim and the interpreted live in separately named slots, always in
/// the same order, and a missing layer shows an abstention rather than a
/// blank. Nothing here decides what the layers mean; it only refuses to let
/// them be confused with one another.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';
import 'specimen_status.dart';
import 'status_chip.dart';

/// The three layers of one field value, in reading order.
enum FieldLayer {
  /// What the pixels say, verbatim.
  asWritten('As written'),

  /// What the reading means, in prose.
  readAs('Read as'),

  /// The value after the standard was applied.
  standardized('Standardized');

  const FieldLayer(this.label);

  /// The slot's visible name. Fixed, so a reviewer learns it once.
  final String label;
}

/// A field name, its state, its three layers and what they are backed by.
class FieldRow extends StatelessWidget {
  const FieldRow({
    super.key,
    required this.name,
    required this.state,
    this.required = false,
    this.asWritten,
    this.readAs,
    this.standardized,
    this.authority,
    this.onEdit,
    this.findings,
  });

  /// The field's name, as the record calls it.
  final String name;

  /// The field state the server reported.
  final SpecimenStatus state;

  /// True when the record cannot be cleared without this field.
  final bool required;

  /// The verbatim transcription. Null renders the field's abstention.
  final String? asWritten;

  /// The interpretation. Null renders the field's abstention.
  final String? readAs;

  /// The standardized value. Null renders the field's abstention.
  final String? standardized;

  /// One line naming the external reference the standardized value came from.
  final String? authority;

  /// Called with the layer the reviewer asked to edit.
  final void Function(FieldLayer layer)? onEdit;

  /// Validation findings for this field, rendered under the layers.
  final Widget? findings;

  String? _valueOf(FieldLayer layer) => switch (layer) {
    FieldLayer.asWritten => asWritten,
    FieldLayer.readAs => readAs,
    FieldLayer.standardized => standardized,
  };

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);

    return Semantics(
      container: true,
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: context.space.space2),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Row(
              children: <Widget>[
                Flexible(
                  child: Text(
                    required ? '$name (required)' : name,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
                SizedBox(width: context.space.space2),
                StatusChip(state, dense: true),
              ],
            ),
            SizedBox(height: context.space.space1),
            for (final FieldLayer layer in FieldLayer.values)
              _Layer(
                layer: layer,
                value: _valueOf(layer),
                state: state,
                onEdit: onEdit == null ? null : () => onEdit!(layer),
              ),
            if (authority != null) ...<Widget>[
              SizedBox(height: context.space.space1),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(
                    Symbols.menu_book,
                    size: context.sizes.iconInline,
                    color: context.tokens.evidenceAuthorityContent,
                  ),
                  SizedBox(width: context.space.space1),
                  Expanded(
                    child: Text(
                      authority!,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ],
              ),
            ],
            if (findings != null) ...<Widget>[
              SizedBox(height: context.space.space2),
              findings!,
            ],
          ],
        ),
      ),
    );
  }
}

/// One named slot: its label, its value or an abstention, and its edit action.
class _Layer extends StatelessWidget {
  const _Layer({
    required this.layer,
    required this.value,
    required this.state,
    this.onEdit,
  });

  final FieldLayer layer;
  final String? value;
  final SpecimenStatus state;
  final VoidCallback? onEdit;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String? text = value;
    final bool verbatim = layer == FieldLayer.asWritten;

    return Padding(
      padding: EdgeInsets.only(bottom: context.space.space1),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            // Wide enough for "Standardized" at `labelSmall`, composed from
            // the grid rather than measured by eye.
            width: context.space.space16 + context.space.space8,
            child: Text(
              layer.label,
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          SizedBox(width: context.space.space2),
          Expanded(
            child: text == null
                // A missing layer shows the field's own abstention, never a
                // blank, so absence is a value the reviewer can read.
                ? _Abstention(state: state)
                : Text(
                    text,
                    style: verbatim
                        ? context.mono.literalDense
                        : theme.textTheme.bodyMedium,
                  ),
          ),
          if (onEdit != null)
            IconButton(
              onPressed: onEdit,
              icon: const Icon(Symbols.edit),
              iconSize: context.sizes.iconInline,
              tooltip: 'Edit ${layer.label.toLowerCase()}',
              constraints: BoxConstraints(
                minWidth: context.sizes.targetMin,
                minHeight: context.sizes.targetMin,
              ),
            ),
        ],
      ),
    );
  }
}

/// The icon and word for a value that is not there.
class _Abstention extends StatelessWidget {
  const _Abstention({required this.state});

  final SpecimenStatus state;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String word = state.isRecordStatus ? 'Not recorded' : state.label;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(
          state.isRecordStatus ? Symbols.horizontal_rule : state.icon,
          size: context.sizes.iconInline,
          color: theme.colorScheme.onSurfaceVariant,
        ),
        SizedBox(width: context.space.space1),
        Text(
          word,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}
