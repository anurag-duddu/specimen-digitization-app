/// Named filter sets (screen blueprints, section 4; pass criterion 7.4).
///
/// A reviewer who works one slice of a collection every morning should not
/// rebuild the same seven filters every morning. A set is a name and the
/// filter map the sheet already returns, so nothing about the wire format
/// changes: what is saved is exactly what `WorkspaceController.applyFilters`
/// accepts.
///
/// Stored on the device with `shared_preferences`, per collection, because the
/// API has no place to put one. That is stated where the sets are listed, so
/// nobody expects a set to follow them to another machine.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// One named filter set.
@immutable
class SavedFilterSet {
  const SavedFilterSet({required this.name, required this.filters});

  /// The name the reviewer typed.
  final String name;

  /// The filters, in the wire format the repository expects.
  final Map<String, String> filters;

  /// How many filters the set carries.
  int get count => filters.length;

  /// The set as it is stored.
  Map<String, Object?> toJson() => <String, Object?>{
    'name': name,
    'filters': filters,
  };

  /// Reads one set back, or null when the stored entry is unreadable.
  static SavedFilterSet? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final Object? name = raw['name'];
    final Object? filters = raw['filters'];
    if (name is! String || name.isEmpty || filters is! Map) return null;
    return SavedFilterSet(
      name: name,
      filters: <String, String>{
        for (final MapEntry<Object?, Object?> entry in filters.entries)
          if (entry.key is String && entry.value is String)
            entry.key! as String: entry.value! as String,
      },
    );
  }
}

/// Reads and writes the saved sets for one collection.
///
/// Every method answers the whole list, so a caller never has to reconcile a
/// local copy with what was written.
class SavedFilterStore {
  const SavedFilterStore(this.collectionKey);

  /// The collection the sets belong to. Sets are per collection, because a
  /// filter that names an upload batch means nothing in another one.
  final String collectionKey;

  /// The preference key this collection's sets live under.
  String get storageKey => 'queue.saved_filters.$collectionKey';

  /// The most sets one collection keeps.
  ///
  /// A cap rather than a promise of unlimited storage: a list longer than
  /// this is a list nobody reads, and the preference store is not a database.
  static const int limit = 20;

  /// The sets, oldest first, skipping any entry that no longer reads.
  Future<List<SavedFilterSet>> load() async {
    final SharedPreferences store = await SharedPreferences.getInstance();
    final String? raw = store.getString(storageKey);
    if (raw == null || raw.isEmpty) return const <SavedFilterSet>[];
    final Object? decoded = _decode(raw);
    if (decoded is! List) return const <SavedFilterSet>[];
    return <SavedFilterSet>[
      for (final Object? entry in decoded)
        if (SavedFilterSet.fromJson(entry) case final SavedFilterSet set) set,
    ];
  }

  /// Adds or replaces [set] by name, and answers the new list.
  Future<List<SavedFilterSet>> save(SavedFilterSet set) async {
    final List<SavedFilterSet> current = await load();
    final List<SavedFilterSet> next = <SavedFilterSet>[
      for (final SavedFilterSet existing in current)
        if (existing.name != set.name) existing,
      set,
    ];
    return _write(
      next.length <= limit ? next : next.sublist(next.length - limit),
    );
  }

  /// Removes the set called [name], and answers the new list.
  Future<List<SavedFilterSet>> remove(String name) async {
    final List<SavedFilterSet> current = await load();
    return _write(<SavedFilterSet>[
      for (final SavedFilterSet existing in current)
        if (existing.name != name) existing,
    ]);
  }

  Future<List<SavedFilterSet>> _write(List<SavedFilterSet> sets) async {
    final SharedPreferences store = await SharedPreferences.getInstance();
    await store.setString(
      storageKey,
      jsonEncode(<Map<String, Object?>>[
        for (final SavedFilterSet set in sets) set.toJson(),
      ]),
    );
    return sets;
  }

  /// A stored value that is not readable JSON is treated as no sets at all,
  /// never as a crash on a screen a reviewer opened to search.
  static Object? _decode(String raw) {
    try {
      return jsonDecode(raw);
    } on FormatException {
      return null;
    }
  }
}
