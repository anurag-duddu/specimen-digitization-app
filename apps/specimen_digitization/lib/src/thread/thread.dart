/// The processing thread of one specimen run (PLAN 4.7; UI.md T2.1).
///
/// Typed views over the thread response S5 serves at
/// `GET /v1/organizations/{organization}/specimens/{id}/thread`
/// (`docs/execution/golive/DATA_CONTRACT.md` section 8). Where the
/// workspace's `Specimen` hands the screen a map, every part here has a type,
/// so an absent part is a null the screen names rather than a key it trips
/// over. Each view reads the decoded response, which nothing mutates.
///
/// Parsing is lenient in one direction only. A missing or malformed value is
/// absent, and absent never becomes a value: an unmeasured ratio stays null
/// rather than zero, and an unknown state keeps the server's word, beside a
/// typed getter that is null (north star, "Say what we know, exactly").
library;

import 'package:flutter/foundation.dart';

import '../models.dart';

/// A non-empty string, for identifiers and names.
String? _text(Object? value) =>
    value is String && value.trim().isNotEmpty ? value : null;

int? _int(Object? value) =>
    value is num && value.isFinite && value == value.truncate()
    ? value.toInt()
    : null;

double? _number(Object? value) =>
    value is num && value.isFinite ? value.toDouble() : null;

