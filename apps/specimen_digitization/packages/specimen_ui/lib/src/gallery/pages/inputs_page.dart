/// The inputs family in every state (10 sections 4.2 and 6).
///
/// Every control the family owns, at rest, focused, filled, in error and
/// disabled with a reason, in both modes and both densities. The golden of
/// this page is the taste review for the family: a change to a field's edge
/// or a switch's thumb shows as a diff here before it shows on a screen.
///
/// The last section draws the box itself rather than a control, in each
/// shape, at rest, focused and focused with a value under the caret. One
/// field on a page can hold focus and the rest cannot, so a page that only
/// autofocused would review one of the four shapes it ships (11 section 4).
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// The inputs page, as the gallery shell lists it.
const GalleryPage inputsPage = GalleryPage(
  id: 'inputs',
  title: 'Inputs',
  summary:
      'Fields, text areas, search, selects, switches, boxes and radios, in '
      'every state.',
  builder: buildInputsPage,
);

/// Builds the inputs page.
Widget buildInputsPage(BuildContext context) => const _InputsPage();

/// How wide a field specimen is drawn.
const double _wide = 280;

/// How wide a toggle specimen is drawn.
const double _narrow = 210;

class _InputsPage extends StatefulWidget {
  const _InputsPage();

  @override
  State<_InputsPage> createState() => _InputsPageState();
}

class _InputsPageState extends State<_InputsPage> {
  final TextEditingController _filled = TextEditingController(
    text: 'The date on the label reads 1946',
  );
  final TextEditingController _counted = TextEditingController(
    text: 'FMNH 1946 0042',
  );
  final TextEditingController _reason = TextEditingController(
    text:
        'The second reading matches the collector on the determination '
        'label, so it is the one to keep.',
  );
  final TextEditingController _search = TextEditingController(text: 'Chicago');

  bool _announce = true;
  bool _rawEvidence = false;
  bool? _coverage;
  bool _regions = true;
  String? _keep = 'model';
  String? _disposition = 'cleared';
  String? _empty;

