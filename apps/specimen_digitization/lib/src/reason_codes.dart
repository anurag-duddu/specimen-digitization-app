/// Reasons a reviewer can pick instead of type (pass criterion 7.6).
///
/// The criterion asks for a reason chosen "from configured codes or recent
/// reasons without typing". Both halves are here, and each says out loud
/// where it came from:
///
/// - **Configured codes.** A collection document or a profile snapshot may
///   publish a decision-reason vocabulary. None of the collection documents
///   or profiles this client has seen does, so [configuredReasonCodes]
///   answers an empty list against every fixture in the repository today and
///   the sheet shows no configured group. It is read under several key
///   spellings because the document is written by whoever set the collection
///   up rather than by this client.
/// - **The record's own reason codes.** The specimen payload does publish
///   `reason_codes`: the machine's reasons this record is in the review
///   queue, such as `human_approval_required` or
///   `mandatory_unresolved:country`. Those are facts about the record, not a
///   reviewer's decision, so they are offered under their own heading rather
///   than mixed in with anything configured.
/// - **Recent reasons.** What this reviewer typed before, kept on the device
///   across sessions, per user.
library;

import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'models.dart';
import 'vocabulary.dart';

/// The keys a collection document or a profile may publish a reviewer's
/// decision-reason vocabulary under.
///
/// Read in order; the first that carries a non-empty list wins. `reason_codes`
/// is deliberately **not** in this list: the API already uses that name on the
/// specimen for something else, and reading a record's queue reasons as if
/// they were a reviewer's decision vocabulary would be the kind of quiet
/// mislabelling this product is trying not to do.
const List<String> configuredReasonKeys = <String>[
  'review_reasons',
  'review_reason_codes',
  'decision_reasons',
  'decision_reason_codes',
  'reason_vocabulary',
];

/// The key this client asks the API to publish.
///
/// Named once so the verification report, the sheet and this file cannot
/// drift. A collection document carrying
/// `"review_reasons": ["Label illegible", "Duplicate specimen"]`, or a list of
/// `{"code": ..., "label": ...}` objects, lights the configured group up with
/// no further client change.
const String preferredConfiguredReasonKey = 'review_reasons';

/// The decision reasons a collection or profile configured, in order.
///
/// [documents] are searched in order: pass the collection document first and
/// the profile snapshot second, so a collection can override a profile.
/// Returns an empty list when nothing published one, which is what every
/// fixture in this repository does today.
List<String> configuredReasonCodes(List<Json?> documents) {
  for (final Json? document in documents) {
    if (document == null) continue;
    for (final String key in configuredReasonKeys) {
      final List<String> codes = _stringsOf(document[key]);
      if (codes.isNotEmpty) return codes;
    }
  }
  return const <String>[];
}

/// The machine's reasons [specimen] is in the review queue, in plain words.
///
/// Read from the `reason_codes` the specimen payload publishes, each through
/// [reasonLabel].
List<String> recordReasonCodes(Specimen specimen) {
  final List<String> codes = _stringsOf(specimen.data['reason_codes']);
  return <String>[
    for (final String code in codes)
      if (reasonLabel(code) case final String phrase when phrase.isNotEmpty)
        phrase,
  ];
}

/// The policy's codes a run stores with a suffix, such as
/// `mandatory_unresolved:taxon` (S3's list of 2026-09-24).
///
/// The search API matches a reason code exactly until S5's T5, so a picked
/// base code would find nothing; until then the filter does not offer these
/// (the coordinator's ruling (b), 2026-09-24). Empty this when T5 lands.
const Set<String> suffixedReasonCodes = <String>{
  'independent_observations_missing',
  'raw_provenance_missing',
  'unresolved_transcription',
  'evidence_lineage_invalid',
  'mandatory_unresolved',
  'evidence_missing',
  'evidence_does_not_support_value',
  'pixel_lineage_missing',
  'unsupported_parsed',
  'unsupported_normalized',
  'unsupported_authority_id',
  'elevation_range',
  'elevation_invalid',
  'elevation_units_conflict',
  'value_shape_mismatch',
};

/// G45's reason: a value that doesn't look like its field's kind. It names
/// the field, "Doesn't look like a habitat" (coordinator ruling for S6,
/// 2026-09-24, from the owner's words).
const String _shapeMismatch = 'value_shape_mismatch';

/// The one field S4 checks for G45 whose name is not a singular noun
/// (`insects.py` SHAPES): "Doesn't look like a collector".
const Map<String, String> _fieldKinds = <String, String>{
  'collectors': 'collector',
};

