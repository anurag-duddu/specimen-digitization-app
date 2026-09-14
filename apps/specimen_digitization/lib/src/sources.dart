/// Registered sources, their inventory snapshots, and the rows a reviewer
/// browses.
///
/// The wire shapes here are the ones recorded in
/// `docs/execution/CONTRACTS.md`, section "Source registry, inventory and
/// server-side import". They are read, never invented: a source is
/// configuration the client can list but cannot create, an inventory is a
/// point-in-time snapshot the client pages through, and a row's state is
/// resolved by the server rather than guessed here.
library;

import 'models.dart';

/// What a reviewer may do with one object in a source listing.
///
/// The server resolves this per row, because only the server can answer
/// "is this already in the queue" (a checksum lookup) and "may this source
/// admit these bytes" (the registered media-type allowlist). A client that
/// guessed either would offer a duplicate or refuse an importable object.
enum SourceObjectState {
  /// Importable: not in the queue, and a media type this source admits.
  available('available'),

  /// Already in the queue, as the specimen named by [SourceObject.specimenId].
  imported('imported'),

  /// The bytes are not media this source admits, so importing would fail.
  unsupportedMediaType('unsupported_media_type');

  const SourceObjectState(this.wire);

  /// The value the server sends.
  final String wire;

  /// The state for a wire value, treating anything unrecognised as
  /// unimportable.
  ///
  /// Clients ignore additive optional fields, but an unknown state must never
  /// enable an action (common wire rules, and the north star's honesty bar).
  /// An unrecognised row is therefore shown and not offered.
  static SourceObjectState of(Object? value) => values.firstWhere(
    (SourceObjectState state) => state.wire == value,
    orElse: () => SourceObjectState.unsupportedMediaType,
  );
}

/// One object in a source inventory snapshot.
class SourceObject {
  const SourceObject(this.data);

  final Json data;

  /// The object's name under the source prefix. Unique within a snapshot, so
  /// it is the selection identity.
  String get objectName => textOf(data['object_name'], '');

  /// The storage generation the snapshot recorded. An import declares this
  /// back, and the server refuses the object if it no longer matches.
  String get generation => textOf(data['generation'], '');

  String get bucket => textOf(data['bucket'], '');

  String get sha256 => textOf(data['sha256'], '');

  String get mediaType => textOf(data['media_type'], '');

  /// The object's size, or null when the server did not say.
  ///
  /// Null and zero are different facts, and absence renders as words rather
  /// than as a value (writing guidelines, rule 14).
  int? get sizeBytes => (data['size_bytes'] as num?)?.toInt();

  SourceObjectState get state => SourceObjectState.of(data['state']);

  /// The specimen this object was imported as, when it is already in the
  /// queue.
  String? get specimenId =>
      data['specimen_id'] is String && (data['specimen_id'] as String).isNotEmpty
      ? data['specimen_id'] as String
      : null;

  /// The last segment of the object name, which is what a reviewer reads.
  String get displayName {
    final String name = objectName;
    final int cut = name.lastIndexOf('/');
    return cut < 0 || cut == name.length - 1 ? name : name.substring(cut + 1);
  }

  /// What an import request sends back for this object.
  Json get selection => <String, dynamic>{
    'object_name': objectName,
    'generation': generation,
  };
}

/// The header of a source's current inventory snapshot.
///
/// A source that has never been captured has no header, which is an honest
/// absence and not an empty snapshot.
class SourceInventory {
  const SourceInventory(this.data);

  final Json data;

  String get id => textOf(data['inventory_id'], '');

  /// How many objects the snapshot holds, across every filter.
  int get objectCount => (data['object_count'] as num?)?.toInt() ?? 0;

  /// When the snapshot was taken, or null when the server did not say.
  DateTime? get capturedAt {
    final Object? raw = data['captured_at'];
    return raw is String && raw.isNotEmpty ? DateTime.tryParse(raw) : null;
  }
}

/// One registered source: a pointer at a storage prefix a collection may
/// ingest from.
class RegisteredSource {
  const RegisteredSource(this.data);

  final Json data;

  String get id => textOf(data['source_id'], '');

  String get collectionId => textOf(data['collection_id'], '');

  String get bucket => textOf(data['bucket'], '');

  String get prefix => textOf(data['prefix'], '');

  /// The media types this source admits. Anything else is refused when the
  /// source is registered, not discovered at import.
  List<String> get mediaTypes =>
      (data['media_types'] as List?)?.map((Object? e) => '$e').toList() ??
      const <String>[];

