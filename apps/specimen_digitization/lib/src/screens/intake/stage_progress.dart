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
  const IntakeProgress(this.label, this.current, this.states, {this.detail});

  final String label;
  final IntakeStage? current;
  final List<IntakeStageState> states;

  /// The precise step inside [current], where the stage name alone would
  /// misreport it. Preparation shares the first processing segment, but a
  /// classifier failure did not happen while finding labels.
  final String? detail;

  /// The words for preparation steps that precede finding labels.
  static const String preparing = 'Preparing photo';

  /// The status of a saved photo waiting behind another in its collection.
  static const String inLine = 'In line';

  static const Set<String> _preparation = <String>{
    'pin_dependencies',
    'classify',
    'quality_check',
  };

  /// True when this row draws an indeterminate, rolling segment.
  ///
  /// Upload has a measured denominator once bytes move, so it never rolls
  /// while uploading.
  static bool rolls(ManifestEntry entry) {
    final IntakeProgress progress = IntakeProgress.of(entry);
    final IntakeStage? stage = progress.current;
    if (stage == null) return false;
    if (progress.states[stage.index] != IntakeStageState.active) return false;
    return !(stage == IntakeStage.upload &&
        entry.state == UploadState.uploading);
  }

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
    'field_research' => IntakeStage.research,
    'finalize' => IntakeStage.finalize,
    'finalized' => IntakeStage.queue,
    _ => null,
  };

  factory IntakeProgress.of(ManifestEntry entry) {
    final states = List<IntakeStageState>.filled(
      IntakeStage.values.length,
      IntakeStageState.waiting,
    );
    String? detail;
    IntakeProgress at(
      String label,
      IntakeStage? stage,
      IntakeStageState state,
    ) {
      if (stage != null) states[stage.index] = state;
      return IntakeProgress(label, stage, states, detail: detail);
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
    if (_preparation.contains(step)) detail = preparing;
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
    if (specimen?.state == 'pending' && progress['waiting_in_line'] == true) {
      return at(inLine, stage, IntakeStageState.waiting);
    }
    if (specimen?.state == 'pending' || entry.state == UploadState.accepted) {
      return at('Waiting to start', stage, IntakeStageState.waiting);
    }
    if (stage == null) {
      return at('Checking processing status', null, IntakeStageState.waiting);
    }
    return at(detail ?? stage.activeLabel, stage, IntakeStageState.active);
  }
}

/// One rolling cycle shared by every active stage track below it.
///
/// A manifest can hold hundreds of photos in processing. Each row owning a
/// repeating controller would schedule hundreds of tickers per frame, so the
/// manifest owns one and every active segment follows it. The cycle runs only
/// while [active] is true and motion is allowed; under reduced motion it is
/// stopped and every segment draws its still frame.
class IntakeStageCycle extends StatefulWidget {
  const IntakeStageCycle({
    super.key,
    required this.active,
    required this.child,
  });

  /// True while at least one row below draws a rolling segment.
  final bool active;

  final Widget child;

  /// The shared cycle, or null where no manifest provides one.
  static Animation<double>? maybeOf(BuildContext context) => context
      .dependOnInheritedWidgetOfExactType<_IntakeStageCycleScope>()
      ?.cycle;

  @override
  State<IntakeStageCycle> createState() => _IntakeStageCycleState();
}

class _IntakeStageCycleState extends State<IntakeStageCycle>
    with SingleTickerProviderStateMixin {
  late final AnimationController _cycle = AnimationController(
    vsync: this,
    // A repeating controller is not compressed by `disableAnimations`; the
    // policy is applied by hand in [_sync], as `UiProgress` does.
    animationBehavior: AnimationBehavior.preserve,
    duration: MotionTokens.slowRaw * 2,
  );
  bool _reduced = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _reduced =
        context.ui.motion.reduced || MediaQuery.disableAnimationsOf(context);
    _sync();
  }

  @override
  void didUpdateWidget(IntakeStageCycle oldWidget) {
    super.didUpdateWidget(oldWidget);
    _sync();
  }

  void _sync() {
    if (widget.active && !_reduced) {
      if (!_cycle.isAnimating) _cycle.repeat();
    } else if (_cycle.isAnimating) {
      _cycle.stop();
    }
  }

  @override
  void dispose() {
    _cycle.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      _IntakeStageCycleScope(cycle: _cycle, child: widget.child);
}

class _IntakeStageCycleScope extends InheritedWidget {
  const _IntakeStageCycleScope({required this.cycle, required super.child});

  final Animation<double> cycle;

  @override
  bool updateShouldNotify(_IntakeStageCycleScope oldWidget) =>
      cycle != oldWidget.cycle;
}

/// Eight equal milestones. Width conveys order only, never relative duration.
/// Only the status label is live; byte values and animation frames are silent.
class IntakeStageProgress extends StatelessWidget {
  const IntakeStageProgress({super.key, required this.entry});

  final ManifestEntry entry;

  /// Transferred and total megabytes, as 02 section 4.8 asks of a file row.
  /// Null when the total is unknown: a percentage alone is never shown.
  static String? transferred(ManifestEntry entry) {
    final int? total = entry.file?.bytes.length;
    if (total == null || total <= 0) return null;
    const int unit = UploadItem.bytesPerMegabyte;
    final double sent = entry.progress.clamp(0, 1) * total / unit;
    return '${sent.toStringAsFixed(1)} of '
        '${(total / unit).toStringAsFixed(1)} MB';
  }

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
        ? progress.detail ?? progress.current!.label
        : null;
    final unrecorded = progress.states.contains(IntakeStageState.unknown);
    final uploading = entry.state == UploadState.uploading;
    final bytes = uploading ? transferred(entry) : null;
    final cycle = IntakeStageCycle.maybeOf(context);
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
                  detail: stage == progress.current ? progress.detail : null,
                  // Only upload has a measured denominator.
                  fraction: stage == IntakeStage.upload && uploading
                      ? entry.progress
                      : null,
                  bytes: stage == IntakeStage.upload ? bytes : null,
                  cycle: cycle,
                ),
              ),
            ],
          ],
        ),
        if (bytes != null) ...<Widget>[
          SizedBox(height: ui.space.s1),
          // The upload segment already speaks these counts as its value.
          ExcludeSemantics(
            child: Text(
              bytes,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          ),
        ],
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
  const _StageSegment({
    required this.stage,
    required this.state,
    this.detail,
    this.fraction,
    this.bytes,
    this.cycle,
  });
  final IntakeStage stage;
  final IntakeStageState state;
  final String? detail;
  final double? fraction;
  final String? bytes;
  final Animation<double>? cycle;

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
    final String? precise = detail?.toLowerCase();
    return Semantics(
      container: true,
      label: [
        '${stage.label}: ${state.label.toLowerCase()}',
        ?precise,
      ].join(', '),
      value: bytes == null
          ? null
          : '${bytes!.replaceFirst(' MB', ' megabytes')} uploaded',
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
                  value: fraction,
                  color: color,
                  cycle: cycle,
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
