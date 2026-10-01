// Where the reviewer is in the queue, and what is still there when they come
// back (pass criterion 6.5), plus the two messages that used to name nobody
// and the banner that used to be cleared by a background process
// (pass criteria 10.3 and 9.5).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart' show UiListRow;
import 'package:specimen_digitization/src/administrator_contact.dart';
import 'package:specimen_digitization/src/app/help_screen.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_digitization/src/workspace.dart';

import '../golden/golden_harness.dart';
import '../ui_finders.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('the queue keeps its view across record exit and reopen', (
    WidgetTester tester,
  ) async {
    // On phones the full-width list is retained offstage during review.
    await pumpGoldenApp(
      tester,
      window: const Size(390, 844),
      brightness: Brightness.light,
      location: goldenQueueLocation,
      repository: GoldenQueueRepository(goldenQueue(40)),
    );
    await pickSpecimenQueue(tester, 'Cleared');
    final controller = WorkspaceScope.read(
      tester.element(find.byType(QueuePane)),
    );
    final list = find.byKey(const PageStorageKey<String>('queue-list'));
    ScrollableState listState() => tester.state<ScrollableState>(
      find.descendant(of: list, matching: find.byType(Scrollable)).first,
    );
    expect(list, findsOneWidget);
    final ScrollableState scroll = listState();
    expect(scroll.position.maxScrollExtent, greaterThan(240));
    await tester.drag(list, const Offset(0, -240));
    await tester.pumpAndSettle();
    final double offset = scroll.position.pixels;
    expect(offset, greaterThan(100));

    final visibleRows = find
        .descendant(of: list, matching: find.byType(UiListRow))
        .hitTestable();
    expect(visibleRows, findsWidgets);
    final String selectedId = tester.widget<UiListRow>(visibleRows.first).title;
    Finder selectedRow() => find.descendant(
      of: list,
      matching: find.byWidgetPredicate(
        (widget) => widget is UiListRow && widget.title == selectedId,
      ),
    );

    await tester.tap(selectedRow().hitTestable());
    await tester.pumpAndSettle();
    expect(
      tester.widget<ReviewWorkbench>(find.byType(ReviewWorkbench)).specimen.id,
      selectedId,
    );
    expect(controller.selectedId, selectedId);
    expect(find.byType(QueuePane), findsNothing);
    expect(scroll.position.pixels, offset);

    final back = uiIconButton(backToQueueLabel).hitTestable();
    expect(back, findsOneWidget);
    await tester.tap(back);
    await tester.pumpAndSettle();
    expect(find.byType(ReviewWorkbench), findsNothing);
    expect(listState(), same(scroll));
    expect(listState().position.pixels, offset);
    expect(controller.disposition, 'cleared');
    expect(controller.selectedId, isNull);
    expect(selectedRow().hitTestable(), findsOneWidget);

    // Reopen without ensureVisible: scrolling to repair a hidden row here
    // would conceal a lost offset. The second exit exercises native Back.
    await tester.tap(selectedRow().hitTestable());
    await tester.pumpAndSettle();
    expect(
      tester.widget<ReviewWorkbench>(find.byType(ReviewWorkbench)).specimen.id,
      selectedId,
    );
    expect(controller.selectedId, selectedId);
    expect(find.byType(QueuePane), findsNothing);
    expect(scroll.position.pixels, offset);
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.byType(ReviewWorkbench), findsNothing);
    expect(listState(), same(scroll));
    expect(listState().position.pixels, offset);
    expect(controller.disposition, 'cleared');
    expect(controller.selectedId, isNull);
    expect(selectedRow().hitTestable(), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the decision bar states the reviewer position', (
    WidgetTester tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 820),
      brightness: Brightness.light,
      location: AppRoutes.specimenOf(
        encodeCollectionKey(goldenCollection),
        'fixture-003',
      ),
      repository: GoldenQueueRepository(goldenQueue(5)),
    );
    expect(find.text('3 of 5'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  group('the administrator contact', () {
    test('reads a plain address out of the collection document', () {
      final AdministratorContact contact = AdministratorContact.of(
        const CollectionScope(
          organizationId: 'org',
          collectionId: 'insects',
          name: 'Insects',
          configuration: <String, dynamic>{
            'administrator_contact': 'curator@example.org',
          },
        ),
      );
      expect(contact.isKnown, isTrue);
      expect(
        contact.sentence,
        'Ask your collection administrator at curator@example.org.',
      );
      expect(
        contact.subjectFor(specimenId: 'fixture-001'),
        contains('fixture-001'),
      );
    });

    test('reads a named role and an address out of an object', () {
      final AdministratorContact contact = AdministratorContact.of(
        const CollectionScope(
          organizationId: 'org',
          collectionId: 'insects',
          name: 'Insects',
          configuration: <String, dynamic>{
            'support': <String, dynamic>{
              'role': 'the entomology data team',
              'email': 'data@example.org',
            },
          },
        ),
      );
      expect(
        contact.sentence,
        'Ask the entomology data team at data@example.org.',
      );
    });

    test('says where a contact would be listed when there is none', () {
      final AdministratorContact contact = AdministratorContact.of(
        const CollectionScope(
          organizationId: 'org',
          collectionId: 'insects',
          name: 'Insects',
        ),
      );
      expect(contact.isKnown, isFalse);
      expect(
        contact.sentence,
        'Your collection administrator is listed in the collection '
        'configuration for Insects.',
      );
    });
  });

  testWidgets('help carries a walkthrough, the build and a way to report', (
    WidgetTester tester,
  ) async {
    // Pass criterion 10.1: one control away, and carrying the shortcuts, a
    // walkthrough, the glossary, a problem report and the build.
    await pumpGoldenApp(
      tester,
      window: const Size(1180, 820),
      brightness: Brightness.light,
      location: AppRoutes.help,
    );
    final Finder sheet = find
        .descendant(
          of: find.byType(HelpScreen),
          matching: find.byType(Scrollable),
        )
        .first;

    Future<void> reach(Finder target) async {
      await tester.scrollUntilVisible(target, 120, scrollable: sheet);
      await tester.pumpAndSettle();
      expect(target, findsWidgets);
    }

    expect(find.text('Keyboard shortcuts'), findsOneWidget);
    await reach(find.text('A first review'));
    await reach(find.textContaining(reviewWalkthrough.first));
    await reach(find.text('Glossary'));
    await reach(find.text('This build'));
    await reach(find.textContaining('Build: '));
    await reach(find.text('Report a problem'));
    await reach(find.text('Administrator contact'));
    await reach(find.textContaining('listed in the collection configuration'));
    await tester.pumpWidget(const SizedBox());
  });
}
