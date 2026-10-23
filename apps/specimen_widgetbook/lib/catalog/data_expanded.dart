import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';
import '../story.dart';

const _observations = [
  UiChartDatum(label: 'Jan', value: 24),
  UiChartDatum(label: 'Feb', value: 42),
  UiChartDatum(label: 'Mar', value: 31),
  UiChartDatum(label: 'Apr', value: 60),
];
const _series = [
  UiChartSeries(label: 'Photographed', data: _observations),
  UiChartSeries(
    label: 'Reviewed',
    data: [
      UiChartDatum(label: 'Jan', value: 12),
      UiChartDatum(label: 'Feb', value: 25),
      UiChartDatum(label: 'Mar', value: 28),
      UiChartDatum(label: 'Apr', value: 42),
    ],
  ),
  UiChartSeries(
    label: 'Published',
    data: [
      UiChartDatum(label: 'Jan', value: 0),
      UiChartDatum(label: 'Feb', value: 12),
      UiChartDatum(label: 'Mar', value: null),
      UiChartDatum(label: 'Apr', value: 30),
    ],
  ),
];

List<UiChartSeries> _data(UiDataVisualizationKind kind) => switch (kind) {
  UiDataVisualizationKind.pie || UiDataVisualizationKind.donut => const [
    UiChartSeries(
      label: 'Collections',
      data: [
        UiChartDatum(label: 'Botany', value: 42),
        UiChartDatum(label: 'Zoology', value: 31),
        UiChartDatum(label: 'Geology', value: 24),
        UiChartDatum(label: 'Anthropology', value: 16),
        UiChartDatum(label: 'Fossils', value: 9),
        UiChartDatum(label: 'Archives', value: 5),
      ],
    ),
  ],
  UiDataVisualizationKind.gauge => const [
    UiChartSeries(
      label: 'Photographed',
      data: [UiChartDatum(label: 'Complete', value: 80)],
    ),
    UiChartSeries(
      label: 'Reviewed',
      data: [UiChartDatum(label: 'Complete', value: 55)],
    ),
    UiChartSeries(
      label: 'Published',
      data: [UiChartDatum(label: 'Complete', value: 30)],
    ),
  ],
  _ => _series,
};

