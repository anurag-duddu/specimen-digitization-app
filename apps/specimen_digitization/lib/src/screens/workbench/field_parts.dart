/// The parts of a field's value, read from the optional `parts` a field may
/// carry (field model v2; wire contract in `docs/execution/FIELD_PARTS_WIRE.md`
/// on pull request 288, planned and not in force).
///
/// A part is one piece of a value: the country, island and province inside a
/// locality, the unit inside an elevation, one collector among several. Each
/// part has its own basis, state and review flag, so a person is asked about
/// the doubtful part and not the whole field.
///
/// The server does not write `parts` yet. Every record today has none, and a
/// field without parts draws exactly as it did before. This file is pure Dart
/// with no widget: it reads what a field map holds, checks it against the
/// contract's rules (section 2.5) and the bounds (section 2.8), and answers
/// with the parts or with none. It never throws and never guesses.
///
/// What a reader does with what it does not understand (section 3.5):
///
/// - A part whose path this reader cannot parse, or whose path belongs to
///   another field, is left out. A later release may add paths; a reader
///   that does not know one shows the field's own value as it always has.
/// - A basis word this reader does not know shows no basis chip.
/// - A review code this reader does not know is read as `doubt`.
/// - A decision action this reader does not know is read as a confirmation.
/// - Everything else that breaks a rule of the contract, a bound included,
///   sets the whole list aside, and the field shows no parts. A half tree
///   misleads, and the field's own value is complete without it.
///
/// Nothing here is stored or sent to the server.
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../../models.dart';
import '../../vocabulary.dart';
import 'value_basis.dart';

/// The most parts one field carries (contract 2.8).
const int maxPartsPerField = 24;

/// The most bytes `parts` takes on one field, as compact UTF-8 JSON (2.8).
const int maxPartBytesPerField = 32 * 1024;

/// The longest a text member of a part may be, in characters (2.8).
const int maxPartTextLength = 240;

/// The longest a part path may be (2.3).
const int maxPartPathLength = 64;

/// The most evidence rows one part cites (2.8).
const int maxPartEvidenceIds = 12;

/// The most alternatives one part offers (2.3).
const int maxPartAlternatives = 4;

/// The most evidence rows one alternative cites (2.4).
const int maxAlternativeEvidenceIds = 2;

/// The most parts one part's value is computed from (2.3).
const int maxPartDerivedFrom = 8;

/// The root of the place tree: the verbatim locality as read. It is the
/// `parent` of the broadest node and is never a part of its own.
const String locationRoot = 'location/verbatim';

/// How the part names of one value are shaped (the grammar of PR 285).
enum _Shape { fixed, list, tree }

/// The nine values a part path can start with, and how each names its parts.
const Map<String, (_Shape, Set<String>)> _values =
    <String, (_Shape, Set<String>)>{
      'ids': (_Shape.fixed, <String>{'catalog_number', 'collection'}),
      'location': (_Shape.tree, <String>{}),
      'elevation': (_Shape.fixed, <String>{'from', 'to', 'unit', 'kind'}),
      'collectors': (_Shape.list, <String>{}),
      'habitat': (_Shape.fixed, <String>{'text'}),
      'collection_method': (_Shape.fixed, <String>{'text'}),
      'when': (
        _Shape.fixed,
        <String>{
          'collected/start',
          'collected/end',
          'collected/time',
          'identified/start',
        },
      ),
      'taxon': (
        _Shape.fixed,
        <String>{'name', 'accepted', 'rank', 'authorship', 'status'},
      ),
      'identified_by': (_Shape.list, <String>{}),
    };

final RegExp _levelName = RegExp(r'^[a-z]+(?:_[a-z]+)*$');
final RegExp _indexNumber = RegExp(r'^[1-9][0-9]{0,5}$');
final RegExp _controlCharacter = RegExp(r'[\u0000-\u001f\u007f]');

