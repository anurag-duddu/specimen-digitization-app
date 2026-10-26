import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';
import '../story.dart';

List<WidgetbookComponent> get applicationPatternComponents => [
  WidgetbookComponent(
    name: 'UiNavigationMenu',
    useCases: [
      for (final dual in [false, true])
        story(
          dual ? 'Dual tier' : 'Grouped nested navigation',
          'Controlled destination trees with counts, unavailable items, search, account and contextual slots. Arrows traverse visible enabled rows; reading-direction arrows expand and collapse groups.',
          (_) => _NavigationExample(dual: dual),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiDrawer',
    useCases: [
      for (final start in [false, true])
        story(
          start ? 'Reading-start navigation' : 'Reading-end filters',
          'A real modal side panel: full-width on phones, fixed footer, scrollable body, safe areas, Escape and focus restoration. Direction follows RTL.',
          (_) => _DrawerExample(fromStart: start),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiNotice',
    useCases: [
      for (final tone in UiBannerTone.values)
        story(
          '${tone.name} · floating alert',
          'Persistent functional feedback with title, supporting copy, two actions and an optional close control. Delivery and dismissal are host-owned.',
          (_) => ActionExample(
            builder: (_, report) => UiNotice(
              title: 'Collection review updated',
              description:
                  'A colleague added source evidence. Review the changes before accepting them.',
              tone: tone,
              onDismiss: () => report('Dismiss requested'),
              actions: [
                UiButton(
                  label: 'Review changes',
                  onPressed: () => report('Review opened'),
                ),
                UiButton(
                  label: 'Later',
                  variant: UiButtonVariant.secondary,
                  onPressed: () => report('Review deferred'),
                ),
              ],
            ),
          ),
        ),
      story(
        'Avatar, timestamp and attachment',
        'Notification slots support people, evidence and progress without adding decorative status hues.',
        (_) => ActionExample(
          builder: (_, report) => UiNotice(
            title: 'Maya added evidence',
            description: 'A label photograph is ready to review.',
            leading: const UiAvatar(name: 'Maya Chen'),
            timestamp: '2 minutes ago',
            child: UiButton(
              label: 'Open photograph',
              variant: UiButtonVariant.secondary,
              onPressed: () => report('Photograph opened'),
            ),
          ),
        ),
      ),
      story(
        'Image attachment',
        'Host-owned images keep accessible names and a neutral presentation.',
        (_) => const UiNotice(
          title: 'New collection photograph',
          description: 'A photograph is ready for review.',
          leading: UiMark(label: 'Specimen photograph preview slot', size: 48),
        ),
      ),
      story(
        'Text-only announcement',
        'The message remains clear without a decorative leading glyph.',
        (_) => const UiNotice(
          title: 'Collection schedule updated',
          description: 'Review the new dates with your team.',
          showIcon: false,
          floating: false,
        ),
      ),
      story(
        'Full-width progress notice',
        'Status is persistent and readable without relying on its color.',
        (_) => const UiNotice(
          title: 'Preparing records',
          description: '12 of 20 records processed',
          floating: false,
          leading: UiIcon(UiIcons.processing),
          child: UiProgress.bar(value: .6, semanticsLabel: 'Records processed'),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiModalPanel',
    useCases: [
      for (final layout in UiModalLayout.values)
        story(
          '${layout.name} · invitation',
          'Featured icon, title, description, form body and persistent action slots share the owned dialog focus and dismissal contract. Header and body scroll on short windows.',
          (_) => _PanelExample(layout: layout),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiTabs variants',
    useCases: [
      for (final size in UiTabsSize.values)
        story(
          'Expanded ${size.name}',
          'Equal-width tabs share the available width while retaining complete labels, 48 dp targets and overflow scrolling.',
          (_) => _TabExample(
            axis: Axis.horizontal,
            variant: UiTabsVariant.soft,
            expanded: true,
            size: size,
          ),
        ),
      for (final axis in Axis.values)
        for (final variant in UiTabsVariant.values)
          story(
            '${axis.name} · ${variant.name}',
            'Tabs retain manual activation and directional keyboard behavior across presentations. Counts are included in names, unavailable tabs explain why, and all labels remain reachable.',
            (_) => _TabExample(axis: axis, variant: variant),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiCommandMenu rich content',
    useCases: [
      story(
        'Users, integration marks and shortcuts',
        'Search matches labels, supporting text and keywords. Avatar/integration leading slots and shortcut hints preserve the same enabled-command keyboard traversal.',
        (_) => ActionExample(
          builder: (_, report) => UiCommandMenu(
            autofocus: false,
            onDismiss: () => report('Dismiss requested'),
            maxHeight: 580,
            header: const Text('Collection workspace'),
            footer: const Text('↑ ↓ Navigate · Enter Select · Esc Close'),
            commands: [
              UiCommand(
                id: 'review',
                label: 'Review specimen',
                group: 'Commands',
                icon: UiIcons.record,
                shortcut: '⌘ R',
                onSelected: () => report('Review selected'),
              ),
              UiCommand(
                id: 'maya',
                label: 'Maya Chen',
                description: 'Collection manager',
                group: 'People',
                leading: const UiAvatar(name: 'Maya Chen'),
                onSelected: () => report('Maya selected'),
              ),
              UiCommand(
                id: 'catalogue',
                label: 'Collection catalogue',
                description: 'Connected source',
                group: 'Integrations',
                leading: const UiIcon(UiIcons.sources),
                onSelected: () => report('Catalogue selected'),
              ),
              const UiCommand(
                id: 'restricted',
                label: 'Restricted source',
                disabledReason: 'Access required',
              ),
            ],
          ),
        ),
      ),
    ],
  ),
];

class _NavigationExample extends StatefulWidget {
  const _NavigationExample({required this.dual});
  final bool dual;
  @override
  State<_NavigationExample> createState() => _NavigationExampleState();
}

class _NavigationExampleState extends State<_NavigationExample> {
  String navigationQuery = '';
  static const _allSections = [
    UiNavigationSection(
      label: 'Workspace',
      items: [
        UiNavigationItem(
          id: 'collections',
          label: 'Collections',
          icon: UiIcons.collection,
          children: [
            UiNavigationItem(id: 'records', label: 'Specimens', badge: '24'),
            UiNavigationItem(id: 'images', label: 'Images', badge: '108'),
            UiNavigationItem(
              id: 'restricted',
              label: 'Restricted records',
              enabled: false,
              disabledReason: 'Collection access required',
            ),
          ],
        ),
        UiNavigationItem(
          id: 'activity',
          label: 'Activity',
          icon: UiIcons.history,
        ),
      ],
    ),
    UiNavigationSection(
      label: 'Account',
      items: [
        UiNavigationItem(
          id: 'settings',
          label: 'Settings',
          icon: UiIcons.settings,
        ),
        UiNavigationItem(id: 'help', label: 'Help', icon: UiIcons.help),
      ],
    ),
  ];
  List<UiNavigationSection> get _visibleSections {
    final q = navigationQuery.trim().toLowerCase();
    if (q.isEmpty) return _allSections;
    return [
      for (final section in _allSections)
        UiNavigationSection(
          label: section.label,
          items: [
            for (final item in section.items)
              if (item.label.toLowerCase().contains(q))
                item
              else if (item.children.any(
                (c) => c.label.toLowerCase().contains(q),
              ))
                UiNavigationItem(
                  id: item.id,
                  label: item.label,
                  icon: item.icon,
                  children: item.children
                      .where((c) => c.label.toLowerCase().contains(q))
                      .toList(),
                ),
          ],
        ),
    ].where((section) => section.items.isNotEmpty).toList();
  }

  String selected = 'records';
  Set<String> expanded = {'collections'};
  @override
  Widget build(BuildContext context) => SizedBox(
    height: 660,
    child: UiNavigationMenu(
      semanticsLabel: 'Specimen workspace',
      selectedId: selected,
      onSelected: (id) => setState(() => selected = id),
      expandedIds: navigationQuery.isEmpty ? expanded : {'collections'},
      onExpandedChanged: (ids) => setState(() => expanded = ids),
      leadingRail: widget.dual
          ? Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                UiIconButton(
                  icon: UiIcons.collection,
                  semanticsLabel: 'Collection workspace',
                  onPressed: () => setState(() => selected = 'records'),
                ),
                UiIconButton(
                  icon: UiIcons.settings,
                  semanticsLabel: 'Workspace settings',
                  onPressed: () => setState(() => selected = 'settings'),
                ),
              ],
            )
          : null,
      header: const Text('Specimen digitization'),
      search: UiSearchField(
        onChanged: (value) => setState(() => navigationQuery = value),
        label: 'Search navigation',
        clearLabel: 'Clear navigation search',
        hintText: 'Search collections',
      ),
      featured: const UiNotice(
        title: 'Review progress',
        description: '8 of 12 records reviewed',
        child: UiProgress.bar(value: 2 / 3, semanticsLabel: 'Records reviewed'),
      ),
      footer: const UiAvatar(name: 'Maya Chen'),
      sections: _visibleSections,
    ),
  );
}

class _DrawerExample extends StatelessWidget {
  const _DrawerExample({required this.fromStart});
  final bool fromStart;
  @override
  Widget build(BuildContext context) => ActionExample(
    builder: (context, report) => UiButton(
      label: fromStart ? 'Open navigation' : 'Open filters',
      onPressed: () async {
        final accepted = await UiDrawer.show<bool>(
          context: context,
          title: fromStart ? 'Collection navigation' : 'Filter specimens',
          fromStart: fromStart,
          description: 'Synthetic example data',
          body: (_) => fromStart
              ? const _NavigationExample(dual: false)
              : const _FilterForm(),
          footer: (context) => UiButtonRow(
            secondary: UiButton(
              label: 'Cancel',
              variant: UiButtonVariant.secondary,
              onPressed: () => Navigator.pop(context, false),
            ),
            primary: UiButton(
              label: 'Apply',
              onPressed: () => Navigator.pop(context, true),
            ),
          ),
        );
        if (context.mounted) report(accepted == true ? 'Applied' : 'Cancelled');
      },
    ),
  );
}

class _FilterForm extends StatefulWidget {
  const _FilterForm();
  @override
  State<_FilterForm> createState() => _FilterFormState();
}

class _FilterFormState extends State<_FilterForm> {
  final selected = <String>{'Needs review'};
  String query = '';
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      UiSearchField(
        onChanged: (value) => setState(() => query = value.toLowerCase()),
        label: 'Search filter options',
        clearLabel: 'Clear filter search',
      ),
      for (final label in [
        'Needs review',
        'Reviewed',
        'In progress',
        'Images available',
        'Has catalogue number',
        'Has location',
        'Has collector',
        'Recently updated',
      ].where((label) => label.toLowerCase().contains(query)))
        UiCheckbox(
          label: label,
          value: selected.contains(label),
          onChanged: (value) => setState(() {
            if (value == true) {
              selected.add(label);
            } else {
              selected.remove(label);
            }
          }),
        ),
    ],
  );
}

class _PanelExample extends StatelessWidget {
  const _PanelExample({required this.layout});
  final UiModalLayout layout;
  @override
  Widget build(BuildContext context) => ActionExample(
    builder: (context, report) => UiButton(
      label: 'Invite a colleague',
      onPressed: () async {
        final result = await UiModalPanel.show<bool>(
          context: context,
          semanticsLabel: 'Invite a colleague',
          builder: (context) => UiModalPanel(
            title: 'Invite a colleague',
            description: 'Share access to the collection workspace.',
            leading: const UiIcon(UiIcons.reviewer),
            layout: layout,
            onDismiss: () => Navigator.pop(context),
            footer: UiButtonRow(
              secondary: UiButton(
                label: 'Cancel',
                variant: UiButtonVariant.secondary,
                onPressed: () => Navigator.pop(context, false),
              ),
              primary: UiButton(
                label: 'Preview invitation',
                onPressed: () => Navigator.pop(context, true),
              ),
            ),
            child: const UiField(
              label: 'Email address',
              hintText: 'colleague@example.org',
            ),
          ),
        );
        if (context.mounted) {
          report(result == true ? 'Invitation previewed locally' : 'Cancelled');
        }
      },
    ),
  );
}

class _TabExample extends StatefulWidget {
  const _TabExample({
    required this.axis,
    required this.variant,
    this.expanded = false,
    this.size = UiTabsSize.regular,
  });
  final Axis axis;
  final UiTabsVariant variant;
  final UiTabsSize size;
  final bool expanded;
  @override
  State<_TabExample> createState() => _TabExampleState();
}

class _TabExampleState extends State<_TabExample> {
  final selected = ValueNotifier(0);
  @override
  void dispose() {
    selected.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      SizedBox(
        height: widget.axis == Axis.vertical ? 280 : null,
        child: UiTabs(
          selected: selected,
          semanticsLabel: 'Record panels',
          axis: widget.axis,
          variant: widget.variant,
          size: widget.size,
          expanded: widget.expanded,
          tabs: const [
            UiTab(label: 'Overview', icon: UiIcons.record, badge: '24'),
            UiTab(label: 'Images', icon: UiIcons.camera, badge: '8'),
            UiTab(label: 'History', icon: UiIcons.history),
            UiTab(
              label: 'Restricted',
              enabled: false,
              disabledReason: 'Access required',
            ),
          ],
        ),
      ),
      UiTabView(
        selected: selected,
        children: const [
          Text('Overview content'),
          Text('Images content'),
          Text('History content'),
          Text('Restricted content'),
        ],
      ),
    ],
  );
}
