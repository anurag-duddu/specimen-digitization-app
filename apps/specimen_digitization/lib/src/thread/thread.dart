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

/// Where a field's literal, a handoff or a lookup's input came from.
enum ThreadInputSource {
  /// The transcript the first pass decided on.
  decidedTranscript('decided_transcript'),

  /// One reader's raw reading, handed over as it was read.
  rawReading('raw_reading');

  const ThreadInputSource(this.wire);

  /// The value on the wire.
  final String wire;

  /// The source named by [value], or null for anything else.
  static ThreadInputSource? fromWire(Object? value) =>
      values.where((ThreadInputSource s) => s.wire == value).firstOrNull;
}

/// The profile group a field belongs to.
enum ThreadFieldGroup {
  /// Clearance needs a supported value.
  mandatory,

  /// Extracted and shown, and never a reason to hold a record.
  optional;

  /// The group named by [value], or null for anything else.
  static ThreadFieldGroup? fromWire(Object? value) =>
      values.where((ThreadFieldGroup g) => g.name == value).firstOrNull;
}

/// How a region's decided transcript was reached.
enum ThreadDecisionKind {
  /// Every reading was the same text.
  identicalReadings('identical_readings'),

  /// The LLM first pass chose among differing readings.
  firstPass('first_pass'),

  /// A reviewer resolved it.
  human('human');

  const ThreadDecisionKind(this.wire);

  /// The value on the wire.
  final String wire;

  /// The kind named by [value], or null for anything else.
  static ThreadDecisionKind? fromWire(Object? value) =>
      values.where((ThreadDecisionKind k) => k.wire == value).firstOrNull;
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

  /// The program's model allowance in micro-dollars, from S3's G30 record,
  /// or null when the run does not carry it (S5 adds it to #88's section 8
  /// after `6b97508`).
  int? get allowanceMicros => _int(_map('allowance')['allowance_micros']);
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

/// The model call the first pass made.
class ThreadModelCall extends _ModelOutput {
  const ThreadModelCall._(super.json);
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

/// What one reader handed to the harness.
class ThreadHandoff extends _View {
  /// The handoff in [json].
  const ThreadHandoff.fromJson(super.json);

  String? get observationId => _t('observation_id');

  /// The role as sent.
  String? get roleName => _t('role');

  /// The role, or null when the server sent one this client does not know.
  ThreadInputSource? get source => ThreadInputSource.fromWire(roleName);

  /// What was handed over, exactly.
  String? get handedText => _verbatim('handed_text');

  /// The first pass's note about this reading.
  String? get note => _t('note');
}

/// How one region's transcript was decided, and what went to the harness.
class ThreadFirstPass extends _View {
  /// The decision in [json].
  const ThreadFirstPass.fromJson(super.json);

  /// The decision kind as sent.
  String? get kindName => _t('decision_kind');

  /// The kind, or null when the server sent one this client does not know.
  ThreadDecisionKind? get kind => ThreadDecisionKind.fromWire(kindName);
  String? get selectedObservationId => _t('selected_observation_id');

  /// The decided transcript, exactly.
  String? get decidedText => _verbatim('decided_text');

  /// True when no reading was chosen or a material difference is open.
  bool? get unresolved => _b('unresolved');

  /// The first pass's rationale, or the reviewer's reason.
  String? get rationale => _t('rationale');

  /// The model call, for a decision the first pass made.
  ThreadModelCall? get modelCall {
    final Json? call = _object(_json['model_call']);
    return call == null ? null : ThreadModelCall._(call);
  }

  /// One per reading of the region.
  List<ThreadHandoff> get handoffs => _each('handoffs', ThreadHandoff.fromJson);
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

  /// How its transcript was decided; null when no decision is recorded, and
  /// the run's stage and blocker say why.
  ThreadFirstPass? get firstPass {
    final Json? pass = _object(_json['first_pass']);
    return pass == null ? null : ThreadFirstPass.fromJson(pass);
  }
}

/// One call the harness made.
class ThreadToolCall extends _View {
  /// The call in [json].
  const ThreadToolCall.fromJson(super.json);

  String? get callKey => _t('call_key');
  String? get phase => _t('phase');
  String? get tool => _t('tool');
  String? get toolVersion => _t('tool_version');

  /// The database it asked, as an identifier (`google-maps-geocoding`).
  String? get source => _t('source');

  /// The fields it served; one geography call serves several.
  List<String> get fieldKeys => _texts('field_keys');

  /// The input source as sent.
  String? get inputSourceName => _t('input_source');

  /// The input source, or null when the server sent one this client does
  /// not know.
  ThreadInputSource? get inputSource =>
      ThreadInputSource.fromWire(inputSourceName);
  String? get regionId => _t('region_id');

  /// The reading whose text it ran on, for a raw-reading call.
  String? get observationId => _t('observation_id');

  /// Which attempt this was, from one.
  int? get attempt => _i('attempt');
  Json get arguments => _map('arguments');

  /// The typed outcome (HAR-008): the `LookupStatus` values.
  String? get outcome => _t('outcome');
  Json? get result => _object(_json['result']);

  /// What went wrong. The contract names it at the call; a writer that
  /// follows `LookupResult` puts it in the result.
  String? get error => _t('error') ?? _text(result?['error']);

  /// When it may be tried again, from the same two places.
  String? get retryAfter => _t('retry_after') ?? _text(result?['retry_after']);
  String? get evidenceId => _t('evidence_id');
  String? get startedAt => _t('started_at');
  String? get completedAt => _t('completed_at');
}

/// One entry of what a field says was written (G27, G28): the decided
/// transcript's text, or, when the first pass chose no reading, one reader's.
class ThreadVerbatim extends _View {
  const ThreadVerbatim._(super.json);

