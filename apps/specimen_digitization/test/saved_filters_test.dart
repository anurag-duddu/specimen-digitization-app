// Named filter sets (pass criterion 7.4).
//
// Save the current filters under a name, list the sets at the top of the
// filter form, apply one in a single action, delete one, and find them all
// still there after a restart. The store is the platform preference store, so
// "survives a restart" is tested the only way a widget test can test it: the
// in-memory implementation is kept across two independent reads, which is
// exactly what a restart does to it.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/saved_filters.dart';
import 'package:specimen_digitization/src/search_filters.dart';

import 'widgets/harness.dart';

void main() {
  const String collection = 'org/insects';

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('the store', () {
    test('a saved set comes back, by name, with its filters', () async {
      const SavedFilterStore store = SavedFilterStore(collection);
      expect(await store.load(), isEmpty);

      await store.save(
        const SavedFilterSet(
          name: 'Blocked this week',
          filters: <String, String>{
            'blocker': 'external_outcome_unknown',
            'risk_min': '40',
          },
        ),
      );

      // A second store object on the same collection is what a restart looks
      // like from here: nothing is held in memory between the two.
      const SavedFilterStore reopened = SavedFilterStore(collection);
      final List<SavedFilterSet> sets = await reopened.load();
      expect(sets, hasLength(1));
      expect(sets.single.name, 'Blocked this week');
      expect(sets.single.filters['blocker'], 'external_outcome_unknown');
      expect(sets.single.count, 2);
    });

    test('reusing a name replaces that set rather than adding a second', () async {
      const SavedFilterStore store = SavedFilterStore(collection);
      await store.save(
        const SavedFilterSet(
          name: 'Mine',
          filters: <String, String>{'uploader_id': 'a'},
        ),
      );
      final List<SavedFilterSet> sets = await store.save(
        const SavedFilterSet(
          name: 'Mine',
          filters: <String, String>{'uploader_id': 'b'},
        ),
      );
      expect(sets, hasLength(1));
      expect(sets.single.filters['uploader_id'], 'b');
    });

    test('sets belong to one collection', () async {
      await const SavedFilterStore(collection).save(
        const SavedFilterSet(name: 'Mine', filters: <String, String>{}),
      );
      expect(await const SavedFilterStore('org/plants').load(), isEmpty);
    });

    test('deleting removes that set and leaves the rest', () async {
      const SavedFilterStore store = SavedFilterStore(collection);
      await store.save(
        const SavedFilterSet(name: 'One', filters: <String, String>{}),
      );
      await store.save(
        const SavedFilterSet(name: 'Two', filters: <String, String>{}),
      );
      final List<SavedFilterSet> sets = await store.remove('One');
      expect(sets.map((SavedFilterSet s) => s.name), <String>['Two']);
    });

    test('an unreadable stored value is no sets, never a crash', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{
        'queue.saved_filters.$collection': 'not json',
      });
      expect(await const SavedFilterStore(collection).load(), isEmpty);
    });
  });

  group('the filter form', () {
    testWidgets('lists the saved sets at the top and applies one in one tap', (
      WidgetTester tester,
    ) async {
      await const SavedFilterStore(collection).save(
        const SavedFilterSet(
          name: 'Blocked this week',
          filters: <String, String>{'blocker': 'external_outcome_unknown'},
        ),
      );

      Map<String, String>? applied;
      await pumpComponent(
        tester,
        Builder(
          builder: (BuildContext context) => TextButton(
            onPressed: () async => applied = await showDialog<Map<String, String>>(
              context: context,
              builder: (BuildContext dialogContext) => Dialog(
                child: SizedBox(
                  width: 480,
                  height: 700,
                  child: SearchFilters(
                    initial: const <String, String>{},
                    savedFilters: const SavedFilterStore(collection),
                  ),
                ),
              ),
            ),
            child: const Text('Open'),
          ),
        ),
        size: const Size(1000, 900),
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      expect(find.text('Saved filter sets'), findsOneWidget);
      expect(find.text('Blocked this week (1)'), findsOneWidget);

      await tester.tap(find.text('Blocked this week (1)'));
      await tester.pumpAndSettle();
      expect(applied, <String, String>{
        'blocker': 'external_outcome_unknown',
      });
    });

    testWidgets('names and saves the filters on screen, and deletes a set', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const SizedBox(
          width: 480,
          height: 760,
          child: SearchFilters(
            initial: <String, String>{'batch_id': 'batch-7'},
            savedFilters: SavedFilterStore(collection),
          ),
        ),
        size: const Size(1000, 900),
      );
      await tester.pumpAndSettle();
      expect(find.text('None saved on this device yet.'), findsOneWidget);

      await tester.tap(find.text('Save these filters'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).last, 'Batch seven');
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save the filter set'));
      await tester.pumpAndSettle();

      expect(find.text('Batch seven (1)'), findsOneWidget);
      expect(
        (await const SavedFilterStore(collection).load()).single.filters,
        <String, String>{'batch_id': 'batch-7'},
      );

      await tester.tap(
        find.byTooltip('Delete the Batch seven filter set'),
      );
      await tester.pumpAndSettle();
      expect(find.text('None saved on this device yet.'), findsOneWidget);
      expect(await const SavedFilterStore(collection).load(), isEmpty);
    });
  });
}
