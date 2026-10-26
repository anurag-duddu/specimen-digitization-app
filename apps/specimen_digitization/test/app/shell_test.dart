// Compact windows use the brand tab bar. Docked windows use the shared
// adaptive primary rail; the specimen queue is central content, not navigation.
import 'dart:async';

import 'package:flutter/cupertino.dart' show CupertinoTabBar;
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart' show NavigationBar;
import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';
import '../widget_test.dart' show TestRepository, TestSession;

class EmptyRepository extends TestRepository {
  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async => const SpecimenPage(<Specimen>[]);
}

class _LoadingRepository extends GoldenRepository {
  final response = Completer<Specimen>();

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async => const SpecimenPage(<Specimen>[]);

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) =>
      response.future;
}

Future<void> pumpAt(WidgetTester tester, double width) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = Size(width, 1000);
  addTearDown(tester.view.reset);
  final session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(session: session, repository: EmptyRepository()),
  );
  await tester.pumpAndSettle();
}

void _expectSingleCollectionSemantics(WidgetTester tester) {
  final root = tester
      .binding
      .rootElement!
      .renderObject
      ?.owner
      ?.semanticsOwner
      ?.rootSemanticsNode;
  expect(root, isNotNull);
  var collectionNames = 0;
  void visit(SemanticsNode node) {
    if (node.label.startsWith('Authorized collection,')) collectionNames++;
    node.visitChildren((child) {
      visit(child);
      return true;
    });
  }

  visit(root!);
  expect(collectionNames, 1, reason: 'Only the active context is announced.');
}

