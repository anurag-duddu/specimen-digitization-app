import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/collection_choices.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';

final catalog = [
  for (final row
      in (jsonDecode(
                File(
                  '../../infra/reference/fieldmuseum-collection-tree.json',
                ).readAsStringSync(),
              )
              as Map)['collections']
          as List)
    CollectionCatalogNode(
      collectionId: row['key'] as String,
      name: row['name'] as String,
      parentCollectionId: row['parent'] as String?,
    ),
  const CollectionCatalogNode(
    collectionId: 'test',
    name: 'Intake E2E',
    parentCollectionId: 'insects',
    testing: true,
  ),
];

class CollectionRepository extends GoldenRepository {
  bool testAccess = true;
  @override
  Future<List<CollectionScope>> scopes() async => [
    if (testAccess)
      CollectionScope(
        organizationId: 'org',
        collectionId: 'test',
        name: 'Intake E2E',
        configuration: const {'kind': 'testing'},
        permissions: const ['reviewer'],
        catalogNodes: catalog,
      ),
    CollectionScope(
      organizationId: 'org',
      collectionId: 'insects',
      name: 'Insects',
      defaultSelection: true,
      permissions: const ['reviewer'],
      catalogNodes: catalog,
    ),
  ];
}

final trigger = find.bySemanticsLabel(RegExp('^Authorized collection,'));

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test(
    'all reviewed museum nodes remain visible without becoming grants',
    () async {
      final scopes = await CollectionRepository().scopes();
      final choices = collectionChoices(scopes, selectedKey: 'org/insects');
      final labels = {
        ...choices.map((choice) => choice.name),
        ...choices.map((choice) => choice.groupLabel).whereType<String>(),
      };
      for (final node in catalog) {
        expect(labels, contains(node.name));
      }
      expect(
        choices
            .where((choice) => choice.scope != null)
            .map((choice) => choice.name),
        ['Insects', 'Intake E2E'],
      );
      expect(choices.last.groupLabel, 'Testing');
      expect(labels, isNot(contains('Coleoptera')));
    },
  );

  for (final size in [const Size(1440, 900), const Size(390, 844)]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets(
        'authorized hierarchy, current choice and overflow at $size x$scale',
        (tester) async {
          await pumpGoldenApp(
            tester,
            window: size,
            brightness: Brightness.light,
            textScale: scale,
            location: goldenQueueLocation,
            repository: CollectionRepository(),
          );
          final controller = WorkspaceScope.read(
            tester.element(find.byType(QueuePane)),
          );
          expect(controller.scope?.collectionId, 'insects');
          final triggerRect = tester.getRect(trigger);
          final arrow = find.descendant(
            of: trigger,
            matching: find.byWidgetPredicate(
              (widget) => widget is UiIcon && widget.spec == UiIcons.expand,
            ),
          );
          expect(arrow, findsOneWidget);
          expect(
            tester.getCenter(arrow).dx,
            greaterThan(triggerRect.center.dx),
          );
          await tester.tap(trigger);
          await tester.pumpAndSettle();
          expect(find.text('Zoology'), findsOneWidget);
          expect(find.text('Testing'), findsOneWidget);
          expect(
            find.text('Only enabled collections can be opened.'),
            findsOneWidget,
          );
          final selected = find.bySemanticsLabel('Insects').last;
          expect(
            tester
                .getSemantics(selected)
                .flagsCollection
                .isSelected
                .toBoolOrNull(),
            isTrue,
          );
          final unavailable = find.bySemanticsLabel('Mammals').last;
          final semantics = tester.getSemantics(unavailable);
          expect(semantics.flagsCollection.isEnabled.toBoolOrNull(), isFalse);
          expect(
            semantics.getSemanticsData().hasAction(SemanticsAction.tap),
            isFalse,
          );
          expect(tester.takeException(), isNull);
          if (find.byType(UiSheet).evaluate().isNotEmpty) {
            final testRow = find.byWidgetPredicate(
              (widget) => widget is UiListRow && widget.title == 'Intake E2E',
            );
            await tester.ensureVisible(testRow);
            await tester.pumpAndSettle();
            expect(testRow.hitTestable(), findsOneWidget);
            await tester.tap(
              find.byWidgetPredicate(
                (widget) => widget is UiButton && widget.label == 'Cancel',
              ),
            );
          } else {
            await tester.sendKeyEvent(LogicalKeyboardKey.escape);
          }
          await tester.pumpAndSettle();
          expect(controller.scope?.collectionId, 'insects');
          expect(find.text('Choose a collection'), findsNothing);
          expect(tester.takeException(), isNull);
        },
      );
    }
  }

  testWidgets(
    'fresh root prefers museum collection and explicit testing deep link remains valid',
    (tester) async {
      await pumpGoldenApp(
        tester,
        window: const Size(1440, 900),
        brightness: Brightness.light,
        repository: CollectionRepository(),
      );
      final controller = WorkspaceScope.read(
        tester.element(find.byType(QueuePane)),
      );
      expect(controller.scope?.collectionId, 'insects');
      final router = GoRouter.of(tester.element(find.byType(QueuePane)));
      router.go(AppRoutes.queueOf(encodeCollectionKey('org/test')));
      await tester.pumpAndSettle();
      expect(controller.scope?.collectionId, 'test');
      await controller.checkAccess();
      await tester.pumpAndSettle();
      expect(controller.scope?.collectionId, 'test');
    },
  );

  testWidgets(
    'keyboard skips unavailable collections and selects only granted Testing',
    (tester) async {
      await pumpGoldenApp(
        tester,
        window: const Size(1440, 900),
        brightness: Brightness.light,
        location: goldenQueueLocation,
        repository: CollectionRepository(),
      );
      final controller = WorkspaceScope.read(
        tester.element(find.byType(QueuePane)),
      );
      await tester.tap(trigger);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(controller.scope?.collectionId, 'test');
    },
  );

  testWidgets(
    'async leave confirmation cannot use a subsequently revoked grant',
    (tester) async {
      final repository = CollectionRepository();
      await pumpGoldenApp(
        tester,
        window: const Size(1440, 900),
        brightness: Brightness.light,
        location: goldenQueueLocation,
        repository: repository,
      );
      final controller = WorkspaceScope.read(
        tester.element(find.byType(QueuePane)),
      );
      final confirmation = Completer<bool>();
      controller.reviewExitGuard = () => confirmation.future;
      await tester.tap(trigger);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Intake E2E'));
      await tester.tap(find.text('Intake E2E'));
      await tester.pump();
      repository.testAccess = false;
      await controller.checkAccess();
      confirmation.complete(true);
      await tester.pumpAndSettle();
      expect(controller.scope?.collectionId, 'insects');
      expect(controller.scopes, hasLength(1));
    },
  );
}