  /// The current snapshot, or null when none has been captured.
  SourceInventory? get inventory {
    final Object? raw = data['inventory'];
    return raw is Map ? SourceInventory(Json.from(raw)) : null;
  }

  /// What a reviewer reads in a source picker: the prefix, which is the part
  /// that distinguishes two sources on one bucket.
  String get displayName {
    final String value = prefix;
    return value.endsWith('/') && value.length > 1
        ? value.substring(0, value.length - 1)
        : value;
  }
}

/// One page of an inventory snapshot, with the snapshot identity that page
/// belongs to.
///
/// [inventoryId] is carried so a screen can tell a new snapshot from a new
/// page. A cursor issued against one snapshot is refused once another is
/// captured, because the rows it addresses are no longer the rows the reviewer
/// was choosing from.
class SourceObjectPage {
  const SourceObjectPage(
    this.items, {
    required this.inventoryId,
    this.nextCursor,
    this.capturedAt,
    this.objectCount = 0,
    this.matchingCount,
  });

  final List<SourceObject> items;
  final String inventoryId;
  final String? nextCursor;
  final DateTime? capturedAt;

  /// How many objects the whole snapshot holds, before any filter.
  final int objectCount;

  /// How many rows the active filter set covers, or null when the server did
  /// not count.
  ///
  /// Null is not zero. The server counts exactly or not at all: `media_type`
  /// is on the row and free to scan, while `imported` resolves through a
  /// checksum lookup per object and is refused rather than estimated. A screen
  /// may only offer a select all over rows it has not loaded when this is a
  /// number, because that is the only case where the count on the confirmation
  /// is one the server actually made.
  final int? matchingCount;
}

/// What one object's import did.
class SourceImportOutcome {
  const SourceImportOutcome(this.data);

  final Json data;

  String get objectName => textOf(data['object_name'], '');

  /// `imported`, `duplicate`, `unsupported_media_type` or `not_in_source`.
  String get state => textOf(data['state'], '');

  String? get specimenId =>
      data['specimen_id'] is String && (data['specimen_id'] as String).isNotEmpty
      ? data['specimen_id'] as String
      : null;
}

/// The most objects one import request may name.
///
/// The server bounds this because it reads every object whole, so a larger
/// selection is sent as several requests and the screen reports progress
/// across them. Mirrors `MAX_IMPORT_OBJECTS` in `source_import.py`.
const int sourceImportBatchSize = 50;

/// How many rows one listing request asks for.
const int sourcePageSize = 50;

/// The result of importing a selection into a batch.
class SourceImportResult {
  const SourceImportResult(this.data);

  final Json data;

  String get batchId => textOf(data['batch_id'], '');

  /// How many objects the request named.
  int get requested => (data['requested'] as num?)?.toInt() ?? 0;

  /// How many became new specimens.
  int get imported => (data['imported'] as num?)?.toInt() ?? 0;

  /// How many were already in the queue. Re-importing is a no-op that returns
  /// the existing specimen, so a selection run twice reports every row here.
  int get duplicates => (data['duplicates'] as num?)?.toInt() ?? 0;

  List<SourceImportOutcome> get items =>
      objects(data['items']).map(SourceImportOutcome.new).toList();

  /// How many the server could not take: neither new nor already present.
  int get refused => (requested - imported - duplicates).clamp(0, requested);
}

/// What a screen needs from the server to browse a source and import from it.
///
/// Separate from `SpecimenRepository` on purpose. The sources screen needs
/// these three calls and none of the specimen surface, and a fake in a test
/// should have to implement what it uses rather than the whole client API.
abstract interface class SourceRepository {
  /// The sources registered to this collection. Configuration, so the list is
  /// short and unpaged, and a runtime configured with none answers with none.
  Future<List<RegisteredSource>> sources(CollectionScope scope);

  /// One page of a source's current inventory snapshot.
  ///
  /// [filters] takes `imported` and `media_type`. A cursor is bound to the
  /// snapshot it was issued against and is refused once another is captured.
  Future<SourceObjectPage> sourceObjectPage(
    CollectionScope scope,
    String sourceId, {
    Map<String, String> filters,
    String? cursor,
  });

  /// Imports up to [sourceImportBatchSize] objects into a new batch.
  ///
  /// Creates specimens. Starts no processing, in any mode: importing a
  /// selection and running one are separate decisions.
  Future<SourceImportResult> importFromSource(
    CollectionScope scope,
    String sourceId,
    List<SourceObject> selection,
    String key, {
    bool sensitive,
  });
}
