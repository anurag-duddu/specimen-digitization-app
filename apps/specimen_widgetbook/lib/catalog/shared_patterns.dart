import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

import '../story.dart';

/// Reference-equivalent shared anatomy with actual controlled interactions.
List<WidgetbookComponent> get sharedPatternComponents => [
  WidgetbookComponent(
    name: 'UiActionButton',
    useCases: [
      for (final hierarchy in UiActionHierarchy.values)
        for (final tone in UiActionTone.values)
          story(
            '${hierarchy.name} · ${tone.name}',
            'Independent hierarchy and semantic tone. All five sizes keep a 48 dp target. Use the environment controls to inspect contrast and large text.',
            (context) => ActionExample(
              builder: (_, report) => Wrap(
                spacing: context.ui.space.s3,
                runSpacing: context.ui.space.s3,
                children: [
                  for (final size in UiActionSize.values)
                    UiActionButton(
                      label: size.name,
                      hierarchy: hierarchy,
                      tone: tone,
                      size: size,
                      leading: UiIcons.add,
                      onPressed: () => report('Activated ${size.name}'),
                    ),
                ],
              ),
            ),
          ),
      story(
        'Content and availability',
        'Dot, trailing icon, icon-only, busy and unavailable states retain complete action names.',
        (_) => ActionExample(
          builder: (_, report) => Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              UiActionButton(
                label: 'Connected',
                leadingDot: true,
                onPressed: () => report('Connected'),
              ),
              UiActionButton(
                label: 'Continue',
                trailing: UiIcons.next,
                onPressed: () => report('Continue'),
              ),
              UiActionButton(
                label: 'Add record',
                leading: UiIcons.add,
                iconOnly: true,
                onPressed: () => report('Added'),
              ),
              const UiActionButton(label: 'Saving', busy: true),
              const UiActionButton(
                label: 'Export',
                disabledReason: 'Select a record first.',
              ),
            ],
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiButtonGroup',
    useCases: [
      for (final iconOnly in [false, true])
        story(
          iconOnly ? 'Icon commands' : 'Joined commands',
          'Arrow keys move focus without issuing a command. Enter or Space activates. The group stacks when its full labels cannot fit.',
          (_) => ActionExample(
            builder: (_, report) => UiButtonGroup(
              label: 'Editing commands',
              iconOnly: iconOnly,
              items: [
                UiButtonGroupItem(
                  label: 'Undo',
                  icon: UiIcons.undo,
                  onPressed: () => report('Undo'),
                ),
                const UiButtonGroupItem(
                  label: 'Redo',
                  icon: UiIcons.next,
                  disabledReason: 'There is no later edit.',
                ),
                UiButtonGroupItem(
                  label: 'Save',
                  leadingDot: true,
                  icon: UiIcons.check,
                  selected: true,
                  onPressed: () => report('Save'),
                ),
              ],
            ),
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiStatusBadge',
    useCases: [
      story(
        'Identity, icon-only and close actions',
        'Avatar and country artwork use the same identity slot. Icon-only badges retain a full accessible label; a close action stays separately named.',
        (_) => ActionExample(
          builder: (_, report) => Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              UiStatusBadge(
                label: 'Verified identity',
                leading: const UiIcon(UiIcons.check),
                iconOnly: true,
                brand: true,
              ),
              UiStatusBadge(
                label: 'Avery Chen',
                leading: const UiAvatar(
                  name: 'Avery Chen',
                  size: UiAvatarSize.extraSmall,
                ),
                onRemove: () => report('Removed Avery Chen'),
              ),
            ],
          ),
        ),
      ),

      for (final emphasis in UiBadgeEmphasis.values)
        for (final shape in UiBadgeShape.values)
          story(
            '${emphasis.name} · ${shape.name}',
            'Neutral, brand and functional state colors replace ornamental palette expansion. Badge meaning is always textual.',
            (context) => Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                for (final size in UiAnnotationSize.values) ...[
                  UiStatusBadge(
                    label: 'Collection',
                    size: size,
                    emphasis: emphasis,
                    shape: shape,
                  ),
                  UiStatusBadge(
                    label: 'Featured',
                    brand: true,
                    size: size,
                    emphasis: emphasis,
                    shape: shape,
                    leading: const UiIcon(
                      UiIcons.check,
                      size: UiIconSize.inline,
                    ),
                  ),
                  UiStatusBadge(
                    label: 'Needs review',
                    status: context.ui.color.status.needsReview,
                    size: size,
                    emphasis: emphasis,
                    shape: shape,
                  ),
                ],
              ],
            ),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiBadgeGroup',
    useCases: [
      for (final trailing in [false, true])
        story(
          trailing ? 'Trailing badge' : 'Leading badge',
          'One announcement and one optional action. Complete text wraps at narrow widths.',
          (_) => ActionExample(
            builder: (_, report) => UiBadgeGroup(
              badge: const UiStatusBadge(label: 'New', brand: true),
              label: 'Review the collection update',
              badgeTrailing: trailing,
              onPressed: () => report('Opened update'),
            ),
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiTag',
    useCases: [
      story(
        'Unavailable actions',
        'A disabled tag keeps its selection, anatomy and explanation while suppressing both selection and removal.',
        (_) => UiTag(
          label: 'Restricted collection',
          selected: true,
          enabled: false,
          disabledReason: 'Collection access is required.',
          onSelected: (_) {},
          onRemove: () {},
        ),
      ),

      story(
        'Checkbox, identity, count and remove',
        'Selection and removal are separate accessible actions. Remove a tag, toggle its checkbox, or reset the set.',
        (_) => const _SharedDemo('tags'),
      ),
      story(
        'Size and informational tags',
        'Sizes change visual density while interactive forms preserve touch targets.',
        (_) => Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            for (final size in UiAnnotationSize.values)
              UiTag(label: size.name, count: 24, size: size),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiProviderButton',
    useCases: [
      story(
        'Provider identity slot',
        'Supply approved provider artwork. This example uses a clearly labeled specimen identity placeholder and only records local actions.',
        (_) => ActionExample(
          builder: (_, report) => Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final inverse in [false, true])
                UiProviderButton(
                  label: 'Continue with institution',
                  supporting: 'Museum account',
                  mark: const UiIcon(UiIcons.collection),
                  inverse: inverse,
                  onPressed: () => report('Institution selected'),
                ),
              UiProviderButton(
                label: 'Continue with institution',
                mark: const UiIcon(UiIcons.collection),
                iconOnly: true,
                onPressed: () => report('Institution selected'),
              ),
              const UiProviderButton(
                label: 'Institution unavailable',
                mark: UiIcon(UiIcons.collection),
                disabledReason: 'Provider setup is incomplete.',
              ),
            ],
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiStoreBadge',
    useCases: [
      story(
        'Store artwork and destination slots',
        'Supply the store’s approved artwork, caption, name and destination. The placeholder is visibly generic; this story opens no store.',
        (_) => ActionExample(
          builder: (_, report) => Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final inverse in [false, true])
                UiStoreBadge(
                  storeName: 'Mobile application',
                  caption: 'Download from your store',
                  mark: const UiIcon(UiIcons.download),
                  inverse: inverse,
                  onPressed: () => report('Store selected'),
                ),
            ],
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiCombobox',
    useCases: [
      for (final multiple in [false, true])
        story(
          multiple ? 'Search and multiple tags' : 'Search and single value',
          'Filter by label, description or keyword. Arrows move through enabled options; Enter selects; Escape dismisses and restores the trigger. Groups and avatars stay attached to options.',
          (_) => _SharedDemo(multiple ? 'multi-combobox' : 'combobox'),
        ),
      story(
        'Loading, empty and unavailable',
        'These are explicit host states, never fabricated search results.',
        (_) => const Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            UiCombobox<String>(
              label: 'Loading collectors',
              options: [],
              selected: {},
              loading: true,
            ),
            UiCombobox<String>(
              label: 'Restricted collectors',
              options: [],
              selected: {},
              disabledReason: 'You need collection access.',
            ),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSelectionCards',
    useCases: [
      for (final mode in UiSelectionMode.values)
        story(
          mode.name,
          'Icon, avatar, supporting content and trailing-detail slots. Single selection follows arrow keys; multiple selection uses Space. Unavailable choices retain a reason.',
          (_) => _SharedDemo(
            mode == UiSelectionMode.single ? 'single-cards' : 'cards',
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiVerificationCode',
    useCases: [
      for (final digits in [4, 6])
        story(
          '$digits digits',
          'Paste a complete code, use native one-time-code autofill, or type one digit at a time. Cells preserve numeric order in RTL and wrap at large text. This story performs no authentication.',
          (_) => _SharedDemo('code-$digits'),
        ),
      story(
        'Expired and unavailable',
        'Errors remain visible alongside the complete form label.',
        (_) => const UiVerificationCode(
          label: 'Email verification code',
          value: '',
          disabledReason: 'Request a new code.',
          errorText: 'This code has expired.',
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiTagField',
    useCases: [
      story(
        'Create and remove tags',
        'Enter adds a trimmed unique tag. Backspace in an empty editor removes the last tag. Changes remain local to this example.',
        (_) => const _SharedDemo('tag-field'),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiInputGroup',
    useCases: [
      story(
        'Leading and trailing controls',
        'Independent country/unit/action controls retain separate focus and semantics. The group stacks at narrow widths and enlarged type.',
        (_) => const _SharedDemo('input-group'),
      ),
      story(
        'Static affixes',
        'Prefix and suffix text stay attached to the input, with the form label providing the accessible meaning.',
        (_) => const UiField(
          label: 'Collection URL',
          prefixText: 'https://',
          suffixText: '.museum',
          hintText: 'collection',
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiPhoneField',
    useCases: [
      story(
        'Explicit country and native phone editing',
        'Country choices are supplied by the host. The field preserves the number verbatim and exposes the telephone keyboard and autofill hints.',
        (_) => const _SharedDemo('phone'),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiTextToolbar',
    useCases: [
      story(
        'Controlled formatting commands',
        'The toolbar emits a real command and displays host-provided active marks. A rich-text host owns selection, document editing, undo and serialization; this story shows the command contract.',
        (_) => const _SharedDemo('toolbar'),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiRangeSlider',
    useCases: [
      for (final position in UiRangeLabelPosition.values)
        story(
          position.name,
          'Two independently named thumbs cannot cross. Drag, arrow, Page, Home and End keys propose values. Labels merge when nearby floating values would collide.',
          (_) => _SharedDemo('range-${position.name}'),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiDateRangePicker',
    useCases: [
      story(
        'Two calendars and preset transactions',
        'Select dates in either order or type YYYY-MM-DD endpoints. Typed dates validate calendar validity, ordering and bounds. Apply commits the draft; Cancel restores the accepted value. Narrow layouts show one calendar and scrollable dates when necessary.',
        (_) => const _SharedDemo('date-range'),
      ),
      story(
        'Immediate range selection',
        'A complete two-date selection commits immediately. Values are date-only UTC calendar dates, never local-midnight instants.',
        (_) => const _SharedDemo('date-range-immediate'),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiDateRangeField',
    useCases: [
      story(
        'Adaptive range dialog',
        'The trigger opens the shared modal route with focus containment and restoration. Apply commits a complete range; Escape or Cancel leaves the value unchanged.',
        (_) => const _SharedDemo('date-field'),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiAvatarGroup',
    useCases: [
      story(
        'Identity overlap and overflow',
        'All members remain announced when only a subset fits. The add-person action has its own target and name.',
        (context) => ActionExample(
          builder: (_, report) => UiAvatarGroup(
            label: 'Collection reviewers',
            people: const [
              UiAvatarPerson(name: 'Avery Chen'),
              UiAvatarPerson(name: 'Morgan Rivera'),
              UiAvatarPerson(name: 'Sam Okafor'),
              UiAvatarPerson(name: 'Taylor Singh'),
              UiAvatarPerson(name: 'Robin Patel'),
              UiAvatarPerson(name: 'Jordan Lee'),
            ],
            maxVisible: context.knobs.int.slider(
              label: 'Visible limit',
              min: 1,
              max: 6,
              initialValue: 4,
            ),
            onAdd: () => report('Add reviewer requested'),
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiAvatarLabel',
    useCases: [
      for (final status in UiAvatarStatus.values)
        story(
          status.name,
          'The person’s full name and status remain readable; image failures fall back to initials.',
          (_) => UiAvatarLabel(
            name: 'Avery Chen',
            supporting: 'Collections reviewer',
            status: status,
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiProgressDisplay',
    useCases: [
      for (final form in UiProgressDisplayForm.values)
        for (final position in UiProgressLabelPosition.values)
          story(
            '${form.name} · ${position.name}',
            'The exact host-reported metric is shown, including downward corrections. Floating values stay within the allocation. No completion is inferred.',
            (context) => UiProgressDisplay(
              label: 'Collection coverage',
              supporting: 'Verified catalogue records',
              value: context.knobs.double.slider(
                label: 'Reported value',
                min: 0,
                max: 1,
                initialValue: .64,
              ),
              form: form,
              labelPosition: position,
            ),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiLoadingIndicator',
    useCases: [
      for (final style in UiLoadingIndicatorStyle.values)
        story(
          style.name,
          'Indeterminate waiting has an accessible description. Reduced motion freezes every visual form without scheduling repeating animation.',
          (_) => UiLoadingIndicator(label: 'Reading collection', style: style),
        ),
    ],
  ),
];

class _SharedDemo extends StatefulWidget {
  const _SharedDemo(this.kind);
  final String kind;
  @override
  State<_SharedDemo> createState() => _SharedDemoState();
}

class _SharedDemoState extends State<_SharedDemo> {
  Set<String> _selected = {'avery'};
  Set<int> _cards = {1};
  List<String> _tags = ['Entomology', 'Verified'];
  String _code = '';
  String? _country;
  String _receipt = 'No action yet';
  Set<UiTextFormat> _marks = {};
  UiRangeValues _range = const UiRangeValues(25, 75);
  UiDateRange? _dates;
  final _text = TextEditingController();
  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  List<UiDateRangePreset> get _presets => [
    UiDateRangePreset(
      label: 'October',
      range: UiDateRange(DateTime.utc(2026, 10, 1), DateTime.utc(2026, 10, 31)),
    ),
    UiDateRangePreset(
      label: 'Autumn',
      range: UiDateRange(DateTime.utc(2026, 9, 1), DateTime.utc(2026, 11, 30)),
    ),
  ];
  @override
  Widget build(BuildContext context) {
    final kind = widget.kind;
    Widget child;
    if (kind == 'tags') {
      child = Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [
          for (final tag in _tags)
            UiTag(
              label: tag,
              leading: const UiAvatar(
                name: 'Avery Chen',
                size: UiAvatarSize.extraSmall,
              ),
              count: 12,
              selected: _selected.contains(tag),
              onSelected: (value) => setState(
                () => value ? _selected.add(tag) : _selected.remove(tag),
              ),
              onRemove: () => setState(() => _tags.remove(tag)),
            ),
          UiButton(
            label: 'Reset tags',
            variant: UiButtonVariant.ghost,
            onPressed: () => setState(() => _tags = ['Entomology', 'Verified']),
          ),
        ],
      );
    } else if (kind.endsWith('combobox')) {
      child = UiCombobox<String>(
        label: 'Collectors',
        selected: _selected,
        multiple: kind.startsWith('multi'),
        onChanged: (value) => setState(() => _selected = value),
        header: const Text('Museum collaborators'),
        options: const [
          UiComboboxOption(
            value: 'avery',
            label: 'Avery Chen',
            supporting: 'Entomology',
            group: 'Reviewers',
            keywords: ['insects'],
            leading: UiAvatar(name: 'Avery Chen', size: UiAvatarSize.small),
          ),
          UiComboboxOption(
            value: 'morgan',
            label: 'Morgan Rivera',
            supporting: 'Botany',
            group: 'Reviewers',
            leading: UiAvatar(name: 'Morgan Rivera', size: UiAvatarSize.small),
          ),
          UiComboboxOption(
            value: 'sam',
            label: 'Sam Okafor',
            group: 'Curators',
          ),
          UiComboboxOption(
            value: 'unavailable',
            label: 'Archived collaborator',
            group: 'Curators',
            enabled: false,
            disabledReason: 'This account is archived.',
          ),
        ],
      );
    } else if (kind.endsWith('cards')) {
      child = UiSelectionCards<int>(
        label: 'Review method',
        selected: _cards,
        mode: kind.startsWith('single')
            ? UiSelectionMode.single
            : UiSelectionMode.multiple,
        onChanged: (value) => setState(() => _cards = value),
        options: const [
          UiSelectionCardOption(
            value: 1,
            label: 'Assisted transcription',
            supporting: 'Read labels while preserving the original evidence.',
            leading: UiIcon(UiIcons.record),
          ),
          UiSelectionCardOption(
            value: 2,
            label: 'Expert review',
            supporting: 'Assign the record to a collection reviewer.',
            leading: UiAvatar(name: 'Avery Chen'),
            trailing: Text('Recommended'),
          ),
          UiSelectionCardOption(
            value: 3,
            label: 'External service',
            supporting: 'Requires a configured connection.',
            enabled: false,
            disabledReason: 'No connection is configured.',
          ),
        ],
      );
    } else if (kind.startsWith('code-')) {
      child = UiVerificationCode(
        label: 'Email verification code',
        value: _code,
        length: int.parse(kind.substring(5)),
        onChanged: (value) => setState(() => _code = value),
        onCompleted: (value) => setState(() => _receipt = 'Entered $value'),
        helpText: 'Enter the code from the email.',
      );
    } else if (kind == 'tag-field') {
      child = UiTagField(
        label: 'Collection tags',
        values: _tags,
        onChanged: (value) => setState(() => _tags = value),
      );
    } else if (kind == 'input-group') {
      child = UiInputGroup(
        leading: UiSelect<String>(
          label: 'Protocol',
          placeholder: 'Choose protocol',
          value: _country,
          options: const [
            UiSelectOption(value: 'https', label: 'HTTPS'),
            UiSelectOption(value: 'ftp', label: 'SFTP'),
          ],
          onChanged: (value) => setState(() => _country = value),
        ),
        field: UiField(label: 'Collection address', controller: _text),
        trailing: UiButton(
          label: 'Copy address',
          onPressed: () => setState(
            () => _receipt =
                'Selected ${_text.text.isEmpty ? 'empty address' : _text.text}',
          ),
        ),
      );
    } else if (kind == 'phone') {
      child = UiPhoneField(
        label: 'Contact phone',
        controller: _text,
        countryCode: _country,
        countries: const [
          UiPhoneCountry(code: 'US', name: 'United States', dialingCode: '+1'),
          UiPhoneCountry(
            code: 'GB',
            name: 'United Kingdom',
            dialingCode: '+44',
          ),
          UiPhoneCountry(code: 'IN', name: 'India', dialingCode: '+91'),
        ],
        onCountryChanged: (value) => setState(() => _country = value),
      );
    } else if (kind == 'toolbar') {
      child = UiTextToolbar(
        active: _marks,
        onCommand: (command) => setState(() {
          _marks = Set.of(_marks);
          _marks.contains(command)
              ? _marks.remove(command)
              : _marks.add(command);
          _receipt = 'Formatting command: ${command.name}';
        }),
      );
    } else if (kind.startsWith('range-')) {
      child = UiRangeSlider(
        label: 'Capture quality bounds',
        values: _range,
        min: 0,
        max: 100,
        divisions: 20,
        valueLabel: (value) => '${value.round()}%',
        labelPosition: UiRangeLabelPosition.values.byName(kind.substring(6)),
        onChanged: (value) => setState(() => _range = value),
        onChangeEnd: (value) => setState(
          () => _receipt =
              'Accepted ${value.start.round()}–${value.end.round()}%',
        ),
      );
    } else if (kind == 'date-field') {
      child = UiDateRangeField(
        label: 'Collected dates',
        value: _dates,
        firstDate: DateTime.utc(2026, 9, 1),
        lastDate: DateTime.utc(2026, 12, 31),
        presets: _presets,
        onChanged: (value) => setState(() => _dates = value),
      );
    } else {
      child = UiDateRangePicker(
        label: 'Collected dates',
        currentDate: DateTime.utc(2026, 10, 22),
        markedDates: {DateTime.utc(2026, 10, 12), DateTime.utc(2026, 10, 22)},
        value: _dates,
        firstDate: DateTime.utc(2026, 9, 1),
        lastDate: DateTime.utc(2026, 12, 31),
        presets: _presets,
        showActions: kind != 'date-range-immediate',
        onChanged: (value) => setState(() {
          _dates = value;
          _receipt =
              'Accepted ${value.start.toIso8601String().substring(0, 10)} through ${value.end.toIso8601String().substring(0, 10)}';
        }),
        onCancel: () => setState(() => _receipt = 'Draft cancelled'),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        child,
        const SizedBox(height: 16),
        Semantics(
          liveRegion: true,
          child: Text(_receipt, style: context.ui.type.bodySmall),
        ),
      ],
    );
  }
}
