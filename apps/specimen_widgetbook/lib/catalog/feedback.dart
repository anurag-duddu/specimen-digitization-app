import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

import '../story.dart';

List<WidgetbookComponent> get feedbackComponents => [
  WidgetbookComponent(
    name: 'UiBanner',
    useCases: [
      for (final tone in UiBannerTone.values)
        for (final form in UiBannerForm.values)
          story(
            '${tone.name} · ${form.name}',
            'Operational feedback belongs above the affected content. Form errors stay beside their field. Compact strips disclose details; recovery actions remain named.',
            (_) => ActionExample(
              builder: (_, report) => UiBanner(
                message: 'The current import needs attention.',
                tone: tone,
                form: form,
                detail:
                    'Three synthetic images need another attempt. Saved records remain available.',
                actionLabel: 'Review import',
                onAction: () => report('Opened import'),
                onDismiss: () => report('Dismiss requested'),
                dismissLabel: 'Dismiss import notice',
              ),
            ),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiDialog',
    useCases: [
      story(
        'Adaptive confirmation',
        'Phone windows use a sheet; larger windows use a dialog. Focus stays inside, Escape dismisses when allowed, and focus returns to the trigger.',
        (_) => _ModalExample(kind: 'adaptive'),
      ),
      story(
        'Centred dialog',
        'Use for a brief decision. Long content scrolls within the available height, including at 200% text.',
        (_) => _ModalExample(kind: 'dialog'),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSheet',
    useCases: [
      story(
        'Bottom sheet',
        'A sheet sits within the active viewport and respects safe areas and the keyboard. Drag or Escape dismisses when permitted.',
        (_) => _ModalExample(kind: 'sheet'),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiPopoverMenu and UiMenuTrigger',
    useCases: [
      story(
        'Commands, unavailable and destructive',
        'Open with Enter or Space; arrows move through commands; Escape closes and restores trigger focus. Disabled commands explain why.',
        (_) => ActionExample(
          builder: (_, report) => Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiMenuTrigger(
              semanticsLabel: 'Record actions',
              label: 'Record actions',
              items: [
                UiMenuItem(
                  label: 'Open source',
                  icon: UiIcons.record,
                  onSelected: () => report('Opened source'),
                ),
                const UiMenuItem(
                  label: 'Export record',
                  onSelected: null,
                  disabledReason: 'Finish validation before export.',
                ),
                UiMenuItem(
                  label: 'Discard draft',
                  destructive: true,
                  onSelected: () => report('Synthetic draft discarded'),
                ),
              ],
            ),
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiTooltip',
    useCases: [
      for (final emphasis in UiTooltipEmphasis.values)
        for (final placement in PopoverPlacement.values)
          story(
            '${emphasis.name} · ${placement.name}',
            'A heading and supporting explanation. Pointer hover or long press reveals the pane; the control remains independently named.',
            (_) => Center(
              child: UiTooltip(
                message: 'Collection identifier',
                supportingText:
                    'Use the original identifier printed on the specimen label.',
                emphasis: emphasis,
                placement: placement,
                child: UiActionButton(
                  label: 'Collection identifier help',
                  hierarchy: UiActionHierarchy.link,
                  onPressed: () {},
                ),
              ),
            ),
          ),

      story(
        'Pointer, keyboard and long press',
        'Supplement an already named control. A tooltip must not be the only available label for a form field.',
        (_) => UiTooltip(
          message: 'Open the original specimen image',
          child: UiIconButton(
            icon: UiIcons.record,
            semanticsLabel: 'Open original image',
            onPressed: () {},
          ),
        ),
      ),
      story(
        'Unavailable reason',
        'Unavailable commands keep their reason reachable by touch and keyboard.',
        (_) => const UiButton(
          label: 'Export record',
          disabledReason: 'Confirm the catalogue number before exporting.',
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiToast and UiToastHost',
    useCases: [
      story(
        'Queued acknowledgement',
        'Transient acknowledgement supplements the persistent source of truth. An action toast stays reachable for assistive technology.',
        (_) => ActionExample(
          builder: (context, report) => UiButton(
            label: 'Save synthetic draft',
            onPressed: () {
              report('Draft saved');
              UiToasts.show(
                context,
                message: 'Draft saved',
                actionLabel: 'Undo save',
                onAction: () => report('Save undone'),
              );
            },
          ),
        ),
      ),
      story(
        'Visible action toast',
        'Preview the toast anatomy without waiting for its entrance or expiry.',
        (_) => ActionExample(
          builder: (_, report) => UiToast(
            data: UiToastData(
              message: 'Draft saved',
              actionLabel: 'Undo save',
              onAction: () => report('Save undone'),
            ),
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiDisclosure',
    useCases: [
      story(
        'Value review hierarchy',
        'Compact provenance stays visible. Supported values use secondary ink and a check; fields needing attention keep full emphasis. Both reveal their evidence on activation.',
        (context) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            UiSectionHeader(
              title: 'Collection',
              meta: Text(
                '1 review · 1 missing',
                style: context.ui.type.bodySmall,
              ),
            ),
            SizedBox(height: context.ui.space.s4),
            UiDisclosure(
              title: 'Country',
              summary: 'Philippines',
              metadata: 'Derived',
              collapsedIcon: UiIcons.check,
              semanticsLabel: 'Country. Supported. Philippines. Basis: derived',
              style: UiDisclosureStyle.value(context.ui, subdued: true),
              child: const Text(
                'The retained label states P.I.; the supported interpretation is Philippines.',
              ),
            ),
            const UiHairline(),
            UiDisclosure(
              title: 'City',
              summary: 'Unresolved',
              semanticsLabel: 'City. Unresolved. Review needed',
              style: UiDisclosureStyle.value(context.ui),
              child: const Text(
                'No supported city has been recorded. Inspect the retained label evidence before correcting this field.',
              ),
            ),
          ],
        ),
      ),
      for (final expanded in [false, true])
        story(
          expanded ? 'Expanded' : 'Collapsed',
          'Use for optional supporting detail. The summary names what is inside; keyboard activation reveals selectable content.',
          (_) => UiDisclosure(
            title: 'Original label transcription',
            summary: 'Verbatim source evidence',
            initiallyExpanded: expanded,
            child: const UiSelectableText(
              'Field label: Example specimen, collected 12 May 1924. Synthetic documentation data.',
            ),
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiTabs',
    useCases: [
      story(
        'Manual keyboard activation',
        'Arrows move focus without changing the pane; Enter or Space activates. Narrow windows scroll the strip while keeping the focused and selected tab visible.',
        (_) => const _TabsExample(),
      ),
    ],
  ),
];

class _ModalExample extends StatelessWidget {
  const _ModalExample({required this.kind});
  final String kind;
  @override
  Widget build(BuildContext context) => ActionExample(
    builder: (context, report) => UiButton(
      label: 'Review synthetic changes',
      onPressed: () async {
        final show = switch (kind) {
          'sheet' => UiSheet.show<bool>,
          'dialog' => UiDialog.show<bool>,
          _ => UiDialog.showAdaptive<bool>,
        };
        final accepted = await show(
          context: context,
          title: 'Save these changes?',
          body: (_) => const Text(
            'This example updates local story state only. Review the new catalogue number before saving.',
          ),
          primaryAction: (dialogContext) => UiButton(
            label: 'Save changes',
            onPressed: () => Navigator.of(dialogContext).pop(true),
          ),
          secondaryAction: (dialogContext) => UiButton(
            label: 'Cancel',
            variant: UiButtonVariant.secondary,
            onPressed: () => Navigator.of(dialogContext).pop(false),
          ),
        );
        if (context.mounted) {
          report(accepted == true ? 'Changes saved' : 'Cancelled');
        }
      },
    ),
  );
}

class _TabsExample extends StatefulWidget {
  const _TabsExample();
  @override
  State<_TabsExample> createState() => _TabsExampleState();
}

class _TabsExampleState extends State<_TabsExample> {
  final _selected = ValueNotifier(0);
  static const _labels = ['Overview', 'Images', 'Metadata', 'Activity history'];
  @override
  void dispose() {
    _selected.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      UiTabs(
        tabs: [for (final label in _labels) UiTab(label: label)],
        selected: _selected,
        semanticsLabel: 'Specimen detail panes',
      ),
      SizedBox(height: context.ui.space.s4),
      ValueListenableBuilder<int>(
        valueListenable: _selected,
        builder: (_, value, _) => Semantics(
          liveRegion: true,
          child: Text('${_labels[value]} pane · synthetic content'),
        ),
      ),
    ],
  );
}
