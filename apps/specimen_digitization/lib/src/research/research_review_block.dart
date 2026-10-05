import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../vocabulary.dart';
import 'derivation_models.dart';
import 'research_models.dart';

/// Why a field waits for a person, in the owner's three cases and the two
/// states the research card already names.
///
/// The case is chosen only from what the server sent. The label lacking a
/// value is claimed only when the research marked it not present: a field that
/// waits for a source or a rule can also be a value the label does carry, so
/// those two say what is known and no more.
enum ResearchReviewCase {
  /// The research marked the value as not present. Nothing in the server
  /// assigns that mark today (the prompts return `unresolved`, and the
  /// harness stops at waiting for a source or a rule), so the owner's first
  /// case usually reads as [noSource] or [noRule] with the harness's reason.
  labelLacksValue,

  /// Public sources searched and none settled the field.
  sourcesCouldNotSettle,

  /// Sources returned several possibilities and none was chosen.
  severalPossibilities,

  /// Readings or sources disagree and none was chosen.
  evidenceDisagrees,

  /// A retained computed value awaiting a person's decision.
  derivedProposal,

  /// Waiting for an approved rule.
  noRule,

  /// Waiting for a source.
  noSource;

  /// The one sentence a reviewer reads first (02 section 4.15: true on its
  /// own, 120 characters or fewer).
  String get headline => switch (this) {
    labelLacksValue => 'The research found no value on the label.',
    sourcesCouldNotSettle => 'Public sources could not settle this field.',
    severalPossibilities =>
      'Several possibilities remain. The research could not choose between them.',
    evidenceDisagrees =>
      'The readings or sources disagree. The research could not choose between them.',
    derivedProposal =>
      'A proposed value is ready for review. It has not been applied.',
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
    case 'derived_proposal':
      return ResearchReviewCase.derivedProposal;
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
  'missing_policy:unstructured_label_event_unqualified':
      'The label is not laid out as named fields, and no approved rule reads a field from such a label yet.',
};

final _wholeReasonCode = RegExp(r'^[a-z0-9_]+(?::[a-z0-9_]+)*$');
final _leadingReasonCode = RegExp(
  r'^([a-z0-9_]+:[a-z0-9_]+)(?:\s+([\s\S]*))?$',
);

/// The reason as lines a reviewer reads, never a machine code.
///
/// The harness writes either prose, or a code alone, or (prompt v4) a code
/// followed by what the readings show: `missing_policy:<code> <prose>`. A known
/// code becomes one plain sentence, an unknown code is dropped, and prose is
/// kept as written.
List<String> researchReasonLines(String? reason) {
  final text = reason?.trim();
  if (text == null || text.isEmpty) return const [];
  if (_wholeReasonCode.hasMatch(text)) {
    final known = _knownReasonCodes[text];
    return known == null ? const [] : [known];
  }
  final match = _leadingReasonCode.firstMatch(text);
  if (match == null) return [text];
  final prose = match[2]?.trim();
  return [
    ?_knownReasonCodes[match[1]],
    if (prose != null && prose.isNotEmpty) prose,
  ];
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
/// Displays retained server candidates and derivation suggestions. The layout
/// follows the width it is given, never the platform: possibilities stack in
/// one column below the medium window class and sit in two from it.
class ResearchReviewBlock extends StatelessWidget {
  const ResearchReviewBlock({
    super.key,
    required this.fieldLabel,
    required this.field,
    this.canSelectCandidates = false,
    this.onSelectCandidate,
    this.derivationProposals = const <ResearchDerivationProposal>[],
    this.canSelectDerivationProposals = false,
  });

  final String fieldLabel;

  /// Null when only retained derivation suggestions are available.
  final ResearchFieldThread? field;
  final bool canSelectCandidates;
  final ValueChanged<ResearchReviewCandidate>? onSelectCandidate;
  final List<ResearchDerivationProposal> derivationProposals;
  final bool canSelectDerivationProposals;

  /// Two columns from the width Material 3 calls medium.
  static const double twoColumnMinWidth = WindowClass.mediumMin;

  @override
  Widget build(BuildContext context) {
    final review = field?.review;
    final applies =
        field != null &&
        review != null &&
        researchReviewApplies(field!.workState);
    if (!applies && derivationProposals.isEmpty) {
      return const SizedBox.shrink();
    }
    final ui = context.ui;
    final reviewCase = applies ? researchReviewCase(field!) : null;
    final reasonLines = applies
        ? researchReasonLines(review.reason)
        : const <String>[];
    final candidates = review?.candidates ?? const <ResearchReviewCandidate>[];
    final children = <Widget>[
      if (applies) ...[
        _Heading('Why it is unresolved'),
        // A live region announces when its words change and never again for a
        // rebuild with the same words (06 section 3).
        Announcer(child: Text(reviewCase!.headline, style: ui.type.body)),
      ],
      if (reasonLines.isNotEmpty) ...[
        _Heading('What the research found'),
        for (final line in reasonLines) Text(line, style: _secondary(context)),
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
        if ((review?.candidatesNotShown ?? 0) > 0)
          Text(
            review!.candidatesNotShown == 1
                ? '1 more possibility is not shown.'
                : '${review.candidatesNotShown} more possibilities are not shown.',
            style: _secondary(context),
          ),
      ],
      if (review != null &&
          (review.evidence.isNotEmpty || review.evidenceNotShown > 0)) ...[
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
      if (derivationProposals.isNotEmpty) ...[
        _Heading('Location suggestions'),
        for (final proposal in derivationProposals)
          _DerivationProposalTile(
            proposal: proposal,
            selectable: canSelectDerivationProposals,
            onSelect: onSelectCandidate,
          ),
      ],
    ];
    return Semantics(
      container: true,
      label: applies
          ? '$fieldLabel: ${reviewCase!.headline}'
          : '$fieldLabel location suggestions',
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
    final candidates =
        field?.review?.candidates ?? const <ResearchReviewCandidate>[];
    final evidence = {
      for (final item
          in field?.review?.evidence ?? const <ResearchReviewEvidence>[])
        item.evidenceId: item,
    };
    final tiles = [
      for (var i = 0; i < candidates.length; i++)
        _CandidateTile(
          candidate: candidates[i],
          position: i + 1,
          total: candidates.length,
          evidence: evidence[candidates[i].evidenceId],
          selectable: canSelectCandidates,
          onSelect: onSelectCandidate,
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

class _DerivationProposalTile extends StatelessWidget {
  const _DerivationProposalTile({
    required this.proposal,
    required this.selectable,
    required this.onSelect,
  });

  final ResearchDerivationProposal proposal;
  final bool selectable;
  final ValueChanged<ResearchReviewCandidate>? onSelect;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final sources = proposal.inputFields.map(vocabularyLabel).join(' and ');
    final candidate = proposal.selectable
        ? ResearchReviewCandidate.fromDerivationProposal(proposal)
        : null;
    return Surface(
      hairline: true,
      radius: ui.shape.inner,
      padding: EdgeInsetsDirectional.all(ui.space.s3),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(proposal.value, style: ui.type.title),
          SizedBox(height: ui.space.s1),
          Text('Based on the reviewed $sources.', style: ui.type.bodySmall),
          if (onSelect != null) ...[
            SizedBox(height: ui.space.s2),
            UiButton(
              label: 'Use this suggestion',
              variant: UiButtonVariant.secondary,
              onPressed: selectable && candidate != null
                  ? () => onSelect!(candidate)
                  : null,
              disabledReason: selectable
                  ? 'This suggestion is not available for review.'
                  : 'Refresh research before reviewing this suggestion.',
              leading: UiIcons.check,
            ),
          ],
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
    required this.selectable,
    required this.onSelect,
  });

  final ResearchReviewCandidate candidate;
  final int position;
  final int total;
  final ResearchReviewEvidence? evidence;
  final bool selectable;
  final ValueChanged<ResearchReviewCandidate>? onSelect;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final secondary = ui.type.bodySmall.copyWith(color: ui.color.inkSecondary);
    final distance = candidate.distanceKm;
    final where = [
      ...candidate.details,
      if (distance != null) '$distance km from where the research expected it',
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
            if (candidate.selectionValue != null) ...[
              SizedBox(height: ui.space.s1),
              Text(
                'Proposed field value',
                style: ui.type.labelSmall.copyWith(
                  color: ui.color.inkSecondary,
                ),
              ),
              Text(candidate.selectionValue!, style: ui.type.body),
            ],
            if (onSelect != null) ...[
              SizedBox(height: ui.space.s2),
              UiButton(
                label: 'Use this possibility',
                semanticsLabel: 'Use possibility $position for this field',
                variant: UiButtonVariant.secondary,
                onPressed:
                    selectable &&
                        candidate.selectionId != null &&
                        candidate.selectionId!.isNotEmpty &&
                        candidate.selectionValue != null &&
                        candidate.selectionValue!.isNotEmpty
                    ? () => onSelect!(candidate)
                    : null,
                disabledReason: selectable
                    ? 'This possibility has no verified selection receipt or exact field value.'
                    : 'This field is read-only or the research result is no longer actionable.',
                leading: UiIcons.check,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
