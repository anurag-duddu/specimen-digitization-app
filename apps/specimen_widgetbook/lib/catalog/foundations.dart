import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

import '../story.dart';

/// Brand and foundational roles, documented beside their real Flutter output.
List<WidgetbookComponent> get foundationComponents => <WidgetbookComponent>[
  WidgetbookComponent(
    name: 'Brand hero',
    useCases: <WidgetbookUseCase>[
      story(
        'Welcome and actions',
        'The Amber-to-Iris gradient is the hero. Copy and actions occupy a separate solid panel. Use on introduction and welcome screens; protect photographic evidence from any tint.',
        (BuildContext context) => ActionExample(
          builder: (BuildContext context, ValueChanged<String> report) =>
              UiBrandHero(
                eyebrow: context.knobs.string(
                  label: 'Eyebrow',
                  initialValue: 'Specimen Digitization',
                ),
                title: context.knobs.string(
                  label: 'Title',
                  initialValue: 'From specimens to knowledge.',
                ),
                description: context.knobs.string(
                  label: 'Description',
                  initialValue: 'A modern platform for museum collections.',
                ),
                actions:
                    context.knobs.boolean(
                      label: 'Show actions',
                      initialValue: true,
                    )
                    ? <Widget>[
                        UiButton(
                          label: 'Explore specimens',
                          onPressed: () => report('Explore selected'),
                        ),
                        UiButton(
                          label: 'Learn more',
                          variant: UiButtonVariant.secondary,
                          onPressed: () => report('Learn more selected'),
                        ),
                      ]
                    : const <Widget>[],
              ),
        ),
      ),
      story(
        'Long content at large text sizes',
        'Resize to 320 dp and select 200 percent text. Heading and description wrap; action targets keep their minimum size.',
        (BuildContext context) => const UiBrandHero(
          eyebrow: 'Collection workspace',
          title: 'Make every specimen part of a richer, searchable collection.',
          description:
              'Digitize photographs, preserve the original label transcription, and review extracted information with its evidence in view.',
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Brand accent',
    useCases: <WidgetbookUseCase>[
      story(
        'Decorative gradient region',
        'Exact endpoints: Amber #F5A45B and Iris #7B61FF. The component has no content slot, so text cannot accidentally be placed over the gradient. It is static and does not encode status.',
        (BuildContext context) => UiBrandAccent(
          height: context.knobs.double.slider(
            label: 'Region height',
            initialValue: 128,
            min: 32,
            max: 256,
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Colour',
    useCases: <WidgetbookUseCase>[
      story(
        'Identity seeds',
        'Five seeds from SD_brand.png. Seeds describe identity; use accessible semantic roles for text and boundaries.',
        (BuildContext context) {
          final UiBrandColors brand = context.ui.brand;
          return _swatches(context, <String, Color>{
            'Obsidian': brand.obsidian,
            'Paper': brand.paper,
            'Amber': brand.amber,
            'Iris': brand.iris,
            'Mist': brand.mist,
          });
        },
      ),
      story(
        'Accessible secondary emphasis',
        'Use the content/fill/on-fill triple together. Derived Iris text clears 4.5:1 on supported surfaces; the exact Iris seed alone is not a universal foreground.',
        (BuildContext context) {
          final UiStatusTriple secondary = context.ui.brand.secondary;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              _swatches(context, <String, Color>{
                'Content': secondary.content,
                'Fill': secondary.fill,
                'On fill': secondary.onFill,
              }),
              SizedBox(height: context.ui.space.s4),
              _RolePanel(label: 'Secondary brand emphasis', role: secondary),
            ],
          );
        },
      ),
      story(
        'Surface, text and edge roles',
        'Text and meaningful glyphs clear 4.5:1. Findable edges clear 3:1. Hairlines are decorative separators. Disabled reasons remain readable.',
        (BuildContext context) {
          final UiColor color = context.ui.color;
          return _swatches(context, <String, Color>{
            ...color.surfaces,
            ...color.textRoles,
            'Hairline': color.hairline,
            'Boundary': color.boundary,
            'Disabled content': color.disabledContent,
            'Focus ring': color.focusRing,
          });
        },
      ),
      story(
        'Functional state families',
        'Neutral and Iris classify information. Green affirms, warm amber asks for attention, red blocks. Keep each state label and Phosphor icon; colour never changes application state.',
        (BuildContext context) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            for (final MapEntry<String, UiStatusTriple> entry
                in context.ui.color.status.triples.entries)
              Padding(
                padding: EdgeInsets.only(bottom: context.ui.space.s2),
                child: _RolePanel(label: entry.key, role: entry.value),
              ),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Typography',
    useCases: <WidgetbookUseCase>[
      story(
        'Proportional roles',
        'Söhne is the named brand reference and is not bundled. Geist is the explicit licensed implementation fallback. All roles below come from UiType; text follows the selected text scaler.',
        (BuildContext context) {
          final String sample = context.knobs.string(
            label: 'Sample text',
            initialValue: 'From specimens to knowledge.',
          );
          return _typeSamples(context, context.ui.type.all, sample);
        },
      ),
      story(
        'Evidence and identifier roles',
        'Geist Mono is bundled for identifiers, code and verbatim evidence. Literal roles disable ligatures; tabular figures keep changing digits aligned.',
        (BuildContext context) => _typeSamples(
          context,
          context.ui.type.mono.all,
          context.knobs.string(
            label: 'Evidence sample',
            initialValue: 'FMNHINS 123456 · 0O 1lI 5S 2Z 8B',
          ),
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Phosphor icons',
    useCases: <WidgetbookUseCase>[
      story(
        'Meaning registry',
        'All glyphs use the owned UiIcons registry. The current/settled form uses fill only where the registered meaning supports it. Control labels remain accessible.',
        (BuildContext context) {
          final UiIconSize size = context.knobs.object.dropdown(
            label: 'Size',
            options: UiIconSize.values,
            initialOption: UiIconSize.action,
            labelBuilder: (UiIconSize size) =>
                '${size.name} · ${size.dimension.toInt()} dp',
          );
          final bool current = context.knobs.boolean(
            label: 'Current destination',
          );
          final String filter = context.knobs
              .string(label: 'Filter meaning')
              .toLowerCase();
          return Wrap(
            spacing: context.ui.space.s2,
            runSpacing: context.ui.space.s2,
            children: <Widget>[
              for (final MapEntry<String, IconSpec> entry
                  in UiIcons.byKey.entries.where(
                    (MapEntry<String, IconSpec> entry) =>
                        entry.key.toLowerCase().contains(filter),
                  ))
                SizedBox(
                  width: 160,
                  child: Surface(
                    hairline: true,
                    padding: EdgeInsets.all(context.ui.space.s4),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        UiIcon(entry.value, size: size, current: current),
                        SizedBox(height: context.ui.space.s2),
                        Text(entry.key, style: context.ui.type.label),
                      ],
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Spacing and density',
    useCases: <WidgetbookUseCase>[
      story(
        'Spacing scale',
        'Eight dp structural grid with a four dp optical half step. s3 and s5 are compatibility aliases, not extra grid steps. Use the density environment control to inspect touch/pointer defaults.',
        (BuildContext context) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            for (final MapEntry<String, double> step
                in context.ui.space.steps.entries)
              Padding(
                padding: EdgeInsets.only(bottom: context.ui.space.s2),
                child: Wrap(
                  spacing: context.ui.space.s4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: <Widget>[
                    Text(
                      '${step.key} · ${step.value.toInt()} dp',
                      style: context.ui.type.mono.identifier,
                    ),
                    SizedBox(
                      width: step.value,
                      height: context.ui.space.s4,
                      child: ColoredBox(
                        color: context.ui.brand.secondary.content,
                      ),
                    ),
                  ],
                ),
              ),
            SizedBox(height: context.ui.space.s4),
            Text(
              'Current density: ${context.ui.density.mode.name}. Visual control: ${context.ui.density.controlHeight.toInt()} dp. Minimum target: ${UiDensity.hitBox.toInt()} dp.',
            ),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Shape and surfaces',
    useCases: <WidgetbookUseCase>[
      story(
        'Shape roles',
        'Shared radii give fields, cards and overlays predictable contours. Evidence and table cells stay square. A decorative hairline is not an actionable boundary.',
        (BuildContext context) => Wrap(
          spacing: context.ui.space.s4,
          runSpacing: context.ui.space.s4,
          children: <Widget>[
            for (final MapEntry<String, double> radius
                in context.ui.shape.radii.entries)
              SizedBox(
                width: 176,
                child: Surface(
                  radius: radius.value,
                  boundary: true,
                  padding: EdgeInsets.all(context.ui.space.s4),
                  child: Text('${radius.key}\n${radius.value.toInt()} dp'),
                ),
              ),
          ],
        ),
      ),
      story(
        'Neutral surface roles',
        'Solid surfaces preserve readability and photographic fidelity. Ground, paper and matte follow the selected appearance. No photograph should inherit a brand wash.',
        (BuildContext context) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            for (final SurfaceRole role in SurfaceRole.values)
              Padding(
                padding: EdgeInsets.only(bottom: context.ui.space.s4),
                child: Surface(
                  role: role,
                  hairline: true,
                  padding: EdgeInsets.all(context.ui.space.s6),
                  child: Text(
                    '${role.name} surface',
                    style: context.ui.type.title,
                  ),
                ),
              ),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Motion',
    useCases: <WidgetbookUseCase>[
      story(
        'State transition and reduced motion',
        'Use the environment control to enable reduced motion. This live disclosure uses the shared duration and curve; content appears immediately when motion is reduced. Brand gradients remain static.',
        (BuildContext context) => const _MotionExample(),
      ),
    ],
  ),
];

String _hex(Color color) =>
    '#${(color.toARGB32() & 0xFFFFFF).toRadixString(16).toUpperCase().padLeft(6, '0')}';

Widget _swatches(BuildContext context, Map<String, Color> colors) => Wrap(
  spacing: context.ui.space.s4,
  runSpacing: context.ui.space.s4,
  children: <Widget>[
    for (final MapEntry<String, Color> entry in colors.entries)
      SizedBox(
        width: 160,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            SizedBox(
              height: context.ui.space.s16,
              width: double.infinity,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: entry.value,
                  border: Border.all(color: context.ui.color.hairline),
                ),
              ),
            ),
            SizedBox(height: context.ui.space.s2),
            Text(entry.key, style: context.ui.type.label),
            Text(
              _hex(entry.value),
              style: context.ui.type.mono.identifier.copyWith(
                color: context.ui.color.inkSecondary,
              ),
            ),
          ],
        ),
      ),
  ],
);

Widget _typeSamples(
  BuildContext context,
  Map<String, TextStyle> roles,
  String sample,
) => Column(
  crossAxisAlignment: CrossAxisAlignment.stretch,
  children: <Widget>[
    for (final MapEntry<String, TextStyle> role in roles.entries)
      Padding(
        padding: EdgeInsets.only(bottom: context.ui.space.s6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              '${role.key} · ${role.value.fontSize?.toInt()} dp',
              style: context.ui.type.label.copyWith(
                color: context.ui.color.inkSecondary,
              ),
            ),
            SizedBox(height: context.ui.space.s2),
            Text(
              sample,
              style: role.value.copyWith(color: context.ui.color.ink),
            ),
          ],
        ),
      ),
  ],
);

class _RolePanel extends StatelessWidget {
  const _RolePanel({required this.label, required this.role});
  final String label;
  final UiStatusTriple role;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: role.fill,
      border: Border.all(color: role.content),
    ),
    child: Padding(
      padding: EdgeInsets.all(context.ui.space.s4),
      child: Text(
        label,
        style: context.ui.type.label.copyWith(color: role.onFill),
      ),
    ),
  );
}

class _MotionExample extends StatefulWidget {
  const _MotionExample();
  @override
  State<_MotionExample> createState() => _MotionExampleState();
}

class _MotionExampleState extends State<_MotionExample> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        for (final (String name, Duration duration) in <(String, Duration)>[
          ('Quick', ui.motion.quick),
          ('Short', ui.motion.short),
          ('Standard', ui.motion.standard),
          ('Medium', ui.motion.medium),
          ('Emphasized', ui.motion.emphasized),
          ('Slow', ui.motion.slow),
        ])
          Text(
            '$name · ${duration.inMilliseconds} ms',
            style: ui.type.mono.identifier,
          ),
        SizedBox(height: ui.space.s4),
        UiButton(
          label: _expanded ? 'Hide details' : 'Show details',
          onPressed: () => setState(() => _expanded = !_expanded),
        ),
        SizedBox(height: ui.space.s4),
        AnimatedSize(
          duration: ui.motion.standard,
          curve: MotionTokens.standardCurve,
          alignment: AlignmentDirectional.topStart,
          child: _expanded
              ? Surface(
                  hairline: true,
                  padding: EdgeInsets.all(ui.space.s4),
                  child: const Text(
                    'Synthetic example: a real state change using the product motion tokens. No collection data is loaded.',
                  ),
                )
              : const SizedBox(width: double.infinity),
        ),
      ],
    );
  }
}
