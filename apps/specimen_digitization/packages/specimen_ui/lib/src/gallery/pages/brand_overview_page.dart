/// The active brand contract, rendered with the real runtime tokens.
library;

import 'package:flutter/widgets.dart';
import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// The catalog's starting point.
const brandOverviewPage = GalleryPage(
  id: 'brand',
  title: 'Brand foundations',
  summary:
      'Amber to Iris. Obsidian, Paper and Mist. A focused identity for collection work.',
  builder: buildBrandOverviewPage,
  maxGlassPanes: 0,
);

/// Shows the palette, typography and component anatomy in one view.
Widget buildBrandOverviewPage(BuildContext context) {
  final ui = context.ui;
  return Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const UiBrandHero(
        eyebrow: 'Specimen Digitization',
        title: 'From specimens\nto knowledge.',
        description:
            'A modern platform for museum collections. Clear evidence, considered tools, and room to focus.',
      ),
      SizedBox(height: ui.space.s8),
      GallerySection(
        title: 'Five seeds. One identity.',
        child: LayoutBuilder(
          builder: (context, constraints) => Wrap(
            spacing: ui.space.s4,
            runSpacing: ui.space.s4,
            children: [
              for (final entry in <String, Color>{
                'Obsidian': ui.brand.obsidian,
                'Paper': ui.brand.paper,
                'Amber': ui.brand.amber,
                'Iris': ui.brand.iris,
                'Mist': ui.brand.mist,
              }.entries)
                SizedBox(
                  width: MediaQuery.textScalerOf(
                    context,
                  ).scale(ui.space.labelMin).clamp(0.0, constraints.maxWidth),
                  child: Directionality(
                    textDirection: TextDirection.ltr,
                    child: GallerySpecimen(
                      label: entry.key,
                      note:
                          '#${entry.value.toARGB32().toRadixString(16).substring(2).toUpperCase()}',
                      child: SizedBox(
                        height: ui.space.s16,
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            color: entry.value,
                            borderRadius: BorderRadius.circular(ui.shape.tile),
                            border: Border.all(color: ui.color.hairline),
                          ),
                          child: const SizedBox.expand(),
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
      GallerySection(
        title: 'Type with a purpose',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Collection knowledge, clearly expressed.',
              style: ui.type.headline,
            ),
            SizedBox(height: ui.space.s3),
            Text(
              'Geist is the bundled implementation face. The brand reference specifies Söhne; a licensed font asset is needed before that substitution.',
              style: ui.type.body.copyWith(color: ui.color.inkSecondary),
            ),
            SizedBox(height: ui.space.s3),
            Text(
              'FMNH 118402 / 41.8781, −87.6298',
              style: ui.type.mono.identifier,
            ),
          ],
        ),
      ),
      GallerySection(
        title: 'Commands and choices',
        child: Wrap(
          spacing: ui.space.s3,
          runSpacing: ui.space.s3,
          children: [
            UiButton(
              label: 'Review specimen',
              leading: UiIcons.record,
              onPressed: () {},
            ),
            UiButton(
              label: 'View source',
              variant: UiButtonVariant.secondary,
              onPressed: () {},
            ),
            const UiButton(
              label: 'Approve record',
              disabledReason: 'Resolve the required fields first.',
            ),
            UiChip(label: 'Needs review', status: ui.color.status.needsReview),
            UiChip(label: 'Verified', status: ui.color.status.cleared),
          ],
        ),
      ),
      GallerySection(
        title: 'Usage rules',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'The gradient introduces the brand. Neutral surfaces support the work. Iris marks secondary emphasis. Status colour appears only when it communicates a result or required action.',
              style: ui.type.body,
            ),
            SizedBox(height: ui.space.s3),
            Text(
              'Every example in this catalog is synthetic. Use Preview settings to inspect both modes, pointer and touch density, 200% text, RTL and reduced motion. Resize the window to review fit.',
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          ],
        ),
      ),
    ],
  );
}