/// "an" before a vowel, "a" otherwise.
String _article(String noun) =>
    noun.isNotEmpty && 'aeiou'.contains(noun[0].toLowerCase()) ? 'an' : 'a';

/// One reason code in words, the one spelling every screen that shows a
/// reason uses: the queue's rows, the blockers list, a field's findings and
/// the reason sheet (UI.md T3.2).
///
/// A qualified code such as `mandatory_unresolved:country` keeps its
/// subject, so it reads "Required field has no supported value: country"
/// rather than losing which field it was about. A subject that is an
/// identifier is left out, and a code the vocabulary does not name reads as
/// its own words.
String reasonLabel(String code) {
  final int colon = code.indexOf(':');
  if (colon < 0) return _sentence(vocabularyLabel(code));
  final String head = vocabularyLabel(code.substring(0, colon));
  final String tail = vocabularyLabel(code.substring(colon + 1));
  if (tail.isEmpty) return _sentence(head);
  // A run identifier is not a reason a reviewer can read, and this list is
  // meant to be picked from rather than looked up.
  if (_looksLikeIdentifier(tail)) return _sentence(head);
  if (code.substring(0, colon) == _shapeMismatch) {
    final String kind = _fieldKinds[code.substring(colon + 1)] ?? tail;
    return "Doesn't look like ${_article(kind)} $kind";
  }
  return '${_sentence(head)}: $tail';
}

bool _looksLikeIdentifier(String value) =>
    value.length >= 16 && RegExp(r'^[0-9a-f-]+$').hasMatch(value);

String _sentence(String value) =>
    value.isEmpty ? value : '${value[0].toUpperCase()}${value.substring(1)}';

List<String> _stringsOf(Object? raw) {
  if (raw is! List) return const <String>[];
  final List<String> out = <String>[];
  for (final Object? entry in raw) {
    if (entry is String && entry.trim().isNotEmpty) {
      out.add(entry.trim());
    } else if (entry is Map) {
      final Object? label = entry['label'] ?? entry['name'] ?? entry['code'];
      if (label is String && label.trim().isNotEmpty) out.add(label.trim());
    }
  }
  return out;
}

/// The reasons this reviewer typed before, kept across sessions.
///
/// Stored on the device with `shared_preferences`, per user, because the
/// review API has nowhere to put one. Per user rather than per device, so a
/// shared imaging-station machine does not offer one reviewer's reasons to
/// the next (pass criterion 7.6).
class RecentReasonStore {
  const RecentReasonStore(this.userId);

  /// The account the reasons belong to. Empty is a valid key: it is the
  /// bucket an unidentified session writes to, and it is never merged with a
  /// named one.
  final String userId;

  /// The most reasons one reviewer keeps.
  static const int limit = 10;

  /// The preference key this reviewer's reasons live under.
  String get storageKey => 'review.recent_reasons.$userId';

  /// The reasons, newest first.
  ///
  /// A store this platform cannot open is no reasons, never an error on a
  /// screen a reviewer opened to save work: the convenience is optional and
  /// the save is not.
  Future<List<String>> load() async {
    try {
      final SharedPreferences store = await SharedPreferences.getInstance();
      final String? raw = store.getString(storageKey);
      if (raw == null || raw.isEmpty) return const <String>[];
      return _stringsOf(_decode(raw));
    } catch (_) {
      return const <String>[];
    }
  }

  /// Puts [reason] at the front, removing any earlier copy, and answers the
  /// new list.
  ///
  /// Answers the list it meant to write even when the write failed, so the
  /// sheet the reviewer opens next still offers what they just typed for as
  /// long as the session lasts.
  Future<List<String>> remember(String reason) async {
    final String trimmed = reason.trim();
    if (trimmed.isEmpty) return load();
    final List<String> current = await load();
    final List<String> next = <String>[
      trimmed,
      for (final String existing in current)
        if (existing != trimmed) existing,
    ];
    final List<String> capped = next.length <= limit
        ? next
        : next.sublist(0, limit);
    try {
      final SharedPreferences store = await SharedPreferences.getInstance();
      await store.setString(storageKey, jsonEncode(capped));
    } catch (_) {
      // Nothing to recover: the list below is still correct for this session.
    }
    return capped;
  }

  /// A stored value that is not readable JSON is treated as no reasons at
  /// all, never as a crash on a sheet a reviewer opened to save work.
  static Object? _decode(String raw) {
    try {
      return jsonDecode(raw);
    } on FormatException {
      return null;
    }
  }
}
