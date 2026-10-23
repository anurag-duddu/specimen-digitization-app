import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_widgetbook/catalog/feedback.dart';
import 'package:specimen_widgetbook/environment.dart';
import 'package:widgetbook/widgetbook.dart';

void main() {
  testWidgets(
    'queued toast belongs to its story and is cleared on navigation',
    (tester) async {
      final root = WidgetbookRoot(children: feedbackComponents);
      final story = root.leaves.whereType<WidgetbookUseCase>().firstWhere(
        (story) => story.name == 'Queued acknowledgement',
      );
      final state = WidgetbookState(root: root, path: story.path);
      addTearDown(state.dispose);
      var showStory = true;
      late StateSetter update;
      await tester.pumpWidget(
        WidgetbookScope(
          state: state,
          child: MaterialApp(
            home: SpecimenEnvironmentScope(
              setting: const SpecimenEnvironment(reduceMotion: true),
              child: StatefulBuilder(
                builder: (context, setState) {
                  update = setState;
                  return SpecimenPreview(
                    child: showStory
                        ? Builder(
                            key: const ValueKey('toast-story'),
                            builder: story.builder,
                          )
                        : const Text('Another story'),
                  );
                },
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(UiButton, 'Save synthetic draft'));
      await tester.pumpAndSettle();
      expect(find.widgetWithText(UiButton, 'Undo save'), findsOneWidget);
      update(() {});
      await tester.pumpAndSettle();
      expect(find.widgetWithText(UiButton, 'Undo save'), findsOneWidget);
      update(() {
        state.path = 'another-story';
        showStory = false;
      });
      await tester.pumpAndSettle();
      expect(find.text('Another story'), findsOneWidget);
      expect(find.widgetWithText(UiButton, 'Undo save'), findsNothing);
      update(() {
        state.path = story.path;
        showStory = true;
      });
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(UiButton, 'Save synthetic draft'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(UiButton, 'Undo save'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    },
  );
}