  /// What was written, exactly.
  String? get text => _verbatim('text');

  /// The input source as sent.
  String? get inputSourceName => _t('input_source');

  /// The input source, or null when the server sent one this client does
  /// not know.
  ThreadInputSource? get inputSource =>
      ThreadInputSource.fromWire(inputSourceName);
  String? get regionId => _t('region_id');

  /// The reader whose text this is, for a raw reading; null for the decided
  /// transcript.
  String? get observationId => _t('observation_id');
}

/// One source's evidence for a field, and how it bears on the value.
class ThreadEvidence extends _View {
  const ThreadEvidence._(super.json);

  String? get evidenceId => _t('evidence_id');

  /// `decides`, `supports` or `contradicts` (G23), as sent.
  String? get relation => _t('relation');

  /// The database, as an identifier (`gbif`).
  String? get source => _t('source');

  /// Where in that source (`place/{place id}` for Google, G26).
  String? get locator => _t('locator');

  /// The lookup's typed outcome.
  String? get outcome => _t('outcome');
}

/// One profile field's result.
class ThreadField extends _View {
  /// The field in [json].
  const ThreadField.fromJson(super.json);

  String? get fieldKey => _t('field_key');

  /// The group as sent.
  String? get groupName => _t('group');

  /// The group, or null when the server sent none this client knows.
  ThreadFieldGroup? get group => ThreadFieldGroup.fromWire(groupName);

  /// The value state: supported, unknown, unreadable and the rest.
  String? get state => _t('state');

  /// What was written: one entry for the decided transcript, or one per
  /// reader when the first pass chose none (G27, G28).
  List<ThreadVerbatim> get verbatim => _each('verbatim', ThreadVerbatim._);

  /// Read as. The thread sends it as text with the precision and the century
  /// rule beside it (G24); the stored object form is read too, so a change
  /// of shape never loses the value.
  String? get parsed {
    final Json? stored = _parsedObject;
    if (stored == null) return _verbatim('parsed');
    final Object? value = stored['value'];
    return value is String ? value : null;
  }

  /// How precise a date is, as written: day, month or year (G24).
  String? get precision =>
      _t('precision') ?? _text(_parsedObject?['precision']);

  /// The rule, with its version, that set a two-digit year's century (G24);
  /// null for a four-digit year and for anything that is not a date.
  String? get centuryRule =>
      _t('century_rule') ?? _text(_parsedObject?['century_rule']);

  /// What was settled: the standardized value. For a Google-confirmed field
  /// it is at most a reader's exactly matching text, never a Google name
  /// (G26); for a GBIF-settled taxon it may be GBIF's accepted name (G28).
  String? get normalized => _verbatim('normalized');

  /// The authority record the value was settled against: a Google place ID,
  /// a GBIF usage and so on.
  String? get authorityId => _t('authority_id');

  /// Each source's evidence and its relation to the value (G23).
  List<ThreadEvidence> get evidence => _each('evidence', ThreadEvidence._);

  /// The readings whose own literal settled the value, in verbatim order:
  /// one per label when the field cleared across labels (G32), the reader a
  /// lookup confirmed (G20), or none, as when the field went to review
  /// (#88 at `4f9997a`).
  List<String> get settledObservationIds => _texts('settled_observation_ids');

  Json? get _parsedObject => _object(_json['parsed']);
}

/// The queue decision and its reasons.
class ThreadDecision extends _View {
  const ThreadDecision._(super.json);

  /// `cleared`, `needs_human_review` or `deferred`, as sent.
  String? get disposition => _t('disposition');
  String? get policyVersion => _t('policy_version');
  List<String> get reasonCodes => _texts('reason_codes');

  /// The one-sentence summary (QUE-006).
  String? get summary => _t('summary');

  /// The findings behind it, hard, warning and info. Warnings and info never
  /// change the disposition.
  List<ThreadFinding> get findings => _each('findings', ThreadFinding._);
}

/// One finding of the queue decision.
class ThreadFinding extends _View {
  const ThreadFinding._(super.json);

  String? get ruleId => _t('rule_id');

  /// `hard`, `warning` or `info`, as sent.
  String? get severity => _t('severity');
  String? get fieldKey => _t('field_key');
  String? get reasonCode => _t('reason_code');
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

  /// The queue decision, or null before the queue decides.
  ThreadDecision? get decision => _part('decision', ThreadDecision._);

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

  /// The harness's calls, in the order they ran.
  List<ThreadToolCall> get toolCalls =>
      _each('tool_calls', ThreadToolCall.fromJson);

  /// Every field, in the profile's order.
  List<ThreadField> get fields => _each('fields', ThreadField.fromJson);

  /// The fields a supported value is needed for.
  List<ThreadField> get mandatoryFields =>
      _grouped((ThreadField f) => f.group == ThreadFieldGroup.mandatory);

  /// The fields that are shown and never hold a record.
  List<ThreadField> get optionalFields =>
      _grouped((ThreadField f) => f.group == ThreadFieldGroup.optional);

  /// The fields with no group this client knows: shown apart, never filed
  /// into a group by guess.
  List<ThreadField> get ungroupedFields =>
      _grouped((ThreadField f) => f.group == null);

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

  List<ThreadField> _grouped(bool Function(ThreadField) test) =>
      List<ThreadField>.unmodifiable(fields.where(test));
}