/// A part's name, `<value>/<part>[/n]`, parsed (contract 2.3; PRD, "Naming a
/// part").
///
/// The first segment is the value, never its group. A fixed value has parts
/// from a fixed set, a list value has entries `<value>/<n>` from 1, and the
/// place is a tree whose levels are not fixed: `location/country`,
/// `location/place`, and `location/place/2` for the second of a level that
/// repeats. `location/verbatim` is the root and takes no index.
@immutable
class PartPath {
  const PartPath._(this.value, this.part, this.index);

  /// The first segment: `location`, `elevation`, `collectors`, and so on.
  final String value;

  /// A fixed part (`unit`, `collected/start`) or a place level (`country`),
  /// and null for a list entry.
  final String? part;

  /// A list entry's number, or the n-th repeat of a place level from 2.
  final int? index;

  /// The path as the wire spells it.
  String get text => <String>[value, ?part, ?index?.toString()].join('/');

  /// True for `location/verbatim`, the root of the place tree.
  bool get isRoot => value == 'location' && part == 'verbatim' && index == null;

  /// True for a part of the place tree.
  bool get isLocation => value == 'location';

  /// The path of [raw], or null when it is not a spelling the grammar allows:
  /// not text, empty, non-ASCII or with a space, an unknown value, no part, an
  /// empty or unknown part, a bad index, or any spelling but the canonical one.
  static PartPath? tryParse(Object? raw) {
    if (raw is! String || raw.isEmpty) return null;
    for (final int unit in raw.codeUnits) {
      if (unit <= 0x20 || unit >= 0x7F) return null;
    }
    final int slash = raw.indexOf('/');
    if (slash < 0) return null;
    final String head = raw.substring(0, slash);
    final String rest = raw.substring(slash + 1);
    final (_Shape, Set<String>)? spec = _values[head];
    if (spec == null || rest.isEmpty) return null;
    final List<String> segments = rest.split('/');
    if (segments.any((String segment) => segment.isEmpty)) return null;
    switch (spec.$1) {
      case _Shape.fixed:
        return spec.$2.contains(rest) ? PartPath._(head, rest, null) : null;
      case _Shape.list:
        if (segments.length != 1 || !_indexNumber.hasMatch(segments.single)) {
          return null;
        }
        return PartPath._(head, null, int.parse(segments.single));
      case _Shape.tree:
        final String level = segments.first;
        if (!_levelName.hasMatch(level)) return null;
        if (segments.length == 1) return PartPath._(head, level, null);
        if (segments.length > 2) return null;
        // The verbatim locality is the root and takes no index.
        if (level == 'verbatim') return null;
        if (!_indexNumber.hasMatch(segments[1])) return null;
        final int repeat = int.parse(segments[1]);
        // The first of a level has no index. Repeats start at 2.
        return repeat < 2 ? null : PartPath._(head, level, repeat);
    }
  }

  /// The field this path's part is carried on, or null when this reader does
  /// not know one (contract 2.1).
  ///
  /// The carrier is chosen by the first segments of the path. Habitat and
  /// collection method are not listed: the contract guesses a carrier for them
  /// and has not settled it, so a part on them is left out and the field shows
  /// its own value. `identified_by` has no carrier until a person's name has
  /// its own value.
  String? get carrierField => switch (value) {
    'location' => 'precise_location',
    'elevation' => 'elevation_from_m',
    'when' =>
      part != null && part!.startsWith('identified/')
          ? 'date_identified'
          : 'date_visited_from',
    'collectors' => 'collectors',
    'taxon' => 'taxon',
    'ids' => 'fmnh_ins_number',
    _ => null,
  };

  /// The reviewer-facing name of this part, in the words of the screen
  /// ("Country", "Named place 2", "Elevation unit").
  ///
  /// A level the app does not know is shown, not hidden: it goes through
  /// [vocabularyLabel], so a place level a later country needs reads in plain
  /// words without a release.
  String get label {
    final String? suffix = index == null ? null : ' $index';
    final String base;
    if (part == null) {
      base = switch (value) {
        'collectors' => 'Collector',
        'identified_by' => 'Identified by',
        _ => _sentence(vocabularyLabel(value)),
      };
    } else {
      base = _partLabels['$value/$part'] ?? _sentence(vocabularyLabel(part!));
    }
    return '$base${suffix ?? ''}';
  }

