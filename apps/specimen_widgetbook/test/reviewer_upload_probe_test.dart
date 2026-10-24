import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_widgetbook/catalog/modal_recipes.dart';
import 'package:specimen_widgetbook/environment.dart';
import 'package:widgetbook/widgetbook.dart';

void main() {
  testWidgets('remove then add preserves distinct upload identities', (
    tester,
  ) async {
    final state = await _pumpTemplate(tester, 'File upload');
    UiFileUpload upload() =>
        tester.widget<UiFileUpload>(find.byType(UiFileUpload));
    upload().onChooseFiles!();
    await tester.pump();
    upload().onChooseFiles!();
    await tester.pump();
    upload().onRemove!(upload().files.first);
    await tester.pump();
    upload().onChooseFiles!();
    await tester.pump();
    expect(
      upload().files.map((f) => f.id).toSet().length,
      upload().files.length,
    );
    await tester.pumpWidget(const SizedBox());
    state.dispose();
  });
}

Future<WidgetbookState> _pumpTemplate(
  WidgetTester tester,
  String name, {
  bool narrow = false,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = narrow
      ? const Size(320, 900)
      : const Size(1180, 900);
  addTearDown(tester.view.reset);
  final root = WidgetbookRoot(children: modalRecipeComponents);
  final story = root.leaves.whereType<WidgetbookUseCase>().firstWhere(
    (story) => story.name == name,
  );
  final state = WidgetbookState(root: root, path: story.path);
  await tester.pumpWidget(
    WidgetbookScope(
      state: state,
      child: MaterialApp(
        home: Builder(
          builder: (context) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: TextScaler.linear(narrow ? 2 : 1)),
            child: SpecimenEnvironmentScope(
              setting: SpecimenEnvironment(
                dark: narrow,
                density: narrow ? UiDensityMode.touch : UiDensityMode.pointer,
                direction: narrow ? TextDirection.rtl : TextDirection.ltr,
                reduceMotion: true,
              ),
              child: SpecimenPreview(child: Builder(builder: story.builder)),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump(const Duration(milliseconds: 200));
  return state;
}
