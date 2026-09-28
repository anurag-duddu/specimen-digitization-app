// The browse and select surface over one source
// (`lib/src/screens/sources/source_screen.dart`).
//
// The behaviours a reviewer depends on: the count is always visible, a select
// all is offered only when the reach can be named, adding asks first, and a
// selection larger than the server's bound still reports one honest result.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/sources/source_controller.dart';
import 'package:specimen_digitization/src/screens/sources/source_screen.dart';
import 'package:specimen_digitization/src/screens/sources/sources_screen.dart';
import 'package:specimen_digitization/src/sources.dart';

import '../sources/source_fixtures.dart';
import '../ui_finders.dart';
import '../widgets/harness.dart';

Future<SourceBrowseController> pumpBrowse(
  WidgetTester tester,
  FakeSourceRepository repository, {
  Size size = const Size(1000, 800),
  ThemeData? theme,
}) async {
  final SourceBrowseController controller = SourceBrowseController(
    repository: repository,
    scope: testScope,
    sourceId: 'src-1',
  );
  addTearDown(controller.dispose);
  await pumpComponent(
    tester,
    SizedBox(
      width: size.width,
      height: size.height,
      child: SourceBrowsePane(controller: controller, source: source()),
    ),
    size: size,
    theme: theme,
  );
  await tester.pumpAndSettle();
  return controller;
}

/// The checkbox on the row naming [name].
Finder checkboxFor(String name) => find.descendant(
  of: find.byKey(ValueKey<String>('source-row-microscopic-slides/$name')),
  matching: find.byType(UiCheckbox),
);

