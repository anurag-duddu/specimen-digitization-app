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
import 'term_text.dart';

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
    this.editSemanticsLabel,
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

  /// Names the edit control for assistive technology.
  ///
  /// The default names the layer only, which is correct inside a row that is
  /// already announced by name but useless to a reader that lands on the
  /// control directly. A screen that knows the field passes this to get
  /// "Edit read as for Scientific name" instead of "Edit read as".
  final String Function(FieldLayer layer)? editSemanticsLabel;

  /// Validation findings for this field, rendered under the layers.
  final Widget? findings;

  String? _valueOf(FieldLayer layer) => switch (layer) {
    FieldLayer.asWritten => asWritten,
    FieldLayer.readAs => readAs,
    FieldLayer.standardized => standardized,
  };

  /// The word shown in place of a missing layer.
  String get _abstention => state.isRecordStatus ? 'Not recorded' : state.label;

  /// Everything the row says, in one phrase.
  ///
  /// Written out rather than left to Flutter's merge. Each layer label is now
  /// its own definition link (pass criterion 10.2), and a node with an action
  /// of its own is not merged into its parent, so a row that relied on the
  /// merge would have stopped telling a screen reader what its three layers
  /// hold. This states it directly, so the row's spoken summary cannot be
  /// changed by how its children are built.
  String get _spoken => <String>[
    required ? '$name, required' : name,
    for (final FieldLayer layer in FieldLayer.values)
      '${layer.label}: ${_valueOf(layer) ?? _abstention}',
  ].map(_withoutTrailingStop).join('. ');

  /// A value that already ends in a full stop does not get a second one.
  /// "U.S.A." is a real transcription, and "U.S.A.." is not a sentence.
  static String _withoutTrailingStop(String part) =>
      part.endsWith('.') ? part.substring(0, part.length - 1) : part;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);

    return Semantics(
      container: true,
      // The field's own name leads the label. Without it twenty rows announce
      // as "Field: supported" and a screen reader user cannot tell which
      // field they are standing on.
      label: _spoken,
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
                editLabel: editSemanticsLabel?.call(layer),
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
    this.editLabel,
  });

  final FieldLayer layer;
  final String? value;
  final SpecimenStatus state;
  final VoidCallback? onEdit;
  final String? editLabel;

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
            // "As written", "Read as" and "Standardized" are the three
            // words this product asks a reviewer to keep apart, so each one
            // carries its own definition (pass criterion 10.2).
            child: TermText(
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
            Semantics(
              label: editLabel,
              child: IconButton(
                onPressed: onEdit,
                icon: const Icon(Symbols.edit),
                iconSize: context.sizes.iconInline,
                tooltip: editLabel ?? 'Edit ${layer.label.toLowerCase()}',
                constraints: BoxConstraints(
                  minWidth: context.sizes.targetMin,
                  minHeight: context.sizes.targetMin,
                ),
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
        // Flexible, because a `Row` hands a non-flex child unbounded width
        // and the row itself is inside a bounded column: "Not recorded"
        // beside its glyph is four pixels wider than a field row on a phone
        // (finding V-1, pass criterion 8.5).
        Flexible(
          child: TermText(
            word,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
      ],
    );
  }
}
