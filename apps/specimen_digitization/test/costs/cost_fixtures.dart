// Scaffolding for the cost tests.
//
// The fake answers in the server's own wire shape and reads it through the
// real `CostReport.fromWire`, so a test of the screen is also a test of the
// parser, and a field the contract renames fails here rather than on a
// reviewer's screen. It keeps its limits the way the server does: setting one
// changes what the next read answers.

import 'dart:async';

import 'package:specimen_digitization/src/costs.dart';
import 'package:specimen_digitization/src/models.dart';

/// The day the suite treats as today (`flutter_test_config.dart`).
const String today = '2026-10-20';

/// The current UTC month, as the suite sees it.
const String thisMonth = '2026-10';

/// The organization the fixture collection belongs to.
const String costOrganization = 'org';

/// One amounts object, as a server that sends the known cost sends it: the
/// known part (`settled_micros`) is the cost without what is held, and
/// [estimated] is the part of it estimated after the call.
Json amounts(
  int cost, {
  int held = 0,
  int? list,
  int entries = 1,
  int estimated = 0,
}) => <String, dynamic>{
  'cost_micros': cost,
  'held_micros': held,
  'settled_micros': cost - held,
  'estimated_micros': estimated,
  'list_cost_micros': list ?? cost,
  'entries': entries,
};

/// The two figures a server that predates them does not send.
const List<String> knownCostFields = <String>[
  'settled_micros',
  'estimated_micros',
];

/// [wire] as a server that predates the known cost answers: every amounts
/// object in it without `settled_micros` and `estimated_micros`.
Json olderServerWire(Json wire) {
  void strip(Object? node) {
    if (node is Map) {
      knownCostFields.forEach(node.remove);
      node.values.forEach(strip);
    } else if (node is List) {
      node.forEach(strip);
    }
  }

  strip(wire);
  return wire;
}

/// A limit as the server sends one.
Json limitWire(int monthly, {required int spent}) => <String, dynamic>{
  'monthly_cap_micros': monthly,
  'month': thisMonth,
  'spent_micros': spent,
  'remaining_micros': monthly - spent,
};

/// The collection tree: Insects with Beetles under it, Plants alone, and a
/// collection whose parent the server did not list.
List<Json> collectionsWire() => <Json>[
  <String, dynamic>{
    'collection_id': 'col-insects',
    'name': 'Insects',
    'parent_id': null,
    'own': amounts(4200000, entries: 40),
    'total': amounts(7100000, held: 100000, list: 8000000, entries: 70),
    'cap': limitWire(10000000, spent: 7100000),
  },
  <String, dynamic>{
    'collection_id': 'col-beetles',
    'name': 'Beetles',
    'parent_id': 'col-insects',
    'own': amounts(2900000, entries: 30),
    'total': amounts(2900000, entries: 30),
    'cap': null,
  },
  <String, dynamic>{
    'collection_id': 'col-plants',
    'name': 'Plants',
    'parent_id': null,
    'own': amounts(5245678, entries: 90),
    'total': amounts(5245678, entries: 90),
    'cap': null,
  },
  <String, dynamic>{
    'collection_id': 'col-slides',
    'name': 'Microscopic slides',
    'parent_id': 'col-removed',
    'own': amounts(0, entries: 0),
    'total': amounts(0, entries: 0),
    'cap': null,
  },
];

/// One month of the report, with the stages the pipeline has.
Json monthWire(String month) => <String, dynamic>{
  'month': month,
  'totals': amounts(
    12345678,
    held: 500000,
    list: 15000000,
    entries: 1234,
    estimated: 2000000,
  ),
  'stages': <Json>[
    <String, dynamic>{'stage': 'first_pass', ...amounts(1800000, entries: 12)},
    <String, dynamic>{
      'stage': 'reading',
      ...amounts(6000000, held: 500000, entries: 400),
    },
    <String, dynamic>{
      'stage': 'label_finding',
      ...amounts(2100000, entries: 1),
    },
    <String, dynamic>{
      'stage': 'storage',
      ...amounts(900000, list: 1000000, entries: 700),
    },
    <String, dynamic>{'stage': 'database', ...amounts(345678, entries: 100)},
    // A stage with nothing in it is not listed on screen.
    <String, dynamic>{'stage': 'api', ...amounts(0, entries: 0)},
  ],
};