  @override
  bool operator ==(Object other) =>
      other is PartPath &&
      other.value == value &&
      other.part == part &&
      other.index == index;

  @override
  int get hashCode => Object.hash(value, part, index);

  @override
  String toString() => text;
}

/// The names of the parts the contract lists. A place level not named here
/// goes through [vocabularyLabel].
const Map<String, String> _partLabels = <String, String>{
  'ids/catalog_number': 'Catalogue number',
  'ids/collection': 'Collection',
  'location/country': 'Country',
  'location/island': 'Island',
  'location/province': 'Province',
  'location/place': 'Named place',
  'location/department': 'Department',
  'location/municipality': 'Municipality',
  'elevation/from': 'Elevation from',
  'elevation/to': 'Elevation to',
  'elevation/unit': 'Elevation unit',
  'elevation/kind': 'Elevation kind',
  'habitat/text': 'Habitat',
  'collection_method/text': 'Collection method',
  'when/collected/start': 'Collection start date',
  'when/collected/end': 'Collection end date',
  'when/collected/time': 'Collection time',
  'when/identified/start': 'Identification date',
  'taxon/name': 'Name as written',
  'taxon/accepted': 'Accepted name',
  'taxon/rank': 'Rank',
  'taxon/authorship': 'Authorship',
  'taxon/status': 'Taxonomic status',
};

/// What a whole value is called in a sentence, for the one reason code whose
/// subject is a value and not a part (`part_bounds_exceeded:<value>`).
String? partValueLabel(String value) => switch (value) {
  'location' => 'location',
  'elevation' => 'elevation',
  'collectors' => 'collectors',
  'when' => 'dates',
  'taxon' => 'taxon',
  'ids' => 'identifiers',
  'habitat' => 'habitat',
  'collection_method' => 'collection method',
  'identified_by' => 'identified by',
  _ => null,
};

/// The field a whole value is carried on, where one field carries it all.
///
/// `when` is carried by two fields (the collecting event and the
/// identification), so a reason about the whole of it names neither.
String? partValueCarrier(String value) => switch (value) {
  'location' => 'precise_location',
  'elevation' => 'elevation_from_m',
  'collectors' => 'collectors',
  'taxon' => 'taxon',
  'ids' => 'fmnh_ins_number',
  _ => null,
};

String _sentence(String text) =>
    text.isEmpty ? text : '${text[0].toUpperCase()}${text.substring(1)}';

/// How a cited evidence row bears on a part (contract 2.6).
enum PartRelation {
  /// A rule or a source that settled the value.
  decides('decides'),

  /// The row states the same value.
  supports('supports'),

  /// The row states a different value, or a lookup refused it.
  contradicts('contradicts'),

  /// A source was examined and neither supports nor contradicts the value.
  considered('considered');

  const PartRelation(this.wire);

  /// The word the wire uses.
  final String wire;

  /// The relation a wire word names, or null for a word this app does not
  /// know.
  static PartRelation? fromWire(Object? value) {
    for (final PartRelation relation in values) {
      if (relation.wire == value) return relation;
    }
    return null;
  }
}

/// Why a person is asked about a part (contract 2.4).
enum PartReviewCode {
  /// Readings or sources disagree.
  conflict('conflict'),

  /// The part is filled and a step in it is in doubt, an inference included.
  doubt('doubt'),

  /// Nothing supports even an inference.
  noSupport('no_support');

  const PartReviewCode(this.wire);

  /// The word the wire uses.
  final String wire;
}

/// What a person did with a part (contract 2.4).
enum PartDecisionAction {
  /// The person accepted the value as found.
  accept('accept'),

  /// The person chose one of the alternatives.
  choose('choose'),

  /// The person entered a value of their own. It has no basis.
  edit('edit'),

  /// An action this app does not know, read as a confirmation.
  other('');

  const PartDecisionAction(this.wire);

  /// The word the wire uses.
  final String wire;

  /// The action a wire word names; a word this app does not know is [other],
  /// which the screen reads as a confirmation.
  static PartDecisionAction fromWire(Object? value) {
    for (final PartDecisionAction action in values) {
      if (action != other && action.wire == value) return action;
    }
    return other;
  }
}