List<WidgetbookComponent> get dataExpandedComponents => [
  WidgetbookComponent(
    name: 'Application templates',
    useCases: [
      for (final template in [
        'Dashboard',
        'Settings',
        'Informational directory',
      ])
        story(
          template,
          'A complete synthetic application content template composed from shared controls. Data and interactions are local; no production connection, payment or account change is made.',
          (_) => _ApplicationTemplate(template: template),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiDataVisualization',
    useCases: [
      for (final kind in UiDataVisualizationKind.values)
        for (final legend in UiChartLegend.values)
          story(
            '${kind.name} · ${legend.name} legend',
            'Synthetic controlled observations. Exact values remain available independently of marks, colour and legend. Missing March publication data breaks traces instead of becoming zero. Narrow Cartesian plots scroll horizontally to retain readable category labels.',
            (_) => UiDataVisualization(
              label: 'Collection activity',
              series: _data(kind),
              kind: kind,
              legend: legend,
              xAxisLabel: 'Month',
              yAxisLabel: 'Specimens',
            ),
          ),
      for (final size in UiChartSize.values)
        story(
          'Donut · ${size.name}',
          'Plot sizes never constrain the readable value table.',
          (_) => UiDataVisualization(
            label: 'Collection distribution',
            series: _data(UiDataVisualizationKind.donut),
            kind: UiDataVisualizationKind.donut,
            size: size,
          ),
        ),
      for (final hole in [0.0, .25, .75])
        story(
          'Donut hole · $hole',
          'A hole changes the presentation, not measured values.',
          (_) => UiDataVisualization(
            label: 'Collection distribution',
            series: _data(UiDataVisualizationKind.donut),
            kind: UiDataVisualizationKind.donut,
            holeRatio: hole,
          ),
        ),
      for (final kind in [
        UiDataVisualizationKind.line,
        UiDataVisualizationKind.area,
        UiDataVisualizationKind.groupedBars,
        UiDataVisualizationKind.stackedBars,
      ])
        story(
          '${kind.name} · without axes',
          'Axes are optional for compact summaries. The exact value table remains visible.',
          (_) => UiDataVisualization(
            label: 'Collection activity',
            series: _series,
            kind: kind,
            showAxes: false,
          ),
        ),
      story(
        'No observations',
        'Absence is stated without a fabricated measurement.',
        (_) => const UiDataVisualization(label: 'No observations', series: []),
      ),
      story(
        'Zero and unavailable',
        'Zero is a measured observation; null is not measured.',
        (_) => const UiDataVisualization(
          label: 'Observed counts',
          series: [
            UiChartSeries(
              label: 'Reviewed',
              data: [
                UiChartDatum(label: 'Today', value: 0),
                UiChartDatum(label: 'Tomorrow', value: null),
              ],
            ),
          ],
        ),
      ),
      story(
        'Negative measurements',
        'Signed Cartesian charts retain zero and both sides of the axis.',
        (_) => const UiDataVisualization(
          label: 'Daily difference',
          kind: UiDataVisualizationKind.stackedBars,
          series: [
            UiChartSeries(
              label: 'Change',
              data: [
                UiChartDatum(label: 'Mon', value: -12),
                UiChartDatum(label: 'Tue', value: 0),
                UiChartDatum(label: 'Wed', value: 18),
              ],
            ),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiPageHeader',
    useCases: [
      for (final banner in [false, true])
        for (final identity in [false, true])
          for (final centered in [false, true])
            story(
              '${banner ? 'Banner' : 'Simple'} · ${identity ? 'identity' : 'text'} · ${centered ? 'centered' : 'start'}',
              'The hero gradient is decorative. Text remains on its own neutral panel; actions wrap, and identity is supplied by the host.',
              (context) => ActionExample(
                builder: (_, report) => UiPageHeader(
                  title: 'Museum collections',
                  supporting:
                      'Photograph, transcribe and connect collection records.',
                  centered: centered,
                  banner: banner
                      ? DecoratedBox(
                          decoration: BoxDecoration(
                            gradient: context.ui.brand.heroGradient,
                          ),
                        )
                      : null,
                  identity: identity
                      ? const UiAvatar(name: 'Field Museum')
                      : null,
                  actions: [
                    UiButton(
                      label: 'Create collection',
                      onPressed: () => report('Create requested'),
                    ),
                  ],
                ),
              ),
            ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiContentFooter',
    useCases: [
      for (final role in UiContentFooterRole.values)
        for (final group in [false, true])
          story(
            '${role.name} · ${group ? 'button group' : 'supporting'}',
            'The footer follows content in document order. Cancel and Save remain real host callbacks.',
            (_) => ActionExample(
              builder: (_, report) => UiContentFooter(
                role: role,
                supporting: 'Changes are stored only after saving.',
                leading: group
                    ? UiButtonGroup(
                        label: 'Section navigation',
                        items: [
                          UiButtonGroupItem(
                            label: 'Previous',
                            onPressed: () => report('Previous'),
                          ),
                          UiButtonGroupItem(
                            label: 'Next',
                            onPressed: () => report('Next'),
                          ),
                        ],
                      )
                    : null,
                actions: [
                  UiButton(
                    label: 'Cancel',
                    variant: UiButtonVariant.secondary,
                    onPressed: () => report('Cancelled'),
                  ),
                  UiButton(
                    label: 'Save changes',
                    onPressed: () => report('Saved locally'),
                  ),
                ],
              ),
            ),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiInlineCta',
    useCases: [
      for (final type in [
        'Image',
        'Actions',
        'Email field',
        'Change plan',
        'Upgrade plan',
        'Payment method',
        'Receipt',
      ])
        story(
          type,
          'Functional anatomy equivalent with Specimen styling. This synthetic example makes no service call, purchase or subscription change.',
          (context) => ActionExample(
            builder: (_, report) => UiInlineCta(
              title: switch (type) {
                'Email field' => 'Get collection updates',
                'Payment method' => 'Payment details',
                'Receipt' => 'Export receipt',
                _ => 'Expand your collection workspace',
              },
              supporting: 'Review the details and choose the next step.',
              media: type == 'Image'
                  ? UiIcon(
                      UiIcons.sources,
                      size: UiIconSize.display,
                      color: context.ui.brand.secondary.content,
                    )
                  : null,
              content: type == 'Email field'
                  ? const UiField(
                      label: 'Email address',
                      hintText: 'name@museum.org',
                    )
                  : [
                      'Change plan',
                      'Upgrade plan',
                      'Payment method',
                      'Receipt',
                    ].contains(type)
                  ? Text(
                      type == 'Payment method'
                          ? 'Example card ···· 4242 · Expires 12/30'
                          : type == 'Receipt'
                          ? 'Example receipt · 0.00 USD · No charge'
                          : 'Example plan · 12 team members',
                      style: context.ui.type.body.copyWith(
                        color: context.ui.color.ink,
                      ),
                    )
                  : null,
              actions: [
                UiButton(
                  label: type == 'Receipt' ? 'Download receipt' : 'Continue',
                  onPressed: () => report('$type requested'),
                ),
                UiButton(
                  label: 'Dismiss',
                  variant: UiButtonVariant.ghost,
                  onPressed: () => report('Dismissed'),
                ),
              ],
            ),
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiContentDivider',
    useCases: [
      for (final style in UiContentDividerStyle.values)
        for (final type in [
          'Text',
          'Heading',
          'Button',
          'Button group',
          'Icon action',
          'Icon group',
        ])
          story(
            '${style.name} · $type',
            'Content is semantic; separator strokes are decorative. Commands are usable by keyboard and touch.',
            (context) => ActionExample(
              builder: (_, report) => UiContentDivider(
                style: style,
                child: type == 'Text' || type == 'Heading'
                    ? Text(
                        'Collection metadata',
                        style: type == 'Heading'
                            ? context.ui.type.title.copyWith(
                                color: context.ui.color.ink,
                              )
                            : context.ui.type.body.copyWith(
                                color: context.ui.color.ink,
                              ),
                      )
                    : type == 'Icon action'
                    ? Align(
                        alignment: AlignmentDirectional.centerStart,
                        child: UiIconButton(
                          icon: UiIcons.add,
                          semanticsLabel: 'Add metadata',
                          onPressed: () => report('Add requested'),
                        ),
                      )
                    : type == 'Icon group' || type == 'Button group'
                    ? UiButtonGroup(
                        label: 'Section commands',
                        iconOnly: type == 'Icon group',
                        items: [
                          UiButtonGroupItem(
                            label: 'Add section',
                            icon: UiIcons.add,
                            onPressed: () => report('Add requested'),
                          ),
                          UiButtonGroupItem(
                            label: 'More options',
                            icon: UiIcons.more,
                            onPressed: () => report('Options requested'),
                          ),
                        ],
                      )
                    : Wrap(
                        spacing: context.ui.space.s2,
                        runSpacing: context.ui.space.s2,
                        children: [
                          UiButton(
                            label: 'Add section',
                            onPressed: () => report('Add requested'),
                          ),
                          if (type == 'Button group')
                            UiButton(
                              label: 'Options',
                              variant: UiButtonVariant.secondary,
                              onPressed: () => report('Options requested'),
                            ),
                        ],
                      ),
              ),
            ),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiLoadingState',
    useCases: [
      for (final inline in [false, true])
        for (final style in UiLoadingIndicatorStyle.values)
          story(
            '${inline ? 'Inline' : 'Pane'} · ${style.name}',
            'Pending operation is named. Reduced motion freezes the indicator; Cancel is caller-owned.',
            (_) => ActionExample(
              builder: (_, report) => UiLoadingState(
                label: 'Loading collection records',
                supporting: 'Waiting for the server response.',
                inline: inline,
                indicatorStyle: style,
                action: UiButton(
                  label: 'Cancel',
                  variant: UiButtonVariant.secondary,
                  onPressed: () => report('Cancel requested'),
                ),
              ),
            ),
          ),
      story(
        'Measured progress',
        'Only a measured fraction is rendered as determinate progress.',
        (_) => const UiLoadingState(
          label: 'Preparing export',
          value: .4,
          supporting: '40 of 100 records prepared',
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiMetricCard',
    useCases: [
      for (final layout in ['Simple', 'Icon', 'Chart'])
        for (final actions in [false, true])
          story(
            '$layout · ${actions ? 'actions' : 'read only'}',
            'Formatted values and trend meaning are supplied by the host. No measurement remains explicit; the chart is synthetic.',
            (_) => ActionExample(
              builder: (_, report) => UiMetricCard(
                label: 'Reviewed specimens',
                value: '128',
                supporting: 'In the current collection',
                leading: layout == 'Icon'
                    ? const UiIcon(UiIcons.checklist)
                    : null,
                trend: const Text('↑ 12 more than last month'),
                chart: layout == 'Chart'
                    ? const UiChart(
                        label: 'Recent reviews',
                        kind: UiChartKind.line,
                        data: _observations,
                      )
                    : null,
                actions: actions
                    ? [
                        UiButton(
                          label: 'View records',
                          variant: UiButtonVariant.ghost,
                          onPressed: () => report('View requested'),
                        ),
                      ]
                    : [],
              ),
            ),
          ),
      story(
        'No measurement',
        'An unavailable metric is never shown as zero.',
        (_) => const UiMetricCard(
          label: 'Published specimens',
          value: 'Not measured',
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiDataTable treatments',
    useCases: [
      for (final dividers in UiTableDividers.values)
        for (final shadedHeader in [false, true])
          story(
            '${dividers.name} · ${shadedHeader ? 'shaded' : 'plain'} header',
            'Neutral alternating fills or row hairlines preserve the same table semantics. Rich cells retain their own actions and labels.',
            (_) => UiDataTable<String>(
              label: 'Collection records',
              dividers: dividers,
              shadedHeader: shadedHeader,
              columns: [
                UiDataColumn(
                  id: 'id',
                  label: 'Catalogue number',
                  helpText: 'The identifier on the original catalogue record.',
                  cellBuilder: (_, value) => UiTableCell(
                    label: value,
                    supporting: 'Preserved specimen',
                  ),
                ),
              ],
              rows: const [
                UiDataRow(
                  id: '001',
                  value: 'EXAMPLE-001',
                  label: 'EXAMPLE-001',
                ),
                UiDataRow(
                  id: '002',
                  value: 'EXAMPLE-002',
                  label: 'EXAMPLE-002',
                ),
                UiDataRow(
                  id: '003',
                  value: 'EXAMPLE-003',
                  label: 'EXAMPLE-003',
                ),
              ],
            ),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiTableCell',
    useCases: [
      for (final layout in [
        'Text',
        'Avatar',
        'Avatar group',
        'Icon',
        'Checkbox',
        'Radio',
        'Toggle',
        'Badge',
        'Badges',
        'Progress',
        'Trend positive',
        'Trend negative',
        'Rating',
        'Payment',
        'Avatar checkbox',
        'Avatar radio',
        'Avatar toggle',
        'Icon checkbox',
        'Icon radio',
        'Icon toggle',
        'Payment checkbox',
        'Payment radio',
        'Payment toggle',
        'Actions',
        'Action icons',
        'Action menu',
      ])
        for (final supporting in [false, true])
          story(
            '$layout · ${supporting ? 'supporting' : 'primary'}',
            'Rich cells compose existing controls and retain their own labels and callbacks. They do not add an implicit competing row tap.',
            (_) => _RichCellExample(layout: layout, supporting: supporting),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiTableActions',
    useCases: [
      for (final presentation in UiTableActionsPresentation.values)
        story(
          'Record commands · ${presentation.name}',
          'Every accessible name includes the record identity. Disabled commands remain visible.',
          (_) => ActionExample(
            builder: (_, report) => UiTableActions(
              rowLabel: 'EXAMPLE-001',
              presentation: presentation,
              actions: [
                UiTableAction(
                  label: 'View',
                  icon: UiIcons.record,
                  onPressed: () => report('Opened EXAMPLE-001'),
                ),
                const UiTableAction(label: 'Edit'),
                UiTableAction(
                  label: 'Remove',
                  destructive: true,
                  onPressed: () => report('Removal requested locally'),
                ),
              ],
            ),
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiRating',
    useCases: [
      for (final value in <double?>[null, 0, 3.5, 5])
        story(
          'Display · ${value ?? 'unrated'}',
          'The exact numeric rating accompanies Phosphor stars. Missing is distinct from zero.',
          (_) => UiRating(label: 'Image quality', value: value),
        ),
      story(
        'Controlled editing',
        'Keyboard arrows, Home/End and accessible increase/decrease request an exact rating. Clear restores the unrated state.',
        (_) => const _RatingExample(),
      ),
      story(
        'Disabled editing',
        'An unavailable rating does not accept pointer, keyboard or accessibility input.',
        (_) => const _RatingExample(enabled: false),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiMessageComposer',
    useCases: [
      story(
        'Draft and send',
        'Type a multiline draft. Ctrl/Cmd+Enter or Send submits locally and clears only the unchanged draft. No network call is made.',
        (_) => const _ComposerExample(),
      ),
      story(
        'Send failure',
        'A simulated delivery failure preserves the entire draft and announces the error.',
        (_) => const _ComposerExample(fail: true),
      ),
      story(
        'Disabled',
        'The host can suspend message drafting and delivery.',
        (_) => const _ComposerExample(enabled: false),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiPageIndicator',
    useCases: [
      for (final style in UiPageIndicatorStyle.values)
        for (final framed in [false, true])
          story(
            '${style.name} · ${framed ? 'framed' : 'plain'}',
            'Each mark has a full touch target and a spoken page position.',
            (_) => _IndicatorExample(style: style, framed: framed),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiCarousel',
    useCases: [
      for (final style in UiPageIndicatorStyle.values)
        story(
          style.name,
          'Controlled synthetic gallery. Arrows, Home/End, touch swipes and indicators request a new slide. It never auto-advances.',
          (_) => _CarouselExample(style: style),
        ),
      story(
        'Empty',
        'An empty carousel names the absence.',
        (_) => const UiCarousel(index: 0, children: []),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiBreadcrumbs variants',
    useCases: [
      for (final style in UiBreadcrumbStyle.values)
        for (final divider in UiBreadcrumbDivider.values)
          story(
            '${style.name} · ${divider.name}',
            'Ancestors remain keyboard links; the final current page is noninteractive. Full labels wrap at large text.',
            (_) => ActionExample(
              builder: (_, report) => UiBreadcrumbs(
                style: style,
                divider: divider,
                items: [
                  UiBreadcrumb(
                    label: 'Collections',
                    icon: UiIcons.sources,
                    onSelected: () => report('Collections'),
                  ),
                  UiBreadcrumb(
                    label: 'Botany',
                    onSelected: () => report('Botany'),
                  ),
                  const UiBreadcrumb(label: 'EXAMPLE-001'),
                ],
              ),
            ),
          ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSteps sizes',
    useCases: [
      for (final size in UiStepSize.values)
        story(
          size.name,
          'Visual marker size changes independently of minimum interactive targets, text scaling and task state.',
          (_) => UiSteps(
            size: size,
            connected: true,
            style: UiStepsStyle.iconTop,
            steps: const [
              UiStep(label: 'Photograph', state: UiStepState.complete),
              UiStep(label: 'Review', state: UiStepState.current),
              UiStep(label: 'Publish'),
            ],
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiEmptyState sizes',
    useCases: [
      for (final size in UiEmptyStateSize.values)
        story(
          size.name,
          'A cell, section or page absence uses the same named recovery contract.',
          (_) => UiEmptyState(
            size: size,
            icon: UiIcons.noResults,
            title: 'No records yet',
            body: 'Add a collection source to begin.',
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiSteps variants',
    useCases: [
      for (final style in UiStepsStyle.values)
        for (final compact in [false, true])
          for (final connected in [false, true])
            story(
              '${style.name} · ${compact ? 'compact' : 'regular'} · ${connected ? 'connected' : 'separate'}',
              'Upcoming, current, complete and error are independent of navigation permission. Layout stacks when labels need room.',
              (_) => ActionExample(
                builder: (_, report) => UiSteps(
                  style: style,
                  compact: compact,
                  connected: connected,
                  steps: [
                    UiStep(
                      label: 'Photograph',
                      state: UiStepState.complete,
                      onSelected: () => report('Photograph'),
                    ),
                    UiStep(
                      label: 'Transcribe',
                      description: 'Read the original labels',
                      state: UiStepState.current,
                      onSelected: () => report('Transcribe'),
                    ),
                    UiStep(
                      label: 'Verify',
                      state: UiStepState.error,
                      onSelected: () => report('Verify'),
                    ),
                    const UiStep(label: 'Publish'),
                  ],
                ),
              ),
            ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiPagination variants',
    useCases: [
      for (final variant in UiPaginationVariant.values)
        for (final shape in UiPaginationShape.values)
          for (final alignment in [
            WrapAlignment.start,
            WrapAlignment.center,
            WrapAlignment.end,
          ])
            story(
              '${variant.name} · ${shape.name} · ${alignment.name}',
              'Known page counts only. Controlled state preserves boundary and busy behavior.',
              (_) => _PaginationExample(
                variant: variant,
                shape: shape,
                alignment: alignment,
              ),
            ),
    ],
  ),
];

class _RichCellExample extends StatefulWidget {
  const _RichCellExample({required this.layout, required this.supporting});
  final String layout;
  final bool supporting;
  @override
  State<_RichCellExample> createState() => _RichCellExampleState();
}

class _RichCellExampleState extends State<_RichCellExample> {
  bool selected = false;
  @override
  Widget build(BuildContext context) => UiTableCell(
    label: widget.layout.startsWith('Payment')
        ? 'Example card ···· 4242'
        : 'EXAMPLE-001',
    supporting: widget.supporting ? 'Preserved specimen · Botany' : null,
    leading: widget.layout == 'Avatar group'
        ? const UiAvatarGroup(
            label: 'Reviewers',
            size: UiAvatarSize.small,
            people: [
              UiAvatarPerson(name: 'Alex Morgan'),
              UiAvatarPerson(name: 'Sam Lee'),
              UiAvatarPerson(name: 'Maya Chen'),
            ],
          )
        : widget.layout.startsWith('Avatar')
        ? const UiAvatar(name: 'Alex Morgan')
        : widget.layout.startsWith('Icon')
        ? const UiIcon(UiIcons.sources)
        : widget.layout.startsWith('Payment')
        ? const UiPaymentMark(name: 'Visa')
        : null,
    selection: widget.layout.toLowerCase().endsWith('checkbox')
        ? UiCheckbox(
            value: selected,
            label: 'Select EXAMPLE-001',
            showLabel: false,
            onChanged: (v) => setState(() => selected = v),
          )
        : widget.layout.toLowerCase().endsWith('toggle')
        ? UiSwitch(
            value: selected,
            label: 'Include EXAMPLE-001',
            showLabel: false,
            onChanged: (v) => setState(() => selected = v),
          )
        : widget.layout.toLowerCase().endsWith('radio')
        ? UiRadioGroup<bool>(
            value: selected,
            label: 'Selection',
            showLabel: false,
            onChanged: (v) => setState(() => selected = v ?? false),
            children: const [
              UiRadio<bool>(
                value: true,
                label: 'Select EXAMPLE-001',
                showLabel: false,
              ),
            ],
          )
        : null,
    detail: widget.layout == 'Progress'
        ? const UiProgress.bar(semanticsLabel: 'Review completion', value: .6)
        : widget.layout.startsWith('Trend')
        ? Text(
            widget.layout == 'Trend positive'
                ? '↑ 12% since previous month'
                : '↓ 12% since previous month',
          )
        : widget.layout == 'Rating'
        ? const UiRating(label: 'Image quality', value: 4.5)
        : widget.layout == 'Badge'
        ? const UiStatusBadge(label: 'Botany')
        : widget.layout == 'Badges'
        ? Wrap(
            spacing: context.ui.space.s1,
            runSpacing: context.ui.space.s1,
            children: const [
              UiStatusBadge(label: 'Botany'),
              UiStatusBadge(label: 'Verified'),
              UiStatusBadge(label: 'Public'),
            ],
          )
        : null,
    trailing: widget.layout.startsWith('Action')
        ? UiTableActions(
            rowLabel: 'EXAMPLE-001',
            presentation: widget.layout == 'Action icons'
                ? UiTableActionsPresentation.icons
                : widget.layout == 'Action menu'
                ? UiTableActionsPresentation.menu
                : UiTableActionsPresentation.buttons,
            actions: [
              UiTableAction(
                label: 'View',
                icon: UiIcons.record,
                onPressed: () => setState(() => selected = !selected),
              ),
            ],
          )
        : null,
  );
}

class _ComposerExample extends StatefulWidget {
  const _ComposerExample({this.fail = false, this.enabled = true});
  final bool fail, enabled;
  @override
  State<_ComposerExample> createState() => _ComposerExampleState();
}

class _ComposerExampleState extends State<_ComposerExample> {
  final controller = TextEditingController();
  String status = 'No message sent';
  bool attached = false;
  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      UiMessageComposer(
        controller: controller,
        enabled: widget.enabled,
        attachments: [
          if (attached)
            UiButton(
              label: 'Remove example attachment',
              variant: UiButtonVariant.secondary,
              onPressed: () => setState(() => attached = false),
            ),
        ],
        onAttach: () => setState(() => attached = true),
        onSend: (text) async {
          if (widget.fail) throw StateError('Synthetic delivery failure');
          setState(() {
            status = 'Sent locally: $text';
            attached = false;
          });
        },
      ),
      Text(status),
    ],
  );
}

class _IndicatorExample extends StatefulWidget {
  const _IndicatorExample({required this.style, required this.framed});
  final UiPageIndicatorStyle style;
  final bool framed;
  @override
  State<_IndicatorExample> createState() => _IndicatorExampleState();
}

class _IndicatorExampleState extends State<_IndicatorExample> {
  int index = 0;
  @override
  Widget build(BuildContext context) => UiPageIndicator(
    index: index,
    count: 5,
    style: widget.style,
    framed: widget.framed,
    onChanged: (value) => setState(() => index = value),
  );
}

class _CarouselExample extends StatefulWidget {
  const _CarouselExample({required this.style});
  final UiPageIndicatorStyle style;
  @override
  State<_CarouselExample> createState() => _CarouselExampleState();
}

class _CarouselExampleState extends State<_CarouselExample> {
  int index = 0;
  @override
  Widget build(BuildContext context) => UiCarousel(
    index: index,
    indicatorStyle: widget.style,
    onChanged: (value) => setState(() => index = value),
    children: [
      for (final label in [
        'Front specimen view',
        'Back specimen view',
        'Original label',
      ])
        ColoredBox(
          color: context.ui.color.ground,
          child: Center(
            child: Text(
              label,
              textAlign: TextAlign.center,
              style: context.ui.type.title.copyWith(
                color: context.ui.color.ink,
              ),
            ),
          ),
        ),
    ],
  );
}

class _PaginationExample extends StatefulWidget {
  const _PaginationExample({
    required this.variant,
    required this.shape,
    required this.alignment,
  });
  final UiPaginationVariant variant;
  final UiPaginationShape shape;
  final WrapAlignment alignment;
  @override
  State<_PaginationExample> createState() => _PaginationExampleState();
}

class _PaginationExampleState extends State<_PaginationExample> {
  int page = 3;
  @override
  Widget build(BuildContext context) => UiPagination(
    page: page,
    pageCount: 12,
    variant: widget.variant,
    shape: widget.shape,
    alignment: widget.alignment,
    onChanged: (value) => setState(() => page = value),
  );
}

class _ApplicationTemplate extends StatefulWidget {
  const _ApplicationTemplate({required this.template});
  final String template;
  @override
  State<_ApplicationTemplate> createState() => _ApplicationTemplateState();
}

class _ApplicationTemplateState extends State<_ApplicationTemplate> {
  final name = TextEditingController(text: 'Alex Morgan');
  final email = TextEditingController(text: 'alex@example.org');
  final tab = ValueNotifier(0);
  bool notifications = true;
  String receipt = 'No changes saved';
  String filter = '';
  String? currentRecord;
  String? activePage;
  String get page => activePage ?? widget.template;
  Set<Object> selected = {};
  @override
  void dispose() {
    name.dispose();
    email.dispose();
    tab.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final settings = page == 'Settings';
    final dashboard = page == 'Dashboard';
    final records = [
      'EXAMPLE-001',
      'EXAMPLE-002',
      'EXAMPLE-003',
    ].where((id) => id.toLowerCase().contains(filter.toLowerCase())).toList();
    final commands = [
      UiButton(
        label: settings ? 'Save settings' : 'Export records',
        onPressed: () => setState(
          () => receipt = settings
              ? 'Saved locally for ${name.text}'
              : 'Export requested for ${records.length} records',
        ),
      ),
    ];
    final content = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        UiPageHeader(
          title: settings
              ? 'Workspace settings'
              : dashboard
              ? 'Collection overview'
              : 'Collection directory',
          supporting: settings
              ? 'Manage your profile and notification preferences.'
              : 'Understand collection progress and inspect the underlying records.',
          breadcrumbs: UiBreadcrumbs(
            items: [
              UiBreadcrumb(
                label: 'Workspace',
                onSelected: () =>
                    setState(() => receipt = 'Workspace requested'),
              ),
              UiBreadcrumb(label: page),
            ],
          ),
          actions: commands,
          tabs: settings
              ? UiTabs(
                  tabs: const [
                    UiTab(label: 'Profile'),
                    UiTab(label: 'Notifications'),
                    UiTab(label: 'Team'),
                  ],
                  selected: tab,
                  semanticsLabel: 'Settings sections',
                )
              : null,
        ),
        SizedBox(height: ui.space.s6),
        if (settings)
          UiTabView(
            selected: tab,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const UiSectionHeader(
                    title: 'Personal details',
                    supporting: 'These values stay within this example.',
                    leading: UiAvatar(name: 'Alex Morgan'),
                  ),
                  SizedBox(height: ui.space.s4),
                  UiField(label: 'Full name', controller: name),
                  SizedBox(height: ui.space.s4),
                  UiField(label: 'Email address', controller: email),
                  SizedBox(height: ui.space.s4),
                  const UiTextArea(
                    label: 'Biography',
                    hintText: 'Tell your team about your collections work',
                  ),
                ],
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const UiSectionHeader(
                    title: 'Notification preferences',
                    supporting: 'Choose which updates you want to receive.',
                  ),
                  UiSwitch(
                    value: notifications,
                    label: 'Collection review updates',
                    onChanged: (value) => setState(() => notifications = value),
                  ),
                  Text(
                    notifications
                        ? 'Review updates are enabled in this example.'
                        : 'Review updates are disabled in this example.',
                  ),
                ],
              ),
              UiDataTable<String>(
                label: 'Workspace members',
                columns: [
                  UiDataColumn(
                    id: 'name',
                    label: 'Member',
                    cellBuilder: (_, value) => UiTableCell(
                      label: value,
                      supporting: 'Example curator',
                      leading: UiAvatar(name: value),
                    ),
                  ),
                ],
                rows: const [
                  UiDataRow(
                    id: 'alex',
                    value: 'Alex Morgan',
                    label: 'Alex Morgan',
                  ),
                  UiDataRow(id: 'sam', value: 'Sam Lee', label: 'Sam Lee'),
                ],
              ),
            ],
          )
        else ...[
          if (dashboard) ...[
            LayoutBuilder(
              builder: (context, constraints) {
                final metrics = [
                  const UiMetricCard(
                    label: 'Photographed',
                    value: '128',
                    supporting: 'Across three collections',
                    trend: Text('↑ 12 this month'),
                  ),
                  const UiMetricCard(
                    label: 'Reviewed',
                    value: '96',
                    supporting: 'Confirmed against original evidence',
                    trend: Text('↑ 8 this month'),
                  ),
                  const UiMetricCard(
                    label: 'Published',
                    value: 'Not measured',
                    supporting: 'No publication measurement available',
                  ),
                ];
                if (constraints.maxWidth <
                    ui.space.readingMax *
                        MediaQuery.textScalerOf(context).scale(1)) {
                  return Column(
                    children: [
                      for (final metric in metrics)
                        Padding(
                          padding: EdgeInsets.only(bottom: ui.space.s4),
                          child: metric,
                        ),
                    ],
                  );
                }
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (final metric in metrics)
                      Expanded(
                        child: Padding(
                          padding: EdgeInsetsDirectional.only(end: ui.space.s3),
                          child: metric,
                        ),
                      ),
                  ],
                );
              },
            ),
            SizedBox(height: ui.space.s6),
            const UiDataVisualization(
              label: 'Collection activity',
              series: _series,
              kind: UiDataVisualizationKind.area,
              legend: UiChartLegend.top,
              xAxisLabel: 'Month',
              yAxisLabel: 'Specimens',
            ),
            SizedBox(height: ui.space.s6),
          ],
          UiDataTable<String>(
            label: 'Collection records',
            header: UiSectionHeader(
              title: 'Records',
              meta: Text('${records.length} records'),
              supporting: 'Open a record to inspect its evidence.',
            ),
            toolbar: UiSearchField(
              label: 'Search catalogue number',
              clearLabel: 'Clear search',
              onChanged: (value) => setState(() => filter = value),
            ),
            columns: [
              UiDataColumn(
                id: 'id',
                label: 'Catalogue number',
                cellBuilder: (_, id) => UiTableCell(
                  label: id,
                  supporting: 'Preserved specimen · Botany',
                  leading: const UiIcon(UiIcons.sources),
                ),
              ),
              UiDataColumn(
                id: 'action',
                label: 'Actions',
                cellBuilder: (_, id) => UiTableActions(
                  rowLabel: id,
                  actions: [
                    UiTableAction(
                      label: 'Open record',
                      onPressed: () => setState(() => currentRecord = id),
                    ),
                  ],
                ),
              ),
            ],
            rows: [
              for (final id in records) UiDataRow(id: id, value: id, label: id),
            ],
            selectedIds: selected,
            onSelectionChanged: (value) => setState(() => selected = value),
          ),
          if (currentRecord != null)
            Padding(
              padding: EdgeInsets.only(top: ui.space.s5),
              child: UiInlineCta(
                title: currentRecord!,
                supporting: 'Example original label and source metadata.',
                content: const UiCodeSnippet(
                  label: 'Occurrence detail',
                  code: '{"basisOfRecord":"PreservedSpecimen"}',
                ),
                actions: [
                  UiButton(
                    label: 'Close record',
                    variant: UiButtonVariant.secondary,
                    onPressed: () => setState(() => currentRecord = null),
                  ),
                ],
              ),
            ),
        ],
        SizedBox(height: ui.space.s6),
        UiContentFooter(
          supporting: receipt,
          leading: settings
              ? UiButton(
                  label: 'Reset settings',
                  variant: UiButtonVariant.secondary,
                  onPressed: () => setState(() {
                    name.text = 'Alex Morgan';
                    email.text = 'alex@example.org';
                    notifications = true;
                    receipt = 'Settings reset locally';
                  }),
                )
              : Text('${selected.length} selected'),
          actions: commands,
        ),
      ],
    );
    Widget navigation(BuildContext navContext, {bool close = false}) =>
        UiNavigationMenu(
          semanticsLabel: 'Example workspace navigation',
          selectedId: page,
          expandedIds: const {},
          onExpandedChanged: (_) {},
          onSelected: (next) {
            setState(() => activePage = next);
            if (close) Navigator.pop(navContext);
          },
          header: const Text('Specimen digitization'),
          footer: const UiAvatar(name: 'Alex Morgan'),
          sections: const [
            UiNavigationSection(
              label: 'Workspace',
              items: [
                UiNavigationItem(
                  id: 'Dashboard',
                  label: 'Overview',
                  icon: UiIcons.collection,
                ),
                UiNavigationItem(
                  id: 'Informational directory',
                  label: 'Collection directory',
                  icon: UiIcons.record,
                ),
                UiNavigationItem(
                  id: 'Settings',
                  label: 'Workspace settings',
                  icon: UiIcons.settings,
                ),
              ],
            ),
          ],
        );
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >=
            (ui.space.readingMax + ui.space.targetMin * 5) *
                MediaQuery.textScalerOf(context).scale(1)) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: ui.space.targetMin * 5,
                height: ui.space.targetMin * 14,
                child: navigation(context),
              ),
              SizedBox(width: ui.space.s6),
              Expanded(child: content),
            ],
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiButton(
                label: 'Workspace navigation',
                variant: UiButtonVariant.secondary,
                onPressed: () => UiDrawer.show<void>(
                  context: context,
                  fromStart: true,
                  title: 'Workspace navigation',
                  body: (context) => SizedBox(
                    height: ui.space.targetMin * 10,
                    child: navigation(context, close: true),
                  ),
                ),
              ),
            ),
            SizedBox(height: ui.space.s5),
            content,
          ],
        );
      },
    );
  }
}

class _RatingExample extends StatefulWidget {
  const _RatingExample({this.enabled = true});
  final bool enabled;
  @override
  State<_RatingExample> createState() => _RatingExampleState();
}

class _RatingExampleState extends State<_RatingExample> {
  double? value = 3;
  @override
  Widget build(BuildContext context) => UiRating(
    label: 'Image quality',
    value: value,
    enabled: widget.enabled,
    onChanged: (next) => setState(() => value = next),
  );
}
