import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';
import '../story.dart';

const _destinations = [
  UiNavDestination(label: 'Specimens', icon: UiIcons.record),
  UiNavDestination(label: 'Intake', icon: UiIcons.uploadFile),
  UiNavDestination(label: 'Search', icon: UiIcons.search),
];

List<WidgetbookComponent> get navigationComponents => [
  WidgetbookComponent(
    name: 'UiViewTabs',
    useCases: [
      story(
        'Specimen views',
        'The current view is named beside its icon. Other views keep accessible names and tooltips. Arrow keys, Home and End move between views; enlarged text wraps without shrinking touch targets.',
        (_) => const _ViewTabsExample(),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiBreadcrumbs',
    useCases: [
      story(
        'Hierarchy',
        'Ancestors are named links. The last item identifies the current page and never activates. Labels wrap rather than disappear at large text.',
        (_) => ActionExample(
          builder: (_, report) => UiBreadcrumbs(
            items: [
              UiBreadcrumb(
                label: 'Collections',
                onSelected: () => report('Collections'),
              ),
              UiBreadcrumb(
                label: 'Entomology',
                onSelected: () => report('Entomology'),
              ),
              const UiBreadcrumb(label: 'FMNH EXAMPLE-001'),
            ],
          ),
        ),
      ),
      story(
        'Long current location',
        'The trail preserves reading order in both directions and under narrow constraints.',
        (_) => ActionExample(
          builder: (_, report) => UiBreadcrumbs(
            items: [
              UiBreadcrumb(
                label: 'Collections and historical research',
                onSelected: () => report('Collections'),
              ),
              const UiBreadcrumb(
                label: 'A specimen with a long descriptive catalogue title',
              ),
            ],
          ),
        ),
      ),
      story(
        'Empty',
        'No ancestors means no navigation region or extra spacing.',
        (_) => const UiBreadcrumbs(items: []),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSteps',
    useCases: [
      story(
        'Controlled workflow',
        'Progress is derived from host state, never inferred from time. Narrow windows stack steps. Only steps with a callback are actionable.',
        (_) => const _StepsExample(),
      ),
      story(
        'Error and upcoming',
        'State is written explicitly so progress remains understandable without colour.',
        (_) => const UiSteps(
          steps: [
            UiStep(label: 'Add images', state: UiStepState.complete),
            UiStep(
              label: 'Validate source',
              description: 'Confirm the missing identifier.',
              state: UiStepState.error,
            ),
            UiStep(label: 'Review record'),
          ],
        ),
      ),
    ],
  ),
  for (final kind in ['UiTabBar', 'UiPillNav', 'UiRail', 'UiSidebar'])
    WidgetbookComponent(
      name: kind,
      useCases: [
        story(
          'Interactive destinations',
          'Destination navigation uses one controlled index. Arrows follow reading direction; Enter or Space activates. Selected labels and icons do not depend on colour alone.',
          (_) => _NavigationExample(kind: kind),
        ),
      ],
    ),
  WidgetbookComponent(
    name: 'UiTopBar',
    useCases: [
      for (final form in UiTopBarForm.values)
        story(
          form.name,
          'Workspace chrome respects the top safe area; page bars keep content commands separate from global navigation. Overflow retains every action.',
          (_) => ActionExample(
            builder: (_, report) => UiTopBar(
              form: form,
              title: form == UiTopBarForm.workspace ? null : 'Specimen details',
              leading: form == UiTopBarForm.workspace
                  ? const Text('Entomology collection')
                  : null,
              actions: [
                UiTopBarAction(
                  icon: UiIcons.search,
                  label: 'Search records',
                  onPressed: () => report('Search'),
                ),
                UiTopBarAction(
                  icon: UiIcons.add,
                  label: 'Add image',
                  onPressed: () => report('Add image'),
                ),
              ],
            ),
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSidePanel',
    useCases: [
      story(
        'Adaptive companion panel',
        'A roomy workspace docks its companion. Narrower allocations open it over the workspace without squeezing the content. Close, Escape and the scrim restore focus; text and scroll survive toggling. Primary navigation keeps all labels.',
        (_) => const _SidePanelExample(),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiScaffold',
    useCases: [
      WidgetbookUseCase(
        name: 'Responsive workspace shell',
        builder: (_) => const _ScaffoldExample(),
      ),
    ],
  ),
];

class _SidePanelExample extends StatefulWidget {
  const _SidePanelExample();
  @override
  State<_SidePanelExample> createState() => _SidePanelExampleState();
}

class _SidePanelExampleState extends State<_SidePanelExample> {
  bool _open = false;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 520,
    child: LayoutBuilder(
      builder: (context, constraints) {
        final metrics = UiLayoutMetrics.fromConstraints(
          constraints,
          textScaler: MediaQuery.textScalerOf(context),
        );
        final layout = UiSidePanelLayout.resolve(
          availableWidth: constraints.maxWidth,
          panelWidth: WindowArrangement.listPaneWidthOf(
            MediaQuery.textScalerOf(context),
          ),
          minBodyWidth: metrics.readableMax,
        );
        return UiSidePanel(
          open: _open,
          mode: layout.mode,
          width: layout.width,
          onDismiss: () => setState(() => _open = false),
          semanticsLabel: 'Specimen queue',
          panel: UiDrawer(
            title: 'Specimens',
            onClose: () => setState(() => _open = false),
            child: Column(
              children: [
                const UiField(label: 'Search specimen ID'),
                for (var i = 1; i <= 20; i++)
                  UiListRow(title: 'Example specimen $i', onPressed: () {}),
              ],
            ),
          ),
          child: ColoredBox(
            color: context.ui.color.ground,
            child: SingleChildScrollView(
              padding: EdgeInsets.all(context.ui.space.s4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  UiButton(
                    label: _open ? 'Hide queue' : 'Show queue',
                    variant: UiButtonVariant.secondary,
                    onPressed: () => setState(() => _open = !_open),
                  ),
                  SizedBox(height: context.ui.space.s6),
                  Text('Specimen details', style: context.ui.type.title),
                  SizedBox(height: context.ui.space.s4),
                  const UiField(label: 'Unfinished correction'),
                ],
              ),
            ),
          ),
        );
      },
    ),
  );
}

class _StepsExample extends StatefulWidget {
  const _StepsExample();
  @override
  State<_StepsExample> createState() => _StepsExampleState();
}

class _StepsExampleState extends State<_StepsExample> {
  int _current = 1;
  @override
  Widget build(BuildContext context) => UiSteps(
    steps: [
      for (var i = 0; i < 3; i++)
        UiStep(
          label: ['Add images', 'Review evidence', 'Save record'][i],
          state: i < _current
              ? UiStepState.complete
              : i == _current
              ? UiStepState.current
              : UiStepState.upcoming,
          onSelected: () => setState(() => _current = i),
        ),
    ],
  );
}

class _NavigationExample extends StatefulWidget {
  const _NavigationExample({required this.kind});
  final String kind;
  @override
  State<_NavigationExample> createState() => _NavigationExampleState();
}

class _NavigationExampleState extends State<_NavigationExample> {
  int _index = 0;
  void _select(int value) => setState(() => _index = value);
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      SizedBox(
        height: widget.kind == 'UiSidebar' || widget.kind == 'UiRail'
            ? 420
            : null,
        child: Align(
          alignment: AlignmentDirectional.topStart,
          child: switch (widget.kind) {
            'UiSidebar' => UiSidebar(
              destinations: _destinations,
              currentIndex: _index,
              onSelect: _select,
              header: const Text('Specimen Digitization'),
            ),
            'UiRail' => UiRail(
              destinations: _destinations,
              currentIndex: _index,
              onSelect: _select,
              extended: context.knobs.boolean(
                label: 'Expanded labels',
                initialValue: true,
              ),
            ),
            'UiPillNav' => UiPillNav(
              destinations: _destinations,
              currentIndex: _index,
              onSelect: _select,
            ),
            _ => UiTabBar(
              labels:
                  context.knobs.boolean(
                    label: 'Only label selected destination',
                    initialValue: true,
                  )
                  ? UiNavigationLabels.selectedOnly
                  : UiNavigationLabels.all,
              destinations: _destinations,
              currentIndex: _index,
              onSelect: _select,
            ),
          },
        ),
      ),
      Semantics(
        liveRegion: true,
        child: Text('Current destination: ${_destinations[_index].label}'),
      ),
    ],
  );
}

class _ViewTabsExample extends StatefulWidget {
  const _ViewTabsExample();
  @override
  State<_ViewTabsExample> createState() => _ViewTabsExampleState();
}

class _ViewTabsExampleState extends State<_ViewTabsExample> {
  int _selected = 0;
  @override
  Widget build(BuildContext context) => UiViewTabs<int>(
    value: _selected,
    semanticsLabel: 'Specimen views',
    onChanged: (value) => setState(() => _selected = value),
    views: [
      UiViewTab(value: 0, label: 'Needs review', icon: UiIcons.needsReview),
      UiViewTab(value: 1, label: 'Cleared', icon: UiIcons.check),
      UiViewTab(value: 2, label: 'All specimens', icon: UiIcons.record),
    ],
  );
}

class _ScaffoldExample extends StatefulWidget {
  const _ScaffoldExample();
  @override
  State<_ScaffoldExample> createState() => _ScaffoldExampleState();
}

class _ScaffoldExampleState extends State<_ScaffoldExample> {
  int _index = 0;
  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 840;
    void select(int value) => setState(() => _index = value);
    return UiScaffold(
      topBar: UiTopBar(title: _destinations[_index].label),
      nav: wide
          ? UiSidebar(
              destinations: _destinations,
              currentIndex: _index,
              onSelect: select,
            )
          : UiTabBar(
              destinations: _destinations,
              currentIndex: _index,
              onSelect: select,
            ),
      navPlacement: wide ? UiNavPlacement.edge : UiNavPlacement.floating,
      body: StoryFrame(
        title: 'Responsive workspace',
        guidance:
            'Synthetic shell. Phone navigation becomes a sidebar on wide windows. Content scrolls independently of the navigation.',
        child: const UiEmptyState(
          icon: UiIcons.record,
          title: 'No records in this example',
          body: 'Change a destination to inspect the navigation state.',
        ),
      ),
    );
  }
}