/// The record that a person is asked about a part (contract 2.4).
@immutable
class PartReview {
  const PartReview({required this.code, required this.reason});

  /// Why. A code this app does not know is read as [PartReviewCode.doubt].
  final PartReviewCode code;

  /// A sentence the writer composed from a fixed template, never model text.
  /// At most 240 characters.
  final String reason;
}

/// The record that a person decided a part (contract 2.4).
@immutable
class PartDecision {
  const PartDecision({required this.action, this.at});

  /// What the person did.
  final PartDecisionAction action;

  /// When, as the wire spelled it. The screen shows "a reviewer", never who.
  final String? at;
}

/// One other value a person can choose for a part (contract 2.4).
@immutable
class PartAlternative {
  const PartAlternative({
    required this.value,
    this.basis,
    this.wording,
    this.evidenceIds = const <String>[],
  });

  /// The alternative value.
  final String value;

  /// Its basis, or null when it states none or a word this app does not know.
  final ValueBasis? basis;

  /// The label's words it came from, when it is a piece of a longer wording.
  final String? wording;

  /// The evidence rows it cites, each also cited by the part.
  final List<String> evidenceIds;
}

/// One part of a field's value, as the server recorded it.
@immutable
class FieldPart {
  const FieldPart({
    required this.path,
    required this.state,
    this.value,
    this.basis,
    this.basisStated = false,
    this.wording,
    this.parent,
    this.authorityId,
    this.derivedFrom = const <PartPath>[],
    this.evidenceIds = const <String>[],
    this.evidenceRelations = const <String, PartRelation>{},
    this.alternatives = const <PartAlternative>[],
    this.review,
    this.decision,
  });

  /// The part's name.
  final PartPath path;

  /// One of the seven value states (`knownFieldStates`).
  final String state;

  /// The part's value, when its state is `supported`. A number is decimal text.
  final String? value;

  /// How the value was obtained, or null when the part states none (an
  /// edited part) or states a word this app does not know.
  final ValueBasis? basis;

  /// True when the wire carried a basis, known or not.
  final bool basisStated;

  /// The label's words the value came from. Kept next to every interpreted
  /// value (PRD rule 4).
  final String? wording;

  /// The next broader node of the place tree, or null outside it.
  final PartPath? parent;

  /// The matched authority record in the form the sources return. Internal:
  /// never drawn as copy.
  final String? authorityId;

  /// The parts whose values this one was computed from.
  final List<PartPath> derivedFrom;

  /// The evidence rows this part cites.
  final List<String> evidenceIds;

  /// How each cited row bears on the part. Has exactly the keys of
  /// [evidenceIds].
  final Map<String, PartRelation> evidenceRelations;

  /// The other values a person can choose.
  final List<PartAlternative> alternatives;

  /// Present when a person is asked about this part.
  final PartReview? review;

  /// Present when a person decided this part.
  final PartDecision? decision;

  /// True when a person is asked about this part.
  bool get needsReview => review != null;

  /// True when a person entered the value, so it has no basis to show.
  bool get editedByPerson => decision?.action == PartDecisionAction.edit;
}

/// One row of the tree, in reading order.
@immutable
class PartNode {
  const PartNode({required this.part, required this.depth, this.parent});

  /// The part.
  final FieldPart part;

  /// How many nodes lie between this one and the root of the tree. The
  /// broadest level is 0, and a part outside the place tree is always 0.
  final int depth;

  /// The part this one sits under, or null at the top.
  final FieldPart? parent;
}

/// A field's parts, or none.
@immutable
class FieldParts {
  const FieldParts._(this.parts, this.ignored);

  /// A field with no parts. What every record has today.
  static const FieldParts none = FieldParts._(<FieldPart>[], null);

  /// The parts, in the order the wire gave them. The place tree is drawn from
  /// `parent` ([tree]), not from this order.
  final List<FieldPart> parts;

  /// Why a list was set aside, as a short code, or null when it was read or
  /// absent. For tests and diagnostics: never shown as copy.
  final String? ignored;

  /// True when there is nothing to draw.
  bool get isEmpty => parts.isEmpty;

