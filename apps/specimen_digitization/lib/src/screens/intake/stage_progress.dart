/// Persisted milestones, not a time estimate or a percentage of processing.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../review_context.dart';
import '../../wall_time.dart';
import '../../widgets/upload_item.dart';
import 'manifest_entry.dart';

enum IntakeStage {
  upload('Upload', 'Uploading photo'),
  segment('Find labels', 'Finding labels'),
  read('Read labels', 'Reading the label'),
  compare('Compare readings', 'Comparing readings'),
  extract('Organise fields', 'Organising fields'),
  research('Check fields', 'Checking fields'),
  finalize('Finish record', 'Finishing the record'),
  queue('Main Queue', 'Moving to main Queue');

  const IntakeStage(this.label, this.activeLabel);
  final String label;
  final String activeLabel;
}

enum IntakeStageState {
  done('Done'),
  active('In progress'),
  waiting('Waiting'),
  retrying('Retry scheduled'),
  attention('Needs attention'),
  unknown('Not recorded');

  const IntakeStageState(this.label);
  final String label;
}

/// Immutable display snapshot: mutable manifest entries must not be retained
/// as the previous value when deciding whether a status has changed.
class IntakeProgress {
  const IntakeProgress(this.label, this.current, this.states);

  final String label;
  final IntakeStage? current;
  final List<IntakeStageState> states;

  static IntakeStage? _stage(Object? step) => switch (step) {
    'pin_dependencies' ||
    'classify' ||
    'quality_check' ||
    'segment' => IntakeStage.segment,
    'transcribe' => IntakeStage.read,
    'first_pass' || 'adjudicate' => IntakeStage.compare,
    'parse' => IntakeStage.extract,
    'plan' ||
    'lookup' ||
    'authority' ||
    'resolve' ||
    'normalize' ||
    'validate' ||
    'field_research' ||
    'field_recheck' => IntakeStage.research,
    'finalize' => IntakeStage.finalize,
    'finalized' => IntakeStage.queue,
    _ => null,
  };

  factory IntakeProgress.of(ManifestEntry entry) {
    final states = List<IntakeStageState>.filled(
      IntakeStage.values.length,
      IntakeStageState.waiting,
    );
    IntakeProgress at(
      String label,
      IntakeStage? stage,
      IntakeStageState state,
    ) {
      if (stage != null) states[stage.index] = state;
      return IntakeProgress(label, stage, states);
    }

    final saved = entry.specimenId != null || entry.settled;
    if (!saved) {
      if (entry.checking || entry.state == UploadState.checking) {
        return at(
          'Checking photo',
          IntakeStage.upload,
          IntakeStageState.active,
        );
      }
      return switch (entry.state) {
        UploadState.uploading => at(
          IntakeStage.upload.activeLabel,
          IntakeStage.upload,
          IntakeStageState.active,
        ),
        UploadState.failed || UploadState.interrupted => at(
          IntakeStageState.attention.label,
          IntakeStage.upload,
          IntakeStageState.attention,
        ),
        UploadState.skipped => at(
          'Not uploaded',
          IntakeStage.upload,
          IntakeStageState.attention,
        ),
        _ => at(
          'Waiting to upload',
          IntakeStage.upload,
          IntakeStageState.waiting,
        ),
      };
    }
    // A duplicate is not evidence that any processing stage has run.
    if (entry.state == UploadState.duplicate) {
      states.fillRange(0, states.length, IntakeStageState.unknown);
      return at(UploadState.duplicate.label, null, IntakeStageState.waiting);
    }
    states[IntakeStage.upload.index] = IntakeStageState.done;
    final specimen = entry.specimen;
    final progress = objectOf(specimen?.data['intake_progress']);
    final completed = progress['completed_stages'];
    if (completed is List) {
      for (final stage in IntakeStage.values) {
        if (completed.contains(stage.name)) {
          states[stage.index] = IntakeStageState.done;
        }
      }
    }
    if (entry.state == UploadState.inMainQueue) {
      // Older servers and early dispositions cannot certify every milestone.
      for (final stage in IntakeStage.values.skip(1)) {
        if (states[stage.index] != IntakeStageState.done) {
          states[stage.index] = IntakeStageState.unknown;
        }
      }
      return at(
        UploadState.inMainQueue.label,
        IntakeStage.queue,
        IntakeStageState.done,
      );
    }
    final step = progress['next_step'] ?? specimen?.data['stage'];
    final stage = _stage(step);
    if (stage != null) {
      for (final earlier in IntakeStage.values.skip(1).take(stage.index - 1)) {
        if (states[earlier.index] != IntakeStageState.done) {
          states[earlier.index] = IntakeStageState.unknown;
        }
      }
    }
    if (entry.checking) {
      return at('Checking status', stage, IntakeStageState.waiting);
    }
    if (specimen?.state == 'retry_scheduled') {
      final raw = progress['next_retry_at'];
      final instant = raw is String ? DateTime.tryParse(raw) : null;
      final retry = instant == null ? null : wallTime(instant);
      final label = retry == null
          ? IntakeStageState.retrying.label
          : 'Retrying at ${retry.hour.toString().padLeft(2, '0')}:'
                '${retry.minute.toString().padLeft(2, '0')}';
      return at(label, stage, IntakeStageState.retrying);
    }
    if (entry.state == UploadState.processingBlocked) {
      return at(
        IntakeStageState.attention.label,
        stage,
        IntakeStageState.attention,
      );
    }
    if (specimen?.state == 'pending' || entry.state == UploadState.accepted) {
      return at('Waiting to start', stage, IntakeStageState.waiting);
    }
    if (stage == null) {
      return at('Checking processing status', null, IntakeStageState.waiting);
    }
    return at(
      const <String>{
            'pin_dependencies',
            'classify',
            'quality_check',
          }.contains(step)
          ? 'Preparing photo'
          : stage.activeLabel,
      stage,
      IntakeStageState.active,
    );
  }
}

