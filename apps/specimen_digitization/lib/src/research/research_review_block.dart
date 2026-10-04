import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'research_models.dart';

/// Why a field waits for a person, in the owner's three cases and the two
/// states the research card already names.
///
/// The case is chosen only from what the server sent. The label lacking a
/// value is claimed only when the research marked it not present: a field that
/// waits for a source or a rule can also be a value the label does carry, so
/// those two say what is known and no more.
enum ResearchReviewCase {
  /// The research marked the value as not on the label.
  labelLacksValue,

  /// Public sources searched and none settled the field.
  sourcesCouldNotSettle,

  /// Sources returned several possibilities and none was chosen.
  severalPossibilities,

  /// Readings or sources disagree and none was chosen.
  evidenceDisagrees,

  /// Waiting for an approved rule.
  noRule,

  /// Waiting for a source.
  noSource;

  /// The one sentence a reviewer reads first (02 section 4.15: true on its
  /// own, 120 characters or fewer).
  String get headline => switch (this) {
    labelLacksValue => 'This field is not on the label.',
    sourcesCouldNotSettle => 'Public sources could not settle this field.',
    severalPossibilities =>
      'Several possibilities remain. The research could not choose between them.',
    evidenceDisagrees =>
      'The readings or sources disagree. The research could not choose between them.',
    noRule => 'No approved rule settles this field yet.',
    noSource => 'No source has settled this field yet.',
  };
}

/// Whether a work state is one a person decides, so a review block belongs.
bool researchReviewApplies(ResearchWorkState state) =>
    state == ResearchWorkState.waitingHuman ||
    state == ResearchWorkState.waitingSource ||
    state == ResearchWorkState.waitingPolicy;

/// The case for [field], from the harness's own codes.
ResearchReviewCase researchReviewCase(ResearchFieldThread field) {
  final review = field.review;
  switch (review?.questionReason) {
    case 'semantic_ambiguity':
      return ResearchReviewCase.severalPossibilities;
    case 'evidence_conflict':
      return ResearchReviewCase.evidenceDisagrees;
    case 'scoped_absence':
      return ResearchReviewCase.sourcesCouldNotSettle;
  }
  if (field.value.state == 'not_present') {
    return ResearchReviewCase.labelLacksValue;
  }
  return field.workState == ResearchWorkState.waitingPolicy
      ? ResearchReviewCase.noRule
      : ResearchReviewCase.noSource;
}

/// The reader's name for a source the server names by id.
String researchSourceName(String sourceId) => switch (sourceId) {
  'global_names_verifier' => 'Global Names Verifier',
  'catalogue_of_life' => 'Catalogue of Life',
  'gbif' => 'GBIF',
  'bugguide' => 'BugGuide',
  'mapcarta' => 'Mapcarta',
  'geolocate' => 'GEOLocate',
  'field_museum_ipt' => 'Field Museum IPT',
  'field_museum_emudata' => 'Field Museum EMu data',
  _ => 'Research source',
};

/// What a lookup outcome means to a reviewer.
String researchOutcomeLabel(String? outcome) => switch (outcome) {
  'success' => 'Match found',
  'ambiguous' => 'Several matches',
  'no_match' => 'No match',
  'policy_blocked' => 'Not searched',
  _ => 'No answer',
};

/// Reason codes the harness writes where a person would read prose.
const _knownReasonCodes = <String, String>{
  'missing_policy:verbatim_dts_definition_examples':
      'The definition and examples for this field have not been supplied.',
};

/// The reason as prose, or null when it is a code with no reader's sentence.
String? researchReasonText(String? reason) {
  if (reason == null) return null;
  final known = _knownReasonCodes[reason];
  if (known != null) return known;
  return RegExp(r'^[a-z0-9_]+(?::[a-z0-9_]+)*$').hasMatch(reason)
      ? null
      : reason;
}

final _typedStatusPrefix = RegExp(r'^(?:success|no_match|ambiguous)(?:: )?');

/// A source's own explanation without the typed status it leads with.
String? _sourceNote(String? note) {
  if (note == null) return null;
  final text = note.replaceFirst(_typedStatusPrefix, '').trim();
  return text.isEmpty ? null : text;
}

/// The harness's findings for one field that waits for a person.
///
/// Read-only: the server installs no way to answer a question or choose a
/// possibility, so nothing here is pressable. The layout follows the width it
/// is given, never the platform: possibilities stack in one column below the
/// medium window class and sit in two from it.
class ResearchReviewBlock extends StatelessWidget {
  const ResearchReviewBlock({
    super.key,
    required this.fieldLabel,
    required this.field,
  });

  final String fieldLabel;
  final ResearchFieldThread field;

  /// Two columns from the width Material 3 calls medium.
  static const double twoColumnMinWidth = WindowClass.mediumMin;

