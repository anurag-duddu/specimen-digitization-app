// The glass measurement of the second verification report
// (`design/12-verification-report-v2.md`, item 3; 09 section 3.3).
//
// `GlassQuality`'s doc comment says the default per platform "is a
// measurement, recorded in the verification report, not a preference". No
// measurement had been taken: `UiThemeData.light` and `.dark` both default to
// `GlassQuality.full` on every platform, and `GlassQuality` appears nowhere in
// `docs/SESSION_LEARNINGS.md`. This is the instrument that takes it.
//
// `flutter run -t test/verification/glass_probe.dart -d <device>` draws the
// glass budget at its maximum over a moving ground, cycles the quality through
// full, reduced and off, and reports the engine's own `FrameTiming` for each:
// the build phase, the raster phase and the share of frames that missed the
// display's own cadence. The numbers are drawn on screen as well as printed,
// so a screenshot of the device is the evidence rather than a log nobody kept.
//
// What is measured is exactly what 09 section 3.3 budgets: four panes on one
// window, one of them modal, each one a save layer, over a ground that changes
// every frame so no pane's blur can be cached between frames.

import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// How long each quality is measured for.
const Duration qualityWindow = Duration(seconds: 6);

/// Frames dropped from the head of each window, while the tree settles.
const int warmupFrames = 20;

void main() => runApp(const GlassProbe());

/// Draws the budget at its maximum and reports what each quality costs.
class GlassProbe extends StatefulWidget {
  /// Builds the probe.
  const GlassProbe({super.key});

  @override
  State<GlassProbe> createState() => _GlassProbeState();
}

class _GlassProbeState extends State<GlassProbe>
    with SingleTickerProviderStateMixin {
  late final AnimationController _drift = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 4),
  )..repeat(reverse: true);

  final List<_Sample> _results = <_Sample>[];
  final List<FrameTiming> _window = <FrameTiming>[];
  int _qualityIndex = 0;
  int _seen = 0;
  Stopwatch? _clock;

  @override
  void initState() {
    super.initState();
    SchedulerBinding.instance.addTimingsCallback(_onTimings);
    WidgetsBinding.instance.addPostFrameCallback((_) => _startWindow());
  }

  @override
  void dispose() {
    SchedulerBinding.instance.removeTimingsCallback(_onTimings);
    _drift.dispose();
    super.dispose();
  }

  void _startWindow() {
    _window.clear();
    _seen = 0;
    _clock = Stopwatch()..start();
  }

  void _onTimings(List<FrameTiming> timings) {
    final Stopwatch? clock = _clock;
    if (clock == null || _qualityIndex >= GlassQuality.values.length) return;
    for (final FrameTiming timing in timings) {
      _seen++;
      if (_seen > warmupFrames) _window.add(timing);
    }
    if (clock.elapsed < qualityWindow) return;
    clock.stop();
    _clock = null;
    final _Sample sample = _Sample.from(
      GlassQuality.values[_qualityIndex],
      _window,
    );
    debugPrint('GLASSROW|${sample.line}');
    setState(() {
      _results.add(sample);
      _qualityIndex++;
    });
    if (_qualityIndex < GlassQuality.values.length) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _startWindow());
    }
  }

  @override
  Widget build(BuildContext context) {
    final bool done = _qualityIndex >= GlassQuality.values.length;
    final GlassQuality quality = done
        ? GlassQuality.full
        : GlassQuality.values[_qualityIndex];
    return UiTheme(
      data: UiThemeData.dark(quality: quality),
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: _Stage(drift: _drift, results: _results, done: done),
      ),
    );
  }
}

/// The budget at its maximum: four panes, one of them modal, over a ground
/// that moves every frame.
class _Stage extends StatelessWidget {
  const _Stage({
    required this.drift,
    required this.results,
    required this.done,
  });

