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
  /// The summary of [firstPass], which is null when no decision is recorded.
  const FirstPassSummary({
    super.key,
    required this.firstPass,
    required this.readerName,
    required this.run,
  });

  /// The decision, as the thread carries it.
  final ThreadFirstPass? firstPass;

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
    if (pass == null) {
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
    final String? decided = pass.decidedText;
    final String? rationale = pass.rationale;
    final ThreadModelCall? call = pass.modelCall;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Semantics(
          container: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(_title(pass), style: ui.type.label),
              if (pass.unresolved == true)
                Text(notResolved, style: ui.type.bodySmall),
              if (decided != null) ...<Widget>[
                SizedBox(height: ui.space.s1),
                Text(decidedLabel, style: secondary),
                Text(decided, style: ui.type.mono.literalDense),
              ],
              if (rationale != null) ...<Widget>[
                SizedBox(height: ui.space.s1),
                Text(rationale, style: ui.type.bodySmall),
              ],
              if (call != null)
                Text(
                  <String>[
                    ?call.model,
                    ?call.provider,
                    if (call.promptVersion case final String prompt)
                      'Prompt $prompt',
                  ].join(' · '),
                  style: secondary,
                ),
            ],
          ),
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
      ],
    );
  }
}
