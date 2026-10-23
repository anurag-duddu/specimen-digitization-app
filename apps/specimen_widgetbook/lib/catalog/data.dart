import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

/// Existing data-family primitives, with explicit states and local interactions.
List<WidgetbookComponent> get dataComponents => <WidgetbookComponent>[
  WidgetbookComponent(
    name: 'Avatar',
    useCases: <WidgetbookUseCase>[
      for (final UiAvatarSize size in UiAvatarSize.values)
        WidgetbookUseCase(
          name: '${size.name} · initials',
          builder: (BuildContext context) => _DataSpecimen(
            note:
                'Neutral initials identify a person. A host-supplied photograph falls back to initials when unavailable.',
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiAvatar(
                name: context.knobs.string(
                  label: 'Name',
                  initialValue: 'Ana Ruiz',
                ),
                size: size,
              ),
            ),
          ),
        ),
      WidgetbookUseCase(
        name: 'Names in different scripts',
        builder: (BuildContext context) => _DataSpecimen(
          note:
              'The full name is announced; initials respect grapheme clusters and the person’s own spelling.',
          child: Wrap(
            spacing: context.ui.space.s4,
            children: const <Widget>[
              UiAvatar(name: 'Ana Ruiz'),
              UiAvatar(name: '李 明'),
              UiAvatar(name: 'Amélie Dubois'),
              UiAvatar(name: 'Anurag'),
            ],
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Data tile and metric',
    useCases: <WidgetbookUseCase>[
      for (final UiDataTileSurface surface in UiDataTileSurface.values)
        WidgetbookUseCase(
          name: '${surface.name} · measured',
          builder: (BuildContext context) => _DataSpecimen(
            note:
                'A neutral metric surface. The legacy glass name resolves to an opaque surface; value changes never add status hues.',
            child: UiDataTile(
              label: 'Synthetic records reviewed',
              value: context.knobs.string(label: 'Value', initialValue: '128'),
              unit: 'OF 240',
              footer: 'Synthetic sample for component review',
              surface: surface,
            ),
          ),
        ),
      WidgetbookUseCase(
        name: 'Hero numeral',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'One hero metric per composition. Numerals step down by type role before scaling as the available width decreases.',
          child: UiDataTile(
            label: 'Synthetic records reviewed',
            value: '1,280',
            hero: true,
            surface: UiDataTileSurface.paper,
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Not measured',
        builder: (BuildContext context) => const _DataSpecimen(
          note: 'An unavailable measurement is words, never a fabricated zero.',
          child: UiDataTile(
            label: 'Average review time',
            value: 'Not measured',
            footer: 'No completed reviews in this synthetic sample',
            surface: UiDataTileSurface.paper,
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'With progress',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'The metric owns one accessible sentence, including the value in its progress slot.',
          child: UiDataTile(
            label: 'Synthetic batch',
            value: '62',
            unit: 'OF 100',
            semanticsLabel: 'Synthetic batch, 62 of 100 records reviewed',
            surface: UiDataTileSurface.paper,
            child: UiProgress.bar(
              value: .62,
              semanticsLabel: 'Synthetic batch progress',
            ),
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Arc indicator',
    useCases: <WidgetbookUseCase>[
      for (final UiArcSweep sweep in UiArcSweep.values)
        WidgetbookUseCase(
          name: '${sweep.name} · measured',
          builder: (BuildContext context) => _DataSpecimen(
            note:
                'A single neutral gauge with named endpoints and an exact accessible value. The number is synthetic.',
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiArcIndicator(
                value: context.knobs.double.slider(
                  label: 'Fraction',
                  initialValue: .62,
                  min: 0,
                  max: 1,
                ),
                semanticsLabel: 'Synthetic score',
                sweep: sweep,
                minLabel: '0',
                maxLabel: '100',
              ),
            ),
          ),
        ),
      WidgetbookUseCase(
        name: 'Unmeasured',
        builder: (BuildContext context) => const _DataSpecimen(
          note: 'An unknown score has no marker and no invented fraction.',
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiArcIndicator(
              value: null,
              semanticsLabel: 'Synthetic score',
            ),
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Progress',
    useCases: <WidgetbookUseCase>[
      for (final UiProgressSize size in UiProgressSize.values)
        WidgetbookUseCase(
          name: '${size.name} ring · determinate',
          builder: (BuildContext context) => _DataSpecimen(
            note:
                'Measured progress uses the host’s last reported fraction. Keyboard-adjustable Widgetbook controls do not contact production.',
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiProgress.ring(
                size: size,
                semanticsLabel: 'Synthetic upload progress',
                value: context.knobs.double.slider(
                  label: 'Progress',
                  initialValue: .62,
                  min: 0,
                  max: 1,
                ),
              ),
            ),
          ),
        ),
      WidgetbookUseCase(
        name: 'Bar · determinate',
        builder: (BuildContext context) => _DataSpecimen(
          note:
              'The bar grows from the reading start edge and retains exact accessible progress.',
          child: UiProgress.bar(
            semanticsLabel: 'Synthetic upload progress',
            value: context.knobs.double.slider(
              label: 'Progress',
              initialValue: .62,
              min: 0,
              max: 1,
            ),
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Ring · indeterminate',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'No completion fraction is invented. Reduced motion replaces the continuous animation.',
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiProgress.ring(
              semanticsLabel: 'Waiting for synthetic response',
            ),
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Bar · indeterminate',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'A local waiting state. Use the reduced-motion addon to inspect its still alternative.',
          child: UiProgress.bar(
            semanticsLabel: 'Waiting for synthetic response',
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Zero and complete',
        builder: (BuildContext context) => _DataSpecimen(
          note:
              'Measured zero and measured completion have distinct geometry and accessible values.',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              const UiProgress.bar(
                value: 0,
                semanticsLabel: 'Synthetic initial progress',
              ),
              SizedBox(height: context.ui.space.s6),
              const UiProgress.bar(
                value: 1,
                semanticsLabel: 'Synthetic completed progress',
              ),
            ],
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Skeleton',
    useCases: <WidgetbookUseCase>[
      for (final (String, Widget) sample in <(String, Widget)>[
        ('Line', const UiSkeleton.line(widthFactor: .7)),
        ('Row', const UiSkeleton.row()),
        ('Tile', const UiSkeleton.tile()),
      ])
        WidgetbookUseCase(
          name: sample.$1,
          builder: (BuildContext context) => _DataSpecimen(
            note:
                'Placeholders are hidden from assistive technology; the host supplies one loading announcement. Reduced motion stops the pulse.',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Semantics(
                  liveRegion: true,
                  child: const Text('Loading synthetic content'),
                ),
                SizedBox(height: context.ui.space.s4),
                sample.$2,
              ],
            ),
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'Empty state',
    useCases: <WidgetbookUseCase>[
      for (final visual in ['Phosphor icon', 'File type', 'Illustration'])
        for (final compact in [false, true])
          WidgetbookUseCase(
            name: '$visual · ${compact ? 'compact' : 'page'}',
            builder: (_) =>
                _EmptyVisualExample(visual: visual, compact: compact),
          ),
      WidgetbookUseCase(
        name: 'Informational',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'Name the absence and explain what would fill it. A state with nothing to do has no action.',
          child: UiEmptyState(
            icon: UiIcons.noResults,
            title: 'No records yet',
            body:
                'Records will appear here after this synthetic collection has content.',
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Recovery action',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'The recovery action changes local sample state; it is not a decorative button.',
          child: _EmptyExample(),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Status strip and blockers',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Facts and provenance',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'Disposition, provenance and factual copy remain separate slots. Labels carry meaning alongside Phosphor icons.',
          child: UiStatusStrip(
            disposition: Text('Needs a human'),
            provenance: <Widget>[
              Text('Synthetic sample'),
              Text('2 photographs'),
              Text('3 fields need review'),
            ],
          ),
        ),
      ),
      WidgetbookUseCase(
        name: 'Blockers with working resolution',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'Open the blocker summary to inspect its sheet. The action resolves this local example only.',
          child: _BlockerExample(),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Hairline',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Horizontal',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'A decorative neutral separator, omitted from the semantics tree.',
          child: UiHairline(),
        ),
      ),
      WidgetbookUseCase(
        name: 'Directional inset',
        builder: (BuildContext context) => _DataSpecimen(
          note: 'The start inset follows the reading direction.',
          child: UiHairline(indent: context.ui.space.targetMin),
        ),
      ),
      WidgetbookUseCase(
        name: 'Vertical',
        builder: (BuildContext context) => _DataSpecimen(
          note: 'Vertical rules use an explicit token-derived parent height.',
          child: SizedBox(
            height: context.ui.space.targetMin,
            child: const Row(
              children: <Widget>[
                UiIcon(UiIcons.image),
                UiHairline.vertical(),
                UiIcon(UiIcons.record),
              ],
            ),
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'List row',
    useCases: <WidgetbookUseCase>[
      for (final UiListRowMode mode in UiListRowMode.values)
        WidgetbookUseCase(
          name: mode.name,
          builder: (BuildContext context) => _DataSpecimen(
            note:
                'Rows publish the correct role for navigation, selection or tabs. Press or use Enter/Space to update the local example.',
            child: _RowExample(mode: mode),
          ),
        ),
      WidgetbookUseCase(
        name: 'Unavailable with reason',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'The host states why the action is unavailable, rather than leaving a silent disabled control.',
          child: UiListRow(
            title: 'DEMO-0041',
            subtitle: 'Synthetic specimen record',
            disabledReason: 'This example is locked while a review is pending.',
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Photo tile',
    useCases: <WidgetbookUseCase>[
      WidgetbookUseCase(
        name: 'Included · separate open and select actions',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'The preview opens the local inspector state; the checkbox changes selection independently. This is a labelled preview placeholder.',
          child: _PhotoExample(),
        ),
      ),
      WidgetbookUseCase(
        name: 'Excluded',
        builder: (BuildContext context) => const _DataSpecimen(
          note:
              'Exclusion from submission is distinct from the current bulk-selection state.',
          child: _PhotoExample(included: false),
        ),
      ),
    ],
  ),
];

class _DataSpecimen extends StatelessWidget {
  const _DataSpecimen({required this.note, required this.child});
  final String note;
  final Widget child;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    child: Padding(
      padding: EdgeInsets.all(context.ui.space.s4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            note,
            style: context.ui.type.bodySmall.copyWith(
              color: context.ui.color.inkSecondary,
            ),
          ),
          SizedBox(height: context.ui.space.s6),
          child,
        ],
      ),
    ),
  );
}

class _EmptyExample extends StatefulWidget {
  const _EmptyExample();
  @override
  State<_EmptyExample> createState() => _EmptyExampleState();
}

class _EmptyExampleState extends State<_EmptyExample> {
  bool _cleared = false;
  @override
  Widget build(BuildContext context) => _cleared
      ? UiListRow(
          title: 'DEMO-0041',
          subtitle:
              'Synthetic record visible after clearing the example filter',
          onPressed: () => setState(() => _cleared = false),
        )
      : UiEmptyState(
          icon: UiIcons.noResults,
          title: 'No matching records',
          body: 'The current synthetic filter hides every record.',
          action: UiButton(
            label: 'Clear filters',
            onPressed: () => setState(() => _cleared = true),
          ),
        );
}

class _BlockerExample extends StatefulWidget {
  const _BlockerExample();
  @override
  State<_BlockerExample> createState() => _BlockerExampleState();
}

class _BlockerExampleState extends State<_BlockerExample> {
  bool _resolved = false;
  @override
  Widget build(BuildContext context) => UiStatusStrip(
    disposition: Text(_resolved ? 'Example resolved' : 'Needs a human'),
    facts: const <String>['Synthetic specimen'],
    blockers: _resolved
        ? null
        : UiBlockers(
            summary: '1 blocker',
            sheetTitle: 'Synthetic review blocker',
            items: <UiBlocker>[
              UiBlocker(
                label: 'Collector needs review',
                detail: 'The original label contains an ambiguous initial.',
                actionLabel: 'Resolve example',
                onAction: () {
                  setState(() => _resolved = true);
                },
              ),
            ],
          ),
  );
}

class _RowExample extends StatefulWidget {
  const _RowExample({required this.mode});
  final UiListRowMode mode;
  @override
  State<_RowExample> createState() => _RowExampleState();
}

class _RowExampleState extends State<_RowExample> {
  bool _selected = false;
  @override
  Widget build(BuildContext context) => UiListRow(
    title: 'DEMO-0041',
    subtitle: _selected
        ? 'Synthetic row activated'
        : 'Synthetic row waiting for interaction',
    mode: widget.mode,
    selected: _selected,
    leading: const UiIcon(UiIcons.record),
    trailing: const UiRowTrailing(
      label: 'Needs a human',
      icon: UiIcons.needsReview,
    ),
    onPressed: () => setState(() => _selected = !_selected),
  );
}

class _PhotoExample extends StatefulWidget {
  const _PhotoExample({this.included = true});
  final bool included;
  @override
  State<_PhotoExample> createState() => _PhotoExampleState();
}

class _PhotoExampleState extends State<_PhotoExample> {
  bool _selected = false;
  bool _opened = false;
  @override
  Widget build(BuildContext context) => SizedBox(
    height:
        context.ui.space.targetMin * 6 +
        UiType.lineHeightOf(context.ui.type.bodySmall, context) * 4,
    child: UiPhotoTile(
      preview: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const UiIcon(UiIcons.image, size: UiIconSize.display),
            Text(
              _opened ? 'Preview opened' : 'Synthetic image placeholder',
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
      name: 'DEMO-0041-label.jpg',
      status: _opened
          ? 'Inspector action recorded locally'
          : 'Synthetic preview',
      included: widget.included,
      selected: _selected,
      onSelected: (bool value) => setState(() => _selected = value),
      onOpen: () => setState(() => _opened = !_opened),
    ),
  );
}

class _EmptyVisualExample extends StatefulWidget {
  const _EmptyVisualExample({required this.visual, required this.compact});
  final String visual;
  final bool compact;
  @override
  State<_EmptyVisualExample> createState() => _EmptyVisualExampleState();
}

class _EmptyVisualExampleState extends State<_EmptyVisualExample> {
  String? receipt;
  @override
  Widget build(BuildContext context) => _DataSpecimen(
    note:
        'Phosphor visuals replace proprietary illustrations; actions update this local example only.',
    child: receipt == null
        ? UiEmptyState(
            icon: UiIcons.noResults,
            title: 'No matching records',
            body: 'Clear the filters or add a source to begin.',
            compact: widget.compact,
            media: widget.visual == 'Phosphor icon'
                ? null
                : widget.visual == 'File type'
                ? const UiFileTypeIcon(extension: 'CSV')
                : SizedBox(
                    height: context.ui.space.targetMin * 2,
                    child: const Stack(
                      alignment: Alignment.center,
                      children: [
                        UiBrandPattern(style: UiBrandPatternStyle.grid),
                        UiFeaturedIcon(icon: UiIcons.sources),
                      ],
                    ),
                  ),
            action: UiButton(
              label: 'Add source',
              onPressed: () =>
                  setState(() => receipt = 'Source chooser requested'),
            ),
            secondaryAction: UiButton(
              label: 'Clear filters',
              variant: UiButtonVariant.secondary,
              onPressed: () => setState(() => receipt = 'Filters cleared'),
            ),
          )
        : Column(
            children: [
              Text(receipt!),
              UiButton(
                label: 'Reset example',
                onPressed: () => setState(() => receipt = null),
              ),
            ],
          ),
  );
}