  final Animation<double> drift;
  final List<_Sample> results;
  final bool done;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return ColoredBox(
      color: ui.color.ground,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          // The ground the panes frost. `FieldLayer` is what every screen in
          // the product paints behind itself, and the drift moves it so no
          // frame can reuse the last frame's blur.
          AnimatedBuilder(
            animation: drift,
            builder: (BuildContext context, Widget? child) =>
                FractionalTranslation(
                  translation: Offset(drift.value * 0.3 - 0.15, 0),
                  child: const FieldLayer(preset: SkyPreset.home),
                ),
          ),
          // Pane 1, the top bar.
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: GlassSurface(
              level: GlassLevel.flat,
              padding: EdgeInsets.all(ui.space.s4),
              child: _Line('Glass probe, ${context.ui.quality.name}'),
            ),
          ),
          // Pane 2, the navigation capsule.
          Positioned(
            bottom: ui.space.s6,
            left: 0,
            right: 0,
            child: Center(
              child: GlassSurface(
                level: GlassLevel.floating,
                capsule: true,
                padding: EdgeInsets.symmetric(
                  horizontal: ui.space.s5,
                  vertical: ui.space.s3,
                ),
                child: const _Line('Queue   Intake'),
              ),
            ),
          ),
          // Pane 3, a tile group.
          Positioned(
            left: ui.space.s4,
            top: ui.space.s10,
            child: GlassSurface(
              level: GlassLevel.flat,
              padding: EdgeInsets.all(ui.space.s4),
              child: const _Line('4 records   1 blocked'),
            ),
          ),
          // Pane 4, the modal.
          Center(
            child: GlassSurface(
              level: GlassLevel.modal,
              padding: EdgeInsets.all(ui.space.s5),
              child: SizedBox(
                width: 420,
                child: _Report(results: results, done: done),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// One line of the probe's own chrome.
class _Line extends StatelessWidget {
  const _Line(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text,
    style: context.ui.type.body.copyWith(color: context.ui.color.ink),
  );
}

/// What each quality measured, drawn so a screenshot carries it.
class _Report extends StatelessWidget {
  const _Report({required this.results, required this.done});

  final List<_Sample> results;
  final bool done;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          done ? 'Measured' : 'Measuring',
          style: ui.type.title.copyWith(color: ui.color.ink),
        ),
        SizedBox(height: ui.space.s2),
        Text(
          'Four panes, one modal. Build and raster in milliseconds, '
          'median and worst, over ${qualityWindow.inSeconds} seconds each.',
          style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
        ),
        SizedBox(height: ui.space.s3),
        for (final _Sample sample in results) ...<Widget>[
          Text(
            sample.line,
            style: ui.type.bodySmall.copyWith(color: ui.color.ink),
          ),
          SizedBox(height: ui.space.s2),
        ],
        if (!done)
          Text(
            'Working.',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkTertiary),
          ),
      ],
    );
  }
}

/// One quality's frame distribution.
class _Sample {
  const _Sample({
    required this.quality,
    required this.frames,
    required this.buildMedian,
    required this.buildWorst,
    required this.rasterMedian,
    required this.rasterWorst,
    required this.totalMedian,
    required this.over16,
  });

  /// Reduces [timings] to the numbers the report quotes.
  factory _Sample.from(GlassQuality quality, List<FrameTiming> timings) {
    if (timings.isEmpty) {
      return _Sample(
        quality: quality,
        frames: 0,
        buildMedian: 0,
        buildWorst: 0,
        rasterMedian: 0,
        rasterWorst: 0,
        totalMedian: 0,
        over16: 0,
      );
    }
    final List<double> build = <double>[
      for (final FrameTiming timing in timings)
        timing.buildDuration.inMicroseconds / 1000,
    ]..sort();
    final List<double> raster = <double>[
      for (final FrameTiming timing in timings)
        timing.rasterDuration.inMicroseconds / 1000,
    ]..sort();
    final List<double> total = <double>[
      for (final FrameTiming timing in timings)
        timing.totalSpan.inMicroseconds / 1000,
    ]..sort();
    double median(List<double> values) => values[values.length ~/ 2];
    return _Sample(
      quality: quality,
      frames: timings.length,
      buildMedian: median(build),
      buildWorst: build.last,
      rasterMedian: median(raster),
      rasterWorst: raster.last,
      totalMedian: median(total),
      over16: total.where((double value) => value > 16.7).length,
    );
  }

  /// Which quality this is.
  final GlassQuality quality;

  /// How many frames were measured.
  final int frames;

  /// The median and worst build phase, in milliseconds.
  final double buildMedian;

  /// The worst build phase.
  final double buildWorst;

  /// The median raster phase.
  final double rasterMedian;

  /// The worst raster phase.
  final double rasterWorst;

  /// The median whole frame.
  final double totalMedian;

  /// How many frames took longer than one sixty hertz frame.
  final int over16;

  /// One line, in the form the report transcribes.
  String get line =>
      '${quality.name.padRight(7)} frames $frames  '
      'build ${_ms(buildMedian)}/${_ms(buildWorst)}  '
      'raster ${_ms(rasterMedian)}/${_ms(rasterWorst)}  '
      'frame ${_ms(totalMedian)}  over 16.7 ms: $over16';

  static String _ms(double value) => value.toStringAsFixed(2);
}
