import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_widgetbook/catalog/shared_patterns.dart';
import 'package:specimen_widgetbook/catalog/inputs.dart';
import 'package:specimen_widgetbook/catalog/advanced_forms.dart';
import 'package:specimen_widgetbook/environment.dart';
import 'package:widgetbook/widgetbook.dart';

void main() {
  testWidgets(
    'every shared pattern story renders in narrow large-text RTL and desktop',
    (tester) async {
      addTearDown(tester.view.reset);
      tester.view.devicePixelRatio = 1;
      final root = WidgetbookRoot(
        children: [
          ...sharedPatternComponents,
          ...inputComponents,
          ...advancedFormsComponents,
        ],
      );
      final failures = <String>[];
      for (final useCase in root.leaves.whereType<WidgetbookUseCase>()) {
        final state = WidgetbookState(root: root, path: useCase.path);
        for (final narrow in [true, false]) {
          tester.view.physicalSize = narrow
              ? const Size(320, 900)
              : const Size(1180, 900);
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
                        density: narrow
                            ? UiDensityMode.touch
                            : UiDensityMode.pointer,
                        direction: narrow
                            ? TextDirection.rtl
                            : TextDirection.ltr,
                        reduceMotion: true,
                      ),
                      child: SpecimenPreview(
                        child: Builder(
                          key: ValueKey('${useCase.path}/$narrow'),
                          builder: useCase.builder,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          );
          await tester.pump(const Duration(milliseconds: 200));
          Object? exception;
          while ((exception = tester.takeException()) != null) {
            failures.add('${useCase.path}, narrow=$narrow: $exception');
          }
        }
        await tester.pumpWidget(const SizedBox.shrink());
        state.dispose();
      }
      expect(failures, isEmpty, reason: failures.join('\n\n'));
    },
  );
}