  @override
  Widget build(BuildContext context) {
    final review = field.review;
    if (review == null || !researchReviewApplies(field.workState)) {
      return const SizedBox.shrink();
    }
    final ui = context.ui;
    final reviewCase = researchReviewCase(field);
    final reason = researchReasonText(review.reason);
    final candidates = review.candidates;
    final children = <Widget>[
      _Heading('Why it is unresolved'),
      // A live region announces when its words change and never again for a
      // rebuild with the same words (06 section 3).
      Announcer(child: Text(reviewCase.headline, style: ui.type.body)),
      if (reason != null) ...[
        _Heading('What the research found'),
        Text(reason, style: _secondary(context)),
      ],
      if (candidates.isNotEmpty ||
          reviewCase == ResearchReviewCase.severalPossibilities) ...[
        _Heading('Possibilities found'),
        if (candidates.isEmpty)
          Text(
            'No possibilities were recorded for this field.',
            style: _secondary(context),
          )
        else
          LayoutBuilder(
            builder: (context, constraints) =>
                _candidates(context, constraints),
          ),
        if (review.candidatesNotShown > 0)
          Text(
            review.candidatesNotShown == 1
                ? '1 more possibility is not shown.'
                : '${review.candidatesNotShown} more possibilities are not shown.',
            style: _secondary(context),
          ),
      ],
      if (review.evidence.isNotEmpty || review.evidenceNotShown > 0) ...[
        _Heading('Sources checked'),
        for (final item in review.evidence) _evidence(context, item),
        if (review.evidenceNotShown > 0)
          Text(
            review.evidenceNotShown == 1
                ? '1 source reference is not shown here.'
                : '${review.evidenceNotShown} source references are not shown here.',
            style: _secondary(context),
          ),
      ],
    ];
    return Semantics(
      container: true,
      label: '$fieldLabel: ${reviewCase.headline}',
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < children.length; i++) ...[
            if (i > 0) SizedBox(height: ui.space.s2),
            children[i],
          ],
        ],
      ),
    );
  }

  TextStyle _secondary(BuildContext context) =>
      context.ui.type.bodySmall.copyWith(color: context.ui.color.inkSecondary);

  Widget _candidates(BuildContext context, BoxConstraints constraints) {
    final ui = context.ui;
    final candidates = field.review!.candidates;
    final evidence = {
      for (final item in field.review!.evidence) item.evidenceId: item,
    };
    final tiles = [
      for (var i = 0; i < candidates.length; i++)
        _CandidateTile(
          candidate: candidates[i],
          position: i + 1,
          total: candidates.length,
          evidence: evidence[candidates[i].evidenceId],
        ),
    ];
    final columns = constraints.maxWidth >= twoColumnMinWidth ? 2 : 1;
    if (columns == 1) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < tiles.length; i++) ...[
            if (i > 0) SizedBox(height: ui.space.s2),
            tiles[i],
          ],
        ],
      );
    }
    final width = (constraints.maxWidth - ui.space.s2) / columns;
    return Wrap(
      spacing: ui.space.s2,
      runSpacing: ui.space.s2,
      children: [for (final tile in tiles) SizedBox(width: width, child: tile)],
    );
  }

  Widget _evidence(BuildContext context, ResearchReviewEvidence item) {
    final ui = context.ui;
    final note = _sourceNote(item.note);
    final lines = <String>[
      if (item.searchedText != null) 'Searched for “${item.searchedText}”',
      if (item.quote != null) 'Quoted “${item.quote}”',
      ?note,
    ];
    return Semantics(
      container: true,
      label:
          '${researchSourceName(item.sourceId)}, '
          '${researchOutcomeLabel(item.outcome)}',
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '${researchSourceName(item.sourceId)} · '
            '${researchOutcomeLabel(item.outcome)}',
            style: ui.type.body,
          ),
          for (final line in lines) Text(line, style: _secondary(context)),
        ],
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);
  final String text;

  @override
  Widget build(BuildContext context) =>
      Semantics(header: true, child: Text(text, style: context.ui.type.label));
}

/// One possibility, as the source named it, with where it came from.
class _CandidateTile extends StatelessWidget {
  const _CandidateTile({
    required this.candidate,
    required this.position,
    required this.total,
    required this.evidence,
  });

  final ResearchReviewCandidate candidate;
  final int position;
  final int total;
  final ResearchReviewEvidence? evidence;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final secondary = ui.type.bodySmall.copyWith(color: ui.color.inkSecondary);
    final distance = candidate.distanceKm;
    final where = [
      ...candidate.details,
      if (distance != null) '$distance km from the estimated location',
    ].join(' · ');
    final searched = evidence?.searchedText;
    final from = [
      researchSourceName(candidate.sourceId),
      if (searched != null) 'Searched for “$searched”',
    ].join(' · ');
    final identifier = candidate.authorityId;
    return Semantics(
      key: ValueKey('review-candidate-$position'),
      container: true,
      label: 'Possibility $position of $total',
      child: Surface(
        hairline: true,
        radius: ui.shape.inner,
        padding: EdgeInsetsDirectional.all(ui.space.s3),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(candidate.label, style: ui.type.title),
            if (where.isNotEmpty) ...[
              SizedBox(height: ui.space.s1),
              Text(where, style: secondary),
            ],
            SizedBox(height: ui.space.s1),
            Text(from, style: secondary),
            if (identifier != null) ...[
              SizedBox(height: ui.space.s1),
              Text(
                identifier,
                style: ui.type.mono.identifier,
                semanticsLabel: 'Identifier $identifier',
              ),
            ],
          ],
        ),
      ),
    );
  }
}