void main() {
  testWidgets('says what the source holds and when it was listed', (
    WidgetTester tester,
  ) async {
    await pumpBrowse(tester, FakeSourceRepository());

    expect(find.text('microscopic-slides'), findsOneWidget);
    // Absolute, not relative: relative time is allowed only in the queue
    // list, and when a snapshot was taken decides whether an import will
    // still bind, so it is a citable value rather than a sense of recency.
    // On the reviewer's clock, never UTC to convert in their head (design/01
    // H1.9; coordinator ruling for S6, 2026-09-24).
    expect(
      find.text('10 photographs · listed 14 Sep 2026, 05:22 CDT'),
      findsOneWidget,
    );
    // No relative age anywhere in the header.
    expect(find.textContaining('ago'), findsNothing);
  });

  testWidgets('separates a count over 999', (WidgetTester tester) async {
    await pumpBrowse(
      tester,
      FakeSourceRepository(objects: manyObjects(1000), pageSize: 4),
    );

    // Section 4.14: thousands separators on every count over 999. This is
    // the first screen in the client to render one.
    expect(find.textContaining('1,000 photographs'), findsOneWidget);
    expect(find.text('Select all 1,000'), findsOneWidget);
  });

  testWidgets('draws a placeholder rather than fetching originals', (
    WidgetTester tester,
  ) async {
    await pumpBrowse(tester, FakeSourceRepository());

    // An un-imported photograph has no asset, and a grid of 300 KB originals
    // would be tens of megabytes. No row asks the network for an image.
    expect(find.byType(Image), findsNothing);
  });

  group('selection', () {
    testWidgets('keeps the count on screen from the first pick', (
      WidgetTester tester,
    ) async {
      await pumpBrowse(tester, FakeSourceRepository());

      await tester.tap(checkboxFor('subject_105526321.jpg'));
      await tester.pumpAndSettle();

      expect(find.text('1 photograph selected'), findsOneWidget);

      await tester.tap(checkboxFor('subject_105526322.jpg'));
      await tester.pumpAndSettle();

      expect(find.text('2 photographs selected'), findsOneWidget);
    });

    testWidgets('counts photographs, never records', (
      WidgetTester tester,
    ) async {
      await pumpBrowse(tester, FakeSourceRepository());

      await tester.tap(checkboxFor('subject_105526321.jpg'));
      await tester.pumpAndSettle();

      // A photograph in storage is not a record until it is added, and the
      // distinction is the whole point of this screen.
      expect(find.textContaining('record'), findsNothing);
    });

    testWidgets('an unsupported photograph is drawn but unavailable', (
      WidgetTester tester,
    ) async {
      await pumpBrowse(
        tester,
        FakeSourceRepository(
          objects: <SourceObject>[
            object('a.jpg'),
            object('b.pdf', state: 'unsupported_media_type'),
          ],
        ),
      );

      // Drawn and disabled, not absent: a reader hearing nothing at all
      // could not tell an unavailable row from one they missed.
      expect(
        tester.widget<UiCheckbox>(checkboxFor('a.jpg')).onChanged,
        isNotNull,
      );
      expect(tester.widget<UiCheckbox>(checkboxFor('b.pdf')).onChanged, isNull);
    });

    testWidgets('an unavailable row stays aligned with the rest', (
      WidgetTester tester,
    ) async {
      await pumpBrowse(
        tester,
        FakeSourceRepository(
          objects: <SourceObject>[
            object('a.jpg'),
            object('b.pdf', state: 'unsupported_media_type'),
          ],
        ),
      );

      // The alignment a reviewer scans a thousand rows down does not break
      // on the one row that cannot be picked.
      expect(
        tester.getTopLeft(find.text('b.pdf')).dx,
        tester.getTopLeft(find.text('a.jpg')).dx,
      );
    });

    testWidgets('an unavailable row cannot be picked by long press', (
      WidgetTester tester,
    ) async {
      await pumpBrowse(
        tester,
        FakeSourceRepository(
          objects: <SourceObject>[
            object('b.pdf', state: 'unsupported_media_type'),
          ],
        ),
        size: const Size(390, 844),
      );

      await tester.longPress(find.text('b.pdf'));
      await tester.pumpAndSettle();

      expect(find.textContaining('selected'), findsNothing);
    });
  });

  group('select all', () {
    testWidgets('names the whole snapshot, not the loaded page', (
      WidgetTester tester,
    ) async {
      await pumpBrowse(tester, FakeSourceRepository());

      // Four rows are loaded and ten match, and the control says ten, because
      // the server counted ten.
      expect(find.text('Select all 10'), findsOneWidget);
    });

    testWidgets('loads the rest before selecting any of it', (
      WidgetTester tester,
    ) async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: manyObjects(20),
        pageSize: 5,
      );
      await pumpBrowse(tester, repository);

      await tester.tap(find.text('Select all 20'));
      await tester.pumpAndSettle();

      // Every selected photograph is loaded, because an import names a
      // generation that only a listing row carries.
      expect(find.text('20 photographs selected'), findsOneWidget);
      expect(repository.listCursors, hasLength(4));
    });

    testWidgets('is absent when the server did not count', (
      WidgetTester tester,
    ) async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: <SourceObject>[
          for (int index = 0; index < 8; index++)
            object('in_$index.jpg', state: 'imported', specimenId: 's$index'),
        ],
      );
      final SourceBrowseController controller = await pumpBrowse(
        tester,
        repository,
      );

      await controller.applyFilter(filter: SourceFilter.inQueue);
      await tester.pumpAndSettle();

      // Counting under this filter costs a checksum lookup per photograph, so
      // the server declines. Null is not zero, and a control that cannot name
      // its reach is absent rather than vague.
      expect(controller.matchingCount, isNull);
      expect(find.textContaining('Select all'), findsNothing);
    });
  });

  group('adding', () {
    testWidgets('asks before it sends anything', (WidgetTester tester) async {
      final FakeSourceRepository repository = FakeSourceRepository();
      await pumpBrowse(tester, repository);

      await tester.tap(checkboxFor('subject_105526321.jpg'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add to queue'));
      await tester.pumpAndSettle();

      expect(find.text('Add 1 photograph to the queue?'), findsOneWidget);
      // Nothing has been sent yet.
      expect(repository.imports, isEmpty);
    });

    testWidgets('sends nothing when the confirmation is cancelled', (
      WidgetTester tester,
    ) async {
      final FakeSourceRepository repository = FakeSourceRepository();
      await pumpBrowse(tester, repository);

      await tester.tap(checkboxFor('subject_105526321.jpg'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add to queue'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      expect(repository.imports, isEmpty);
      // The selection survives, because the reviewer's work is still on
      // screen and they may have meant to change it.
      expect(find.text('1 photograph selected'), findsOneWidget);
    });

    testWidgets('adds and says so when everything landed', (
      WidgetTester tester,
    ) async {
      final FakeSourceRepository repository = FakeSourceRepository();
      await pumpBrowse(tester, repository);

      await tester.tap(checkboxFor('subject_105526321.jpg'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add to queue'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add 1 photograph'));
      await tester.pumpAndSettle();

      expect(repository.imports, <List<String>>[
        <String>['microscopic-slides/subject_105526321.jpg'],
      ]);
      expect(find.text('1 photograph added to the queue'), findsOneWidget);
    });

    testWidgets('opens a report when something did not land', (
      WidgetTester tester,
    ) async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: <SourceObject>[
          object('a.jpg'),
          object('b.jpg', state: 'imported', specimenId: 'spec-b'),
        ],
      );
      await pumpBrowse(tester, repository);

      await tester.tap(find.text('Select all 2'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add to queue'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add 2 photographs'));
      await tester.pumpAndSettle();

      expect(find.text('1 of 2 photographs added'), findsOneWidget);
      expect(find.text('Already in the queue, unchanged.'), findsOneWidget);
    });

    testWidgets('a selection past the server bound is one honest result', (
      WidgetTester tester,
    ) async {
      final FakeSourceRepository repository = FakeSourceRepository(
        objects: manyObjects(60),
        pageSize: 60,
      );
      await pumpBrowse(tester, repository);

      await tester.tap(find.text('Select all 60'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add to queue'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Add 60 photographs'));
      await tester.pumpAndSettle();

      // Two requests, because the server reads every photograph whole and
      // bounds one request at fifty. One result, because the reviewer made
      // one gesture.
      expect(repository.imports.map((List<String> c) => c.length), <int>[
        50,
        10,
      ]);
      expect(find.text('60 photographs added to the queue'), findsOneWidget);
    });
  });

  group('honesty', () {
    testWidgets('offers no way to run anything', (WidgetTester tester) async {
      await pumpBrowse(tester, FakeSourceRepository());

      await tester.tap(checkboxFor('subject_105526321.jpg'));
      await tester.pumpAndSettle();

      // Running a selection needs an estimate, an allowance and a
      // reservation, and no endpoint reports any of them yet. An affordance
      // the server cannot serve is hidden rather than disabled.
      expect(find.textContaining('Run'), findsNothing);
      expect(find.textContaining('Process'), findsNothing);
    });

    testWidgets('a source that refuses the listing names who can fix it', (
      WidgetTester tester,
    ) async {
      final FakeSourceRepository repository = FakeSourceRepository()
        ..listFailure = const ApiFailure(
          'Access denied',
          code: 'access_denied',
          status: 403,
        );
      await pumpBrowse(tester, repository);

      expect(find.text('Source not available'), findsOneWidget);
      expect(find.textContaining('Ask your administrator'), findsOneWidget);
      // Retry is not offered for a refusal retrying cannot resolve.
      expect(find.text('Retry'), findsNothing);
    });

    testWidgets('a snapshot recaptured under the reviewer says so once', (
      WidgetTester tester,
    ) async {
      final FakeSourceRepository repository = FakeSourceRepository();
      final SourceBrowseController controller = await pumpBrowse(
        tester,
        repository,
      );

      repository.inventoryId = 'inv-2';
      await controller.loadMore();
      await tester.pumpAndSettle();

      expect(find.textContaining('listed again'), findsOneWidget);
      // The band's dismiss draws a glyph, so the control is reached by the
      // name it publishes rather than by a word on screen.
      await tester.tap(uiControl(sourceRefreshedDismissLabel));
      await tester.pumpAndSettle();
      expect(find.textContaining('listed again'), findsNothing);
    });
  });

  group('the source list', () {
    testWidgets('names a source that has never been listed', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        SourcesScreen(
          repository: FakeSourceRepository(
            sources0: <RegisteredSource>[source(objectCount: null)],
          ),
          scope: testScope,
          onOpen: (RegisteredSource _) {},
        ),
      );

      // Never listed and empty are different facts.
      expect(find.text(SourcesScreenCopy.notListed), findsOneWidget);
    });

    testWidgets('a collection with none says who registers one', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        SourcesScreen(
          repository: FakeSourceRepository(
            sources0: const <RegisteredSource>[],
          ),
          scope: testScope,
          onOpen: (RegisteredSource _) {},
        ),
      );

      expect(find.text('No sources registered'), findsOneWidget);
      expect(find.text(SourcesScreenCopy.noneBody), findsOneWidget);
    });

    testWidgets('opens the source it was asked to open', (
      WidgetTester tester,
    ) async {
      String? opened;
      await pumpComponent(
        tester,
        SourcesScreen(
          repository: FakeSourceRepository(),
          scope: testScope,
          onOpen: (RegisteredSource source) => opened = source.id,
        ),
      );

      await tester.tap(find.text('microscopic-slides'));
      await tester.pumpAndSettle();

      expect(opened, 'src-1');
    });
  });
}