  /// True when there is something to draw.
  bool get isNotEmpty => parts.isNotEmpty;

  /// The parts a person is asked about.
  List<FieldPart> get flagged => <FieldPart>[
    for (final FieldPart part in parts)
      if (part.needsReview) part,
  ];

  /// The part named [path], or null.
  FieldPart? byPath(String path) {
    for (final FieldPart part in parts) {
      if (part.path.text == path) return part;
    }
    return null;
  }

  /// The rows in reading order: each node, then the nodes under it.
  ///
  /// A part outside the place tree, or whose parent is the root, is at the top.
  /// Siblings keep the order the wire gave them. The rules [read] checks mean
  /// every part has a parent in the list or the root and no chain loops, so
  /// every part appears exactly once.
  List<PartNode> get tree {
    final Map<String, List<FieldPart>> under = <String, List<FieldPart>>{};
    final List<FieldPart> top = <FieldPart>[];
    for (final FieldPart part in parts) {
      final PartPath? parent = part.parent;
      if (parent == null || parent.isRoot) {
        top.add(part);
      } else {
        (under[parent.text] ??= <FieldPart>[]).add(part);
      }
    }
    final List<PartNode> rows = <PartNode>[];
    void walk(FieldPart part, int depth, FieldPart? parent) {
      rows.add(PartNode(part: part, depth: depth, parent: parent));
      for (final FieldPart child in under[part.path.text] ?? const []) {
        walk(child, depth + 1, part);
      }
    }

    for (final FieldPart part in top) {
      walk(part, 0, null);
    }
    return rows;
  }

  /// The parts of [field], a field map as the workspace builds it.
  static FieldParts of(Json field) =>
      read(field['parts'], fieldKey: field['field_key']?.toString() ?? '');

  /// The parts [raw] holds for the field [fieldKey], or none.
  ///
  /// Absent, null and empty give [none]. A list that breaks a rule of the
  /// contract or a bound gives none with [ignored] set. Nothing here throws.
  static FieldParts read(Object? raw, {required String fieldKey}) {
    if (raw == null) return none;
    if (raw is! List<Object?>) {
      return const FieldParts._(<FieldPart>[], 'not_a_list');
    }
    if (raw.isEmpty) return none;
    if (raw.length > maxPartsPerField) {
      return const FieldParts._(<FieldPart>[], 'too_many_parts');
    }
    try {
      if (utf8.encode(jsonEncode(raw)).length > maxPartBytesPerField) {
        return const FieldParts._(<FieldPart>[], 'too_large');
      }
    } on Object {
      // A value JSON cannot carry never came off the wire.
      return const FieldParts._(<FieldPart>[], 'not_json');
    }
    try {
      final List<FieldPart> parts = _readAll(raw, fieldKey);
      return parts.isEmpty ? none : FieldParts._(parts, null);
    } on _Malformed catch (problem) {
      return FieldParts._(const <FieldPart>[], problem.code);
    } on Object {
      // A shape the reader did not foresee is still not a crash.
      return const FieldParts._(<FieldPart>[], 'unreadable');
    }
  }
}

/// A rule of the contract that a list breaks.
class _Malformed implements Exception {
  const _Malformed(this.code);

  final String code;
}

List<FieldPart> _readAll(List<Object?> raw, String fieldKey) {
  final List<FieldPart> parts = <FieldPart>[];
  final Set<String> seen = <String>{};
  for (final Object? entry in raw) {
    if (entry is! Map) throw const _Malformed('not_an_object');
    final Map<Object?, Object?> map = entry;
    final Object? rawPath = map['path'];
    if (rawPath is! String ||
        rawPath.isEmpty ||
        rawPath.length > maxPartPathLength) {
      throw const _Malformed('bad_path');
    }
    final PartPath? path = PartPath.tryParse(rawPath);
    // A path a later release may add, or one that belongs to another field, is
    // left out: the field shows its own value as it always has.
    if (path == null) continue;
    if (path.isRoot) throw const _Malformed('root_as_part');
    if (path.carrierField != fieldKey) continue;
    if (!seen.add(path.text)) throw const _Malformed('duplicate_path');
    parts.add(_readPart(map, path));
  }

  // Rule 5: `parent` names a part in the list or the root, and no chain loops.
  final Set<String> paths = <String>{
    for (final FieldPart p in parts) p.path.text,
  };
  final Map<String, FieldPart> byPath = <String, FieldPart>{
    for (final FieldPart p in parts) p.path.text: p,
  };
  for (final FieldPart part in parts) {
    final PartPath? parent = part.parent;
    if (parent != null && !parent.isRoot && !paths.contains(parent.text)) {
      throw const _Malformed('parent_missing');
    }
  }
  for (final FieldPart part in parts) {
    final Set<String> walked = <String>{part.path.text};
    PartPath? next = part.parent;
    while (next != null && !next.isRoot) {
      if (!walked.add(next.text)) throw const _Malformed('parent_loop');
      next = byPath[next.text]?.parent;
    }
  }
  return parts;
}

