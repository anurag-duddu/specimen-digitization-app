// The costs route and its entry (`AppRoutes.costs`).
//
// The route names no collection, so the collection frame's rules do not apply
// to it, and the account menu offers it to an administrator of the open
// collection's organization and to nobody else. The tests that matter most
// here count requests: the API repository keeps the first 401 or 403 as the
// failure of the whole session, so an account that is not an administrator
// must never be the one to find out.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/costs/costs_screen.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../costs/cost_fixtures.dart';
import '../golden/golden_harness.dart';
import '../ui_finders.dart';
import 'routing_test.dart' show locationOf, systemBack;

/// A repository with an administrator on it and no cost meter behind it.
class _AdminWithoutMeter extends GoldenRepository {
  @override
  Future<List<CollectionScope>> scopes() async => const <CollectionScope>[
    CollectionScope(
      organizationId: costOrganization,
      collectionId: 'insects',
      name: 'Synthetic Insects',
      permissions: <String>['admin'],
    ),
  ];
}

/// A cost meter and the scopes [held] says an account has.
class _Scoped extends GoldenCostRepository {
  _Scoped(this.held);

  final List<CollectionScope> held;

  @override
  Future<List<CollectionScope>> scopes() async => held;
}

CollectionScope scope(String organization, String collection, String role) =>
    CollectionScope(
      organizationId: organization,
      collectionId: collection,
      name: collection,
      permissions: <String>[role],
    );

const Size phone = Size(390, 844);
const Size desk = Size(1280, 900);

String get queueLocation => goldenQueueLocation;

/// The page on top. A page opened with `push` leaves the address where it
/// was, as Help does, so this reads the route that is showing and not the
/// address.
String pageOf(WidgetTester tester) => GoRouter.of(
  tester.element(find.byType(Navigator).first),
).routerDelegate.currentConfiguration.last.matchedLocation;

Future<void> pump(
  WidgetTester tester,
  GoldenRepository repository, {
  Size window = phone,
  String location = AppRoutes.setup,
  bool signedIn = true,
}) => pumpGoldenApp(
  tester,
  window: window,
  brightness: Brightness.light,
  location: location,
  signedIn: signedIn,
  repository: repository,
);

Future<void> openAccountMenu(WidgetTester tester) async {
  await tester.tap(uiMenuTrigger(RegExp('^Account menu')));
  await tester.pumpAndSettle();
}

/// What the menu holds, by label.
Set<String> menuLabels(WidgetTester tester) => <String>{
  for (final String label in <String>[
    'Costs',
    'Help and shortcuts',
    'Sign out',
    'Refresh collection',
  ])
    if (find.text(label).evaluate().isNotEmpty) label,
};