/// Eight equal milestones. Width conveys order only, never relative duration.
/// Only the status label is live; byte values and animation frames are silent.
class IntakeStageProgress extends StatelessWidget {
  const IntakeStageProgress({super.key, required this.entry});

  final ManifestEntry entry;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final progress = IntakeProgress.of(entry);
    final state = progress.current == null
        ? (entry.state == UploadState.processingBlocked
              ? IntakeStageState.attention
              : entry.specimen?.state == 'retry_scheduled'
              ? IntakeStageState.retrying
              : IntakeStageState.waiting)
        : progress.states[progress.current!.index];
    final color = switch (state) {
      IntakeStageState.attention => ui.color.status.blocked.content,
      IntakeStageState.retrying => ui.color.status.needsReview.content,
      _ => ui.color.inkSecondary,
    };
    final icon = switch (state) {
      IntakeStageState.attention => UiIcons.blocked,
      IntakeStageState.retrying => UiIcons.retry,
      IntakeStageState.done => UiIcons.cleared,
      IntakeStageState.active => UiIcons.processing,
      _ => UiIcons.time,
    };
    final contextLabel =
        progress.current != null &&
            progress.current != IntakeStage.upload &&
            (state == IntakeStageState.retrying ||
                state == IntakeStageState.attention ||
                state == IntakeStageState.waiting)
        ? progress.current!.label
        : null;
    final unrecorded = progress.states.contains(IntakeStageState.unknown);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Semantics(
          key: const ValueKey<String>('intake-stage-status'),
          container: true,
          liveRegion: true,
          label: [progress.label, ?contextLabel].join('. '),
          excludeSemantics: true,
          child: Row(
            children: <Widget>[
              UiIcon(icon, size: UiIconSize.inline, color: color),
              SizedBox(width: ui.space.s2),
              Expanded(
                child: Text(
                  progress.label,
                  style: ui.type.bodySmall.copyWith(color: color),
                ),
              ),
            ],
          ),
        ),
        SizedBox(height: ui.space.s2),
        Row(
          children: <Widget>[
            for (final stage in IntakeStage.values) ...<Widget>[
              if (stage.index > 0) SizedBox(width: ui.space.s1),
              Expanded(
                child: _StageSegment(
                  stage: stage,
                  state: progress.states[stage.index],
                  // Only upload has a measured denominator.
                  bytes:
                      stage == IntakeStage.upload &&
                          entry.state == UploadState.uploading
                      ? entry.progress
                      : null,
                ),
              ),
            ],
          ],
        ),
        if (contextLabel != null) ...<Widget>[
          SizedBox(height: ui.space.s1),
          ExcludeSemantics(
            child: Text(
              contextLabel,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          ),
        ],
        if (unrecorded) ...<Widget>[
          SizedBox(height: ui.space.s1),
          Text(
            'Some stages were not recorded.',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ],
      ],
    );
  }
}

class _StageSegment extends StatelessWidget {
  const _StageSegment({required this.stage, required this.state, this.bytes});
  final IntakeStage stage;
  final IntakeStageState state;
  final double? bytes;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final color = switch (state) {
      IntakeStageState.attention => ui.color.status.blocked.content,
      IntakeStageState.retrying => ui.color.status.needsReview.content,
      IntakeStageState.active => ui.color.status.processing.content,
      IntakeStageState.done => ui.color.inkSecondary,
      _ => ui.color.boundary,
    };
    return Semantics(
      container: true,
      label: '${stage.label}: ${state.label.toLowerCase()}',
      value: bytes == null
          ? null
          : '${(bytes! * 100).round()} percent uploaded',
      excludeSemantics: true,
      child: Container(
        key: ValueKey<String>('stage-${stage.name}-${state.name}'),
        height: ui.space.s2,
        decoration: BoxDecoration(
          color: state == IntakeStageState.done ? color : null,
          borderRadius: BorderRadius.circular(ui.shape.stroke.caretRadius),
          border: Border.all(
            color: color,
            width: state == IntakeStageState.attention
                ? ui.shape.stroke.emphasis
                : ui.shape.stroke.boundary,
          ),
        ),
        child: state == IntakeStageState.active
            ? Center(
                child: UiProgress.bar(
                  semanticsLabel: stage.activeLabel,
                  value: bytes,
                  color: color,
                ),
              )
            : state == IntakeStageState.retrying
            ? Center(
                child: SizedBox(
                  width: ui.space.s2,
                  child: Container(
                    height: ui.shape.stroke.emphasis,
                    color: color,
                  ),
                ),
              )
            : null,
      ),
    );
  }
}
