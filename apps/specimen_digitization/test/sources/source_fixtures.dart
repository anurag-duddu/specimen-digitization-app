// Scaffolding for the source browse tests.
//
// The fake pages exactly as the server does: an opaque cursor over one
// immutable snapshot, a `matching_count` that is a number or absent, and an
// import bounded at the same size the server bounds it at. A fake that paged
// more generously than the real thing would hide the bug the screen exists to
// avoid.

import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/sources.dart';

/// One inventory row.
SourceObject object(
  String name, {
  String state = 'available',
  String generation = '1',
  String mediaType = 'image/jpeg',
  int? sizeBytes = 312000,
  String? specimenId,
}) => SourceObject(<String, dynamic>{
  'bucket': 'specimen-digitization.firebasestorage.app',
  'object_name': 'microscopic-slides/$name',
  'generation': generation,
  'sha256': 'sha-$name',
  'size_bytes': sizeBytes,
  'media_type': mediaType,
  'state': state,
  'specimen_id': specimenId,
});

/// The ten pilot specimens, as they appear in a source listing.
List<SourceObject> pilotTen() => <SourceObject>[
  for (int ordinal = 1; ordinal <= 10; ordinal++)
    object('subject_${105526320 + ordinal}.jpg'),
];

/// [count] rows, named in snapshot order.
List<SourceObject> manyObjects(int count) => <SourceObject>[
  for (int index = 0; index < count; index++)
    object('slide_${index.toString().padLeft(4, '0')}.jpg'),
];

/// One registered source.
RegisteredSource source({
  String id = 'src-1',
  String collectionId = 'col-1',
  String prefix = 'microscopic-slides/',
  int? objectCount = 10,
}) => RegisteredSource(<String, dynamic>{
  'source_id': id,
  'collection_id': collectionId,
  'bucket': 'specimen-digitization.firebasestorage.app',
  'prefix': prefix,
  'media_types': <String>['image/jpeg', 'image/png', 'image/tiff'],
  'registered_by': 'administrator',
  'registered_at': '2026-09-14T10:22:00Z',
  'inventory': objectCount == null
      ? null
      : <String, dynamic>{
          'inventory_id': 'inv-1',
          'object_count': objectCount,
          'captured_at': '2026-09-14T10:22:00Z',
        },
});

/// The scope every test runs in.
const CollectionScope testScope = CollectionScope(
  organizationId: 'org-1',
  collectionId: 'col-1',
  name: 'Microscopic slides',
);

/// A source repository that pages one snapshot and imports from it.
class FakeSourceRepository implements SourceRepository {
  FakeSourceRepository({
    List<SourceObject>? objects,
    this.pageSize = 4,
    this.matchingCount,
    this.countsMatching = true,
    this.inventoryId = 'inv-1',
    this.sources0,
  }) : rows = objects ?? pilotTen();

  /// The snapshot, in order.
  List<SourceObject> rows;

  /// How many rows one page answers.
  final int pageSize;

  /// Overrides the count the listing reports, when set.
  final int? matchingCount;

  /// False for the filter the server refuses to count, where the listing
  /// reports no number at all.
  final bool countsMatching;

  /// The snapshot's identity. Change it to simulate a recapture.
  String inventoryId;

  /// The registered sources, or null for one default source.
  final List<RegisteredSource>? sources0;

  /// Every listing request, for asserting how many pages a select all cost.
  final List<String?> listCursors = <String?>[];

  /// Every filter set a listing was asked for.
  final List<Map<String, String>> listFilters = <Map<String, String>>[];

  /// Every import request, as the objects it named.
  final List<List<String>> imports = <List<String>>[];

  /// Every idempotency key an import carried.
  final List<String> importKeys = <String>[];

  /// Set to fail the next import with this failure.
  ApiFailure? importFailure;

  /// How many imports to let through before [importFailure] applies.
  int importsBeforeFailure = 0;

  /// Set to fail the next listing with this failure.
  ApiFailure? listFailure;

  @override
  Future<List<RegisteredSource>> sources(CollectionScope scope) async =>
      sources0 ?? <RegisteredSource>[source()];

  @override
  Future<SourceObjectPage> sourceObjectPage(
    CollectionScope scope,
    String sourceId, {
    Map<String, String> filters = const <String, String>{},
    String? cursor,
  }) async {
    listCursors.add(cursor);
    listFilters.add(Map<String, String>.from(filters));
    final ApiFailure? failure = listFailure;
    if (failure != null) {
      listFailure = null;
      throw failure;
    }
    final List<SourceObject> matching = rows
        .where(
          (SourceObject row) =>
              filters['media_type'] == null ||
              row.mediaType == filters['media_type'],
        )
        .where(
          (SourceObject row) =>
              filters['imported'] == null ||
              (filters['imported'] == 'true') ==
                  (row.state == SourceObjectState.imported),
        )
        .toList();
    final int start = cursor == null ? 0 : int.parse(cursor);
    final int end = (start + pageSize).clamp(0, matching.length);
    return SourceObjectPage(
      matching.sublist(start, end),
      inventoryId: inventoryId,
      nextCursor: end < matching.length ? '$end' : null,
      capturedAt: DateTime.utc(2026, 9, 14, 10, 22),
      objectCount: rows.length,
      // The server counts exactly or not at all. Under the `imported` filter
      // it does not count, and the field is absent rather than zero.
      matchingCount: filters['imported'] != null || !countsMatching
          ? null
          : matchingCount ?? matching.length,
    );
  }

  @override
  Future<SourceImportResult> importFromSource(
    CollectionScope scope,
    String sourceId,
    List<SourceObject> selection,
    String key, {
    bool sensitive = true,
  }) async {
    imports.add(
      selection.map((SourceObject object) => object.objectName).toList(),
    );
    importKeys.add(key);
    final ApiFailure? failure = importFailure;
    if (failure != null && imports.length > importsBeforeFailure) {
      throw failure;
    }
    // The server bounds one request, and a fake that ignored the bound would
    // let a screen ship a request the server refuses.
    if (selection.length > sourceImportBatchSize) {
      throw const ApiFailure(
        'An import selects at most 50 photographs.',
        code: 'invalid_input',
        status: 422,
      );
    }
    final List<Map<String, dynamic>> results = <Map<String, dynamic>>[
      for (final SourceObject object in selection)
        <String, dynamic>{
          'object_name': object.objectName,
          'generation': object.generation,
          'sha256': object.sha256,
          'state': switch (object.state) {
            SourceObjectState.imported => 'duplicate',
            SourceObjectState.unsupportedMediaType => 'unsupported_media_type',
            SourceObjectState.available => 'imported',
          },
          'specimen_id': 'spec-${object.displayName}',
        },
    ];
    return SourceImportResult(<String, dynamic>{
      'batch_id': 'batch-1',
      'source_id': sourceId,
      'requested': selection.length,
      'imported': results
          .where((Map<String, dynamic> r) => r['state'] == 'imported')
          .length,
      'duplicates': results
          .where((Map<String, dynamic> r) => r['state'] == 'duplicate')
          .length,
      'items': results,
    });
  }
}
