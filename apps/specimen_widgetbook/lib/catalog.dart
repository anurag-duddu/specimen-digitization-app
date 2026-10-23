import 'package:specimen_ui/gallery.dart';
import 'package:widgetbook/widgetbook.dart';
import 'catalog/actions.dart';
import 'catalog/advanced_forms.dart';
import 'catalog/content.dart';
import 'catalog/compositions.dart';
import 'catalog/data.dart';
import 'catalog/data_patterns.dart';
import 'catalog/data_expanded.dart';
import 'catalog/feedback.dart';
import 'catalog/foundations.dart';
import 'catalog/inputs.dart';
import 'catalog/navigation.dart';
import 'catalog/marketing.dart';
import 'catalog/application_patterns.dart';
import 'catalog/foundation_assets.dart';
import 'catalog/shared_patterns.dart';
import 'catalog/modal_recipes.dart';
import 'story.dart';

List<WidgetbookNode> get specimenCatalog => [
  WidgetbookCategory(
    name: 'Foundations',
    children: [...foundationComponents, ...foundationAssetComponents],
  ),
  WidgetbookCategory(name: 'Actions', children: actionComponents),
  WidgetbookCategory(
    name: 'Shared patterns',
    children: sharedPatternComponents,
  ),
  WidgetbookCategory(
    name: 'Forms',
    children: [...inputComponents, ...advancedFormsComponents],
  ),
  WidgetbookCategory(
    name: 'Data',
    children: [
      ...dataComponents,
      ...dataPatternComponents,
      ...dataExpandedComponents,
    ],
  ),
  WidgetbookCategory(name: 'Navigation', children: navigationComponents),
  WidgetbookCategory(name: 'Feedback', children: feedbackComponents),
  WidgetbookCategory(name: 'Content', children: contentComponents),
  WidgetbookCategory(name: 'Compositions', children: compositionComponents),
  WidgetbookCategory(name: 'Marketing', children: marketingComponents),
  WidgetbookCategory(
    name: 'Application patterns',
    children: [...applicationPatternComponents, ...modalRecipeComponents],
  ),
  WidgetbookCategory(
    name: 'Reference sheets',
    children: [
      for (final page in galleryPages)
        WidgetbookComponent(
          name: page.title,
          useCases: [story('Family overview', page.summary, page.builder)],
        ),
    ],
  ),
];
