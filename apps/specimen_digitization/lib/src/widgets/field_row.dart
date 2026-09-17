/// One field of the record (design system, 7.3 `FieldRow`; UX writing, 1.13;
/// 10 section 5).
///
/// The verbatim and the interpreted live in separately named slots, always in
/// the same order, and a missing layer shows an abstention rather than a
/// blank. Nothing here decides what the layers mean; it only refuses to let
/// them be confused with one another.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

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
    this.editBlockedReason,
    this.findings,
  });

  /// The disclosure the three layers sit behind (10 section 5).
  ///
  /// Open from medium up, where the pane has the room for three layers per
  /// field, and closed on a compact window, where twelve fields would
  /// otherwise be thirty six lines before the first correction
  /// (11 section 3.1: the arrangement is declared per window class).
  static const String layersTitle = 'Values';

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

  /// Why this field cannot be corrected, or null when it can.
  ///
  /// It lands on the row's own node rather than on a wrapper, so a screen
  /// reader that focuses the row hears the sentence rather than only that the
  /// control is dimmed (accessibility, section 3.2).
  final String? editBlockedReason;

  /// Validation findings for this field, rendered under the layers.
  final Widget? findings;

  String? _valueOf(FieldLayer layer) => switch (layer) {
    FieldLayer.asWritten => asWritten,
    FieldLayer.readAs => readAs,
    FieldLayer.standardized => standardized,
  };

  /// The word shown in place of a missing layer.
  String get _abstention => state.isRecordStatus ? 'Not recorded' : state.label;

  /// The row's own title, with the required marker a reviewer reads.
  String get _title => required ? '$name (required)' : name;

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

  /// Everything the row says, with its state at the end.
  ///
  /// One node rather than two: the row is the control a reader lands on, and
  /// a container above it repeating the name announces the field twice.
  String get _rowSpoken => '$_spoken. ${state.semanticsLabel}';

  /// A value that already ends in a full stop does not get a second one.
  /// "U.S.A." is a real transcription, and "U.S.A.." is not a sentence.
  static String _withoutTrailingStop(String part) =>
      part.endsWith('.') ? part.substring(0, part.length - 1) : part;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final bool compact = WindowClass.of(context).isCompact;
    final Widget chip = StatusChip(state, dense: true);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        // The status chip is the row's trailing from medium up. On a
        // compact window it moves to a line of its own beneath the row,
        // because a trailing the row cannot measure is bounded to what is
        // left after the title's minimum, and at 360 dp that is not enough
        // for "Processing blocked" (11 section 3.3, the open row variant).
        //
        // The field's own name leads the row's label. Without it twenty rows
        // announce as "Field: supported" and a screen reader user cannot tell
        // which field they are standing on.
        UiListRow(
          title: _title,
          semanticsLabel: _rowSpoken,
          trailing: compact ? null : chip,
          disabledReason: editBlockedReason,
          onPressed: onEdit == null
              ? null
              : () => onEdit!(FieldLayer.asWritten),
        ),
        if (compact)
          Padding(
            padding: EdgeInsetsDirectional.only(bottom: ui.space.s1),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: chip,
            ),
          ),
        UiDisclosure(
          title: layersTitle,
          summary:
              '${FieldLayer.asWritten.label}: '
              '${asWritten ?? _abstention}',
          semanticsLabel: '$layersTitle, $name',
          initiallyExpanded: !compact,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              for (final FieldLayer layer in FieldLayer.values)
                _Layer(
                  layer: layer,
                  value: _valueOf(layer),
                  state: state,
                  onEdit: onEdit == null ? null : () => onEdit!(layer),
                  editLabel: editSemanticsLabel?.call(layer),
                ),
              if (authority != null) ...<Widget>[
                SizedBox(height: ui.space.s1),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    UiIcon(
                      UiIcons.authority,
                      size: UiIconSize.inline,
                      color: ui.color.status.authority.content,
                    ),
                    SizedBox(width: ui.space.s1),
                    Expanded(
                      child: Text(
                        authority!,
                        style: ui.type.bodySmall.copyWith(
                          color: ui.color.inkSecondary,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
        if (findings != null) ...<Widget>[
          SizedBox(height: ui.space.s2),
          findings!,
        ],
      ],
    );
  }
}

/// One named slot: its label, its value or an abstention, and its edit action.
///
/// The name sits above the value rather than beside it in a column of fixed
/// width. "Standardized" at 200 percent text is wider than any column this
/// pane can spare, and a label that ellipsises is a layer a reviewer can
/// confuse with another (11 section 2.2).
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
    final UiThemeData ui = context.ui;
    final String? text = value;
    final bool verbatim = layer == FieldLayer.asWritten;
    final String edit = editLabel ?? 'Edit ${layer.label.toLowerCase()}';

    return Padding(
      padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                // "As written", "Read as" and "Standardized" are the three
                // words this product asks a reviewer to keep apart, so each
                // one carries its own definition (pass criterion 10.2).
                TermText(
                  layer.label,
                  style: ui.type.labelSmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
                if (text == null)
                  // A missing layer shows the field's own abstention, never a
                  // blank, so absence is a value the reviewer can read.
                  _Abstention(state: state)
                else
                  // A node of its own: without it the value merges into the
                  // panel above and a reader hears every field's text in one
                  // utterance rather than beside the layer it belongs to.
                  Semantics(
                    container: true,
                    child: Text(
                      text,
                      style: verbatim
                          ? ui.type.mono.literalDense
                          : ui.type.body,
                    ),
                  ),
              ],
            ),
          ),
          if (onEdit != null)
            UiIconButton(
              icon: UiIcons.edit,
              semanticsLabel: edit,
              tooltip: edit,
              onPressed: onEdit,
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
    final UiThemeData ui = context.ui;
    final String word = state.isRecordStatus ? 'Not recorded' : state.label;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        UiIcon(
          state.isRecordStatus ? UiIcons.notPresent : state.iconSpec,
          size: UiIconSize.inline,
          color: ui.color.inkSecondary,
        ),
        SizedBox(width: ui.space.s1),
        // Flexible, because a `Row` hands a non-flex child unbounded width
        // and the row itself is inside a bounded column: "Not recorded"
        // beside its glyph is four pixels wider than a field row on a phone
        // (finding V-1, pass criterion 8.5).
        Flexible(
          child: TermText(
            word,
            style: ui.type.body.copyWith(color: ui.color.inkSecondary),
          ),
        ),
      ],
    );
  }
}