/// The model rows of a month.
List<Json> modelsWire(String month) => <Json>[
  <String, dynamic>{
    'month': month,
    'stage': 'reading',
    'provider': 'huggingface',
    'resource': 'handwriting-qwen',
    ...amounts(4000000, held: 500000, entries: 250),
  },
  <String, dynamic>{
    'month': month,
    'stage': 'reading',
    'provider': 'novita',
    'resource': 'printed-glm',
    ...amounts(2000000, entries: 150),
  },
  <String, dynamic>{
    'month': month,
    'stage': 'first_pass',
    'provider': 'huggingface',
    'resource': 'first-pass-glm',
    ...amounts(1800000, entries: 12),
  },
];

/// The full `GET .../costs` body for [month].
Json costWire(String month) => <String, dynamic>{
  'organization_id': costOrganization,
  'currency': 'USD',
  'from_month': month,
  'to_month': month,
  'updated_at': '2026-10-20T15:04:05Z',
  'totals': monthWire(month)['totals'],
  'organization_cap': limitWire(50000000, spent: 12345678),
  'collections': collectionsWire(),
  'months': <Json>[monthWire(month)],
  'models': modelsWire(month),
  'meter': <String, dynamic>{
    'allocated_through': '2026-10-19',
    'allocation_status': 'ok',
  },
  'caps_status': 'ok',
};

/// [wire] as the server answers when it could not read the limits: every limit
/// is null and `caps_status` says why.
Json capsUnavailableWire(Json wire) {
  wire['caps_status'] = 'unavailable';
  wire['organization_cap'] = null;
  for (final Object? row in wire['collections'] as List<Object?>) {
    (row! as Json)['cap'] = null;
  }
  return wire;
}

/// The id of a collection the server no longer lists.
const String retiredCollection = '3f9a2c1e-5b7d-4e0a-9c1d-0a1b2c3d4e5f';

/// [wire] with the rows of a collection the server no longer lists: they still
/// count, under a null name (`COST_METER.md`: "Rows of a collection not listed
/// still count, under a `null` name"), with no parent and no limit.
Json unlistedWire(Json wire) {
  (wire['collections'] as List<Object?>).add(<String, dynamic>{
    'collection_id': retiredCollection,
    'name': null,
    'parent_id': null,
    'own': amounts(1200000, entries: 4),
    'total': amounts(1200000, entries: 4),
    'cap': null,
  });
  return wire;
}

/// [wire] with a credit among its stages and its models: Google's free
/// allowance, recorded below zero, and a total that falls with it.
Json creditWire(Json wire) {
  final Json month = (wire['months'] as List<Object?>).first! as Json;
  (month['stages'] as List<Object?>).add(<String, dynamic>{
    'stage': 'worker',
    ...amounts(-300000, list: 0, entries: 3),
  });
  (wire['models'] as List<Object?>).add(<String, dynamic>{
    'month': month['month'],
    'stage': 'worker',
    'provider': 'google_cloud',
    'resource': 'specimen-sam',
    ...amounts(-300000, list: 0, entries: 3),
  });
  return wire;
}

/// The body for a month in which nothing was recorded.
Json emptyCostWire(String month) => <String, dynamic>{
  'organization_id': costOrganization,
  'currency': 'USD',
  'from_month': month,
  'to_month': month,
  'updated_at': '2026-10-20T15:04:05Z',
  'totals': amounts(0, entries: 0),
  'organization_cap': null,
  'collections': <Json>[
    <String, dynamic>{
      'collection_id': 'col-insects',
      'name': 'Insects',
      'parent_id': null,
      'own': amounts(0, entries: 0),
      'total': amounts(0, entries: 0),
      'cap': null,
    },
  ],
  'months': <Json>[],
  'models': <Json>[],
  'meter': null,
  'caps_status': 'ok',
};