FieldPart _readPart(Map<Object?, Object?> map, PartPath path) {
  final Object? rawState = map['state'];
  if (rawState is! String || !knownFieldStates.contains(rawState)) {
    throw const _Malformed('bad_state');
  }
  final String state = rawState;
  final String? value = _text(map, 'value');
  final String? wording = _text(map, 'wording');
  final String? authorityId = _text(map, 'authority_id');
  final bool basisStated = map['basis'] != null;
  if (basisStated && map['basis'] is! String) {
    throw const _Malformed('bad_basis');
  }
  final ValueBasis? basis = ValueBasis.fromWire(map['basis']);

  final PartDecision? decision = _readDecision(map['decision']);
  final PartReview? review = _readReview(map['review']);
  final bool edited = decision?.action == PartDecisionAction.edit;

  // Rule 2: a value only on a supported part, and a value and a basis together
  // except on a part a person edited.
  if (value != null && state != 'supported') {
    throw const _Malformed('value_on_unsupported_state');
  }
  if (state == 'supported' && value == null) {
    throw const _Malformed('supported_without_value');
  }
  if (value != null && !basisStated && !edited) {
    throw const _Malformed('value_without_basis');
  }
  if (value == null && basisStated) {
    throw const _Malformed('basis_without_value');
  }
  // Rule 3.
  if (basis == ValueBasis.derived && wording == null) {
    throw const _Malformed('derived_without_wording');
  }

  // Rule 5, the part of it a single part can show: `parent` is on every place
  // part and on no other.
  final Object? rawParent = map['parent'];
  PartPath? parent;
  if (path.isLocation) {
    parent = PartPath.tryParse(rawParent);
    if (parent == null ||
        rawParent is! String ||
        rawParent.length > maxPartPathLength) {
      throw const _Malformed('bad_parent');
    }
  } else if (rawParent != null) {
    throw const _Malformed('parent_outside_location');
  }

  final List<PartPath> derivedFrom = <PartPath>[];
  final Object? rawDerived = map['derived_from'];
  if (rawDerived != null) {
    if (rawDerived is! List<Object?> ||
        rawDerived.length > maxPartDerivedFrom) {
      throw const _Malformed('bad_derived_from');
    }
    for (final Object? item in rawDerived) {
      final PartPath? from = item is String && item.length <= maxPartPathLength
          ? PartPath.tryParse(item)
          : null;
      if (from == null || from == path) {
        throw const _Malformed('bad_derived_from');
      }
      derivedFrom.add(from);
    }
  }

  // Rule 4: every cited row has exactly one relation.
  final List<String> evidenceIds = _stringList(
    map['evidence_ids'],
    max: maxPartEvidenceIds,
    code: 'bad_evidence_ids',
  );
  if (evidenceIds.toSet().length != evidenceIds.length) {
    throw const _Malformed('duplicate_evidence');
  }
  final Object? rawRelations = map['evidence_relations'];
  final Map<String, PartRelation> relations = <String, PartRelation>{};
  if (rawRelations != null) {
    if (rawRelations is! Map) throw const _Malformed('bad_evidence_relations');
    for (final MapEntry<Object?, Object?> entry in rawRelations.entries) {
      final PartRelation? relation = PartRelation.fromWire(entry.value);
      if (entry.key is! String || relation == null) {
        throw const _Malformed('bad_evidence_relations');
      }
      relations[entry.key! as String] = relation;
    }
  }
  if (relations.length != evidenceIds.length ||
      !relations.keys.toSet().containsAll(evidenceIds)) {
    throw const _Malformed('relations_do_not_match_evidence');
  }
  if (state == 'supported' && decision == null && evidenceIds.isEmpty) {
    throw const _Malformed('supported_without_evidence');
  }

  // Rule 7 and the bound on alternatives.
  final Object? rawAlternatives = map['alternatives'];
  final List<PartAlternative> alternatives = <PartAlternative>[];
  if (rawAlternatives != null) {
    if (rawAlternatives is! List<Object?> ||
        rawAlternatives.length > maxPartAlternatives) {
      throw const _Malformed('bad_alternatives');
    }
    for (final Object? item in rawAlternatives) {
      if (item is! Map) throw const _Malformed('bad_alternatives');
      final String? altValue = _text(item, 'value');
      if (altValue == null) throw const _Malformed('bad_alternatives');
      final Object? altBasis = item['basis'];
      if (altBasis != null && altBasis is! String) {
        throw const _Malformed('bad_alternatives');
      }
      final List<String> altEvidence = _stringList(
        item['evidence_ids'],
        max: maxAlternativeEvidenceIds,
        code: 'bad_alternatives',
      );
      if (!evidenceIds.toSet().containsAll(altEvidence)) {
        throw const _Malformed('alternative_evidence_not_cited');
      }
      alternatives.add(
        PartAlternative(
          value: altValue,
          basis: ValueBasis.fromWire(altBasis),
          wording: _text(item, 'wording'),
          evidenceIds: altEvidence,
        ),
      );
    }
  }

  // Rules 2 and 6: the shapes of an ambiguous part and of a review.
  if (state == 'ambiguous' &&
      (alternatives.length < 2 || review?.code != PartReviewCode.conflict)) {
    throw const _Malformed('ambiguous_shape');
  }
  if (review?.code == PartReviewCode.noSupport && value != null) {
    throw const _Malformed('no_support_with_value');
  }
  if (review?.code == PartReviewCode.conflict &&
      alternatives.isEmpty &&
      state != 'ambiguous') {
    throw const _Malformed('conflict_without_alternatives');
  }

  return FieldPart(
    path: path,
    state: state,
    value: value,
    basis: basis,
    basisStated: basisStated,
    wording: wording,
    parent: parent,
    authorityId: authorityId,
    derivedFrom: derivedFrom,
    evidenceIds: evidenceIds,
    evidenceRelations: relations,
    alternatives: alternatives,
    review: review,
    decision: decision,
  );
}

