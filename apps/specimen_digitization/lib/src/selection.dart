/// Selection over a list nobody can see the end of.
///
/// A reviewer picking records out of the queue and a reviewer picking objects
/// out of a data source are the same gesture over two different lists, so the
/// model is written over neither. It knows three things: what is loaded, what
/// is picked, and whether the server said there is more. Everything else
/// belongs to the screen.
///
/// **What "select all" means here.** It means every record currently loaded,
/// and nothing else. That is not a simplification that could be lifted later:
/// the list API answers a page and a cursor, never a total, and the bulk
/// decisions endpoint takes named records at named versions. A control
/// claiming "all matching" would be claiming authority over records the client
/// has never seen, at versions it does not hold, and it could not state the
/// count on the confirmation, which is the one thing a bulk confirmation has
/// to do. So this model has no way to express it, and [moreToLoad] is how a
/// screen tells the reviewer that the reach stops where the loading stopped.
library;

import 'package:flutter/foundation.dart';

/// A selection over one page-at-a-time list.
///
/// [identify] turns an item into the stable identifier the selection is kept
/// in, so a poll that answers new objects for the same records does not lose
/// the selection.
///
/// The selection is always a subset of what is loaded. [syncLoaded] enforces
/// that: a record that leaves the list leaves the selection with it, because a
/// count that includes records the reviewer can no longer see is a count no
/// confirmation should be built on.
class PagedSelection<T extends Object> extends ChangeNotifier {
  PagedSelection({required this.identify});

  /// The stable identifier of one item.
  final String Function(T item) identify;

  final Set<String> _selected = <String>{};
  List<T> _loaded = <T>[];
  bool _moreToLoad = false;
  bool _active = false;
  String? _anchor;

  /// True once the reviewer has entered selection, and false again the moment
  /// they leave it.
  ///
  /// A screen wide enough to keep a checkbox column always shows one; this is
  /// for the narrow window that reveals the column on a long press.
  bool get active => _active;

  /// How many records are selected. Always visible on screen.
  int get count => _selected.length;

  bool get isEmpty => _selected.isEmpty;

  bool get isNotEmpty => _selected.isNotEmpty;

  /// The identifiers, for a caller that only needs to ask a row about itself.
  Set<String> get ids => Set<String>.unmodifiable(_selected);

  /// The selected items, in the order the list holds them.
  List<T> get items => List<T>.unmodifiable(
    _loaded.where((T item) => _selected.contains(identify(item))),
  );

  /// How many items are loaded, which is how far a select all reaches.
  int get loadedCount => _loaded.length;

  /// True when the server said there is another page.
  ///
  /// The honest half of a select all: everything loaded is picked, and more
  /// than that matches.
  bool get moreToLoad => _moreToLoad;

  /// True when every loaded item is selected and there is at least one.
  bool get allLoadedSelected =>
      _loaded.isNotEmpty && _selected.length == _loaded.length;

  bool isSelected(T item) => _selected.contains(identify(item));

  bool isSelectedId(String id) => _selected.contains(id);

  /// Replaces what is loaded, keeping only the selection that survives it.
  ///
  /// [moreToLoad] is whether the list has a next page. Call this whenever the
  /// list answers, including when a later page is appended: appending leaves
  /// every selected record selected and makes [allLoadedSelected] false again,
  /// which is correct, because a select all cannot have reached a page that
  /// had not arrived.
  void syncLoaded(List<T> loaded, {required bool moreToLoad}) {
    final List<T> next = List<T>.unmodifiable(loaded);
    final Set<String> present = next.map(identify).toSet();
    final int removed =
        _selected.length - _selected.intersection(present).length;
    final bool changed =
        removed > 0 ||
        _moreToLoad != moreToLoad ||
        !listEquals(
          _loaded.map(identify).toList(),
          next.map(identify).toList(),
        );
    _loaded = next;
    _moreToLoad = moreToLoad;
    if (removed > 0) _selected.retainAll(present);
    if (_anchor != null && !present.contains(_anchor)) _anchor = null;
    if (_selected.isEmpty) _anchor = null;
    if (changed) notifyListeners();
  }

  /// Picks or unpicks one item, and makes it the anchor a range extends from.
  void toggle(T item) {
    final String id = identify(item);
    _active = true;
    if (!_selected.remove(id)) _selected.add(id);
    _anchor = _selected.contains(id) ? id : null;
    notifyListeners();
  }

  /// Picks one item without unpicking it if it is already picked.
  void select(T item) {
    final String id = identify(item);
    _active = true;
    _anchor = id;
    if (_selected.add(id)) notifyListeners();
  }

  /// Picks everything between the anchor and [item], inclusive.
  ///
  /// With no anchor this is an ordinary [select], so a range gesture with
  /// nothing to extend from picks one record rather than doing nothing.
  void selectRange(T item) {
    final String id = identify(item);
    final String? anchor = _anchor;
    if (anchor == null) {
      select(item);
      return;
    }
    final List<String> order = _loaded.map(identify).toList();
    final int from = order.indexOf(anchor);
    final int to = order.indexOf(id);
    if (from < 0 || to < 0) {
      select(item);
      return;
    }
    _active = true;
    final int start = from < to ? from : to;
    final int end = from < to ? to : from;
    _selected.addAll(order.sublist(start, end + 1));
    _anchor = id;
    notifyListeners();
  }

  /// Picks every loaded item. Nothing beyond the loaded page is reachable.
  void selectAllLoaded() {
    if (_loaded.isEmpty) return;
    _active = true;
    _selected
      ..clear()
      ..addAll(_loaded.map(identify));
    _anchor = null;
    notifyListeners();
  }

  /// Empties the selection and leaves selection.
  void clear() {
    if (_selected.isEmpty && !_active) return;
    _selected.clear();
    _anchor = null;
    _active = false;
    notifyListeners();
  }

  /// Enters selection without picking anything.
  void begin() {
    if (_active) return;
    _active = true;
    notifyListeners();
  }
}