  @override
  void dispose() {
    _filled.dispose();
    _counted.dispose();
    _reason.dispose();
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        GallerySection(
          title: 'UiField, every state',
          child: _Grid(
            spacing: ui.space.s4,
            children: <Widget>[
              const _Cell(
                width: _wide,
                label: 'rest',
                child: UiField(
                  label: 'Reason for this decision',
                  hintText: 'Say what you saw on the label',
                  helpText: 'Kept in the record history.',
                ),
              ),
              const _Cell(
                width: _wide,
                label: 'focused',
                note: 'the ring is the whole of it; the edge holds',
                child: UiField(
                  label: 'Reason for this decision',
                  hintText: 'Say what you saw on the label',
                  helpText: 'Kept in the record history.',
                  autofocus: true,
                ),
              ),
              _Cell(
                width: _wide,
                label: 'filled, with a clear control',
                child: UiField(
                  label: 'Reason for this decision',
                  controller: _filled,
                  clearLabel: 'Clear the reason',
                  helpText: 'Kept in the record history.',
                ),
              ),
              const _Cell(
                width: _wide,
                label: 'error',
                child: UiField(
                  label: 'Reason for this decision',
                  errorText: 'Enter a reason for this decision.',
                ),
              ),
              const _Cell(
                width: _wide,
                label: 'disabled with a reason',
                note: 'the reason is on the semantics hint',
                child: UiField(
                  label: 'Reason for this decision',
                  enabled: false,
                  disabledReason: 'Sign in again before you record a decision.',
                ),
              ),
              _Cell(
                width: _wide,
                label: 'leading glyph and a counter',
                child: UiField(
                  label: 'Catalogue number',
                  controller: _counted,
                  leading: UiIcons.record,
                  maxLength: 24,
                  autocorrect: false,
                ),
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'UiSwitch, UiCheckbox and UiRadio',
          child: _Grid(
            spacing: ui.space.s4,
            children: <Widget>[
              _Cell(
                width: _narrow,
                label: 'switch, on',
                child: UiSwitch(
                  label: 'Announce decisions',
                  value: _announce,
                  onChanged: (bool value) => setState(() => _announce = value),
                ),
              ),
              _Cell(
                width: _narrow,
                label: 'switch, off',
                child: UiSwitch(
                  label: 'Show raw evidence',
                  value: _rawEvidence,
                  onChanged: (bool value) =>
                      setState(() => _rawEvidence = value),
                ),
              ),
              const _Cell(
                width: _narrow,
                label: 'switch, disabled',
                child: UiSwitch(
                  label: 'Announce decisions',
                  value: true,
                  disabledReason: 'Turn on a screen reader to use this.',
                ),
              ),
              _Cell(
                width: _narrow,
                label: 'checkbox, indeterminate',
                child: UiCheckbox(
                  label: 'Label coverage',
                  value: _coverage,
                  onChanged: (bool value) => setState(() => _coverage = value),
                ),
              ),
              _Cell(
                width: _narrow,
                label: 'checkbox, checked',
                child: UiCheckbox(
                  label: 'Regions corrected',
                  value: _regions,
                  onChanged: (bool value) => setState(() => _regions = value),
                ),
              ),
              const _Cell(
                width: _narrow,
                label: 'checkbox, disabled',
                child: UiCheckbox(
                  label: 'Regions corrected',
                  value: false,
                  disabledReason: 'Open the region editor to correct these.',
                ),
              ),
              _Cell(
                width: _narrow + _narrow,
                label: 'radio group',
                child: UiRadioGroup<String>(
                  label: 'Which reading to keep',
                  value: _keep,
                  onChanged: (String? value) => setState(() => _keep = value),
                  children: const <Widget>[
                    UiRadio<String>(label: 'The model reading', value: 'model'),
                    UiRadio<String>(
                      label: 'The reviewer reading',
                      value: 'human',
                    ),
                    UiRadio<String>(
                      label: 'Neither reading',
                      value: 'neither',
                      enabled: false,
                      disabledReason: 'Record a reason to reject both.',
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'UiSelect, UiSearchField and UiTextArea',
          child: _Grid(
            spacing: ui.space.s4,
            children: <Widget>[
              _Cell(
                width: _wide,
                label: 'select, filled',
                child: UiSelect<String>(
                  label: 'Disposition',
                  placeholder: 'Pick a disposition',
                  value: _disposition,
                  options: _dispositions,
                  onChanged: (String value) =>
                      setState(() => _disposition = value),
                  helpText: 'Shown on the queue row.',
                ),
              ),
              _Cell(
                width: _wide,
                label: 'select, at rest',
                child: UiSelect<String>(
                  label: 'Disposition',
                  placeholder: 'Pick a disposition',
                  value: _empty,
                  options: _dispositions,
                  onChanged: (String value) => setState(() => _empty = value),
                ),
              ),
              _Cell(
                width: _wide,
                label: 'select, disabled with a reason',
                child: UiSelect<String>(
                  label: 'Disposition',
                  placeholder: 'Pick a disposition',
                  value: _empty,
                  options: _dispositions,
                  disabledReason: 'The run is still reading this specimen.',
                ),
              ),
              _Cell(
                width: _wide,
                label: 'search, filled',
                child: UiSearchField(
                  label: 'Search the queue',
                  clearLabel: 'Clear the search',
                  hintText: 'Specimen id, collector or place',
                  controller: _search,
                ),
              ),
              const _Cell(
                width: _wide,
                label: 'search, at rest',
                child: UiSearchField(
                  label: 'Search the queue',
                  clearLabel: 'Clear the search',
                  hintText: 'Specimen id, collector or place',
                ),
              ),
              _Cell(
                width: _wide,
                label: 'text area, filled',
                child: UiTextArea(
                  label: 'Reason for this decision',
                  controller: _reason,
                  maxLength: 240,
                ),
              ),
            ],
          ),
        ),
        GallerySection(
          title: 'The box, in every shape and every focus state',
          child: _Grid(
            spacing: ui.space.s4,
            children: const <Widget>[
              _Cell(
                width: _wide,
                label: 'box, at rest',
                child: _BoxPaint(shape: UiFieldShape.box),
              ),
              _Cell(
                width: _wide,
                label: 'box, focused',
                note: 'a superellipse ring on a superellipse edge',
                child: _BoxPaint(shape: UiFieldShape.box, focused: true),
              ),
              _Cell(
                width: _wide,
                label: 'box, focused and typing',
                child: _BoxPaint(
                  shape: UiFieldShape.box,
                  focused: true,
                  value: 'The date on the label reads 1946',
                ),
              ),
              _Cell(
                width: _wide,
                label: 'capsule, at rest',
                child: _BoxPaint(
                  shape: UiFieldShape.capsule,
                  leading: UiIcons.search,
                ),
              ),
              _Cell(
                width: _wide,
                label: 'capsule, focused',
                note: 'a stadium ring on a stadium edge',
                child: _BoxPaint(
                  shape: UiFieldShape.capsule,
                  leading: UiIcons.search,
                  focused: true,
                ),
              ),
              _Cell(
                width: _wide,
                label: 'capsule, focused and typing',
                child: _BoxPaint(
                  shape: UiFieldShape.capsule,
                  leading: UiIcons.search,
                  focused: true,
                  value: 'Chicago',
                ),
              ),
              _Cell(
                width: _wide,
                label: 'paragraph, focused and typing',
                child: _BoxPaint(
                  shape: UiFieldShape.box,
                  focused: true,
                  multiline: true,
                  value:
                      'The second reading matches the collector on the '
                      'determination label.',
                ),
              ),
              _Cell(
                width: _wide,
                label: 'box, in error',
                note: 'the edge turns, and keeps its width',
                child: _BoxPaint(shape: UiFieldShape.box, error: true),
              ),
            ],
          ),
        ),
      ],
    );
  }

  static const List<UiSelectOption<String>> _dispositions =
      <UiSelectOption<String>>[
        UiSelectOption<String>(
          value: 'cleared',
          label: 'Cleared',
          leading: UiIcons.cleared,
        ),
        UiSelectOption<String>(
          value: 'review',
          label: 'Needs human review',
          leading: UiIcons.needsReview,
        ),
        UiSelectOption<String>(
          value: 'deferred',
          label: 'Deferred',
          leading: UiIcons.deferred,
        ),
        UiSelectOption<String>(
          value: 'blocked',
          label: 'Processing blocked',
          leading: UiIcons.blocked,
        ),
      ];
}

/// The box on its own, in one shape and one state.
///
/// A control drives its own focus and only one control on a page can hold it,
/// so the states a reviewer most needs to compare are drawn here rather than
/// acted out: the same [UiFieldBox] every field and every select is built
/// from, in the paint it takes when it is focused.
class _BoxPaint extends StatelessWidget {
  const _BoxPaint({
    required this.shape,
    this.focused = false,
    this.error = false,
    this.multiline = false,
    this.value,
    this.leading,
  });

  final UiFieldShape shape;
  final bool focused;
  final bool error;
  final bool multiline;
  final String? value;
  final IconSpec? leading;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiInputStyle style = UiInputStyle.resolve(
      ui,
      shape,
      textScaler: MediaQuery.textScalerOf(context),
    );
    final Set<WidgetState> states = <WidgetState>{if (error) WidgetState.error};
    final String? text = value;
    return Padding(
      // Room for the ring, which is drawn outside the box and would otherwise
      // run into the specimen beside it.
      padding: EdgeInsetsDirectional.all(ui.space.s1),
      child: UiFieldBox(
        style: style,
        states: states,
        focusRing: focused,
        multiline: multiline,
        leading: leading,
        child: Text(
          text ?? 'Say what you saw on the label',
          style: style.text.copyWith(
            color: text == null ? ui.color.inkTertiary : ui.color.ink,
          ),
          maxLines: multiline ? null : 1,
          softWrap: multiline,
          // An ellipsis with no line limit is a single line: the paragraph
          // engine takes the two together as "one line, cut short".
          overflow: multiline ? TextOverflow.clip : TextOverflow.ellipsis,
        ),
      ),
    );
  }
}

/// A row of specimens that wraps.
class _Grid extends StatelessWidget {
  const _Grid({required this.spacing, required this.children});

  final double spacing;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: spacing,
    runSpacing: spacing,
    crossAxisAlignment: WrapCrossAlignment.start,
    children: children,
  );
}

/// One specimen, at a fixed width so a field has somewhere to be.
class _Cell extends StatelessWidget {
  const _Cell({
    required this.width,
    required this.label,
    required this.child,
    this.note,
  });

  final double width;
  final String label;
  final Widget child;
  final String? note;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: width,
    child: GallerySpecimen(label: label, note: note, child: child),
  );
}