PartReview? _readReview(Object? raw) {
  if (raw == null) return null;
  if (raw is! Map) throw const _Malformed('bad_review');
  final String? reason = _text(raw, 'reason');
  final Object? code = raw['code'];
  if (reason == null || code is! String) throw const _Malformed('bad_review');
  // A code this app does not know is read as a doubt (contract 3.5).
  final PartReviewCode known = PartReviewCode.values.firstWhere(
    (PartReviewCode c) => c.wire == code,
    orElse: () => PartReviewCode.doubt,
  );
  return PartReview(code: known, reason: reason);
}

PartDecision? _readDecision(Object? raw) {
  if (raw == null) return null;
  if (raw is! Map) throw const _Malformed('bad_decision');
  return PartDecision(
    action: PartDecisionAction.fromWire(raw['action']),
    at: _text(raw, 'at'),
  );
}

/// A text member: absent when missing or null, otherwise 1 to
/// [maxPartTextLength] characters with no control character.
String? _text(Map<Object?, Object?> map, String key) {
  final Object? value = map[key];
  if (value == null) return null;
  if (value is! String ||
      value.isEmpty ||
      value.runes.length > maxPartTextLength ||
      _controlCharacter.hasMatch(value)) {
    throw _Malformed('bad_$key');
  }
  return value;
}

