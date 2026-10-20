// The costs screen (`lib/src/screens/costs/costs_screen.dart`): what an
// administrator reads, and what they can change.
//
// A fake repository answers in the server's wire shape, so the parser is under
// test with the screen. The suite's clock is 20 October 2026, so the current
// month is October 2026 and the list runs back to November 2025.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/costs/cost_limit_form.dart';
import 'package:specimen_digitization/src/screens/costs/costs_screen.dart';
import 'package:specimen_digitization/src/widgets/loading_announcement.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../costs/cost_fixtures.dart';
import '../ui_finders.dart';
import '../widgets/harness.dart';

/// Records what a screen reader would be told, while the test runs.
///
/// The waits ("Loading costs for October 2026") are left out unless
/// [waits] asks for them, so a test about an update does not count the load
/// that came before it.
List<String> captureAnnouncements(WidgetTester tester, {bool waits = false}) {
  final List<String> announced = <String>[];
  tester.binding.defaultBinaryMessenger.setMockDecodedMessageHandler<dynamic>(
    SystemChannels.accessibility,
    (dynamic message) async {
      final Map<Object?, Object?> event = message! as Map<Object?, Object?>;
      if (event['type'] != 'announce') return;
      final String said = (event['data']! as Map<Object?, Object?>)['message']
          .toString();
      if (waits || !said.startsWith('Loading ')) announced.add(said);
    },
  );
  addTearDown(
    () => tester.binding.defaultBinaryMessenger
        .setMockDecodedMessageHandler<dynamic>(
          SystemChannels.accessibility,
          null,
        ),
  );
  return announced;
}

/// Pumps the screen on its own, tall enough that no row needs scrolling to.
Future<void> pumpCosts(
  WidgetTester tester,
  FakeCostRepository repository, {
  Size size = const Size(900, 3200),
  double textScale = 1.0,
  bool reduceMotion = false,
  ThemeData? theme,
}) async {
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  await pumpComponent(
    tester,
    Builder(
      builder: (BuildContext context) => MediaQuery(
        data: MediaQuery.of(context).copyWith(supportsAnnounce: true),
        child: SizedBox(
          width: size.width,
          height: size.height,
          child: CostsScreen(
            repository: repository,
            organizationId: costOrganization,
          ),
        ),
      ),
    ),
    size: size,
    reduceMotion: reduceMotion,
    theme: theme,
  );
}

Finder collectionRow(String id) =>
    find.byKey(ValueKey<String>('cost-collection-$id'));

Finder stageRow(String stage) =>
    find.byKey(ValueKey<String>('cost-stage-$stage'));

/// The words a row publishes to a screen reader.
String spoken(WidgetTester tester, Finder row) {
  final Finder list = find.descendant(
    of: row,
    matching: find.byType(UiListRow),
  );
  final SemanticsHandle handle = tester.ensureSemantics();
  final String label = tester
      .getSemantics(list.evaluate().isEmpty ? row : list)
      .label;
  handle.dispose();
  return label;
}

/// The wire body with [edit] applied to it.
Json Function(String) edited(void Function(Json wire) edit) => (String month) {
  final Json wire = costWire(month);
  edit(wire);
  return wire;
};

Future<void> openLimit(WidgetTester tester, Finder control) async {
  await tester.tap(control);
  await tester.pumpAndSettle();
}