Json? _object(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : null;

/// One object of the response, read through typed getters.
@immutable
abstract class _View {
  const _View(this._json);

  final Json _json;

  String? _t(String key) => _text(_json[key]);

  /// A string exactly as sent, for the texts readers and people wrote: an
  /// empty reading and a doubled space are both evidence.
  String? _verbatim(String key) =>
      _json[key] is String ? _json[key] as String : null;

  int? _i(String key) => _int(_json[key]);

  bool? _b(String key) => _json[key] is bool ? _json[key] as bool : null;

  List<String> _texts(String key) => _json[key] is List
      ? List<String>.unmodifiable((_json[key] as List).whereType<String>())
      : const <String>[];

  Json _map(String key) => _object(_json[key]) ?? const <String, dynamic>{};

  List<T> _each<T>(String key, T Function(Json) read) => _json[key] is List
      ? List<T>.unmodifiable(
          (_json[key] as List).whereType<Map>().map(
            (Map item) => read(Map<String, dynamic>.from(item)),
          ),
        )
      : List<T>.empty();
}

/// A retained raw response: which evidence file, and its checksum.
class ThreadAssetRef extends _View {
  const ThreadAssetRef._(super.json);

  /// The reference in [json], or null when it names no asset.
  static ThreadAssetRef? fromJson(Object? json) {
    final Json? map = _object(json);
    return map != null && _text(map['asset_id']) != null
        ? ThreadAssetRef._(map)
        : null;
  }

  String get assetId => _t('asset_id')!;
  String? get sha256 => _t('sha256');
}

/// The run the thread describes, and where it stands.
class ThreadRun extends _View {
  /// The run in [json]; every part may be absent.
  ThreadRun.fromJson(Object? json)
    : super(_object(json) ?? const <String, dynamic>{});

  String? get runId => _t('run_id');

  /// The summary's `status` vocabulary: pending, running,
  /// processing_blocked, retry_scheduled, paused, cancelled or completed.
  String? get status => _t('status');
  String? get stage => _t('stage');
  String? get blocker => _t('blocker');
  String? get nextRetryAt => _t('next_retry_at');
  String? get profileKey => _text(_map('profile')['key']);
  String? get profileVersion => _text(_map('profile')['version']);
}

/// The run's Logfire trace.
class ThreadTrace extends _View {
  /// The trace in [json]; both parts may be absent.
  ThreadTrace.fromJson(Object? json)
    : super(_object(json) ?? const <String, dynamic>{});

  /// The W3C trace id, or null when the run recorded none.
  String? get traceId => _t('trace_id');

  /// The link the server built, or null when none is configured. Only an
  /// absolute https URL is kept: the link opens in the reviewer's browser,
  /// so nothing else the payload carries may become one.
  Uri? get url {
    final String? text = _t('url');
    final Uri? uri = text == null ? null : Uri.tryParse(text);
    return uri != null && uri.isScheme('https') && uri.host.isNotEmpty
        ? uri
        : null;
  }
}

/// The original image the run read.
class ThreadImage extends _View {
  const ThreadImage._(super.json);

  String? get assetId => _t('asset_id');
  String? get sha256 => _t('sha256');
  int? get width => _i('width');
  int? get height => _i('height');

  /// Which pixel grid region geometry is in.
  String? get pixelBasis => _t('pixel_basis');
}

/// What label detection ran with (SAM 3).
class ThreadSegmentation extends _View {
  const ThreadSegmentation._(super.json);

  String? get modelRevision => _t('model_revision');

  /// The concept prompt, the thresholds and the region limit, as sent.
  Json get settings => _map('settings');
}

/// One check inside the automatic coverage check.
class ThreadCheck extends _View {
  const ThreadCheck._(super.json);

  /// `region_count` or `full_image` today.
  String? get name => _t('name');

  /// Whether it passed; null when the server did not say.
  bool? get passed => _b('passed');

  /// What it measured, as sent.
  Json get detail => _map('detail');
}

/// The automatic label-coverage check (G15).
class ThreadCoverageCheck extends _View {
  const ThreadCoverageCheck._(super.json);

  /// `passed`, `failed` or `not_run`, as sent.
  String? get status => _t('status');
  List<ThreadCheck> get checks => _each('checks', ThreadCheck._);
  String? get evidenceId => _t('evidence_id');
  String? get checkedAt => _t('checked_at');
}

/// Where a label region sits on the original, in the image's pixel basis.
@immutable
class ThreadGeometry {
  const ThreadGeometry._(this.x, this.y, this.width, this.height);

  /// The rectangle in [json], or null unless all four sides are numbers.
  static ThreadGeometry? fromJson(Object? json) {
    final Json? map = _object(json);
    final List<double?> sides = <String>[
      'x',
      'y',
      'width',
      'height',
    ].map((String key) => _number(map?[key])).toList();
    if (sides.contains(null)) return null;
    return ThreadGeometry._(sides[0]!, sides[1]!, sides[2]!, sides[3]!);
  }

  final double x;
  final double y;
  final double width;
  final double height;
}

/// Who produced a model output: the route, the model, its provider and the
/// prompt, how the call ended and the raw response kept. A reader's reading
/// and the first pass's call are both one.
abstract class _ModelOutput extends _View {
  const _ModelOutput(super.json);

  String? get observationId => _t('observation_id');
  String? get routeId => _t('route_id');
  String? get model => _t('model');
  String? get provider => _t('provider');
  String? get promptVersion => _t('prompt_version');
  String? get outcome => _t('outcome');
  ThreadAssetRef? get rawResponse =>
      ThreadAssetRef.fromJson(_json['raw_response']);
}

/// One reader's reading of one region.
class ThreadReading extends _ModelOutput {
  /// The reading in [json].
  const ThreadReading.fromJson(super.json);

  /// What the reader returned, exactly.
  String? get literalText => _verbatim('literal_text');

  /// The spans the reader declared it could not read.
  List<String> get unreadableSpans => _texts('unreadable_spans');
}

/// The measured difference between two readings of one region.
class ThreadComparison extends _View {
  /// The comparison in [json].
  const ThreadComparison.fromJson(super.json);

  String? get leftObservationId => _t('left_observation_id');
  String? get rightObservationId => _t('right_observation_id');

  /// `bounded-levenshtein-fraction-v1` today.
  String? get algorithm => _t('algorithm');

  /// Edits over characters, or null when the difference was not measured.
  double? get ratio => _number(_json['ratio']);
  int? get editDistance => _i('edit_distance');

  /// The characters the ratio divides by.
  int? get lengthBasis => _i('length_basis');

  /// `agreement`, `disagreement`, or why it was not measured, as sent.
  String? get status => _t('status');
  List<String> get reasons => _texts('reasons');

  /// The server's label: the ratio orders review and is not a probability.
  String? get calibration => _t('calibration');
}

/// One label region: its readings, their comparison and the decision.
class ThreadRegion extends _View {
  /// The region in [json].
  const ThreadRegion.fromJson(super.json);

  String? get regionId => _t('region_id');

  /// Its number on the slide, from zero: "Label 1" is ordinal 0.
  int? get ordinal => _i('ordinal');

  /// The quarter turns that stand the label upright.
  int? get rotationQuarterTurns => _i('rotation_quarter_turns');
  ThreadGeometry? get geometry => ThreadGeometry.fromJson(_json['geometry']);
  List<ThreadReading> get readings => _each('readings', ThreadReading.fromJson);
  List<ThreadComparison> get comparisons =>
      _each('comparisons', ThreadComparison.fromJson);
}

/// One specimen run's whole thread.
class SpecimenThread extends _View {
  /// The thread in [json].
  const SpecimenThread.fromJson(super.json);

  String get specimenId => _t('specimen_id') ?? '';

  /// The record version the thread was read at.
  int? get revision => _i('revision');
  ThreadRun get run => ThreadRun.fromJson(_json['run']);
  ThreadTrace get trace => ThreadTrace.fromJson(_json['trace']);
  ThreadImage? get image => _part('image', ThreadImage._);
  ThreadSegmentation? get segmentation =>
      _part('segmentation', ThreadSegmentation._);

  /// The automatic coverage check (G15).
  ThreadCoverageCheck? get coverageCheck =>
      _part('coverage_check', ThreadCoverageCheck._);

  /// The label regions: numbered ones in order, then any unnumbered one in
  /// the order it was sent. `List.sort` is not stable, so the index breaks
  /// ties.
  List<ThreadRegion> get regions {
    final List<(int, ThreadRegion)> indexed = _each(
      'regions',
      ThreadRegion.fromJson,
    ).indexed.toList();
    indexed.sort(((int, ThreadRegion) a, (int, ThreadRegion) b) {
      final int left = a.$2.ordinal ?? -1;
      final int right = b.$2.ordinal ?? -1;
      if (left != right) {
        if (left < 0) return 1;
        if (right < 0) return -1;
        return left.compareTo(right);
      }
      return a.$1.compareTo(b.$1);
    });
    return List<ThreadRegion>.unmodifiable(
      indexed.map(((int, ThreadRegion) entry) => entry.$2),
    );
  }

  /// The reading with [observationId], wherever it sits.
  ThreadReading? readingOf(String? observationId) => observationId == null
      ? null
      : regions
            .expand((ThreadRegion r) => r.readings)
            .where((ThreadReading r) => r.observationId == observationId)
            .firstOrNull;

  /// The region with [regionId].
  ThreadRegion? regionOf(String? regionId) => regionId == null
      ? null
      : regions.where((ThreadRegion r) => r.regionId == regionId).firstOrNull;

  T? _part<T>(String key, T Function(Json) read) {
    final Json? part = _object(_json[key]);
    return part == null ? null : read(part);
  }
}
