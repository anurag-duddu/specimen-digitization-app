/// What an organization's work costs, as the server's cost meter reports it.
///
/// The client reads one report per month and shows it; it adds nothing up and
/// works nothing out. Every amount is an integer count of micro-dollars (see
/// `money.dart`), and a figure the server did not send is absent rather than
/// zero.
///
/// The screen needs three calls and none of the specimen surface, so they are
/// an interface of their own, exactly as `SourceRepository` is, and a fake in
/// a test implements what the screen uses.
library;

import 'package:flutter/foundation.dart';

import 'models.dart';

/// The role that may read the costs and change a limit.
const String costAdminRole = 'admin';

/// The currency every amount is counted in.
const String costCurrency = 'USD';

// ---------------------------------------------------------------------------
// The clock.
// ---------------------------------------------------------------------------

/// Reads the instant "this month" is taken from, in a debug build only.
///
/// The month list is the current UTC month and the eleven before it, so a
/// screen drawn on the first of a month differs from one drawn on the last.
/// The test suite pins it (`flutter_test_config.dart`), the way it pins the
/// zone, so no golden depends on the day it is drawn. A release build ignores
/// the override.
@visibleForTesting
DateTime Function()? debugCostClock;

/// The current instant, in UTC.
DateTime costNow() =>
    ((kDebugMode ? debugCostClock : null) ?? DateTime.now)().toUtc();