List<String> _stringList(
  Object? raw, {
  required int max,
  required String code,
}) {
  if (raw == null) return const <String>[];
  if (raw is! List<Object?> || raw.length > max) throw _Malformed(code);
  final List<String> out = <String>[];
  for (final Object? item in raw) {
    if (item is! String ||
        item.isEmpty ||
        item.runes.length > maxPartTextLength ||
        _controlCharacter.hasMatch(item)) {
      throw _Malformed(code);
    }
    out.add(item);
  }
  return out;
}

// ---------------------------------------------------------------------------
// What a part reads as on screen.
// ---------------------------------------------------------------------------

/// The longest a value runs inside a sentence before it is cut (contract 5).
const int sentenceValueLength = 40;

/// [text] cut to [sentenceValueLength] characters, with an ellipsis where it
/// was cut, so a long value stays one clause of a sentence.
String sentenceValue(String text) => text.runes.length <= sentenceValueLength
    ? text
    : '${String.fromCharCodes(text.runes.take(sentenceValueLength - 1))}…';

/// A count of readings as the first word of a sentence: "Two readings
/// differ" (UX writing 2.3).
String _countWord(int count) => switch (count) {
  2 => 'Two',
  3 => 'Three',
  4 => 'Four',
  5 => 'Five',
  _ => '$count',
};

extension FieldPartPresentation on FieldPart {
  /// What the value slot says: the value in its unit, or the state in words
  /// where there is no value. Absence is words, never a blank (UX writing,
  /// rule 14).
  String get valueText {
    final String? text = value;
    if (text == null) return vocabularyLabel(state);
    return switch (path.text) {
      'elevation/from' || 'elevation/to' => '$text m',
      'elevation/unit' => switch (text) {
        'ft' => 'Feet',
        'm' => 'Metres',
        _ => text,
      },
      'elevation/kind' => _sentence(text),
      _ => text,
    };
  }

  /// The label's own words, when they say something the value does not.
  ///
  /// Shown beneath an interpreted value (UX writing 1.13; PRD rule 4). A
  /// wording that is the value itself is not repeated.
  String? get originalWording {
    final String? words = wording;
    if (words == null || words.trim() == value?.trim()) return null;
    return words;
  }

  /// The values a conflict is between: the part's own, then each alternative.
  List<String> get conflictValues => <String>[
    ?value,
    for (final PartAlternative alternative in alternatives) alternative.value,
  ];
}

/// The sentence a part's review states in the row, or null when the chip is
/// all it needs (UX writing 2.4, data ambiguity: the source is the subject).
///
/// - A conflict names what differs, with each value cut to 40 characters:
///   "Two readings differ: Werner, Wermer." It says "sources" where an
///   alternative rests on a lookup and not on a reading.
/// - No support says so: "No source supports this part."
/// - A doubt has no sentence of its own. Its reason is the writer's own words,
///   and sits behind "Why" (UX writing, rule 13).
///
/// [evidenceKinds] maps an evidence id to its kind, so a conflict can tell a
/// disagreement between readings from one between sources.
String? partReviewSentence(
  FieldPart part, {
  Map<String, String> evidenceKinds = const <String, String>{},
}) {
  final PartReview? review = part.review;
  if (review == null) return null;
  switch (review.code) {
    case PartReviewCode.conflict:
      final List<String> values = part.conflictValues;
      if (values.length < 2) return null;
      final String subject = partConflictSubject(part, evidenceKinds);
      return '${_countWord(values.length)} $subject differ: '
          '${values.map(sentenceValue).join(', ')}.';
    case PartReviewCode.noSupport:
      return 'No source supports this part.';
    case PartReviewCode.doubt:
      return null;
  }
}

/// What a conflict is between: `readings`, or `sources` where an alternative
/// rests on a row that is not a reading. With no row to tell, readings, which
/// is what the contract's headline says.
String partConflictSubject(FieldPart part, Map<String, String> evidenceKinds) {
  for (final PartAlternative alternative in part.alternatives) {
    for (final String id in alternative.evidenceIds) {
      final String? kind = evidenceKinds[id];
      if (kind != null && kind != 'literal') return 'sources';
    }
  }
  return 'readings';
}