/// A repository that answers in the wire shape and remembers what it was
/// asked.
class FakeCostRepository implements CostRepository {
  FakeCostRepository({Json Function(String month)? wire}) : _wire = wire;

  final Json Function(String month)? _wire;

  /// Every read, in order.
  final List<({String organization, String from, String to})> reads =
      <({String organization, String from, String to})>[];

  /// Every update request, in order.
  final List<String> refreshes = <String>[];

  /// Every limit change, in order.
  final List<({String organization, String? collection, int? micros})> limits =
      <({String organization, String? collection, int? micros})>[];

  /// Months that answer with nothing recorded.
  final Set<String> emptyMonths = <String>{};

  /// Set to fail every read with this.
  ApiFailure? readFailure;

  /// Set to fail the next read only.
  ApiFailure? readFailureOnce;

  /// Set to fail every update request with this.
  ApiFailure? refreshFailure;

  /// Holds the next update request until completed, so a test can look at the
  /// button while the request is out.
  Completer<void>? refreshHold;

  /// Set to fail every limit change with this.
  ApiFailure? limitFailure;

  /// What an update request answers.
  bool refreshStarts = true;

  /// A body to answer with instead of the fixture, for edge cases.
  Json Function(String month)? customWire;

  /// Holds the next read until completed, so a test can look at the wait.
  Completer<void>? hold;

  /// Limits changed since the start, applied to the fixture the way the
  /// server applies them.
  final Map<String?, int?> _changed = <String?, int?>{};

  Json _body(String month) {
    final Json Function(String)? custom = customWire ?? _wire;
    final Json body = custom != null
        ? custom(month)
        : emptyMonths.contains(month)
        ? emptyCostWire(month)
        : costWire(month);
    _changed.forEach((String? collection, int? micros) {
      Json? limit(int spent) =>
          micros == null ? null : limitWire(micros, spent: spent);
      if (collection == null) {
        body['organization_cap'] = limit(12345678);
        return;
      }
      for (final Object? row in body['collections'] as List<Object?>) {
        final Json collectionRow = row! as Json;
        if (collectionRow['collection_id'] == collection) {
          collectionRow['cap'] = limit(
            (collectionRow['total'] as Json)['cost_micros'] as int,
          );
        }
      }
    });
    return body;
  }

  @override
  Future<CostReport> costs(
    String organizationId, {
    required String from,
    required String to,
  }) async {
    reads.add((organization: organizationId, from: from, to: to));
    final Completer<void>? waiting = hold;
    if (waiting != null) {
      hold = null;
      await waiting.future;
    }
    final ApiFailure? once = readFailureOnce;
    if (once != null) {
      readFailureOnce = null;
      throw once;
    }
    final ApiFailure? failure = readFailure;
    if (failure != null) throw failure;
    return CostReport.fromWire(_body(from));
  }

  @override
  Future<bool> refreshCosts(String organizationId) async {
    refreshes.add(organizationId);
    final Completer<void>? waiting = refreshHold;
    if (waiting != null) {
      refreshHold = null;
      await waiting.future;
    }
    final ApiFailure? failure = refreshFailure;
    if (failure != null) throw failure;
    return refreshStarts;
  }

  @override
  Future<void> setCostLimit(
    String organizationId, {
    String? collectionId,
    int? micros,
  }) async {
    limits.add((
      organization: organizationId,
      collection: collectionId,
      micros: micros,
    ));
    final ApiFailure? failure = limitFailure;
    if (failure != null) throw failure;
    _changed[collectionId] = micros;
  }
}
