import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

import '../story.dart';

const _commandGuidance =
    'One primary command per decision. Labels state the action; icon slots use Phosphor. Tab to focus; Enter or Space activates. Every visual size preserves a 48 dp target. Busy prevents duplicate submission.';

List<WidgetbookComponent> get actionComponents => [
  WidgetbookComponent(
    name: 'UiButton',
    useCases: [
      for (final variant in UiButtonVariant.values)
        for (final size in UiSize.values)
          for (final state in [
            'Rest',
            'Hover',
            'Pressed',
            'Focused',
            'Disabled',
            'Loading',
          ])
            story(
              '${variant.name} · ${size.name} · $state',
              _commandGuidance,
              (context) =>
                  _ButtonExample(variant: variant, size: size, state: state),
            ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiIconButton',
    useCases: [
      for (final variant in UiIconButtonVariant.values)
        for (final current in [false, true])
          story(
            '${variant.name} · ${current ? 'current' : 'rest'}',
            'Icon commands need a complete accessible name. Current state is persistent. Hover, focus or long press exposes the tooltip.',
            (context) => ActionExample(
              builder: (_, report) => Align(
                alignment: AlignmentDirectional.centerStart,
                child: UiIconButton(
                  icon: UiIcons.rotateView,
                  semanticsLabel: 'Rotate the specimen view',
                  tooltip: 'Rotate the specimen view',
                  current: current,
                  variant: variant,
                  onPressed: () => report('Rotated view'),
                ),
              ),
            ),
          ),
      story(
        'Disabled',
        'Unavailable commands retain a reason. Try tap, keyboard focus and pointer hover.',
        (_) => const UiIconButton(
          icon: UiIcons.rotateView,
          semanticsLabel: 'Rotate the specimen view',
          disabledReason: 'Wait for the image to finish loading.',
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiChip',
    useCases: [
      for (final variant in UiChipVariant.values)
        story(
          variant.name,
          'Tags describe; filters toggle; entered values expose a named remove action. Do not use a tag as a button.',
          (_) => _ChipExample(variant: variant),
        ),
      story(
        'Status roles',
        'Status words and icons carry meaning even without colour. Use functional roles, never a new category palette.',
        (context) => Wrap(
          spacing: context.ui.space.s2,
          runSpacing: context.ui.space.s2,
          children: [
            UiChip(
              label: 'Needs review',
              status: context.ui.color.status.needsReview,
              icon: UiIcons.needsReview,
            ),
            UiChip(
              label: 'Cleared',
              status: context.ui.color.status.cleared,
              icon: UiIcons.check,
            ),
            UiChip(
              label: 'Blocked',
              status: context.ui.color.status.blocked,
              icon: UiIcons.blocked,
            ),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiBadge',
    useCases: [
      for (final count in [0, 1, 24, 999])
        story(
          'Count $count',
          'Counts qualify an adjacent heading or destination; use a standalone accessible label.',
          (_) => Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiBadge(count, semanticsLabel: '$count records'),
          ),
        ),
      story(
        'Dot',
        'Use a dot only with a text or accessibility description of the change.',
        (_) => const UiBadge.dot(semanticsLabel: 'New activity'),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiKeyCap',
    useCases: [
      story(
        'Keyboard shortcut',
        'Display hints beside a real registered shortcut; this component does not register keys.',
        (_) => const Wrap(
          spacing: 8,
          children: [
            UiKeyCap(label: '⌘', semanticsLabel: 'Command'),
            UiKeyCap(label: 'K'),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiChoiceGroup',
    useCases: [
      for (final disabled in [false, true])
        story(
          disabled ? 'Disabled' : 'Interactive selection and reset',
          'Value filters wrap at narrow widths. Arrows move focus; Enter or Space selects. Explicit reset clears the filter.',
          (_) => _ChoiceExample(disabled: disabled),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiCapsuleToggle',
    useCases: [
      for (final selection in UiToggleSelection.values)
        for (final size in UiSize.values)
          story(
            '${selection.name} · ${size.name}',
            'Toggle independent values. Selection includes a check and outline. Single mode can clear its current value.',
            (_) => _ToggleExample(selection: selection, size: size),
          ),
      story(
        'Disabled',
        'Explain unavailable selection without removing the selected values.',
        (_) => const UiCapsuleToggle<String>(
          options: [
            UiToggleOption(value: 'a', label: 'Images'),
            UiToggleOption(value: 'b', label: 'Metadata'),
          ],
          selected: {'a'},
          onChanged: null,
          disabledReason: 'Wait for the current export.',
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSegmented',
    useCases: [
      for (final size in UiSize.values)
        story(
          size.name,
          'Two to five mutually exclusive modes. When labels cannot fit, the control falls back to an accessible select.',
          (_) => _SegmentExample(size: size),
        ),
      story(
        'Disabled',
        'Keep the selected mode visible while changes are unavailable.',
        (_) => const UiSegmented<int>(
          label: 'View',
          segments: [
            UiSegment(value: 0, label: 'List'),
            UiSegment(value: 1, label: 'Grid'),
          ],
          value: 0,
          onChanged: null,
          disabledReason: 'Wait for the image list.',
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiButtonRow',
    useCases: [
      story(
        'Responsive command group',
        'Actions become a full-width stack when labels cannot fit. Reading and focus order follow the visual arrangement.',
        (_) => ActionExample(
          builder: (_, report) => UiButtonRow(
            primary: UiButton(
              label: 'Save correction',
              onPressed: () => report('Saved correction'),
            ),
            secondary: UiButton(
              label: 'Cancel',
              variant: UiButtonVariant.secondary,
              onPressed: () => report('Cancelled'),
            ),
            tertiary: [
              UiButton(
                label: 'Preview changes',
                variant: UiButtonVariant.ghost,
                onPressed: () => report('Previewed changes'),
              ),
            ],
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiDecisionBar',
    useCases: [
      story(
        'Decisions and record navigation',
        'Keeps the primary decision available; secondary commands move into overflow at narrow widths. This is a synthetic action receipt, not a Queue transition.',
        (_) => ActionExample(
          builder: (_, report) => UiDecisionBar(
            primary: UiButton(
              label: 'Approve record',
              onPressed: () => report('Synthetic approval'),
            ),
            secondary: UiButton(
              label: 'Defer record',
              variant: UiButtonVariant.secondary,
              onPressed: () => report('Synthetic defer'),
            ),
            count: '3 of 12',
            onPrevious: () => report('Previous record'),
            onNext: () => report('Next record'),
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiDecisionSwipe',
    useCases: [
      story(
        'Touch record navigation',
        'Horizontal navigation supplements explicit previous/next commands. It must not replace discoverable controls.',
        (_) => ActionExample(
          builder: (_, report) => UiDecisionSwipe(
            onPrevious: () => report('Previous record'),
            onNext: () => report('Next record'),
            child: const SizedBox(
              height: 160,
              child: Center(child: Text('Swipe across this specimen region')),
            ),
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiGoogleSignInButton',
    useCases: [
      story(
        'Provider branding',
        'Provider-required artwork is an isolated identity exception. This example does not enable Google sign-in in the app.',
        (_) => ActionExample(
          builder: (_, report) => UiGoogleSignInButton(
            onPressed: () => report('Synthetic provider request'),
          ),
        ),
      ),
      story(
        'Busy',
        'Blocks duplicate provider requests without changing the provider label.',
        (_) => const UiGoogleSignInButton(busy: true),
      ),
      story(
        'Unavailable',
        'The host controls provider availability.',
        (_) => const UiGoogleSignInButton(
          disabledReason: 'This sign-in provider is not available.',
        ),
      ),
    ],
  ),
];

class _ButtonExample extends StatefulWidget {
  const _ButtonExample({
    this.variant = UiButtonVariant.primary,
    this.size = UiSize.md,
    this.state = 'Rest',
  });
  final UiButtonVariant variant;
  final UiSize size;
  final String state;
  @override
  State<_ButtonExample> createState() => _ButtonExampleState();
}

class _ButtonExampleState extends State<_ButtonExample> {
  final _states = WidgetStatesController();
  final _focus = FocusNode();
  @override
  void initState() {
    super.initState();
    _states.update(WidgetState.hovered, widget.state == 'Hover');
    _states.update(WidgetState.pressed, widget.state == 'Pressed');
  }

  @override
  void dispose() {
    _states.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final label = context.knobs.string(
      label: 'Label',
      initialValue: 'Save correction',
    );
    final icon = context.knobs.object.dropdown(
      label: 'Icon placement',
      options: ['None', 'Leading', 'Trailing'],
    );
    return ActionExample(
      builder: (_, report) => Align(
        alignment: AlignmentDirectional.centerStart,
        child: UiButton(
          label: label,
          variant: widget.variant,
          size: widget.size,
          leading: icon == 'Leading' ? UiIcons.add : null,
          trailing: icon == 'Trailing' ? UiIcons.next : null,
          loading: widget.state == 'Loading',
          busyLabel: 'Saving correction',
          disabledReason: widget.state == 'Disabled'
              ? 'You have read access to this record.'
              : null,
          onPressed: widget.state == 'Disabled'
              ? null
              : () => report('Saved correction'),
          statesController: _states,
          focusNode: _focus,
          autofocus: widget.state == 'Focused',
        ),
      ),
    );
  }
}

class _ChipExample extends StatefulWidget {
  const _ChipExample({required this.variant});
  final UiChipVariant variant;
  @override
  State<_ChipExample> createState() => _ChipExampleState();
}

class _ChipExampleState extends State<_ChipExample> {
  bool _selected = false;
  bool _removed = false;
  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 8,
    runSpacing: 8,
    children: [
      if (!_removed)
        UiChip(
          label: 'Entomology',
          variant: widget.variant,
          selected: _selected,
          onPressed: widget.variant == UiChipVariant.filter
              ? () => setState(() => _selected = !_selected)
              : null,
          onRemove: widget.variant == UiChipVariant.input
              ? () => setState(() => _removed = true)
              : null,
          removeSemanticsLabel: 'Remove Entomology filter',
        ),
      if (_removed)
        UiButton(
          label: 'Restore filter',
          variant: UiButtonVariant.secondary,
          onPressed: () => setState(() => _removed = false),
        ),
    ],
  );
}

class _ChoiceExample extends StatefulWidget {
  const _ChoiceExample({required this.disabled});
  final bool disabled;
  @override
  State<_ChoiceExample> createState() => _ChoiceExampleState();
}

class _ChoiceExampleState extends State<_ChoiceExample> {
  int? _value = 0;
  @override
  Widget build(BuildContext context) => UiChoiceGroup<int>(
    label: 'Review state',
    choices: const [
      UiChoice(value: 0, label: 'Needs review'),
      UiChoice(value: 1, label: 'Cleared'),
      UiChoice(value: 2, label: 'Processing'),
    ],
    value: _value,
    onChanged: widget.disabled
        ? null
        : (value) => setState(() => _value = value),
    disabledReason: widget.disabled ? 'Loading the collection.' : null,
  );
}

class _ToggleExample extends StatefulWidget {
  const _ToggleExample({required this.selection, required this.size});
  final UiToggleSelection selection;
  final UiSize size;
  @override
  State<_ToggleExample> createState() => _ToggleExampleState();
}

class _ToggleExampleState extends State<_ToggleExample> {
  Set<int> _value = {0};
  @override
  Widget build(BuildContext context) => UiCapsuleToggle<int>(
    options: const [
      UiToggleOption(value: 0, label: 'Images'),
      UiToggleOption(value: 1, label: 'Metadata'),
      UiToggleOption(value: 2, label: 'Annotations'),
    ],
    selected: _value,
    selection: widget.selection,
    size: widget.size,
    onChanged: (value) => setState(() => _value = value),
  );
}

class _SegmentExample extends StatefulWidget {
  const _SegmentExample({required this.size});
  final UiSize size;
  @override
  State<_SegmentExample> createState() => _SegmentExampleState();
}

class _SegmentExampleState extends State<_SegmentExample> {
  int _value = 0;
  @override
  Widget build(BuildContext context) => UiSegmented<int>(
    label: 'View',
    segments: const [
      UiSegment(value: 0, label: 'List', icon: UiIcons.record),
      UiSegment(value: 1, label: 'Images', icon: UiIcons.camera),
    ],
    value: _value,
    size: widget.size,
    onChanged: (value) => setState(() => _value = value),
  );
}
