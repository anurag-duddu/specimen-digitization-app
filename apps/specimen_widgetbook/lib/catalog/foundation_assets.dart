import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';
import '../story.dart';

List<WidgetbookComponent> get foundationAssetComponents => [
  WidgetbookComponent(
    name: 'UiDesignPointer',
    useCases: [
      story(
        'Arrow, drag and hand',
        'Review-only Phosphor gesture pointers. They have accessible names and do not impersonate interactive controls.',
        (_) => Wrap(
          spacing: 24,
          runSpacing: 24,
          children: [
            for (final kind in UiDesignPointerKind.values)
              UiDesignPointer(kind: kind, label: 'Collection reviewer'),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiMeasurement',
    useCases: [
      for (final spacer in [false, true])
        story(
          spacer ? 'Spacing bands' : 'Dimension lines',
          'Measured labels are caller-supplied; left and right describe diagram coordinates even in RTL.',
          (_) => Wrap(
            spacing: 24,
            runSpacing: 24,
            children: [
              for (final position in UiMeasurementLabelPosition.values)
                UiMeasurement(
                  label: '24 dp',
                  position: position,
                  spacer: spacer,
                ),
            ],
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiFeaturedIcon',
    useCases: [
      for (final shape in UiFeaturedIconShape.values)
        story(
          shape.name,
          'Featured Phosphor glyphs use neutral surfaces or functional status. Their geometry is independent of the interactive hit target.',
          (_) => Wrap(
            spacing: 16,
            runSpacing: 16,
            children: [
              for (final tone in UiBannerTone.values)
                UiFeaturedIcon(
                  icon: UiIcons.record,
                  shape: shape,
                  tone: tone,
                  semanticsLabel: '${tone.name} record',
                ),
            ],
          ),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiFileTypeIcon',
    useCases: [
      story(
        'Format vocabulary',
        'File formats are named in text and semantics. All glyphs remain Phosphor and the format does not invent a new brand color.',
        (_) => Wrap(
          spacing: 16,
          runSpacing: 16,
          children: [
            for (final extension in [
              'PDF',
              'JPG',
              'PNG',
              'SVG',
              'CSV',
              'XLSX',
              'DOCX',
              'PPTX',
              'ZIP',
              'RAR',
              'MP3',
              'MP4',
              'JSON',
              'HTML',
              'CSS',
              'JS',
              'FIG',
            ])
              UiFileTypeIcon(extension: extension),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiPaymentMark',
    useCases: [
      story(
        'Named provider slots',
        'Use authentic provider artwork when the host supplies it; the neutral fallback names the provider. These marks do not imply a connected payment service.',
        (_) => const Wrap(
          spacing: 16,
          runSpacing: 16,
          children: [
            UiPaymentMark(name: 'Visa'),
            UiPaymentMark(name: 'Mastercard'),
            UiPaymentMark(name: 'American Express'),
            UiPaymentMark(name: 'Apple Pay'),
            UiPaymentMark(name: 'Bank transfer'),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Design annotations',
    useCases: [
      story(
        'Notes, keyboard combinations and measurements',
        'Annotation slots support design review without becoming product UI. Key combinations wrap at large text and have explicit spoken names.',
        (context) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const UiNotice(
              title: 'Anatomy note',
              description:
                  'The label names the action. Supporting text explains consequences. Status remains understandable without color.',
              showIcon: false,
            ),
            SizedBox(height: context.ui.space.s4),
            const Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                UiKeyCap(label: '⌘', semanticsLabel: 'Command'),
                UiKeyCap(label: '⇧', semanticsLabel: 'Shift'),
                UiKeyCap(label: 'K'),
                UiKeyCap(label: 'Esc', semanticsLabel: 'Escape'),
                UiKeyCap(label: '←', semanticsLabel: 'Left arrow'),
              ],
            ),
            SizedBox(height: context.ui.space.s4),
            Text(
              '1 · Label\n2 · Supporting text\n3 · Leading glyph\n4 · Action or status',
              style: context.ui.type.body,
            ),
            SizedBox(height: context.ui.space.s3),
            Text(
              'Spacing: ${context.ui.space.s4.toInt()} dp · Minimum interactive target: 48 dp',
              style: context.ui.type.mono.identifier,
            ),
          ],
        ),
      ),
    ],
  ),
  WidgetbookComponent(
    name: 'Identity and portfolio',
    useCases: [
      story(
        'Owned mark and wordmark slot',
        'Specimen identity replaces reference company logos. Host-supplied partner logos remain content slots with accessible names.',
        (_) => const Wrap(
          spacing: 24,
          runSpacing: 24,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            UiMark(label: 'Specimen digitization', size: 64),
            Text('Specimen\nDigitization'),
          ],
        ),
      ),
    ],
  ),
];