void main() {
  group('the location', () {
    test('is a page of its own, named by no collection', () {
      expect(AppRoutes.costs, '/costs');
      expect(AppRoutes.isGlobalLocation(AppRoutes.costs), isTrue);
      expect(AppRoutes.isEntryLocation(AppRoutes.costs), isFalse);
      expect(AppRoutes.collectionKeyIn(Uri.parse(AppRoutes.costs)), isNull);
    });

    test('is left alone by the web history restore', () {
      // `restoreWebHistory` only recognises collection paths, and it must not
      // read this one as a collection's.
      expect(AppRoutes.restoreWebHistory(Uri.parse(AppRoutes.costs)), isNull);
      expect(
        AppRoutes.restoreWebHistory(Uri.parse('/costs?month=2026-09')),
        isNull,
      );
    });
  });

  group('the entry in the account menu', () {
    for (final Size window in <Size>[phone, desk]) {
      testWidgets('is offered to an administrator at ${window.width.toInt()}', (
        WidgetTester tester,
      ) async {
        await pump(tester, GoldenCostRepository(), window: window);

        await openAccountMenu(tester);

        expect(menuLabels(tester), contains('Costs'));
        expect(menuLabels(tester), contains('Help and shortcuts'));
        await tester.pumpWidget(const SizedBox());
      });
    }

    for (final List<String> roles in <List<String>>[
      <String>['reviewer'],
      <String>['manager'],
      <String>['reviewer', 'manager'],
      <String>[],
    ]) {
      testWidgets('is not offered to $roles', (WidgetTester tester) async {
        final GoldenCostRepository repository = GoldenCostRepository(
          permissions: roles,
        );
        await pump(tester, repository);

        await openAccountMenu(tester);

        expect(menuLabels(tester), isNot(contains('Costs')));
        expect(menuLabels(tester), contains('Help and shortcuts'));
        // Nothing was asked of the server on the way.
        expect(repository.meter.reads, isEmpty);
        await tester.pumpWidget(const SizedBox());
      });
    }

    testWidgets('is not offered where the build has no costs to show', (
      WidgetTester tester,
    ) async {
      await pump(tester, _AdminWithoutMeter());

      await openAccountMenu(tester);

      expect(menuLabels(tester), isNot(contains('Costs')));
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('is not offered to an administrator of another organization', (
      WidgetTester tester,
    ) async {
      final _Scoped repository = _Scoped(<CollectionScope>[
        scope(costOrganization, 'insects', 'reviewer'),
        scope('other', 'birds', 'admin'),
      ]);
      await pump(tester, repository);

      await openAccountMenu(tester);

      expect(menuLabels(tester), isNot(contains('Costs')));
      expect(repository.meter.reads, isEmpty);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('is offered to an administrator of any collection in it', (
      WidgetTester tester,
    ) async {
      final _Scoped repository = _Scoped(<CollectionScope>[
        scope(costOrganization, 'insects', 'reviewer'),
        scope(costOrganization, 'plants', 'admin'),
      ]);
      await pump(tester, repository);

      await openAccountMenu(tester);
      expect(menuLabels(tester), contains('Costs'));

      await tester.tap(find.text('Costs'));
      await tester.pumpAndSettle();
      expect(repository.meter.reads.single.organization, costOrganization);
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('opening and leaving', () {
    for (final Size window in <Size>[phone, desk]) {
      testWidgets(
        'opens over the queue and goes back to it at ${window.width.toInt()}',
        (WidgetTester tester) async {
          final GoldenCostRepository repository = GoldenCostRepository();
          await pump(tester, repository, window: window);
          expect(locationOf(tester), queueLocation);
          expect(repository.meter.reads, isEmpty);

          await openAccountMenu(tester);
          await tester.tap(find.text('Costs'));
          await tester.pumpAndSettle();

          expect(pageOf(tester), AppRoutes.costs);
          expect(find.text('Known cost in October 2026'), findsOneWidget);
          expect(repository.meter.reads.single.organization, costOrganization);

          await tester.tap(uiIconButton('Go back'));
          await tester.pumpAndSettle();

          expect(locationOf(tester), queueLocation);
          expect(find.text('Known cost in October 2026'), findsNothing);
          await tester.pumpWidget(const SizedBox());
        },
      );
    }

    testWidgets('the system back gesture leaves it too', (
      WidgetTester tester,
    ) async {
      await pump(tester, GoldenCostRepository());
      await openAccountMenu(tester);
      await tester.tap(find.text('Costs'));
      await tester.pumpAndSettle();
      expect(pageOf(tester), AppRoutes.costs);

      await systemBack(tester);

      expect(locationOf(tester), queueLocation);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a link to it is honoured, and back goes to the queue', (
      WidgetTester tester,
    ) async {
      final GoldenCostRepository repository = GoldenCostRepository();
      await pump(tester, repository, location: AppRoutes.costs);

      expect(pageOf(tester), AppRoutes.costs);
      expect(find.text('Known cost in October 2026'), findsOneWidget);

      // Nothing to return to, so the control goes to the queue.
      await tester.tap(uiIconButton('Go back'));
      await tester.pumpAndSettle();

      expect(locationOf(tester), queueLocation);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('takes the status bar\'s inset once, under the band or not', (
      WidgetTester tester,
    ) async {
      const double statusBar = 47;
      Future<double> barHeight(String mode) async {
        tester.view.padding = const FakeViewPadding(top: statusBar);
        tester.view.viewPadding = const FakeViewPadding(top: statusBar);
        final GoldenCostRepository repository = GoldenCostRepository()
          ..mode = mode;
        await pump(tester, repository, location: AppRoutes.costs);
        final double height = tester.getSize(find.byType(UiTopBar)).height;
        await tester.pumpWidget(const SizedBox());
        return height;
      }

      final double underBand = await barHeight('synthetic');
      final double alone = await barHeight('production');

      // With the band, the band owns the inset and the bar sits flush under
      // it. Without one, the bar owns it.
      expect(alone - underBand, statusBar);
    });

    testWidgets('names itself in the top bar, once', (
      WidgetTester tester,
    ) async {
      await pump(tester, GoldenCostRepository(), location: AppRoutes.costs);

      expect(find.text('Costs'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('for an account that may not see costs', () {
    testWidgets('a link says why, and the server is never asked', (
      WidgetTester tester,
    ) async {
      final GoldenCostRepository repository = GoldenCostRepository(
        permissions: const <String>['reviewer'],
      );
      await pump(tester, repository, location: AppRoutes.costs);

      expect(pageOf(tester), AppRoutes.costs);
      expect(find.text('Costs are for administrators'), findsOneWidget);
      expect(find.byType(CostsScreen), findsNothing);
      expect(repository.meter.reads, isEmpty);
      expect(repository.meter.refreshes, isEmpty);
      expect(repository.meter.limits, isEmpty);

      await tester.tap(uiIconButton('Go back'));
      await tester.pumpAndSettle();
      expect(locationOf(tester), queueLocation);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('an administrator of only another organization is told no', (
      WidgetTester tester,
    ) async {
      final _Scoped repository = _Scoped(<CollectionScope>[
        scope(costOrganization, 'insects', 'reviewer'),
        scope('other', 'birds', 'admin'),
      ]);
      await pump(tester, repository, location: AppRoutes.costs);

      expect(find.text('Costs are for administrators'), findsOneWidget);
      expect(repository.meter.reads, isEmpty);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a build without costs says so, and asks nothing', (
      WidgetTester tester,
    ) async {
      await pump(tester, _AdminWithoutMeter(), location: AppRoutes.costs);

      expect(find.text('Costs not available'), findsOneWidget);
      expect(
        find.text(
          'This build of the app cannot read costs. Use the current release.',
        ),
        findsOneWidget,
      );
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a window with no session reaches sign in, not the meter', (
      WidgetTester tester,
    ) async {
      final GoldenCostRepository repository = GoldenCostRepository();
      await pump(
        tester,
        repository,
        location: AppRoutes.costs,
        signedIn: false,
      );

      expect(locationOf(tester), AppRoutes.signIn);
      expect(repository.meter.reads, isEmpty);
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('the screen inside the app', () {
    testWidgets('reads the organization of the open collection', (
      WidgetTester tester,
    ) async {
      final GoldenCostRepository repository = GoldenCostRepository();
      await pump(tester, repository, location: AppRoutes.costs);

      expect(repository.meter.reads.single.organization, costOrganization);
      expect(repository.meter.reads.single.from, '2026-10');
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('sets a limit end to end', (WidgetTester tester) async {
      final GoldenCostRepository repository = GoldenCostRepository();
      await pump(tester, repository, location: AppRoutes.costs);

      await tester.ensureVisible(uiButton('Change limit'));
      await tester.pumpAndSettle();
      await tester.tap(uiButton('Change limit'));
      await tester.pumpAndSettle();
      await tester.enterText(uiField('Limit in US dollars'), '60');
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();

      expect(repository.meter.limits.single.micros, 60000000);
      expect(repository.meter.limits.single.collection, isNull);
      expect(pageOf(tester), AppRoutes.costs);
      await tester.pumpWidget(const SizedBox());
    });
  });

  test('the fixture collection is in the fixture organization', () {
    // The premise of every test above: the cost fixtures name `org`, and the
    // collection the app opens is `org/insects`.
    expect(goldenCollection, '$costOrganization/insects');
  });
}