void main() {
  group('while it loads', () {
    testWidgets('draws placeholders and announces the wait once', (
      WidgetTester tester,
    ) async {
      final List<String> announced = captureAnnouncements(tester, waits: true);
      final FakeCostRepository repository = FakeCostRepository()
        ..hold = Completer<void>();
      final Completer<void> release = repository.hold!;

      await pumpCosts(tester, repository, reduceMotion: true);
      await tester.pump();

      expect(find.byType(UiSkeleton), findsWidgets);
      expect(find.byType(UiDataTile), findsNothing);
      expect(find.byType(LoadingAnnouncement), findsOneWidget);
      expect(announced, <String>['Loading costs for October 2026']);
      // The month can be chosen while the figures load.
      expect(find.text('October 2026'), findsOneWidget);

      release.complete();
      await tester.pumpAndSettle();

      expect(find.byType(UiSkeleton), findsNothing);
      expect(find.byType(UiDataTile), findsWidgets);
      expect(
        announced,
        hasLength(1),
        reason: 'the figures arriving is not announced a second time',
      );
    });

    testWidgets('asks for the current month, for this organization', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository);

      expect(repository.reads, hasLength(1));
      expect(repository.reads.single.organization, costOrganization);
      expect(repository.reads.single.from, '2026-10');
      expect(repository.reads.single.to, '2026-10');
    });
  });

  group('when it cannot load', () {
    testWidgets('says what happened and offers a retry that works', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..readFailureOnce = const ApiFailure(
          'The request timed out. Retry to reconcile the saved server state.',
          code: 'timeout',
        );
      await pumpCosts(tester, repository);

      expect(find.text('Costs not loaded'), findsOneWidget);
      expect(
        find.text(
          'The request timed out. Retry to reconcile the saved server state.',
        ),
        findsOneWidget,
      );
      expect(find.byType(UiDataTile), findsNothing);

      await tester.tap(uiButton('Retry'));
      await tester.pumpAndSettle();

      expect(find.text('Costs not loaded'), findsNothing);
      expect(find.text('Cost in October 2026'), findsOneWidget);
      expect(repository.reads, hasLength(2));
    });

    testWidgets('says the failure in a live region', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..readFailure = const ApiFailure('Offline.', code: 'network');
      await pumpCosts(tester, repository);

      final SemanticsHandle handle = tester.ensureSemantics();
      expect(tester.getSemantics(find.text('Costs not loaded')), isNotNull);
      final Finder live = find.ancestor(
        of: find.text('Costs not loaded'),
        matching: find.byWidgetPredicate(
          (Widget w) => w is Semantics && w.properties.liveRegion == true,
        ),
      );
      expect(live, findsOneWidget);
      handle.dispose();
    });

    testWidgets('a server without a meter says so and offers no retry', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..readFailure = const ApiFailure(
          'No cost meter is configured.',
          code: 'cost_meter_unavailable',
          status: 503,
        );
      await pumpCosts(tester, repository);

      expect(find.text('Costs not available'), findsOneWidget);
      expect(find.text(CostsScreenCopy.unavailableBody), findsOneWidget);
      // Retrying cannot turn a meter on.
      expect(uiButton('Retry'), findsNothing);
    });

    testWidgets('a refusal names the role and offers no retry', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..readFailure = const ApiFailure(
          'Administrators only.',
          code: 'forbidden',
          status: 403,
        );
      await pumpCosts(tester, repository);

      expect(find.text('Costs are for administrators'), findsOneWidget);
      expect(uiButton('Retry'), findsNothing);
    });
  });

  group('a month with nothing recorded', () {
    testWidgets('says so in words, and draws no zero', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..emptyMonths.add(thisMonth);
      await pumpCosts(tester, repository);

      expect(
        find.text(
          'No costs were counted for the organization in October 2026.',
        ),
        findsOneWidget,
      );
      // The organization, the stages and the models each say it, and so does
      // the collection that has nothing.
      expect(find.text('No costs recorded'), findsNWidgets(3));
      expect(find.textContaining('No costs recorded · '), findsOneWidget);
      expect(find.byType(UiDataTile), findsNothing);
      expect(find.textContaining(r'$0.00'), findsNothing);
      expect(find.textContaining('micro'), findsNothing);
    });

    testWidgets('still offers the organization\'s limit', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..emptyMonths.add(thisMonth);
      await pumpCosts(tester, repository);

      expect(
        find.text('No monthly limit is set for the organization.'),
        findsOneWidget,
      );
      expect(uiButton('Set limit'), findsOneWidget);
    });
  });

  group('the figures', () {
    testWidgets('give the organization\'s three amounts in dollars', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      expect(find.text('Cost in October 2026'), findsOneWidget);
      expect(find.text(r'$12.35'), findsWidgets);
      expect(find.text('Held in full'), findsOneWidget);
      expect(find.text(r'$0.50'), findsWidgets);
      expect(find.text('Before free allowance'), findsOneWidget);
      expect(find.text(r'$15.00'), findsOneWidget);
      expect(find.textContaining('micro'), findsNothing);
    });

    testWidgets('use one hero numeral, no more', (WidgetTester tester) async {
      await pumpCosts(tester, FakeCostRepository());

      final Iterable<UiDataTile> tiles = tester.widgetList<UiDataTile>(
        find.byType(UiDataTile),
      );
      expect(tiles.where((UiDataTile tile) => tile.hero), hasLength(1));
    });

    testWidgets('say the line under each numeral to a screen reader too', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      final SemanticsHandle handle = tester.ensureSemantics();
      String said(String label) => tester
          .getSemantics(
            find.byWidgetPredicate(
              (Widget w) => w is UiDataTile && w.label == label,
            ),
          )
          .label;
      expect(
        said('Cost in October 2026'),
        r"Cost in October 2026, $12.35. After Google's free allowance.",
      );
      expect(
        said('Held in full'),
        r"Held in full, $0.50. Counted in full until a call's outcome is known.",
      );
      expect(
        said('Left in October 2026'),
        r'Left in October 2026, $37.65. $12.35 spent of $50.00 in October 2026.',
      );
      handle.dispose();
    });

    testWidgets('say when nothing is held, rather than draw a bare zero', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          (wire['totals'] as Json)['held_micros'] = 0;
        }),
      );
      await pumpCosts(tester, repository);

      expect(find.text('No call has an unknown outcome.'), findsOneWidget);
      expect(
        find.text("Counted in full until a call's outcome is known."),
        findsNothing,
      );
    });

    testWidgets('list the stages, largest first, in plain words', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      final List<String> order = <String>[
        'reading',
        'label_finding',
        'first_pass',
        'storage',
        'database',
      ];
      final List<double> tops = <double>[
        for (final String stage in order) tester.getTopLeft(stageRow(stage)).dy,
      ];
      expect(tops, orderedEquals(<double>[...tops]..sort()));
      expect(tops.toSet(), hasLength(order.length));
      expect(find.text('Reading labels'), findsOneWidget);
      expect(find.text('Finding labels'), findsOneWidget);
      expect(find.text('First pass'), findsWidgets);
      // A stage that recorded nothing is not a row.
      expect(stageRow('api'), findsNothing);
      expect(find.text('api'), findsNothing);
      expect(
        spoken(tester, stageRow('reading')),
        r'Reading labels, $6.00, 400 entries · $0.50 held',
      );
    });

    testWidgets('name a stage and a provider the client has not met', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          ((wire['months'] as List<Object?>).first! as Json)['stages'] = <Json>[
            <String, dynamic>{'stage': 'image_cleanup', ...amounts(5000000)},
          ];
          (wire['models'] as List<Object?>).add(<String, dynamic>{
            'month': thisMonth,
            'stage': 'image_cleanup',
            'provider': 'fireworks',
            'resource': 'cleanup-1',
            ...amounts(5000000, entries: 1),
          });
        }),
      );
      await pumpCosts(tester, repository);

      expect(find.text('Image cleanup'), findsOneWidget);
      expect(find.text('image_cleanup'), findsNothing);
      expect(find.text('Image cleanup · Fireworks · 1 entry'), findsOneWidget);
    });

    testWidgets('list the models with their stage, provider and calls', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      expect(find.text('handwriting-qwen'), findsOneWidget);
      expect(
        find.text('Reading labels · Hugging Face · 250 entries'),
        findsOneWidget,
      );
      expect(find.text('printed-glm'), findsOneWidget);
      expect(
        find.text('Reading labels · Novita · 150 entries'),
        findsOneWidget,
      );
      expect(
        spoken(
          tester,
          find.byKey(
            const ValueKey<String>(
              'cost-model-reading-huggingface-handwriting-qwen',
            ),
          ),
        ),
        r'handwriting-qwen, $4.00, Reading labels · Hugging Face · 250 entries',
      );
    });

    testWidgets('say when the figures were updated, on the reader\'s clock', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      expect(find.text('Updated 20 Oct 2026, 10:04 CDT.'), findsOneWidget);
      expect(
        find.text('Costs are counted through 19 Oct 2026.'),
        findsOneWidget,
      );
    });

    testWidgets('say when the update time is not recorded', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) => wire.remove('updated_at')),
      );
      await pumpCosts(tester, repository);

      expect(find.text('Update time not recorded.'), findsOneWidget);
      expect(find.textContaining('Updated '), findsNothing);
    });
  });

  group('the collections', () {
    testWidgets('sit under their parent, one step in', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      final double parent = tester.getTopLeft(find.text('Insects')).dx;
      final double child = tester.getTopLeft(find.text('Beetles')).dx;
      final double sibling = tester.getTopLeft(find.text('Plants')).dx;
      expect(child, greaterThan(parent));
      expect(sibling, parent);
      expect(
        tester.getTopLeft(find.text('Beetles')).dy,
        greaterThan(tester.getTopLeft(find.text('Insects')).dy),
      );
      expect(
        tester.getTopLeft(find.text('Beetles')).dy,
        lessThan(tester.getTopLeft(find.text('Plants')).dy),
      );
      // A collection whose parent the server did not list is still shown.
      expect(find.text('Microscopic slides'), findsOneWidget);
    });

    testWidgets('give each total and each limit, or the lack of one', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      expect(find.text(r'$7.10 · $2.90 left of $10.00'), findsOneWidget);
      expect(find.text(r'$2.90 · No monthly limit'), findsOneWidget);
      expect(find.text(r'$5.25 · No monthly limit'), findsOneWidget);
      expect(find.text('No costs recorded · No monthly limit'), findsOneWidget);
    });

    testWidgets('speak the whole row, including what it opens', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      expect(
        spoken(tester, collectionRow('col-insects')),
        r'Insects, $7.10 including sub-collections, $2.90 left of $10.00. '
        'Change limit',
      );
      expect(
        spoken(tester, collectionRow('col-plants')),
        r'Plants, $5.25, No monthly limit. Set limit',
      );
    });

    testWidgets('say a limit that is used up', (WidgetTester tester) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          final Json insects =
              (wire['collections'] as List<Object?>).first! as Json;
          insects['cap'] = limitWire(7000000, spent: 7100000);
        }),
      );
      await pumpCosts(tester, repository);

      expect(find.text(r'$7.10 · Limit of $7.00 reached'), findsOneWidget);
    });

    testWidgets('say when there are none', (WidgetTester tester) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) => wire['collections'] = <Json>[]),
      );
      await pumpCosts(tester, repository);

      expect(find.text('No collections to show.'), findsOneWidget);
    });
  });

  group('the organization\'s limit', () {
    testWidgets('says what is left, of what, and for which month', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      expect(find.text('Left in October 2026'), findsOneWidget);
      expect(find.text(r'$37.65'), findsOneWidget);
      expect(
        find.text(r'$12.35 spent of $50.00 in October 2026.'),
        findsOneWidget,
      );
      expect(uiButton('Change limit'), findsOneWidget);
    });

    testWidgets('names the limit\'s own month on a past month', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository);

      await pickUiSelect(tester, 'Month', 'September 2026');

      // The server's limit is for its current month whichever month is read,
      // so the screen names that month instead of the one on the selector.
      expect(find.text('Cost in September 2026'), findsOneWidget);
      expect(find.text('Left in October 2026'), findsOneWidget);
    });

    testWidgets('says none left once it is reached', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          wire['organization_cap'] = limitWire(10000000, spent: 12345678);
        }),
      );
      await pumpCosts(tester, repository);

      expect(find.text('None left'), findsOneWidget);
      expect(
        find.text(r'$12.35 spent of $10.00 in October 2026.'),
        findsOneWidget,
      );
    });

    testWidgets('says there is none, and offers to set one', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) => wire['organization_cap'] = null),
      );
      await pumpCosts(tester, repository);

      expect(
        find.text('No monthly limit is set for the organization.'),
        findsOneWidget,
      );
      expect(uiButton('Set limit'), findsOneWidget);
      expect(uiButton('Change limit'), findsNothing);
      expect(find.textContaining('Left in'), findsNothing);
    });
  });

  group('the month', () {
    testWidgets('offers the current month and the eleven before it', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      final UiSelect<String> select = tester.widget(uiSelect('Month'));
      expect(select.options, hasLength(12));
      expect(select.options.first.label, 'October 2026');
      expect(select.options.last.label, 'November 2025');
      expect(select.value, '2026-10');
      expect(find.text('Months are counted in UTC.'), findsOneWidget);
    });

    testWidgets('reads the month that is chosen, and announces its wait', (
      WidgetTester tester,
    ) async {
      final List<String> announced = captureAnnouncements(tester, waits: true);
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository, reduceMotion: true);
      // Held, so the wait is on screen long enough to be drawn.
      repository.hold = Completer<void>();
      final Completer<void> release = repository.hold!;

      await pickUiSelect(tester, 'Month', 'August 2026');
      expect(find.byType(UiSkeleton), findsWidgets);
      release.complete();
      await tester.pumpAndSettle();

      expect(repository.reads.map((r) => r.from).toList(), <String>[
        '2026-10',
        '2026-08',
      ]);
      expect(repository.reads.last.to, '2026-08');
      expect(find.text('Cost in August 2026'), findsOneWidget);
      expect(announced, <String>[
        'Loading costs for October 2026',
        'Loading costs for August 2026',
      ]);
    });

    testWidgets('drops an answer for a month the reviewer moved on from', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..hold = Completer<void>();
      final Completer<void> late = repository.hold!;
      await pumpCosts(tester, repository, reduceMotion: true);

      await pickUiSelect(tester, 'Month', 'September 2026');
      expect(find.text('Cost in September 2026'), findsOneWidget);

      late.complete();
      await tester.pumpAndSettle();

      expect(find.text('Cost in September 2026'), findsOneWidget);
      expect(find.text('Cost in October 2026'), findsNothing);
    });

    testWidgets('a month with nothing recorded replaces the figures', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..emptyMonths.add('2026-07');
      await pumpCosts(tester, repository);
      expect(find.byType(UiDataTile), findsWidgets);

      await pickUiSelect(tester, 'Month', 'July 2026');

      expect(
        find.text('No costs were counted for the organization in July 2026.'),
        findsOneWidget,
      );
      expect(find.text('Cost in October 2026'), findsNothing);
    });
  });

  group('the meter', () {
    testWidgets('a healthy meter says how far costs are counted', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      expect(find.byType(UiBanner), findsNothing);
      expect(
        find.text('Costs are counted through 19 Oct 2026.'),
        findsOneWidget,
      );
    });

    testWidgets('unreadable usage says costs may be missing', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          wire['meter'] = <String, dynamic>{
            'allocated_through': '2026-10-18',
            'allocation_status': 'monitoring_unavailable',
          };
        }),
      );
      await pumpCosts(tester, repository);

      expect(find.text('Some costs may be missing.'), findsOneWidget);
      expect(find.textContaining('18 Oct 2026'), findsNothing);
    });

    testWidgets('a meter that has not run says costs are not counted yet', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          wire['meter'] = <String, dynamic>{
            'allocated_through': null,
            'allocation_status': 'never_run',
          };
        }),
      );
      await pumpCosts(tester, repository);

      expect(find.text('Some costs are not counted yet.'), findsOneWidget);
      expect(find.textContaining('counted through'), findsNothing);
    });

    testWidgets('the warning offers the update that can clear it', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          wire['meter'] = <String, dynamic>{
            'allocated_through': null,
            'allocation_status': 'never_run',
          };
        }),
      );
      await pumpCosts(tester, repository);

      await tester.tap(uiControl('Update figures').first);
      await tester.pumpAndSettle();

      expect(repository.refreshes, <String>[costOrganization]);
    });

    testWidgets('a status the client has not met is named, not hidden', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          wire['meter'] = <String, dynamic>{
            'allocated_through': '2026-10-19',
            'allocation_status': 'catching_up',
          };
        }),
      );
      await pumpCosts(tester, repository);

      expect(find.text('Cost counting: catching up.'), findsOneWidget);
    });

    testWidgets('no meter at all says nothing about counting', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) => wire['meter'] = null),
      );
      await pumpCosts(tester, repository);

      expect(find.byType(UiBanner), findsNothing);
      expect(find.textContaining('counted through'), findsNothing);
      expect(find.textContaining('Cost counting'), findsNothing);
    });
  });

  group('updating the figures', () {
    testWidgets('asks the server, then says they update within minutes', (
      WidgetTester tester,
    ) async {
      final List<String> announced = captureAnnouncements(tester);
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository);

      await tester.tap(uiButton('Update figures'));
      await tester.pumpAndSettle();

      expect(repository.refreshes, <String>[costOrganization]);
      expect(
        find.text('Update requested. The figures update within minutes.'),
        findsOneWidget,
      );
      expect(announced, <String>[
        'Update requested. The figures update within minutes.',
      ]);
      // The figures themselves are not re-read: they change within minutes.
      expect(repository.reads, hasLength(1));
    });

    testWidgets('says so when the server started nothing new', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..refreshStarts = false;
      await pumpCosts(tester, repository);

      await tester.tap(uiButton('Update figures'));
      await tester.pumpAndSettle();

      expect(
        find.text(
          'No new update was started. The figures update within minutes.',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('Update requested'), findsNothing);
    });

    testWidgets('says what went wrong and why, once', (
      WidgetTester tester,
    ) async {
      final List<String> announced = captureAnnouncements(tester);
      final FakeCostRepository repository = FakeCostRepository()
        ..refreshFailure = const ApiFailure(
          'The meter is busy.',
          code: 'busy',
          status: 409,
        );
      await pumpCosts(tester, repository);

      await tester.tap(uiButton('Update figures'));
      await tester.pumpAndSettle();

      expect(
        find.text('The update did not start. Retry in a moment.'),
        findsOneWidget,
      );
      expect(announced, <String>[
        'The update did not start. Retry in a moment.',
      ]);
    });

    testWidgets('can be pressed again, and is heard again', (
      WidgetTester tester,
    ) async {
      final List<String> announced = captureAnnouncements(tester);
      await pumpCosts(tester, FakeCostRepository());

      await tester.tap(uiButton('Update figures'));
      await tester.pumpAndSettle();
      await tester.tap(uiButton('Update figures'));
      await tester.pumpAndSettle();

      expect(announced, hasLength(2));
    });
  });

  group('setting a limit', () {
    testWidgets('on the organization, in dollars', (WidgetTester tester) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) => wire['organization_cap'] = null),
      );
      final List<String> announced = captureAnnouncements(tester);
      await pumpCosts(tester, repository);

      await openLimit(tester, uiButton('Set limit'));
      expect(find.text('Monthly limit'), findsWidgets);
      expect(find.text('Organization'), findsWidgets);
      expect(find.text('No monthly limit now.'), findsOneWidget);
      expect(uiButton('Remove limit'), findsNothing);

      await tester.enterText(uiField('Limit in US dollars'), '25');
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();

      expect(repository.limits.single.organization, costOrganization);
      expect(repository.limits.single.collection, isNull);
      expect(repository.limits.single.micros, 25000000);
      // The sheet is gone, the figures were read again, and the new limit is
      // what the server now says.
      expect(find.text('Save limit'), findsNothing);
      expect(repository.reads, hasLength(2));
      expect(find.text(r'$12.65'), findsOneWidget);
      expect(announced, contains('Monthly limit saved for Organization.'));
    });

    testWidgets('on a collection, by opening its row', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository);

      await openLimit(tester, collectionRow('col-plants'));
      expect(find.text('Plants'), findsWidgets);
      await tester.enterText(uiField('Limit in US dollars'), r'$1,250.50');
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();

      expect(repository.limits.single.collection, 'col-plants');
      expect(repository.limits.single.micros, 1250500000);
      expect(find.text(r'$5.25 · $1,245.25 left of $1,250.50'), findsOneWidget);
    });

    testWidgets('keeps the figures on screen while it reads them again', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository, reduceMotion: true);

      await openLimit(tester, collectionRow('col-plants'));
      await tester.enterText(uiField('Limit in US dollars'), '9');
      repository.hold = Completer<void>();
      final Completer<void> release = repository.hold!;
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();

      expect(find.byType(UiSkeleton), findsNothing);
      expect(find.text('Cost in October 2026'), findsOneWidget);

      release.complete();
      await tester.pumpAndSettle();
      expect(find.text(r'$5.25 · $3.75 left of $9.00'), findsOneWidget);
    });
  });

  group('changing and removing a limit', () {
    testWidgets('starts from the limit in force', (WidgetTester tester) async {
      await pumpCosts(tester, FakeCostRepository());

      await openLimit(tester, collectionRow('col-insects'));

      expect(find.text('Now \$10.00 a month.'), findsOneWidget);
      final EditableText field = tester.widget(
        find.descendant(
          of: uiField('Limit in US dollars'),
          matching: find.byType(EditableText),
        ),
      );
      expect(field.controller.text, '10.00');
      expect(uiButton('Remove limit'), findsOneWidget);
    });

    testWidgets('changes it', (WidgetTester tester) async {
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository);

      await openLimit(tester, collectionRow('col-insects'));
      await tester.enterText(uiField('Limit in US dollars'), '12.5');
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();

      expect(repository.limits.single.collection, 'col-insects');
      expect(repository.limits.single.micros, 12500000);
      expect(find.text(r'$7.10 · $5.40 left of $12.50'), findsOneWidget);
    });

    testWidgets('removes it by sending none, and says so', (
      WidgetTester tester,
    ) async {
      final List<String> announced = captureAnnouncements(tester);
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository);

      await openLimit(tester, collectionRow('col-insects'));
      await tester.tap(uiButton('Remove limit'));
      await tester.pumpAndSettle();

      expect(repository.limits.single.collection, 'col-insects');
      expect(repository.limits.single.micros, isNull);
      expect(find.text(r'$7.10 · No monthly limit'), findsOneWidget);
      expect(announced, contains('Monthly limit removed for Insects.'));
    });

    testWidgets('removes the organization\'s', (WidgetTester tester) async {
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository);

      await openLimit(tester, uiButton('Change limit'));
      await tester.tap(uiButton('Remove limit'));
      await tester.pumpAndSettle();

      expect(repository.limits.single.collection, isNull);
      expect(repository.limits.single.micros, isNull);
      expect(
        find.text('No monthly limit is set for the organization.'),
        findsOneWidget,
      );
    });

    testWidgets('changes nothing when cancelled', (WidgetTester tester) async {
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository);

      await openLimit(tester, collectionRow('col-insects'));
      await tester.enterText(uiField('Limit in US dollars'), '99');
      await tester.tap(uiButton('Cancel'));
      await tester.pumpAndSettle();

      expect(repository.limits, isEmpty);
      expect(repository.reads, hasLength(1));
      expect(find.text(r'$7.10 · $2.90 left of $10.00'), findsOneWidget);
    });
  });

  group('checking what is typed', () {
    Future<void> typeAndSave(WidgetTester tester, String text) async {
      await tester.enterText(uiField('Limit in US dollars'), text);
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();
    }

    for (final (String typed, String message) in <(String, String)>[
      ('', 'Enter a monthly limit in US dollars, like 25.00.'),
      // Letters never get into the field, so "not an amount" is a stray dot.
      ('1.2.3', 'Enter dollars and cents, like 25.00.'),
      ('25.123', 'Use at most two decimal places, like 25.00.'),
      ('0', r'Enter an amount above $0.00.'),
      ('2000000', r'Enter an amount up to $1,000,000.00.'),
    ]) {
      testWidgets('refuses "$typed" with the rule, once, and sends nothing', (
        WidgetTester tester,
      ) async {
        final FakeCostRepository repository = FakeCostRepository();
        await pumpCosts(tester, repository);
        await openLimit(tester, collectionRow('col-plants'));

        await typeAndSave(tester, typed);

        expect(find.text(message), findsOneWidget);
        expect(repository.limits, isEmpty);
        // The sheet stays open with what was typed.
        expect(uiButton('Save limit'), findsOneWidget);
        if (typed.isNotEmpty) {
          expect(find.text(typed), findsOneWidget);
        }
        // None of the retired words, and no "invalid".
        expect(message.toLowerCase(), isNot(contains('invalid')));
      });
    }

    testWidgets('clears the message as soon as the text changes', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());
      await openLimit(tester, collectionRow('col-plants'));

      await typeAndSave(tester, '1.2.3');
      expect(find.text('Enter dollars and cents, like 25.00.'), findsOneWidget);

      await tester.enterText(uiField('Limit in US dollars'), '12');
      await tester.pump();

      expect(find.text('Enter dollars and cents, like 25.00.'), findsNothing);
    });

    testWidgets('checks when the field is left, not on every keystroke', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());
      await openLimit(tester, collectionRow('col-plants'));

      await tester.enterText(uiField('Limit in US dollars'), '2.5.5');
      await tester.pump();
      expect(find.text('Enter dollars and cents, like 25.00.'), findsNothing);

      FocusManager.instance.primaryFocus?.unfocus();
      await tester.pumpAndSettle();
      expect(find.text('Enter dollars and cents, like 25.00.'), findsOneWidget);
    });

    testWidgets('does not scold an empty field that was only tabbed past', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());
      await openLimit(tester, collectionRow('col-plants'));

      FocusManager.instance.primaryFocus?.unfocus();
      await tester.pumpAndSettle();

      expect(
        find.text('Enter a monthly limit in US dollars, like 25.00.'),
        findsNothing,
      );
    });

    testWidgets('keeps only the characters an amount is made of', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());
      await openLimit(tester, collectionRow('col-plants'));

      await tester.enterText(uiField('Limit in US dollars'), 'a1b2.5c');

      final EditableText field = tester.widget(
        find.descendant(
          of: uiField('Limit in US dollars'),
          matching: find.byType(EditableText),
        ),
      );
      expect(field.controller.text, '12.5');
    });

    testWidgets('submits from the keyboard as the button does', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository);
      await openLimit(tester, collectionRow('col-plants'));

      await tester.enterText(uiField('Limit in US dollars'), '30');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();

      expect(repository.limits.single.micros, 30000000);
    });
  });

  group('when the server refuses a limit', () {
    testWidgets('keeps the sheet open with the reason and what was typed', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..limitFailure = const ApiFailure(
          'The limit is below what is already spent.',
          code: 'cap_below_spend',
          status: 422,
        );
      await pumpCosts(tester, repository);
      await openLimit(tester, collectionRow('col-insects'));

      await tester.enterText(uiField('Limit in US dollars'), '1');
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();

      expect(
        find.text('The limit was not saved. Retry in a moment.'),
        findsOneWidget,
      );
      expect(uiButton('Save limit'), findsOneWidget);
      expect(find.text('1'), findsOneWidget);
      // Nothing was read again: nothing changed.
      expect(repository.reads, hasLength(1));
      expect(find.text(r'$7.10 · $2.90 left of $10.00'), findsOneWidget);
    });

    testWidgets('names a failed removal as a removal', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..limitFailure = const ApiFailure('Offline.', code: 'network');
      await pumpCosts(tester, repository);
      await openLimit(tester, collectionRow('col-insects'));

      await tester.tap(uiButton('Remove limit'));
      await tester.pumpAndSettle();

      expect(
        find.text('The limit was not removed. Retry in a moment.'),
        findsOneWidget,
      );
      expect(
        find.text('The limit was not saved. Retry in a moment.'),
        findsNothing,
      );
    });

    testWidgets('can be tried again once it works', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..limitFailure = const ApiFailure('Offline.', code: 'network');
      await pumpCosts(tester, repository);
      await openLimit(tester, collectionRow('col-insects'));
      await tester.enterText(uiField('Limit in US dollars'), '11');
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();

      repository.limitFailure = null;
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();

      expect(repository.limits, hasLength(2));
      expect(find.text(r'$7.10 · $3.90 left of $11.00'), findsOneWidget);
    });
  });

  group('the form on its own', () {
    testWidgets('closes with the outcome', (WidgetTester tester) async {
      CostLimitResult? result;
      await pumpComponent(
        tester,
        Builder(
          builder: (BuildContext context) => UiButton(
            label: 'Open',
            onPressed: () async {
              result = await Navigator.of(context).push<CostLimitResult>(
                PageRouteBuilder<CostLimitResult>(
                  pageBuilder:
                      (
                        BuildContext _,
                        Animation<double> a,
                        Animation<double> b,
                      ) => Material(
                        child: CostLimitForm(
                          subject: 'Insects',
                          current: null,
                          apply: (int? micros) async {},
                        ),
                      ),
                ),
              );
            },
          ),
        ),
      );
      await tester.tap(uiButton('Open'));
      await tester.pumpAndSettle();
      await tester.enterText(uiField('Limit in US dollars'), '4');
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();

      expect(result, CostLimitResult.saved);
    });
  });

  group('for everyone', () {
    testWidgets('meets the tap target and label guidelines', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      await expectAccessible(tester);
    });

    testWidgets('headings are headings', (WidgetTester tester) async {
      await pumpCosts(tester, FakeCostRepository());

      final SemanticsHandle handle = tester.ensureSemantics();
      for (final String heading in <String>[
        'Organization',
        'Organization limit',
        'Collections',
        'Cost by stage',
        'Cost by model',
        'Figures',
      ]) {
        expect(
          tester.getSemantics(find.text(heading)).flagsCollection.isHeader,
          isTrue,
          reason: heading,
        );
      }
      handle.dispose();
    });

    testWidgets('fits a phone at twice the text size', (
      WidgetTester tester,
    ) async {
      // An overflow is a test failure, so reaching the end is the assertion.
      await pumpCosts(
        tester,
        FakeCostRepository(),
        size: const Size(390, 844),
        textScale: 2.0,
      );
      final Finder scroll = find.byType(Scrollable).first;
      await tester.scrollUntilVisible(
        uiButton('Update figures'),
        400,
        scrollable: scroll,
      );

      expect(uiButton('Update figures'), findsOneWidget);
      expect(find.byType(Scrollable), findsWidgets);
    });

    testWidgets(
      'stacks the tiles on a phone and sets them side by side on a desk',
      (WidgetTester tester) async {
        await pumpCosts(
          tester,
          FakeCostRepository(),
          size: const Size(390, 1600),
        );
        final List<double> phone = <double>[
          for (final Element tile in find.byType(UiDataTile).evaluate().take(3))
            tester.getTopLeft(find.byWidget(tile.widget)).dy,
        ];
        expect(phone.toSet(), hasLength(3), reason: 'three rows on a phone');

        await pumpCosts(
          tester,
          FakeCostRepository(),
          size: const Size(1280, 1600),
        );
        final List<double> desk = <double>[
          for (final Element tile in find.byType(UiDataTile).evaluate().take(3))
            tester.getTopLeft(find.byWidget(tile.widget)).dy,
        ];
        expect(desk.toSet(), hasLength(1), reason: 'one row on a desk');
      },
    );

    testWidgets('draws in dark as it does in light', (
      WidgetTester tester,
    ) async {
      await pumpCosts(
        tester,
        FakeCostRepository(),
        theme: productThemes['dark'],
      );

      expect(find.text('Cost in October 2026'), findsOneWidget);
      await expectAccessible(tester);
    });
  });
}
