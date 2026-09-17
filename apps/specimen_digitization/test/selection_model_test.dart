// The shared selection model (`lib/src/selection.dart`).
//
// The behaviour worth pinning is what happens across paging, because that is
// where a selection over a cursor-paged list stops being a set of strings and
// starts being a promise: the count on a confirmation has to be the count the
// server will act on, and "select all" has to reach exactly as far as the
// reviewer was told it would.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/selection.dart';

/// A stand-in for whatever a list holds. The model is written over neither the
/// queue nor a data source, and this test proves it by using neither.
class Row {
  const Row(this.id, [this.label = '']);

  final String id;
  final String label;
}

List<Row> page(int from, int to) => <Row>[
  for (int i = from; i <= to; i++) Row('r$i'),
];

PagedSelection<Row> selectionOf(List<Row> loaded, {bool moreToLoad = false}) {
  final PagedSelection<Row> selection = PagedSelection<Row>(
    identify: (Row row) => row.id,
  );
  selection.syncLoaded(loaded, moreToLoad: moreToLoad);
  return selection;
}

void main() {
  group('picking', () {
    test('starts empty and out of selection', () {
      final PagedSelection<Row> selection = selectionOf(page(1, 3));
      expect(selection.count, 0);
      expect(selection.isEmpty, isTrue);
      expect(selection.active, isFalse);
      expect(selection.allLoadedSelected, isFalse);
    });

    test('one row', () {
      final List<Row> loaded = page(1, 3);
      final PagedSelection<Row> selection = selectionOf(loaded);
      selection.toggle(loaded[1]);
      expect(selection.count, 1);
      expect(selection.active, isTrue);
      expect(selection.isSelected(loaded[1]), isTrue);
      expect(selection.isSelected(loaded[0]), isFalse);
      selection.toggle(loaded[1]);
      expect(selection.count, 0);
    });

    test('several, as a range from the last one picked', () {
      final List<Row> loaded = page(1, 6);
      final PagedSelection<Row> selection = selectionOf(loaded);
      selection.toggle(loaded[1]);
      selection.selectRange(loaded[4]);
      expect(selection.items.map((Row row) => row.id).toList(), <String>[
        'r2',
        'r3',
        'r4',
        'r5',
      ]);
    });

    test('a range runs in either direction', () {
      final List<Row> loaded = page(1, 6);
      final PagedSelection<Row> selection = selectionOf(loaded);
      selection.toggle(loaded[4]);
      selection.selectRange(loaded[1]);
      expect(selection.items.map((Row row) => row.id).toList(), <String>[
        'r2',
        'r3',
        'r4',
        'r5',
      ]);
    });

    test('a range with nothing to extend from picks one row', () {
      final List<Row> loaded = page(1, 4);
      final PagedSelection<Row> selection = selectionOf(loaded);
      selection.selectRange(loaded[2]);
      expect(selection.items.single.id, 'r3');
    });

    test('the selection is in the order the list holds it', () {
      final List<Row> loaded = page(1, 4);
      final PagedSelection<Row> selection = selectionOf(loaded);
      selection.toggle(loaded[3]);
      selection.toggle(loaded[0]);
      expect(selection.items.map((Row row) => row.id).toList(), <String>[
        'r1',
        'r4',
      ]);
    });

    test('clearing empties the selection and leaves selection', () {
      final List<Row> loaded = page(1, 3);
      final PagedSelection<Row> selection = selectionOf(loaded);
      selection.toggle(loaded[0]);
      selection.clear();
      expect(selection.count, 0);
      expect(selection.active, isFalse);
    });
  });

  group('select all reaches what is loaded, and says so', () {
    test('picks every loaded row', () {
      final List<Row> loaded = page(1, 5);
      final PagedSelection<Row> selection = selectionOf(loaded);
      selection.selectAllLoaded();
      expect(selection.count, 5);
      expect(selection.allLoadedSelected, isTrue);
    });

    test('a page the server has not sent is not reachable', () {
      final List<Row> loaded = page(1, 5);
      final PagedSelection<Row> selection = selectionOf(
        loaded,
        moreToLoad: true,
      );
      selection.selectAllLoaded();
      // Everything loaded is picked and the model still says there is more,
      // which is the pair of facts the bar renders. Nothing here can express
      // a selection of records the client has never seen.
      expect(selection.count, selection.loadedCount);
      expect(selection.allLoadedSelected, isTrue);
      expect(selection.moreToLoad, isTrue);
    });

    test('appending a page keeps the picks and reopens the select all', () {
      final List<Row> first = page(1, 3);
      final PagedSelection<Row> selection = selectionOf(
        first,
        moreToLoad: true,
      );
      selection.selectAllLoaded();
      expect(selection.allLoadedSelected, isTrue);

      selection.syncLoaded(page(1, 6), moreToLoad: false);
      expect(selection.count, 3, reason: 'the first page stays picked');
      expect(
        selection.allLoadedSelected,
        isFalse,
        reason:
            'a select all could not have reached a page that had not '
            'arrived, so the control comes back',
      );
      expect(selection.moreToLoad, isFalse);

      selection.selectAllLoaded();
      expect(selection.count, 6);
    });
  });

  group('the selection is always a subset of what is loaded', () {
    test('a row that leaves the list leaves the selection', () {
      final List<Row> loaded = page(1, 4);
      final PagedSelection<Row> selection = selectionOf(loaded);
      selection.selectAllLoaded();
      expect(selection.count, 4);

      // A record that was cleared drops out of a "needs review" filter.
      selection.syncLoaded(<Row>[loaded[0], loaded[2]], moreToLoad: false);
      expect(
        selection.items.map((Row row) => row.id).toList(),
        <String>['r1', 'r3'],
        reason:
            'a count that includes records the reviewer can no longer see '
            'is not a count a confirmation can be built on',
      );
    });

    test('the same rows in new objects keep the selection', () {
      final PagedSelection<Row> selection = selectionOf(page(1, 3));
      selection.selectAllLoaded();
      // A poll answers equal records as fresh objects. Identity is the
      // identifier, never the instance.
      selection.syncLoaded(page(1, 3), moreToLoad: false);
      expect(selection.count, 3);
    });

    test('a range anchor that left the list does not resurrect it', () {
      final List<Row> loaded = page(1, 5);
      final PagedSelection<Row> selection = selectionOf(loaded);
      selection.toggle(loaded[0]);
      selection.syncLoaded(page(2, 5), moreToLoad: false);
      expect(selection.count, 0);
      selection.selectRange(loaded[3]);
      expect(
        selection.items.map((Row row) => row.id).toList(),
        <String>['r4'],
        reason:
            'with the anchor gone a range picks one row, never a range '
            'measured from a record that is no longer there',
      );
    });
  });

  group('listeners', () {
    test('every change notifies once', () {
      final List<Row> loaded = page(1, 3);
      final PagedSelection<Row> selection = selectionOf(loaded);
      int notices = 0;
      selection.addListener(() => notices++);
      selection.toggle(loaded[0]);
      selection.selectAllLoaded();
      selection.clear();
      expect(notices, 3);
    });

    test('a sync that changes nothing is quiet', () {
      final PagedSelection<Row> selection = selectionOf(page(1, 3));
      int notices = 0;
      selection.addListener(() => notices++);
      selection.syncLoaded(page(1, 3), moreToLoad: false);
      expect(
        notices,
        0,
        reason:
            'a twenty second poll that answered the same records must not '
            'rebuild the bar',
      );
    });
  });
}
