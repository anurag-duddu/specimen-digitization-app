import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

enum _InputState { editable, error, readOnly, disabled }

_InputState _state(BuildContext context) =>
    context.knobs.object.dropdown<_InputState>(
      label: 'State',
      options: _InputState.values,
      labelBuilder: (_InputState value) => value.name,
    );

/// The base form anatomy, native editing behaviour and controlled choice stories.
List<WidgetbookComponent> get inputComponents => <WidgetbookComponent>[
  WidgetbookComponent(
    name: 'UiField',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Anatomy and editing states',
        builder: (BuildContext context) {
          final String text = context.knobs.string(
            label: 'Initial text',
            initialValue: 'FMNH 1946 0042',
          );
          return _InputFrame(
            description:
                'Label, optional leading icon, editable value, one trailing action and supporting text. Error replaces help and announces once. Read-only text remains selectable. The disabled state explains why editing is unavailable.',
            child: _TextDemo(
              key: ValueKey<String>(text),
              text: text,
              state: _state(context),
              shape: context.knobs.object.dropdown<UiFieldShape>(
                label: 'Shape',
                options: UiFieldShape.values,
                labelBuilder: (UiFieldShape value) => value.name,
              ),
              leading: context.knobs.boolean(
                label: 'Leading icon',
                initialValue: true,
              ),
              clear: context.knobs.boolean(
                label: 'Clear action',
                initialValue: true,
              ),
              counter: context.knobs.boolean(label: 'Character count'),
            ),
          );
        },
      ),
      WidgetbookUseCase(
        name: 'Email and password anatomy',
        builder: (BuildContext context) => _InputFrame(
          description:
              'Native email keyboard and autofill hints; password visibility is an explicit accessible action. These local examples never authenticate or send credentials.',
          child: _CredentialsDemo(
            enabled: context.knobs.boolean(
              label: 'Enabled',
              initialValue: true,
            ),
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Numeric input and formatting',
        builder: (_) => _InputFrame(
          description:
              'The caller chooses the numeric keyboard and formatter. Shared field chrome does not parse, normalize or save domain data.',
          child: UiField(
            label: 'Image count',
            hintText: 'For example, 12',
            keyboardType: TextInputType.number,
            inputFormatters: <TextInputFormatter>[
              FilteringTextInputFormatter.digitsOnly,
            ],
            helpText: 'Digits only; the caller validates the allowed range.',
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiTextArea',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Supporting text and counter',
        builder: (BuildContext context) {
          final String text = context.knobs.string(
            label: 'Initial text',
            initialValue: 'The date on the handwritten label reads 1946.',
            maxLines: 4,
          );
          return _InputFrame(
            description:
                'Multiline text preserves native selection, newline entry and scrolling. Height grows from three to six lines. A character limit counts user-perceived characters, including composed emoji.',
            child: _TextDemo(
              key: ValueKey<String>(text),
              text: text,
              state: _state(context),
              multiline: true,
              counter: context.knobs.boolean(
                label: 'Character count',
                initialValue: true,
              ),
            ),
          );
        },
      ),
      WidgetbookUseCase(
        name: 'Empty validation state',
        builder: (_) => const _InputFrame(
          description:
              'An explicit error explains how to recover while retaining the field label.',
          child: UiTextArea(
            label: 'Reason for the correction',
            hintText: 'Describe the evidence you used',
            errorText:
                'Enter a reason so the next reviewer can follow this correction.',
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSearchField',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Filter, clear and submit',
        builder: (BuildContext context) => _InputFrame(
          description:
              'Search icon and clear action share field anatomy. Escape clears a query, then releases focus on the next press. Enter submits. A supplied onEscape can instead dismiss a containing search surface.',
          child: _SearchDemo(
            enabled: context.knobs.boolean(
              label: 'Enabled',
              initialValue: true,
            ),
            showLabel: context.knobs.boolean(
              label: 'Visible label',
              initialValue: true,
            ),
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Disabled with a reason',
        builder: (_) => const _InputFrame(
          description:
              'Disabling search removes editing without replacing its accessible name.',
          child: UiSearchField(
            label: 'Search specimens',
            clearLabel: 'Clear specimen search',
            hintText: 'Search by catalogue number',
            enabled: false,
            disabledReason: 'Select a collection before searching.',
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSelect',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Short list and validation',
        builder: (BuildContext context) => _InputFrame(
          description:
              'A field trigger opens owned option rows. Enter/Space opens, arrows move real focus and Escape closes with focus returned to the trigger. Selected state remains controlled.',
          child: _SelectDemo(
            enabled: context.knobs.boolean(
              label: 'Enabled',
              initialValue: true,
            ),
            error: context.knobs.boolean(label: 'Validation error'),
            many: false,
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Filterable long list',
        builder: (BuildContext context) => _InputFrame(
          description:
              'Lists of more than eight options gain an accessible filter field. Type to narrow, move with arrows and activate with Enter. No remote lookup is performed.',
          child: _SelectDemo(
            enabled: context.knobs.boolean(
              label: 'Enabled',
              initialValue: true,
            ),
            error: context.knobs.boolean(label: 'Validation error'),
            many: true,
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Empty options',
        builder: (_) => const _InputFrame(
          description:
              'An empty option collection disables the trigger and retains its reason.',
          child: UiSelect<String>(
            label: 'Collection',
            value: null,
            placeholder: 'No collections available',
            options: <UiSelectOption<String>>[],
            disabledReason: 'Your account does not yet have a collection.',
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiCheckbox',
    useCases: <WidgetbookUseCase>[
      for (final size in UiSelectionControlSize.values)
        WidgetbookUseCase(
          name: 'Supporting text · ${size.name}',
          builder: (_) => _InputFrame(
            description:
                'A compact visual control retains the 48 dp target, full semantic label and supporting explanation. The second example demonstrates a visually hidden label.',
            child: _SelectionAnatomy('UiCheckbox', size),
          ),
        ),

      WidgetbookUseCase(
        name: 'Checked, unchecked and mixed',
        builder: (BuildContext context) => _InputFrame(
          description:
              'The parent box is mixed when only some child items are selected. Activating mixed selects all. The full row has a minimum 48 dp hit target and a checkbox semantic role.',
          child: _CheckboxDemo(
            enabled: context.knobs.boolean(
              label: 'Enabled',
              initialValue: true,
            ),
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Disabled with reason',
        builder: (_) => const _InputFrame(
          description:
              'The reason remains available to assistive technology and the disabled state never toggles.',
          child: UiCheckbox(
            label: 'Include original photographs',
            value: true,
            disabledReason:
                'Original photographs are required for this collection.',
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiRadioGroup',
    useCases: <WidgetbookUseCase>[
      for (final size in UiSelectionControlSize.values)
        WidgetbookUseCase(
          name: 'Supporting text · ${size.name}',
          builder: (_) => _InputFrame(
            description:
                'Supporting text and hidden-label variants preserve the native radio group keyboard contract and a 48 dp target.',
            child: _SelectionAnatomy('UiRadio', size),
          ),
        ),

      WidgetbookUseCase(
        name: 'Exclusive options and keyboard navigation',
        builder: (BuildContext context) => _InputFrame(
          description:
              'UiRadio belongs inside UiRadioGroup. The group supplies a legend and a single controlled value; arrows move among enabled exclusive options. Unsupported choices explain why they are disabled.',
          child: _RadioDemo(
            enabled: context.knobs.boolean(
              label: 'Enabled',
              initialValue: true,
            ),
            showLabel: context.knobs.boolean(
              label: 'Visible group label',
              initialValue: true,
            ),
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Unselected options',
        builder: (_) => const _InputFrame(
          description:
              'No initial selection is represented by null, rather than silently choosing the first option.',
          child: _RadioDemo(initial: null, enabled: true, showLabel: true),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSwitch',
    useCases: <WidgetbookUseCase>[
      for (final size in UiSelectionControlSize.values)
        WidgetbookUseCase(
          name: 'Supporting text · ${size.name}',
          builder: (_) => _InputFrame(
            description:
                'A compact visual control retains the 48 dp target, full semantic label and supporting explanation. The second example demonstrates a visually hidden label.',
            child: _SelectionAnatomy('UiSwitch', size),
          ),
        ),

      WidgetbookUseCase(
        name: 'Immediate on and off setting',
        builder: (BuildContext context) => _InputFrame(
          description:
              'A switch changes a setting immediately. The entire label row is interactive; semantic toggled state, keyboard activation and reduced-motion behavior are built in.',
          child: _SwitchDemo(
            enabled: context.knobs.boolean(
              label: 'Enabled',
              initialValue: true,
            ),
            label: context.knobs.string(
              label: 'Label',
              initialValue: 'Show original label text',
            ),
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Disabled on and off',
        builder: (_) => const _InputFrame(
          description:
              'Both disabled values retain their meaning and an explanation.',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              UiSwitch(
                label: 'Keep an audit trail',
                value: true,
                disabledReason:
                    'An audit trail is required for every correction.',
              ),
              SizedBox(height: 16),
              UiSwitch(
                label: 'Send background notifications',
                value: false,
                disabledReason: 'Notification permission has not been granted.',
              ),
            ],
          ),
        ),
      ),
    ],
  ),
];

class _InputFrame extends StatelessWidget {
  const _InputFrame({required this.description, required this.child});
  final String description;
  final Widget child;
  @override
  Widget build(BuildContext context) => Align(
    alignment: AlignmentDirectional.topStart,
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 620),
      child: SingleChildScrollView(
        child: Padding(
          padding: EdgeInsets.all(context.ui.space.s4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                description,
                style: context.ui.type.bodySmall.copyWith(
                  color: context.ui.color.inkSecondary,
                ),
              ),
              SizedBox(height: context.ui.space.s5),
              child,
            ],
          ),
        ),
      ),
    ),
  );
}

class _TextDemo extends StatefulWidget {
  const _TextDemo({
    super.key,
    required this.text,
    required this.state,
    this.multiline = false,
    this.shape = UiFieldShape.box,
    this.leading = false,
    this.clear = false,
    this.counter = false,
  });
  final String text;
  final _InputState state;
  final bool multiline;
  final UiFieldShape shape;
  final bool leading;
  final bool clear;
  final bool counter;
  @override
  State<_TextDemo> createState() => _TextDemoState();
}

class _TextDemoState extends State<_TextDemo> {
  late final TextEditingController _text = TextEditingController(
    text: widget.text,
  );
  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bool enabled = widget.state != _InputState.disabled;
    final bool readOnly = widget.state == _InputState.readOnly;
    final String? error = widget.state == _InputState.error
        ? 'Enter a value supported by the specimen label.'
        : null;
    const String reason =
        'This record is locked while another reviewer saves it.';
    if (widget.multiline) {
      return UiTextArea(
        label: 'Reason for the correction',
        controller: _text,
        helpText: 'Keep the observation separate from your interpretation.',
        errorText: error,
        enabled: enabled,
        readOnly: readOnly,
        disabledReason: enabled ? null : reason,
        maxLength: widget.counter ? 200 : null,
      );
    }
    return UiField(
      label: 'Catalogue number',
      controller: _text,
      hintText: 'Enter the number as written',
      helpText: 'Preserve spaces and punctuation from the label.',
      errorText: error,
      leading: widget.leading ? UiIcons.record : null,
      clearLabel: widget.clear ? 'Clear catalogue number' : null,
      enabled: enabled,
      readOnly: readOnly,
      disabledReason: enabled ? null : reason,
      maxLength: widget.counter ? 80 : null,
      shape: widget.shape,
    );
  }
}

class _CredentialsDemo extends StatefulWidget {
  const _CredentialsDemo({required this.enabled});
  final bool enabled;
  @override
  State<_CredentialsDemo> createState() => _CredentialsDemoState();
}

class _CredentialsDemoState extends State<_CredentialsDemo> {
  bool _obscured = true;
  @override
  Widget build(BuildContext context) => AutofillGroup(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        UiField(
          label: 'Email address',
          hintText: 'name@example.org',
          leading: UiIcons.email,
          keyboardType: TextInputType.emailAddress,
          textInputAction: TextInputAction.next,
          autofillHints: const <String>[AutofillHints.email],
          autocorrect: false,
          enabled: widget.enabled,
          disabledReason: widget.enabled
              ? null
              : 'A sign-in request is in progress.',
        ),
        SizedBox(height: context.ui.space.s4),
        UiField(
          label: 'Password',
          obscureText: _obscured,
          autocorrect: false,
          autofillHints: const <String>[AutofillHints.password],
          textInputAction: TextInputAction.done,
          enabled: widget.enabled,
          disabledReason: widget.enabled
              ? null
              : 'A sign-in request is in progress.',
          trailing: UiIconButton(
            icon: _obscured ? UiIcons.show : UiIcons.unreadable,
            semanticsLabel: _obscured ? 'Show password' : 'Hide password',
            onPressed: widget.enabled
                ? () => setState(() => _obscured = !_obscured)
                : null,
          ),
        ),
      ],
    ),
  );
}

class _SearchDemo extends StatefulWidget {
  const _SearchDemo({required this.enabled, required this.showLabel});
  final bool enabled;
  final bool showLabel;
  @override
  State<_SearchDemo> createState() => _SearchDemoState();
}

class _SearchDemoState extends State<_SearchDemo> {
  String _query = '';
  String _submission = 'No submitted search.';
  static const List<String> _specimens = <String>[
    'FMNH 1946 0042 · Butterfly',
    'FMNH 1946 0043 · Fern',
    'FMNH 1952 0018 · Beetle',
  ];
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: <Widget>[
      UiSearchField(
        label: 'Search specimens',
        clearLabel: 'Clear specimen search',
        hintText: 'Catalogue number or specimen',
        showLabel: widget.showLabel,
        enabled: widget.enabled,
        disabledReason: widget.enabled
            ? null
            : 'Select a collection before searching.',
        onChanged: (String query) => setState(() => _query = query),
        onSubmitted: (String query) =>
            setState(() => _submission = 'Submitted: $query'),
      ),
      SizedBox(height: context.ui.space.s3),
      for (final String specimen in _specimens.where(
        (String text) => text.toLowerCase().contains(_query.toLowerCase()),
      ))
        Padding(
          padding: EdgeInsets.symmetric(vertical: context.ui.space.s2),
          child: Text(specimen),
        ),
      Text(
        _submission,
        style: context.ui.type.bodySmall.copyWith(
          color: context.ui.color.inkSecondary,
        ),
      ),
    ],
  );
}

class _SelectDemo extends StatefulWidget {
  const _SelectDemo({
    required this.enabled,
    required this.error,
    required this.many,
  });
  final bool enabled;
  final bool error;
  final bool many;
  @override
  State<_SelectDemo> createState() => _SelectDemoState();
}

class _SelectDemoState extends State<_SelectDemo> {
  String? _value;
  @override
  Widget build(BuildContext context) => UiSelect<String>(
    label: widget.many ? 'Collection' : 'Evidence state',
    value: _value,
    placeholder: 'Choose an option',
    options: widget.many
        ? <UiSelectOption<String>>[
            for (int index = 1; index <= 12; index++)
              UiSelectOption<String>(
                value: '$index',
                label: 'Collection $index',
                leading: UiIcons.collection,
              ),
          ]
        : const <UiSelectOption<String>>[
            UiSelectOption<String>(
              value: 'supported',
              label: 'Supported',
              leading: UiIcons.check,
            ),
            UiSelectOption<String>(
              value: 'unknown',
              label: 'Unknown',
              leading: UiIcons.unknown,
            ),
            UiSelectOption<String>(
              value: 'absent',
              label: 'Not present',
              leading: UiIcons.notPresent,
            ),
          ],
    onChanged: widget.enabled
        ? (String value) => setState(() => _value = value)
        : null,
    helpText: 'The accepted value remains owned by the caller.',
    errorText: widget.error ? 'Choose an option before continuing.' : null,
    disabledReason: widget.enabled
        ? null
        : 'Selection is unavailable while this record saves.',
  );
}

class _CheckboxDemo extends StatefulWidget {
  const _CheckboxDemo({required this.enabled});
  final bool enabled;
  @override
  State<_CheckboxDemo> createState() => _CheckboxDemoState();
}

class _CheckboxDemoState extends State<_CheckboxDemo> {
  final List<bool> _selected = <bool>[true, false, false];
  @override
  Widget build(BuildContext context) {
    final bool? all = _selected.every((bool value) => value)
        ? true
        : _selected.every((bool value) => !value)
        ? false
        : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        UiCheckbox(
          label: 'Select all photographs',
          value: all,
          onChanged: widget.enabled
              ? (bool value) => setState(
                  () => _selected.fillRange(0, _selected.length, value),
                )
              : null,
          disabledReason: widget.enabled ? null : 'Selection is locked.',
        ),
        for (int index = 0; index < _selected.length; index++)
          UiCheckbox(
            label: 'Photograph ${index + 1}',
            value: _selected[index],
            onChanged: widget.enabled
                ? (bool value) => setState(() => _selected[index] = value)
                : null,
            disabledReason: widget.enabled ? null : 'Selection is locked.',
          ),
      ],
    );
  }
}

class _RadioDemo extends StatefulWidget {
  const _RadioDemo({
    required this.enabled,
    required this.showLabel,
    this.initial = 'original',
  });
  final bool enabled;
  final bool showLabel;
  final String? initial;
  @override
  State<_RadioDemo> createState() => _RadioDemoState();
}

class _RadioDemoState extends State<_RadioDemo> {
  late String? _value = widget.initial;
  @override
  Widget build(BuildContext context) => UiRadioGroup<String>(
    label: 'Image view',
    showLabel: widget.showLabel,
    value: _value,
    onChanged: (String? value) => setState(() => _value = value),
    helpText: 'One view is selected at a time.',
    children: <Widget>[
      UiRadio<String>(
        label: 'Original photograph',
        value: 'original',
        enabled: widget.enabled,
        disabledReason: widget.enabled ? null : 'Image settings are locked.',
      ),
      UiRadio<String>(
        label: 'Label regions',
        value: 'regions',
        enabled: widget.enabled,
        disabledReason: widget.enabled ? null : 'Image settings are locked.',
      ),
      const UiRadio<String>(
        label: 'Processed image',
        value: 'processed',
        enabled: false,
        disabledReason: 'Processing has not finished.',
      ),
    ],
  );
}

class _SwitchDemo extends StatefulWidget {
  const _SwitchDemo({required this.enabled, required this.label});
  final bool enabled;
  final String label;
  @override
  State<_SwitchDemo> createState() => _SwitchDemoState();
}

class _SwitchDemoState extends State<_SwitchDemo> {
  bool _value = true;
  @override
  Widget build(BuildContext context) => UiSwitch(
    label: widget.label,
    value: _value,
    onChanged: widget.enabled
        ? (bool value) => setState(() => _value = value)
        : null,
    disabledReason: widget.enabled ? null : 'Display preferences are locked.',
  );
}

class _SelectionAnatomy extends StatefulWidget {
  const _SelectionAnatomy(this.component, this.size);
  final String component;
  final UiSelectionControlSize size;
  @override
  State<_SelectionAnatomy> createState() => _SelectionAnatomyState();
}

class _SelectionAnatomyState extends State<_SelectionAnatomy> {
  bool _value = false;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (final showLabel in [true, false])
        if (widget.component == 'UiCheckbox')
          UiCheckbox(
            label: 'Include reviewed records',
            supporting:
                'Show records that have already been confirmed by a reviewer.',
            value: _value,
            shape: UiCheckboxShape.circle,
            size: widget.size,
            showLabel: showLabel,
            onChanged: (value) => setState(() => _value = value),
          )
        else if (widget.component == 'UiRadio')
          UiRadioGroup<bool>(
            label: 'Review method',
            value: _value,
            onChanged: (value) => setState(() => _value = value ?? false),
            children: [
              UiRadio<bool>(
                label: 'Assisted review',
                supporting:
                    'Retain the original evidence beside the model reading.',
                value: true,
                size: widget.size,
                showLabel: showLabel,
              ),
              UiRadio<bool>(
                label: 'Manual review',
                value: false,
                size: widget.size,
                showLabel: showLabel,
              ),
            ],
          )
        else
          UiSwitch(
            label: 'Show collection activity',
            supporting: 'Keep recent changes visible beside the collection.',
            value: _value,
            size: widget.size,
            showLabel: showLabel,
            onChanged: (value) => setState(() => _value = value),
          ),
    ],
  );
}
