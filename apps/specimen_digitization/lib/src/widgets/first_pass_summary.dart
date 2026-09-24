/// How one label region's transcript was decided, and what each reader
/// handed to the harness (UI.md T2.2; PLAN 4.7).
///
/// Said in words, in the order a reviewer asks: who decided, what they
/// decided, why, with which model and prompt, and then, reader by reader,
/// whether the harness got the decided transcript or that reader's own raw
/// reading (G19: when nothing was chosen, every reader hands its own).
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../thread/thread.dart';
import '../vocabulary.dart';

/// The decision for one region, or its absence.
class FirstPassSummary extends StatelessWidget {
  /// The summary of [firstPass], which is null when no decision is recorded,
  /// and of a reviewer's decision after it.
  const FirstPassSummary({
    super.key,
    required this.firstPass,
    required this.readerName,
    required this.run,
    this.reviewerDecision,
  });

  /// The decision, as the thread carries it.
  final ThreadFirstPass? firstPass;

  /// A reviewer's decision on the region, shown after what the readers
  /// handed on, in the order the thread ran. The model's decision stays
  /// above it (G38).
  final ThreadReviewerDecision? reviewerDecision;

  /// The name a reader goes by on this screen, from its observation id.
  final String Function(String? observationId) readerName;

  /// The run, whose step and blocker say why a decision is missing.
  final ThreadRun run;

  /// The heading over the readers' handoffs.
  static const String handedTitle = 'Handed to the harness';

  /// A region with no recorded decision.
  static const String noDecision = 'No decision recorded';

  /// Every reading was the same text.
  static const String readingsMatch = 'The readings match';

  /// The first pass ran and chose none of the readings.
  static const String choseNone = 'The first pass chose no reading';

  /// A reviewer decided it, which need not resolve it.
  static const String reviewer = 'Decided by a reviewer';

  /// The decision leaves the transcript unresolved (DATA_CONTRACT.md section
  /// 4.2). The workspace's `resolved` flag cannot say this: it means only
  /// that a reading was selected.
  static const String notResolved = 'Transcription not resolved';

  /// The first pass chose [reader]'s reading.
  static String chose(String reader) => 'The first pass chose $reader';

  /// The label over the decided transcript.
  static const String decidedLabel = 'Decided transcript';

  /// The words for where a text came from: the decided transcript, a
  /// reader's own raw reading, or a reviewer's text. An input source this
  /// client does not know keeps the server's word.
  static String sourceWords(ThreadInputSource? source, String? name) =>
      switch (source) {
        ThreadInputSource.decidedTranscript => 'decided transcript',
        ThreadInputSource.rawReading => 'raw reading',
        ThreadInputSource.review => "reviewer's text",
        null => vocabularyLabel(name ?? 'not recorded'),
      };

  /// The words for what one reader handed over.
  static String handoff(String reader, ThreadHandoff handoff) =>
      '$reader · ${sourceWords(handoff.source, handoff.roleName)}';

  String _title(ThreadFirstPass pass) => switch (pass.kind) {
    ThreadDecisionKind.identicalReadings => readingsMatch,
    ThreadDecisionKind.firstPass =>
      pass.selectedObservationId == null
          ? choseNone
          : chose(readerName(pass.selectedObservationId)),
    ThreadDecisionKind.human => reviewer,
    null => vocabularyLabel(pass.kindName ?? 'not recorded'),
  };

  /// Where the run is, for a region with no decision: the step, and what
  /// blocks it in the words the blockers list uses.
  String get _where {
    final String step = vocabularyLabel(run.stage ?? 'not recorded');
    final String? blocker = run.blocker;
    return blocker == null
        ? 'Processing is at $step.'
        : 'Processing is blocked at $step: ${vocabularyLabel(blocker)}.';
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final TextStyle secondary = ui.type.bodySmall.copyWith(
      color: ui.color.inkSecondary,
    );
    final ThreadFirstPass? pass = firstPass;
    final ThreadReviewerDecision? review = reviewerDecision;
    final Widget? reviewed = review == null
        ? null
        : _Decision(
            title: reviewer,
            unresolved: review.unresolved == true,
            decided: review.decidedText,
            rationale: review.rationale,
          );
    if (pass == null) {
      // A reviewer's decision is a recorded decision, so "No decision
      // recorded" is only for a region with neither.
      if (reviewed != null) return reviewed;
      return Semantics(
        container: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(noDecision, style: ui.type.label),
            Text(_where, style: secondary),
          ],
        ),
      );
    }
    final ThreadModelCall? call = pass.modelCall;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _Decision(
          title: _title(pass),
          unresolved: pass.unresolved == true,
          decided: pass.decidedText,
          rationale: pass.rationale,
          provenance: call == null
              ? null
              : <String>[
                  ?call.model,
                  ?call.provider,
                  if (call.promptVersion case final String prompt)
                    'Prompt $prompt',
                ].join(' · '),
        ),
        if (pass.handoffs.isNotEmpty) ...<Widget>[
          SizedBox(height: ui.space.s3),
          Text(handedTitle, style: ui.type.label),
          for (final ThreadHandoff item in pass.handoffs)
            Padding(
              padding: EdgeInsetsDirectional.only(top: ui.space.s2),
              child: Semantics(
                container: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text(
                      handoff(readerName(item.observationId), item),
                      style: secondary,
                    ),
                    if (item.handedText case final String text)
                      Text(text, style: ui.type.mono.literalDense),
                    if (item.note case final String note)
                      Text(note, style: secondary),
                  ],
                ),
              ),
            ),
        ],
        if (reviewed != null) ...<Widget>[
          SizedBox(height: ui.space.s3),
          reviewed,
        ],
      ],
    );
  }
}

/// One decision, as one announcement: who decided, whether it left the
/// transcript unresolved, what was decided, why, and, for the first pass,
/// its model and prompt.
class _Decision extends StatelessWidget {
  const _Decision({
    required this.title,
    required this.unresolved,
    required this.decided,
    required this.rationale,
    this.provenance,
  });

  final String title;
  final bool unresolved;
  final String? decided;
  final String? rationale;
  final String? provenance;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final TextStyle secondary = ui.type.bodySmall.copyWith(
      color: ui.color.inkSecondary,
    );
    return Semantics(
      container: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(title, style: ui.type.label),
          if (unresolved)
            Text(FirstPassSummary.notResolved, style: ui.type.bodySmall),
          if (decided case final String text) ...<Widget>[
            SizedBox(height: ui.space.s1),
            Text(FirstPassSummary.decidedLabel, style: secondary),
            Text(text, style: ui.type.mono.literalDense),
          ],
          if (rationale case final String reason) ...<Widget>[
            SizedBox(height: ui.space.s1),
            Text(reason, style: ui.type.bodySmall),
          ],
          if (provenance case final String line) Text(line, style: secondary),
        ],
      ),
    );
  }
}
