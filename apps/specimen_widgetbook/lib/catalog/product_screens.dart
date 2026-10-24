import 'package:flutter/widgets.dart';
import 'package:widgetbook/widgetbook.dart';

import '../product/fixture_repository.dart';
import '../product/product_preview.dart';

/// Full-screen cases own their scrolls; never wrap them in StoryFrame.
List<WidgetbookComponent> get productScreenComponents => [
  WidgetbookComponent(
    name: 'Queue',
    useCases: [
      _screen('Loaded', ProductPreviewCase.queueLoaded),
      _screen('Empty', ProductPreviewCase.queueEmpty),
      _screen('Error and retry', ProductPreviewCase.queueError),
    ],
  ),
  WidgetbookComponent(
    name: 'Intake',
    useCases: [
      _screen('Empty batch', ProductPreviewCase.intakeEmpty),
      _screen('Saved draft', ProductPreviewCase.intakeSaved),
    ],
  ),
  WidgetbookComponent(
    name: 'Workbench',
    useCases: [
      _screen('Fields labels and history', ProductPreviewCase.workbench),
    ],
  ),
];

WidgetbookUseCase _screen(String name, ProductPreviewCase example) =>
    WidgetbookUseCase(
      name: name,
      builder: (_) => ProductPreview(key: ValueKey(example), example: example),
    );