void main() {
  for (final width in [400.0, 700.0, 900.0, 1300.0]) {
    testWidgets('one global navigation surface at width $width', (
      tester,
    ) async {
      await pumpAt(tester, width);
      final mobile = width < WindowArrangement.dockedMinWidth;
      expect(
        find.byKey(const ValueKey('mobile-navigation')),
        mobile ? findsOneWidget : findsNothing,
      );
      expect(find.byType(UiTabBar), mobile ? findsOneWidget : findsNothing);
      expect(find.byType(NavigationBar), findsNothing);
      expect(find.byType(CupertinoTabBar), findsNothing);
      expect(
        find.byKey(const ValueKey('global-rail')),
        mobile ? findsNothing : findsOneWidget,
      );
      expect(find.byType(UiPillNav), findsNothing);
      expect(find.byType(UiMark), findsOneWidget);
      expect(
        tester.widget<UiMark>(find.byType(UiMark)).label,
        AppShell.markLabel,
      );
      // Docked layouts consume the same shared rail as the catalog.
      expect(find.byType(UiRail), mobile ? findsNothing : findsOneWidget);
      expect(find.byType(UiSidebar), findsNothing);
      if (!mobile) {
        final panel = tester.widget<UiSidePanel>(find.byType(UiSidePanel));
        expect(panel.leading, isNotNull);
        expect(panel.leadingWidth, greaterThan(0));
        for (final label in ['Specimens', 'Intake']) {
          expect(
            find.descendant(
              of: find.byType(UiRail),
              matching: find.text(label),
            ),
            findsOneWidget,
          );
        }
      }
      expect(uiDestination('Specimens'), findsOneWidget);
      expect(uiDestination('Intake'), findsOneWidget);
      expect(find.byType(QueuePane), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('collection and account remain reachable at width $width', (
      tester,
    ) async {
      await pumpAt(tester, width);
      final switcher = find.bySemanticsLabel(RegExp('^Authorized collection,'));
      expect(switcher, findsOneWidget);
      expect(switcher.hitTestable(), findsOneWidget);
      expect(uiMenuTrigger(RegExp('^Account menu')), findsOneWidget);
      await tester.tap(uiMenuTrigger(RegExp('^Account menu')));
      await tester.pumpAndSettle();
      expect(find.text(AppShell.helpLabel), findsOneWidget);
      expect(find.text(AppShell.reloadLabel), findsOneWidget);
      expect(find.text('Sign out'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });
  }

  testWidgets(
    'large windows put collection context above queue content, outside the rail',
    (tester) async {
      await pumpAt(tester, 1300);
      final sidebar = find.byKey(const ValueKey('global-sidebar'));
      expect(sidebar, findsOneWidget);
      expect(
        find.descendant(of: sidebar, matching: find.byType(QueuePane)),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(UiRail),
          matching: find.bySemanticsLabel(RegExp('^Authorized collection,')),
        ),
        findsNothing,
      );
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('queue-context-header')),
          matching: find.bySemanticsLabel(RegExp('^Authorized collection,')),
        ),
        findsOneWidget,
      );
      expect(find.text('From specimens to knowledge.'), findsNothing);
      expect(tester.getSize(find.byType(QueuePane)).width, greaterThan(900));
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'environment context is available without a repeated full-width banner',
    (tester) async {
      await pumpAt(tester, 400);
      await tester.tap(find.bySemanticsLabel('Test environment'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Test environment'), findsWidgets);
      expect(find.textContaining('Synthetic'), findsWidgets);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('a phone record hides global tabs and retains a way back', (
    tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: const Size(390, 844),
      brightness: Brightness.light,
      location: goldenSpecimenLocation,
    );
    expect(find.byKey(const ValueKey('mobile-navigation')), findsNothing);
    expect(find.byKey(const ValueKey('global-sidebar')), findsNothing);
    expect(uiIconButton(AppShell.backLabel), findsOneWidget);
    expect(find.text(goldenVerifiedSpecimen().displayReference), findsWidgets);
    expect(
      find.bySemanticsLabel(RegExp('^Authorized collection,')),
      findsNothing,
    );
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
    'a desktop record retains global actions and can collapse its specimen list',
    (tester) async {
      final semantics = tester.ensureSemantics();
      await pumpGoldenApp(
        tester,
        window: const Size(1440, 900),
        brightness: Brightness.light,
        location: goldenSpecimenLocation,
      );
      expect(find.byKey(const ValueKey('global-rail')), findsOneWidget);
      expect(uiMenuTrigger(RegExp('^Account menu')), findsOneWidget);
      expect(find.byKey(const ValueKey('global-sidebar')), findsOneWidget);
      final collection = find
          .bySemanticsLabel(RegExp('^Authorized collection,'))
          .hitTestable();
      expect(collection, findsOneWidget);
      _expectSingleCollectionSemantics(tester);
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('queue-context-header')),
          matching: collection,
        ),
        findsOneWidget,
      );
      expect(
        tester
            .widget<UiIconButton>(
              find.byKey(const ValueKey('queue-panel-close')),
            )
            .icon,
        UiIcons.sidebar,
      );
      tester
          .widget<UiIconButton>(find.byKey(const ValueKey('queue-panel-close')))
          .focusNode!
          .requestFocus();
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('queue-panel-close')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('global-sidebar')), findsNothing);
      expect(uiIconButton('Show queue'), findsOneWidget);
      expect(
        tester
            .widget<UiIconButton>(uiIconButton('Show queue'))
            .focusNode!
            .hasFocus,
        isTrue,
      );
      expect(collection, findsOneWidget);
      _expectSingleCollectionSemantics(tester);
      expect(collection.hitTestable(), findsOneWidget);
      await tester.tap(uiIconButton('Show queue'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('global-sidebar')), findsOneWidget);
      expect(collection, findsOneWidget);
      _expectSingleCollectionSemantics(tester);
      semantics.dispose();
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'pointer rail keeps primary names in hover labels',
    (tester) async {
      await pumpAt(tester, 1300);
      final rail = find.byType(UiRail);
      expect(tester.getSize(rail).width, lessThanOrEqualTo(80));
      for (final label in ['Specimens', 'Intake', 'Account']) {
        expect(
          find.descendant(of: rail, matching: find.text(label)),
          findsNothing,
        );
      }
      final pointer = await tester.createGesture(kind: PointerDeviceKind.mouse);
      await pointer.addPointer(location: Offset.zero);
      await pointer.moveTo(tester.getCenter(uiDestination('Intake')));
      await tester.pump(UiTooltipStyle.hoverDelay);
      await tester.pumpAndSettle();
      expect(find.text('Intake'), findsOneWidget);
      await pointer.moveTo(
        tester.getCenter(uiMenuTrigger(RegExp('^Account menu'))),
      );
      await tester.pump(UiTooltipStyle.hoverDelay);
      await tester.pumpAndSettle();
      expect(find.text('Account'), findsOneWidget);
      await pointer.removePointer();
      await tester.pumpWidget(const SizedBox());
    },
    variant: TargetPlatformVariant.only(TargetPlatform.linux),
  );

  testWidgets(
    'touch rail puts every name beneath its icon, including account',
    (tester) async {
      await pumpAt(tester, 900);
      final rail = find.byType(UiRail);
      for (final label in ['Specimens', 'Intake', 'Account']) {
        final target = label == 'Account'
            ? uiMenuTrigger(RegExp('^Account menu'))
            : uiDestination(label);
        final icon = find.descendant(of: target, matching: find.byType(UiIcon));
        final text = find.descendant(of: target, matching: find.text(label));
        expect(text, findsOneWidget);
        expect(
          tester.getRect(text).top,
          greaterThan(tester.getRect(icon).bottom),
        );
        expect(
          tester.getRect(text).left,
          greaterThanOrEqualTo(tester.getRect(rail).left),
        );
        expect(
          tester.getRect(text).right,
          lessThanOrEqualTo(tester.getRect(rail).right),
        );
      }
      await tester.pumpWidget(const SizedBox());
    },
    variant: TargetPlatformVariant.only(TargetPlatform.android),
  );

  for (final width in [1024.0, 1440.0]) {
    testWidgets('loading record retains one collection context at $width', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = Size(width, 1000);
      addTearDown(tester.view.reset);
      final session = TestSession();
      addTearDown(session.controller.close);
      final repository = _LoadingRepository();
      await tester.pumpWidget(
        SpecimenDigitizationApp(
          session: session,
          repository: repository,
          initialLocation: goldenSpecimenLocation,
        ),
      );
      // The unresolved repository read deliberately keeps the loading bar's
      // animation alive; bounded pumps let its context finish mounting.
      for (var frame = 0; frame < 8; frame++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(
        find.byKey(const ValueKey('loading-record-toolbar')),
        findsOneWidget,
      );
      final collection = find
          .bySemanticsLabel(RegExp('^Authorized collection,'))
          .hitTestable();
      expect(collection, findsOneWidget);
      _expectSingleCollectionSemantics(tester);
      if (width == 1440) {
        expect(uiIconButton('Hide queue'), findsOneWidget);
        await tester.tap(find.byKey(const ValueKey('queue-panel-close')));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        await tester.pump();
      }
      expect(collection, findsOneWidget);
      _expectSingleCollectionSemantics(tester);
      expect(collection.hitTestable(), findsOneWidget);
      expect(uiIconButton('Show queue').hitTestable(), findsOneWidget);
      expect(uiIconButton('Hide queue'), findsNothing);
      await tester.tap(uiIconButton('Show queue'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();
      expect(collection, findsOneWidget);
      _expectSingleCollectionSemantics(tester);
      expect(uiIconButton('Hide queue'), findsOneWidget);
      expect(uiIconButton('Show queue').hitTestable(), findsNothing);
      expect(tester.takeException(), isNull);
      repository.response.complete(repository.record);
      await tester.pumpAndSettle();
      expect(find.byType(ReviewWorkbench), findsOneWidget);
      expect(collection, findsOneWidget);
      _expectSingleCollectionSemantics(tester);
      semantics.dispose();
      await tester.pumpWidget(const SizedBox());
    });
  }

  testWidgets(
    'native Intake navigation returns from sources to the intake root',
    (tester) async {
      await pumpGoldenApp(
        tester,
        window: const Size(390, 844),
        brightness: Brightness.light,
        location: goldenSourcesLocation,
        repository: GoldenSourceRepository(),
      );
      await tester.tap(uiDestination('Intake'));
      await tester.pumpAndSettle();
      expect(find.byType(IntakeScreen), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
