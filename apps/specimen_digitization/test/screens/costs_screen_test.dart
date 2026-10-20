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

  const String counted =
      'Shared Google costs are counted through 19 Oct 2026, a billing day in '
      'Pacific time.';

  group('the figures', () {
    testWidgets('give the organization\'s three amounts in dollars', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, FakeCostRepository());

      expect(find.text('Cost in October 2026'), findsOneWidget);
      expect(find.text(r'$12.35'), findsWidgets);
      expect(find.text('Held, cost unknown'), findsOneWidget);
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
        said('Held, cost unknown'),
        r'Held, cost unknown, $0.50. The part held for calls whose cost is '
        'unknown.',
      );
      expect(
        said('Before free allowance'),
        r"Before free allowance, $15.00. The same costs before Google's free "
        'allowance.',
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

      expect(
        find.text('Nothing is held for calls whose cost is unknown.'),
        findsOneWidget,
      );
      expect(
        find.text('The part held for calls whose cost is unknown.'),
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
      expect(find.text(counted), findsOneWidget);
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
      expect(find.text(counted), findsOneWidget);
    });

    testWidgets('a meter that is behind says by how much, and through when', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          wire['meter'] = <String, dynamic>{
            'allocated_through': '2026-10-16',
            'allocation_status': 'behind',
          };
        }),
      );
      await pumpCosts(tester, repository);

      expect(find.text('Shared Google costs are behind.'), findsOneWidget);
      // The line under the update time stays out of it: the banner is what
      // says how far the count has got.
      expect(find.textContaining('are counted through'), findsNothing);
    });

    testWidgets('a meter that is behind names the day it counted through', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          wire['meter'] = <String, dynamic>{
            'allocated_through': '2026-10-16',
            'allocation_status': 'behind',
          };
        }),
      );
      await pumpCosts(tester, repository);

      // The detail is behind the banner's disclosure.
      await tester.tap(uiControl(UiBanner.defaultDetailLabel));
      await tester.pumpAndSettle();
      expect(
        find.text(
          'More than two complete billing days behind. Counted through 16 Oct '
          '2026, a billing day in Pacific time.',
        ),
        findsOneWidget,
      );
    });

    testWidgets('the earlier status for unreadable usage is not a state', (
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

      // A word this client has not met is named plainly, with no banner.
      expect(find.byType(UiBanner), findsNothing);
      expect(
        find.text('Shared Google costs: monitoring unavailable.'),
        findsOneWidget,
      );
    });

    testWidgets('a meter that has not run says no shared cost is counted', (
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

      expect(
        find.text('No shared Google costs have been counted.'),
        findsOneWidget,
      );
      expect(find.textContaining('are counted through'), findsNothing);
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

      // One under the band and one in the Figures section.
      expect(uiButton('Update figures'), findsNWidgets(2));
      await tester.tap(uiButton('Update figures').first);
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

      expect(find.text('Shared Google costs: catching up.'), findsOneWidget);
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
      expect(find.textContaining('Shared Google costs'), findsNothing);
    });
  });

  group('a credit', () {
    FakeCostRepository withCredit() =>
        FakeCostRepository(wire: (String month) => creditWire(costWire(month)));

    testWidgets('is written as a credit, never with a minus', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, withCredit());

      expect(find.text(r'$0.30 credit'), findsWidgets);
      expect(find.text('Processing worker'), findsOneWidget);
      for (final int mark in <int>[0x2013, 0x2014, 0x2212]) {
        expect(find.textContaining(String.fromCharCode(mark)), findsNothing);
      }
      expect(find.textContaining(r'-$'), findsNothing);
    });

    testWidgets('sits after every cost among the stages', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, withCredit());

      final double database = tester.getTopLeft(stageRow('database')).dy;
      final double worker = tester.getTopLeft(stageRow('worker')).dy;
      expect(worker, greaterThan(database));
      expect(
        spoken(tester, stageRow('worker')),
        r'Processing worker, $0.30 credit, 3 entries',
      );
    });

    testWidgets('sits after every cost among the models, with its provider', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, withCredit());

      expect(find.text('specimen-sam'), findsOneWidget);
      expect(
        find.text('Processing worker · Google Cloud · 3 entries'),
        findsOneWidget,
      );
      final double credit = tester.getTopLeft(find.text('specimen-sam')).dy;
      final double paid = tester.getTopLeft(find.text('first-pass-glm')).dy;
      expect(credit, greaterThan(paid));
    });

    testWidgets('can be the whole of the organization\'s figures', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          wire['totals'] = <String, dynamic>{
            'cost_micros': -300000,
            'held_micros': 0,
            'list_cost_micros': 0,
            'entries': 0,
          };
        }),
      );
      await pumpCosts(tester, repository);

      // Recorded, though nothing was spent: not "No costs recorded".
      expect(find.text('Cost in October 2026'), findsOneWidget);
      expect(find.text(r'$0.30 credit'), findsWidgets);
      expect(
        find.text(
          'No costs were counted for the organization in October 2026.',
        ),
        findsNothing,
      );
    });

    testWidgets('says what a collection holds that fell below zero', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          final Json plants =
              (wire['collections'] as List<Object?>)[2]! as Json;
          plants['total'] = amounts(-450000, entries: 2);
        }),
      );
      await pumpCosts(tester, repository);

      expect(find.text(r'$0.45 credit · No monthly limit'), findsOneWidget);
      expect(
        spoken(tester, collectionRow('col-plants')),
        r'Plants, $0.45 credit, No monthly limit. Set limit',
      );
    });

    testWidgets('a held amount below zero is still said, not hidden', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository(
        wire: edited((Json wire) {
          (wire['totals'] as Json)['held_micros'] = -20000;
        }),
      );
      await pumpCosts(tester, repository);

      expect(find.text(r'$0.02 credit'), findsOneWidget);
      expect(
        find.text('The part held for calls whose cost is unknown.'),
        findsOneWidget,
      );
    });

    testWidgets('keeps the figures readable at twice the text size', (
      WidgetTester tester,
    ) async {
      // A credit is a longer word than a number; an overflow fails the test.
      await pumpCosts(
        tester,
        withCredit(),
        size: const Size(390, 1600),
        textScale: 2.0,
      );

      expect(find.text(r'$0.30 credit'), findsWidgets);
    });
  });

  group('limits that could not be read', () {
    FakeCostRepository unreadable() =>
        FakeCostRepository()
          ..customWire = (String month) => capsUnavailableWire(costWire(month));

    testWidgets('are not called "no limit"', (WidgetTester tester) async {
      await pumpCosts(tester, unreadable());

      expect(
        find.text('The monthly limits could not be read.'),
        findsOneWidget,
      );
      expect(
        find.text('No monthly limit is set for the organization.'),
        findsNothing,
      );
      expect(find.textContaining('No monthly limit'), findsNothing);
      expect(find.text('Left in October 2026'), findsNothing);
    });

    testWidgets('offer no way to set one over a limit that cannot be seen', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, unreadable());

      expect(uiButton('Set limit'), findsNothing);
      expect(uiButton('Change limit'), findsNothing);
      expect(find.text('Set limit'), findsNothing);
      expect(find.text('Change limit'), findsNothing);
    });

    testWidgets('leave each collection showing its costs, and say its limit', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, unreadable());

      expect(find.text(r'$7.10 · Limit could not be read'), findsOneWidget);
      expect(find.text(r'$2.90 · Limit could not be read'), findsOneWidget);
      expect(
        find.text('No costs recorded · Limit could not be read'),
        findsOneWidget,
      );
      expect(
        spoken(tester, collectionRow('col-insects')),
        r'Insects, $7.10 including sub-collections, Limit could not be read',
      );
    });

    testWidgets('open no form from a collection row', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = unreadable();
      await pumpCosts(tester, repository);

      await tester.tap(collectionRow('col-insects'), warnIfMissed: false);
      await tester.pumpAndSettle();

      expect(find.text('Monthly limit'), findsNothing);
      expect(uiButton('Save limit'), findsNothing);
      expect(repository.limits, isEmpty);
    });

    testWidgets('can be read again from the page', (WidgetTester tester) async {
      final FakeCostRepository repository = unreadable();
      await pumpCosts(tester, repository);

      repository.customWire = null;
      await tester.tap(uiButton('Retry'));
      await tester.pumpAndSettle();

      expect(repository.reads, hasLength(2));
      expect(find.text('The monthly limits could not be read.'), findsNothing);
      expect(find.text(r'$7.10 · $2.90 left of $10.00'), findsOneWidget);
      expect(find.text('Left in October 2026'), findsOneWidget);
    });

    testWidgets('keep the figures on screen while they are read again', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = unreadable();
      await pumpCosts(tester, repository, reduceMotion: true);

      repository.hold = Completer<void>();
      final Completer<void> release = repository.hold!;
      await tester.tap(uiButton('Retry'));
      await tester.pumpAndSettle();

      expect(find.byType(UiSkeleton), findsNothing);
      expect(find.text('Cost in October 2026'), findsOneWidget);
      release.complete();
      await tester.pumpAndSettle();
    });

    testWidgets('still show the costs whole', (WidgetTester tester) async {
      await pumpCosts(tester, unreadable());

      expect(find.text('Cost in October 2026'), findsOneWidget);
      expect(find.text(r'$12.35'), findsWidgets);
      expect(find.text('Reading labels'), findsOneWidget);
      expect(find.text('handwriting-qwen'), findsOneWidget);
    });
  });

  group('the band\'s update', () {
    FakeCostRepository behind() => FakeCostRepository(
      wire: edited((Json wire) {
        wire['meter'] = <String, dynamic>{
          'allocated_through': '2026-10-16',
          'allocation_status': 'behind',
        };
      }),
    );

    Finder bandButton() => uiButton('Update figures').first;
    Finder figuresButton() => uiButton('Update figures').last;

    testWidgets('is busy while the request runs, and so is the other', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = behind();
      await pumpCosts(tester, repository, reduceMotion: true);
      repository.refreshHold = Completer<void>();
      final Completer<void> release = repository.refreshHold!;

      await tester.tap(bandButton());
      await tester.pump();

      // Both say Updating while the one request is out, and neither can send a
      // second.
      expect(find.text('Updating…'), findsNWidgets(2));
      for (final Element button in uiButton('Updating…').evaluate()) {
        expect((button.widget as UiButton).loading, isTrue);
      }
      // The last button on the page is the Figures section's, which now reads
      // Updating, so it is found by its place and not by its label.
      await tester.tap(find.byType(UiButton).last, warnIfMissed: false);
      await tester.pump();
      expect(repository.refreshes, hasLength(1));

      release.complete();
      await tester.pumpAndSettle();
      expect(find.text('Updating…'), findsNothing);
    });

    testWidgets('writes its outcome under the band, where it was pressed', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = behind();
      await pumpCosts(tester, repository);

      await tester.tap(bandButton());
      await tester.pumpAndSettle();

      const String said =
          'Update requested. The figures update within minutes.';
      expect(find.text(said), findsOneWidget);
      // Under the band, above the figures it is about.
      final double outcome = tester.getTopLeft(find.text(said)).dy;
      expect(
        outcome,
        lessThan(tester.getTopLeft(find.text('Organization')).dy),
      );
    });

    testWidgets('is announced once, not once for each place it is written', (
      WidgetTester tester,
    ) async {
      final List<String> announced = captureAnnouncements(tester);
      await pumpCosts(tester, behind());

      await tester.tap(bandButton());
      await tester.pumpAndSettle();

      expect(announced, <String>[
        'Update requested. The figures update within minutes.',
      ]);
    });

    testWidgets('and the Figures section writes under itself', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, behind());

      await tester.tap(figuresButton());
      await tester.pumpAndSettle();

      final double outcome = tester
          .getTopLeft(
            find.text('Update requested. The figures update within minutes.'),
          )
          .dy;
      expect(outcome, greaterThan(tester.getTopLeft(find.text('Figures')).dy));
    });

    testWidgets('says a refusal under the band, with the reason behind it', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = behind()
        ..refreshFailure = const ApiFailure(
          'The worker job is not configured.',
          code: 'unavailable',
          status: 503,
        );
      await pumpCosts(tester, repository);

      await tester.tap(bandButton());
      await tester.pumpAndSettle();

      expect(
        find.text('The update did not start. Retry in a moment.'),
        findsOneWidget,
      );
      expect(uiButton('Update figures'), findsNWidgets(2));
    });

    testWidgets('can be pressed again once it has answered', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = behind();
      await pumpCosts(tester, repository);

      await tester.tap(bandButton());
      await tester.pumpAndSettle();
      await tester.tap(bandButton());
      await tester.pumpAndSettle();

      expect(repository.refreshes, hasLength(2));
    });
  });

  group('a collection the server no longer lists', () {
    FakeCostRepository retired() => FakeCostRepository(
      wire: (String month) => unlistedWire(costWire(month)),
    );

    testWidgets('is said in words, never by its id', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, retired());

      expect(find.text('Collection no longer listed'), findsOneWidget);
      expect(find.textContaining(retiredCollection), findsNothing);
      expect(find.textContaining('3f9a2c1e'), findsNothing);
      // Its costs are still its costs.
      expect(find.text(r'$1.20'), findsOneWidget);
    });

    testWidgets('does not speak the id either', (WidgetTester tester) async {
      await pumpCosts(tester, retired());

      final String said = spoken(tester, collectionRow(retiredCollection));
      expect(said, r'Collection no longer listed, $1.20');
      expect(said, isNot(contains('3f9a2c1e')));
    });

    testWidgets('offers no limit, because the service refuses one', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = retired();
      await pumpCosts(tester, repository);

      // The four listed collections offer one; this row does not.
      expect(find.text('Set limit'), findsNWidgets(3));
      // The organization's own button reads Change limit too.
      expect(find.text('Change limit'), findsNWidgets(2));
      expect(
        find.descendant(
          of: collectionRow(retiredCollection),
          matching: find.byType(UiRowTrailing),
        ),
        findsNothing,
      );
      await tester.tap(collectionRow(retiredCollection), warnIfMissed: false);
      await tester.pumpAndSettle();

      expect(find.text('Monthly limit'), findsNothing);
      expect(uiButton('Save limit'), findsNothing);
      expect(repository.limits, isEmpty);
    });

    testWidgets('says nothing about a limit it cannot have', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, retired());

      expect(find.textContaining('No monthly limit'), findsNWidgets(3));
      final Finder row = find.descendant(
        of: collectionRow(retiredCollection),
        matching: find.byType(Text),
      );
      for (final Element text in row.evaluate()) {
        expect(
          (text.widget as Text).data ?? '',
          isNot(contains('limit')),
          reason: 'a retired collection has no limit to name',
        );
      }
    });

    testWidgets('stays a row, indented as a root, among the others', (
      WidgetTester tester,
    ) async {
      await pumpCosts(tester, retired());

      expect(
        tester.getTopLeft(find.text('Collection no longer listed')).dx,
        tester.getTopLeft(find.text('Plants')).dx,
      );
      expect(
        tester.getTopLeft(find.text('Collection no longer listed')).dy,
        greaterThan(tester.getTopLeft(find.text('Microscopic slides')).dy),
      );
    });

    testWidgets('is the same when the limits could not be read', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository()
        ..customWire = (String month) =>
            capsUnavailableWire(unlistedWire(costWire(month)));
      await pumpCosts(tester, repository);

      expect(find.text('Collection no longer listed'), findsOneWidget);
      expect(find.text(r'$1.20'), findsOneWidget);
      expect(find.textContaining('3f9a2c1e'), findsNothing);
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
        find.text('No update was started. Try again later.'),
        findsOneWidget,
      );
      // Nothing is promised when nothing was started.
      expect(find.textContaining('Update requested'), findsNothing);
      expect(find.textContaining('within minutes'), findsNothing);
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

    testWidgets('of nothing at all, which the service takes as a limit', (
      WidgetTester tester,
    ) async {
      final FakeCostRepository repository = FakeCostRepository();
      await pumpCosts(tester, repository);

      await openLimit(tester, collectionRow('col-plants'));
      await tester.enterText(uiField('Limit in US dollars'), '0');
      await tester.tap(uiButton('Save limit'));
      await tester.pumpAndSettle();

      // Zero is sent as zero, never as the removal that null is.
      expect(repository.limits.single.collection, 'col-plants');
      expect(repository.limits.single.micros, 0);
      expect(find.text(r'$5.25 · Limit of $0.00 reached'), findsOneWidget);
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
      ('9007199255', r'Enter an amount up to $9,007,199,254.74.'),
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