const List<String> _monthNames = <String>[
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

const List<String> _shortMonthNames = <String>[
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/// How many months the month list offers: the current one and eleven before.
const int costMonthCount = 12;

/// [instant]'s month, spelled the way the API spells one: `2026-10`.
String costMonthKey(DateTime instant) {
  final DateTime utc = instant.toUtc();
  return '${utc.year.toString().padLeft(4, '0')}-'
      '${utc.month.toString().padLeft(2, '0')}';
}

/// The months a reviewer may look at, newest first, counted in UTC.
List<String> costMonthChoices(DateTime now) {
  final DateTime utc = now.toUtc();
  return <String>[
    for (int back = 0; back < costMonthCount; back++)
      costMonthKey(DateTime.utc(utc.year, utc.month - back)),
  ];
}

final RegExp _monthPattern = RegExp(r'^(\d{4})-(\d{2})$');
final RegExp _dayPattern = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$');

/// A month as a reviewer reads it: `October 2026`. A key this cannot read is
/// returned as it came, so an unexpected value is still on screen.
String costMonthLabel(String key) {
  final RegExpMatch? match = _monthPattern.firstMatch(key);
  if (match == null) return key;
  final int month = int.parse(match.group(2)!);
  if (month < 1 || month > _monthNames.length) return key;
  return '${_monthNames[month - 1]} ${int.parse(match.group(1)!)}';
}

/// A day as the citable form spells it: `19 Oct 2026`.
///
/// Built from the date's own parts. A date with no time carries no zone, and
/// converting it to the reviewer's clock would move it a day for anyone west
/// of UTC.
String costDayLabel(String day) {
  final RegExpMatch? match = _dayPattern.firstMatch(day);
  if (match == null) return day;
  final int month = int.parse(match.group(2)!);
  if (month < 1 || month > _shortMonthNames.length) return day;
  return '${int.parse(match.group(3)!)} ${_shortMonthNames[month - 1]} '
      '${int.parse(match.group(1)!)}';
}

// ---------------------------------------------------------------------------
// Reading the wire.
// ---------------------------------------------------------------------------

int _micros(Object? value) => value is num ? value.toInt() : 0;

/// A figure the server may not send: null when it did not, never zero.
int? _optionalMicros(Object? value) => value is num ? value.toInt() : null;

String? _text(Object? value) =>
    value is String && value.isNotEmpty ? value : null;

Json? _object(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : null;

// ---------------------------------------------------------------------------
// The report.
// ---------------------------------------------------------------------------

/// The figures the meter reports for any slice of the work.
@immutable
class CostAmounts {
  const CostAmounts({
    required this.costMicros,
    required this.heldMicros,
    required this.listCostMicros,
    required this.entries,
    this.settledMicros,
    this.estimatedMicros,
  });

  /// A slice with nothing recorded in it.
  static const CostAmounts none = CostAmounts(
    costMicros: 0,
    heldMicros: 0,
    listCostMicros: 0,
    entries: 0,
  );

  /// Reads one `{cost_micros, held_micros, settled_micros, estimated_micros,
  /// list_cost_micros, entries}` object. A missing object is a slice with
  /// nothing recorded.
  factory CostAmounts.fromWire(Object? wire) {
    final Json? json = _object(wire);
    if (json == null) return none;
    return CostAmounts(
      costMicros: _micros(json['cost_micros']),
      heldMicros: _micros(json['held_micros']),
      listCostMicros: _micros(json['list_cost_micros']),
      entries: _micros(json['entries']),
      settledMicros: _optionalMicros(json['settled_micros']),
      estimatedMicros: _optionalMicros(json['estimated_micros']),
    );
  }

  /// What the meter counts, after Google's free allowance. Includes
  /// [heldMicros], so it is not what the work is known to have cost: that is
  /// [settledMicros].
  ///
  /// Every sum is signed. Google's free allowance is recorded as a negative
  /// row, and a residual can come out below the charges it is measured
  /// against, so a sum can be below zero: a credit.
  final int costMicros;

  /// The part of [costMicros] held for calls whose cost is unknown, counted at
  /// the most each call could have cost.
  final int heldMicros;

  /// What the meter counts as known: [costMicros] without [heldMicros], each
  /// call measured, billed, or estimated from evidence after it was made.
  ///
  /// The server's own figure, read as sent and never worked out here. Null
  /// when the server did not send it (one that predates the figure), and then
  /// nothing on screen may claim to know it.
  final int? settledMicros;

  /// The part of [settledMicros] estimated after the call: a held call valued
  /// again from its recorded usage, or from the provider's bill for that day
  /// and model. Never more than [settledMicros]. Null when the server did not
  /// send it.
  final int? estimatedMicros;

  /// The cost before Google's free allowance.
  final int listCostMicros;

  /// How many metered rows the figures add up. Never below zero.
  final int entries;

  /// The amount a row shows: [settledMicros] where the server sent it, and
  /// [costMicros], held included, where it did not. Rows are ordered by it,
  /// so "largest first" holds for the figure on screen.
  int get shownMicros => settledMicros ?? costMicros;

  /// True when the meter recorded anything here at all, a credit included.
  /// Nothing recorded is not the same as a recorded nothing, and the screen
  /// says which.
  bool get hasCosts =>
      entries > 0 ||
      costMicros != 0 ||
      heldMicros != 0 ||
      listCostMicros != 0 ||
      (settledMicros ?? 0) != 0 ||
      (estimatedMicros ?? 0) != 0;
}

/// A monthly limit and how much of it the current month has used.
@immutable
class CostLimit {
  const CostLimit({
    required this.monthlyMicros,
    required this.month,
    required this.spentMicros,
    required this.remainingMicros,
  });

  /// Reads one limit object, or null for no limit (or one that cannot be
  /// read, which is shown as no limit rather than as a guessed figure).
  static CostLimit? fromWire(Object? wire) {
    final Json? json = _object(wire);
    if (json == null) return null;
    final Object? monthly = json['monthly_cap_micros'];
    if (monthly is! num) return null;
    final int spent = _micros(json['spent_micros']);
    final Object? remaining = json['remaining_micros'];
    return CostLimit(
      monthlyMicros: monthly.toInt(),
      month: _text(json['month']) ?? '',
      spentMicros: spent,
      remainingMicros: remaining is num
          ? remaining.toInt()
          : monthly.toInt() - spent,
    );
  }

  /// The limit, in micro-dollars a month.
  final int monthlyMicros;

  /// The month [spentMicros] and [remainingMicros] are for: the server's
  /// current UTC month, whichever month the report asked about.
  final String month;

  /// What that month has counted against the limit: the known costs and what
  /// is held for calls whose cost is unknown, so not all of it is spent.
  final int spentMicros;

  /// What that month has left. Zero or less once the limit is reached.
  final int remainingMicros;

  /// True once nothing is left.
  bool get reached => remainingMicros <= 0;
}

/// One collection in the organization's tree.
@immutable
class CostCollection {
  const CostCollection({
    required this.id,
    required this.name,
    required this.parentId,
    required this.own,
    required this.total,
    required this.limit,
  });

  /// Reads one collection object, or null when it names no collection.
  static CostCollection? fromWire(Object? wire) {
    final Json? json = _object(wire);
    final String? id = json == null ? null : _text(json['collection_id']);
    if (json == null || id == null) return null;
    final CostAmounts own = CostAmounts.fromWire(json['own']);
    return CostCollection(
      id: id,
      name: _text(json['name']),
      parentId: _text(json['parent_id']),
      own: own,
      total: json['total'] == null ? own : CostAmounts.fromWire(json['total']),
      limit: CostLimit.fromWire(json['cap']),
    );
  }

  final String id;

  /// The collection's name, or null when the server no longer lists it: rows
  /// of a collection that is not one of the organization's collections still
  /// count, under a null name. The id is not a name and is never shown.
  final String? name;

  /// True when the server names this collection. A collection it does not
  /// name cannot be given a limit: the service refuses an id that is not one
  /// of the organization's collections.
  bool get listed => name != null;

  /// The collection this one sits under, or null for a top level one.
  final String? parentId;

  /// This collection alone.
  final CostAmounts own;

  /// This collection and everything under it.
  final CostAmounts total;

  /// Its monthly limit, or null for none.
  final CostLimit? limit;
}

/// One collection placed in reading order.
typedef CostCollectionRow = ({
  CostCollection collection,
  int depth,
  bool hasChildren,
});

/// [collections] in reading order: each collection, then those under it,
/// indented by [CostCollectionRow.depth].
///
/// The server's order is kept among siblings. A collection whose parent is not
/// in the list is shown at the top level rather than dropped, and so is one
/// caught in a cycle, so no collection the server reported can go missing.
List<CostCollectionRow> costCollectionRows(List<CostCollection> collections) {
  final Map<String, CostCollection> byId = <String, CostCollection>{
    for (final CostCollection collection in collections)
      collection.id: collection,
  };
  final Map<String, List<CostCollection>> children =
      <String, List<CostCollection>>{};
  final List<CostCollection> roots = <CostCollection>[];
  for (final CostCollection collection in collections) {
    final String? parent = collection.parentId;
    if (parent == null ||
        parent == collection.id ||
        !byId.containsKey(parent)) {
      roots.add(collection);
    } else {
      (children[parent] ??= <CostCollection>[]).add(collection);
    }
  }
  final List<CostCollectionRow> rows = <CostCollectionRow>[];
  final Set<String> placed = <String>{};
  void place(CostCollection collection, int depth) {
    if (!placed.add(collection.id)) return;
    final List<CostCollection> below =
        children[collection.id] ?? const <CostCollection>[];
    rows.add((
      collection: collection,
      depth: depth,
      hasChildren: below.isNotEmpty,
    ));
    for (final CostCollection child in below) {
      place(child, depth + 1);
    }
  }

  for (final CostCollection root in roots) {
    place(root, 0);
  }
  // Whatever a cycle kept out of the walk above.
  for (final CostCollection collection in collections) {
    place(collection, 0);
  }
  return rows;
}

/// One pipeline stage's share of a month.
@immutable
class CostStage {
  const CostStage({required this.stage, required this.amounts});

  static CostStage? fromWire(Object? wire) {
    final Json? json = _object(wire);
    final String? stage = json == null ? null : _text(json['stage']);
    if (json == null || stage == null) return null;
    return CostStage(stage: stage, amounts: CostAmounts.fromWire(json));
  }

  /// The server's stage key. Not every key is known to this client, so it is
  /// kept as sent and named by `costStageLabel`.
  final String stage;
  final CostAmounts amounts;
}

/// One month of the report.
@immutable
class CostMonth {
  const CostMonth({
    required this.month,
    required this.totals,
    required this.stages,
  });

  static CostMonth? fromWire(Object? wire) {
    final Json? json = _object(wire);
    final String? month = json == null ? null : _text(json['month']);
    if (json == null || month == null) return null;
    return CostMonth(
      month: month,
      totals: CostAmounts.fromWire(json['totals']),
      stages: <CostStage>[
        for (final Json stage in objects(json['stages']))
          ?CostStage.fromWire(stage),
      ],
    );
  }

  /// `2026-10`.
  final String month;
  final CostAmounts totals;
  final List<CostStage> stages;

  /// The stages that recorded anything, largest first by the amount each row
  /// shows ([CostAmounts.shownMicros]). A credit is the smallest cost there
  /// is, so it comes last. Ties read in stage order so the list is the same
  /// every time it is drawn.
  List<CostStage> get stagesByCost {
    final List<CostStage> shown = stages
        .where((CostStage stage) => stage.amounts.hasCosts)
        .toList();
    shown.sort((CostStage a, CostStage b) {
      final int byCost = b.amounts.shownMicros.compareTo(a.amounts.shownMicros);
      return byCost != 0 ? byCost : a.stage.compareTo(b.stage);
    });
    return shown;
  }
}

/// One model or service's share of a month at one stage.
@immutable
class CostModelRow {
  const CostModelRow({
    required this.month,
    required this.stage,
    required this.provider,
    required this.resource,
    required this.amounts,
  });

  static CostModelRow? fromWire(Object? wire) {
    final Json? json = _object(wire);
    final String? resource = json == null ? null : _text(json['resource']);
    if (json == null || resource == null) return null;
    return CostModelRow(
      month: _text(json['month']) ?? '',
      stage: _text(json['stage']) ?? '',
      provider: _text(json['provider']) ?? '',
      resource: resource,
      amounts: CostAmounts.fromWire(json),
    );
  }

  final String month;
  final String stage;
  final String provider;

  /// The model or service, as the server names it.
  final String resource;
  final CostAmounts amounts;
}

/// The server's `snake_case` word for an enum value declared in `camelCase`.
///
/// The server's words are read by the name each is declared with, so the wire
/// word and the Dart name are one spelling and no wire word is written twice.
String _wireWord(Enum value) => value.name.replaceAllMapped(
  RegExp('[A-Z]'),
  (Match match) => '_${match.group(0)!.toLowerCase()}',
);

/// The states of the meter's allocation of shared Google costs, as the server
/// sends them: [ok], `behind` and `never_run`.
enum CostAllocation {
  /// The shared costs are counted through the billing day the meter names.
  ok,

  /// The shared costs are more than two complete billing days behind.
  behind,

  /// No shared cost has been counted: the organization has no allocation row.
  neverRun;

  /// The state a server word names, or null for one this client has not met.
  static CostAllocation? fromWire(String wire) {
    for (final CostAllocation state in values) {
      if (_wireWord(state) == wire) return state;
    }
    return null;
  }
}

/// Whether the report could read the monthly limits: `ok`, or `unavailable`
/// when it could not. Then every limit in the report is null, and null does
/// not mean no limit is set.
enum CostCapsStatus {
  /// The limits were read. A null limit is no limit.
  ok,

  /// The limits could not be read.
  unavailable;

  /// The state a server word names, or null for none this client knows.
  static CostCapsStatus? fromWire(String? wire) {
    for (final CostCapsStatus state in values) {
      if (_wireWord(state) == wire) return state;
    }
    return null;
  }
}

/// How far the meter has counted, and whether that count is complete.
@immutable
class CostMeter {
  const CostMeter({required this.allocatedThrough, required this.status});

  static CostMeter? fromWire(Object? wire) {
    final Json? json = _object(wire);
    final String? status = json == null
        ? null
        : _text(json['allocation_status']);
    if (json == null || status == null) return null;
    return CostMeter(
      allocatedThrough: _text(json['allocated_through']),
      status: status,
    );
  }

  /// The last day counted, `2026-10-19`, or null when none has been.
  final String? allocatedThrough;

  /// The status as the server sent it, kept so one this client has not met can
  /// still be named.
  final String status;

  /// The status as a state this client knows, or null for one it does not.
  CostAllocation? get allocation => CostAllocation.fromWire(status);
}

/// The meter's answer for one organization and one range of months.
@immutable
class CostReport {
  const CostReport({
    required this.organizationId,
    required this.fromMonth,
    required this.toMonth,
    required this.updatedAt,
    required this.totals,
    required this.organizationLimit,
    required this.collections,
    required this.months,
    required this.models,
    required this.meter,
    required this.capsUnavailable,
  });

  /// Reads the `GET .../costs` body.
  ///
  /// Throws an [ApiFailure] for an answer that is not a report or is counted
  /// in a currency this client does not show, rather than showing figures in
  /// the wrong unit.
  factory CostReport.fromWire(Json wire) {
    final String? currency = _text(wire['currency']);
    if (currency != null && currency != costCurrency) {
      throw const ApiFailure(
        'The costs are counted in a currency this screen cannot show.',
        code: 'unsupported_currency',
      );
    }
    final String? organization = _text(wire['organization_id']);
    if (organization == null) {
      throw const ApiFailure(
        'The service returned costs that could not be read. Retry in a moment.',
        code: 'invalid_response',
      );
    }
    final String? updated = _text(wire['updated_at']);
    return CostReport(
      organizationId: organization,
      fromMonth: _text(wire['from_month']) ?? '',
      toMonth: _text(wire['to_month']) ?? '',
      updatedAt: updated == null ? null : DateTime.tryParse(updated)?.toUtc(),
      totals: CostAmounts.fromWire(wire['totals']),
      organizationLimit: CostLimit.fromWire(wire['organization_cap']),
      collections: <CostCollection>[
        for (final Json collection in objects(wire['collections']))
          ?CostCollection.fromWire(collection),
      ],
      months: <CostMonth>[
        for (final Json month in objects(wire['months']))
          ?CostMonth.fromWire(month),
      ],
      models: <CostModelRow>[
        for (final Json model in objects(wire['models']))
          ?CostModelRow.fromWire(model),
      ],
      meter: CostMeter.fromWire(wire['meter']),
      capsUnavailable:
          CostCapsStatus.fromWire(_text(wire['caps_status'])) ==
          CostCapsStatus.unavailable,
    );
  }

  final String organizationId;
  final String fromMonth;
  final String toMonth;

  /// When the figures were last brought up to date, or null when the server
  /// did not say.
  final DateTime? updatedAt;

  /// The whole range, all collections.
  final CostAmounts totals;

  /// The organization's own monthly limit, or null for none.
  final CostLimit? organizationLimit;
  final List<CostCollection> collections;
  final List<CostMonth> months;
  final List<CostModelRow> models;

  /// How far shared costs are counted, or null when the server did not say.
  final CostMeter? meter;

  /// True when the server says it could not read the limits
  /// (`caps_status` is `unavailable`). Every limit in the report is then null,
  /// and the screen must not say none is set. A report that does not carry the
  /// word, or carries one this client has not met, is read as having its
  /// limits.
  final bool capsUnavailable;

  /// [month] of the report, or null when the server sent no such month.
  CostMonth? monthOf(String month) {
    for (final CostMonth candidate in months) {
      if (candidate.month == month) return candidate;
    }
    return null;
  }

  /// The model rows for [month], largest first by the amount each row shows
  /// ([CostAmounts.shownMicros]), a credit last.
  List<CostModelRow> modelsOf(String month) {
    final List<CostModelRow> shown = models
        .where((CostModelRow row) => row.month == month && row.amounts.hasCosts)
        .toList();
    shown.sort((CostModelRow a, CostModelRow b) {
      final int byCost = b.amounts.shownMicros.compareTo(a.amounts.shownMicros);
      if (byCost != 0) return byCost;
      final int byStage = a.stage.compareTo(b.stage);
      return byStage != 0 ? byStage : a.resource.compareTo(b.resource);
    });
    return shown;
  }
}

// ---------------------------------------------------------------------------
// The seam.
// ---------------------------------------------------------------------------

/// What a screen needs from the server to show costs and manage limits.
///
/// Separate from `SpecimenRepository` on purpose: the screen needs these
/// three calls and none of the specimen surface. All three are for an
/// administrator. The API repository records any 401 or 403 as a failure of
/// the session's access, not of the one call, so no caller makes one for
/// anybody who is not an administrator.
abstract interface class CostRepository {
  /// The costs of [organizationId] from the month [from] to the month [to],
  /// both `YYYY-MM`.
  Future<CostReport> costs(
    String organizationId, {
    required String from,
    required String to,
  });

  /// Asks the server to bring the figures up to date. True when an update
  /// started. The figures themselves change within minutes, not in this call.
  Future<bool> refreshCosts(String organizationId);

  /// Sets the monthly limit of one collection, or of the organization when
  /// [collectionId] is null. A null [micros] removes the limit.
  Future<void> setCostLimit(
    String organizationId, {
    String? collectionId,
    int? micros,
  });
}

/// The cost surface of [repository], or null when this build has none.
///
/// A build whose repository does not serve costs is a build without them,
/// not a failure, so the caller shows an absence rather than an error.
CostRepository? costsIn(Object? repository) =>
    repository is CostRepository ? repository : null;

/// The organization whose costs this account may open, or null for none.
///
/// The organization of the open collection, and only when the account is an
/// administrator of at least one collection in it. This is the one test of
/// who may ask: the entry, the route and the request all use it, because a
/// refused request cannot be taken back (the API repository keeps the first
/// 401 or 403 as the session's access failure).
String? costOrganizationOf(
  Iterable<CollectionScope> scopes,
  CollectionScope? open,
) {
  if (open == null) return null;
  final bool admin = scopes.any(
    (CollectionScope scope) =>
        scope.organizationId == open.organizationId &&
        scope.permissions.contains(costAdminRole),
  );
  return admin ? open.organizationId : null;
}
