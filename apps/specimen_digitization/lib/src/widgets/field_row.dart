/// One field of the record (design system, 7.3 `FieldRow`; UX writing, 1.13;
/// 10 section 5).
///
/// A concise preview names the value's actual state and the layer it comes
/// from. The original wording, interpretation and standardized value remain
/// separate when the reviewer opens the field's details.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'specimen_status.dart';

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
    this.showRequirementMarker = true,
    this.asWritten,
    this.readAs,
    this.standardized,
    this.authority,
    this.onEdit,
    this.editSemanticsLabel,
    this.editBlockedReason,
    this.findings,
    this.findingCount = 0,
    this.sourceLabel,
    this.sourceDetails,
    this.onExpansionChanged,
  });

  /// The disclosure the three layers sit behind (10 section 5).
  static const String layersTitle = 'Values';

  /// The field's name, as the record calls it.
  final String name;

  /// The field state the server reported.
  final SpecimenStatus state;

  /// True when the record cannot be cleared without this field.
  final bool required;

  /// False when a surrounding Required or Optional group already names it.
  /// The disclosure still announces the requirement to assistive technology.
  final bool showRequirementMarker;

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

  /// Validation findings for this field, revealed with the details.
  final Widget? findings;

  /// The number of recorded checks needing attention, shown in the preview.
  final int findingCount;

  /// Evidence linkage, shown with the expanded values.
  final String? sourceLabel;

  /// Retained evidence excerpts and actions for inspecting their label sources.
  final Widget? sourceDetails;

  /// Notifies the host when the reviewer opens or closes this field.
  final ValueChanged<bool>? onExpansionChanged;

  String? _valueOf(FieldLayer layer) => switch (layer) {
    FieldLayer.asWritten => asWritten,
    FieldLayer.readAs => readAs,
    FieldLayer.standardized => standardized,
  };

  /// A recorded value, with its layer named so normalization is not mistaken
  /// for original wording. The state remains first when a long value wraps.
  String get _summary {
    final layer = FieldLayer.values.reversed.where((layer) {
      final value = _valueOf(layer);
      return value != null && value.trim().isNotEmpty;
    }).firstOrNull;
    final value = layer == null ? null : _valueOf(layer);
    return <String>[
      state.label,
      if (layer != null) '${layer.label}: $value',
      if (findingCount > 0)
        '$findingCount ${findingCount == 1 ? 'check' : 'checks'} to review',
    ].join(' · ');
  }

  /// The row's own title, with the required marker a reviewer reads.
  String get _title =>
      required && showRequirementMarker ? '$name (required)' : name;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _FieldDisclosure(
          title: _title,
          requirement: showRequirementMarker
              ? null
              : required
              ? 'required'
              : 'optional',
          summary: _summary,
          onExpansionChanged: onExpansionChanged,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text('Field state: ${state.label}', style: ui.type.bodySmall),
              SizedBox(height: ui.space.s2),
              if (sourceLabel != null)
                Padding(
                  padding: EdgeInsets.only(bottom: ui.space.s2),
                  child: Text(
                    sourceLabel!,
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                ),
              if (editBlockedReason != null)
                Text(editBlockedReason!, style: ui.type.bodySmall),
              if (sourceDetails != null) ...<Widget>[
                sourceDetails!,
                SizedBox(height: ui.space.s3),
              ],
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
              if (findings != null) ...<Widget>[
                SizedBox(height: ui.space.s2),
                findings!,
              ],
            ],
          ),
        ),
      ],
    );
  }
}

/// Keeps the collapsed value available to screen readers without repeating
/// it in the expanded header, while retaining the field's requirement.
class _FieldDisclosure extends StatefulWidget {
  const _FieldDisclosure({
    required this.title,
    required this.summary,
    required this.requirement,
    required this.child,
    this.onExpansionChanged,
  });

  final String title;
  final String summary;
  final String? requirement;
  final Widget child;
  final ValueChanged<bool>? onExpansionChanged;

  @override
  State<_FieldDisclosure> createState() => _FieldDisclosureState();
}

class _FieldDisclosureState extends State<_FieldDisclosure> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) => UiDisclosure(
    title: widget.title,
    summary: widget.summary,
    hideSummaryWhenExpanded: true,
    semanticsLabel: widget.requirement == null
        ? null
        : '${widget.title}, ${widget.requirement}'
              '${_expanded ? '' : '. ${widget.summary}'}',
    onExpansionChanged: (expanded) {
      setState(() => _expanded = expanded);
      widget.onExpansionChanged?.call(expanded);
    },
    child: widget.child,
  );
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
                Text(
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
    final missing = state.isRecordStatus || state == SpecimenStatus.supported;
    final String word = missing ? 'Not recorded' : state.label;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        UiIcon(
          missing ? UiIcons.notPresent : state.iconSpec,
          size: UiIconSize.inline,
          color: ui.color.inkSecondary,
        ),
        SizedBox(width: ui.space.s1),
        // Flexible, because a `Row` hands a non-flex child unbounded width
        // and the row itself is inside a bounded column: "Not recorded"
        // beside its glyph is four pixels wider than a field row on a phone
        // (finding V-1, pass criterion 8.5).
        Flexible(
          child: Text(
            word,
            style: ui.type.body.copyWith(color: ui.color.inkSecondary),
          ),
        ),
      ],
    );
  }
}
