// Instruments for the second verification report
// (`design/12-verification-report-v2.md`).
//
// Everything here measures. Nothing here decides: a verdict in the report is
// derived from the numbers these functions print, and the run that printed
// them is named beside it. Where a measurement cannot be taken, the report
// says so rather than carrying a number nobody produced, which is the north
// star's honesty invariant applied to the report about itself.

import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../golden/golden_harness.dart';
import '../widget_test.dart' show TestSession;

/// The boundary a verification capture is taken from.
const Key verificationBoundary = ValueKey<String>('verification-boundary');

/// The accent, as the palette declares it (09 section 3.1).
///
/// One colour in both modes. The rule it carries is "one use per screen", and
/// [accentRegions] is how that is counted rather than asserted.
const int accentValue = 0xFFE8FF47;

/// How far a pixel may sit from the accent and still be counted as it.
///
/// Eight per channel. The nearest other token in the system is the sun field
/// centre, `0xFFF2FF66`, which is 31 away on blue before it is composited over
/// paper and further after, so this separates the accent from the sky without
/// dropping the antialiased edge of a disc.
const int accentTolerance = 8;

/// The smallest run of connected accent pixels that counts as a use.
///
/// Sixteen pixels. Below that a run is the corner of an antialiased glyph
/// rather than a mark a reviewer sees.
const int accentRegionFloor = 16;

// ---------------------------------------------------------------------------
// Layout errors
// ---------------------------------------------------------------------------

/// The errors the frames of the current test reported.
List<String> _captured = <String>[];

/// The handler in place before the collector was installed.
FlutterExceptionHandler? _previous;

/// Starts collecting this test's layout errors.
///
/// Collected rather than thrown, for the reason the size-class goldens give:
/// `flutter_test` folds a second and later exception into one summary that no
/// longer says what any of them was, and an overflow is reported once per
/// frame.
void captureLayoutErrors() {
  _previous = FlutterError.onError;
  _captured = <String>[];
  FlutterError.onError = (FlutterErrorDetails details) =>
      _captured.add(details.exceptionAsString());
  addTearDown(_stopCapturing);
}

void _stopCapturing() {
  if (_previous == null) return;
  FlutterError.onError = _previous;
  _previous = null;
}

/// Puts the framework's handler back and says whether anything overflowed.
///
/// Anything that is not an overflow fails the test here, so a capture is
/// never taken from a broken frame.
bool stopAndReportOverflow(WidgetTester tester) {
  _stopCapturing();
  final List<String> errors = _captured;
  final Iterable<String> other = errors.where(
    (String error) => !error.contains('overflowed by'),
  );
  expect(
    other,
    isEmpty,
    reason: 'a cell must not be measured from a broken frame: $other',
  );
  return errors.any((String error) => error.contains('overflowed by'));
}

/// What the frames of the current test reported, overflow or not.
List<String> get capturedErrors => List<String>.unmodifiable(_captured);

// ---------------------------------------------------------------------------
// Arrangement
// ---------------------------------------------------------------------------

/// Which navigation arrangement the shell chose (05 section 2; shell.dart).
///
/// One per window class: a floating pill below 600, a collapsed rail to 839,
/// an extended rail to 1199, and a sidebar at 1200 and above. A screen drawn
/// outside the collection shell reports `none`, which is itself the intended
/// arrangement for the entry screens and for a surface the app pushes whole.
String navigationVariant(WidgetTester tester) {
  if (find.byType(UiSidebar).evaluate().isNotEmpty) return 'sidebar';
  final Iterable<UiRail> rails = tester.widgetList<UiRail>(find.byType(UiRail));
  if (rails.isNotEmpty) {
    return rails.first.extended ? 'rail extended' : 'rail';
  }
  if (find.byType(UiPillNav).evaluate().isNotEmpty) return 'pill';
  return 'none';
}

/// True when anything on screen has somewhere to scroll to.
///
/// The fit question a scale answers is whether the arrangement still holds
/// its content. A screen that fits at 1.0 and scrolls at 1.3 has been
/// squeezed by the type, which is the intended behaviour of 11 section 2.2
/// and worth recording per cell rather than assuming.
bool anyScrollableHasExtent(WidgetTester tester) {
  for (final ScrollableState scroll in tester.stateList<ScrollableState>(
    find.byType(Scrollable),
  )) {
    final ScrollPosition position = scroll.position;
    if (position.hasContentDimensions && position.maxScrollExtent > 0.5) {
      return true;
    }
  }
  return false;
}

/// The frosted panes on screen, and how many of them are modal.
({int panes, int modal}) glassPanes() =>
    (panes: glassPaneCount(), modal: modalGlassPaneCount());

// ---------------------------------------------------------------------------
// Reporting
// ---------------------------------------------------------------------------

/// Prints one cell of a matrix, in a form the report is transcribed from.
///
/// One line, pipe separated, with a fixed tag so a run's log can be filtered
/// without the reader having to trust a summary.
void reportCell({
  required String screen,
  required String window,
  required double scale,
  required String mode,
  required String variant,
  required bool scrolls,
  required bool overflowed,
  int? accent,
  int? panes,
}) {
  final StringBuffer line = StringBuffer('FITROW|$screen|$window|$scale|$mode')
    ..write('|$variant')
    ..write('|${scrolls ? 'scrolls' : 'fits'}')
    ..write('|${overflowed ? 'OVERFLOW' : 'clean'}');
  if (accent != null) line.write('|accent=$accent');
  if (panes != null) line.write('|panes=$panes');
  debugPrint(line.toString());
}

// ---------------------------------------------------------------------------
// Capture
// ---------------------------------------------------------------------------

/// Pumps the whole application inside a boundary a capture can be taken from.
///
/// The same arguments [pumpGoldenApp] takes, and the same repository, so a
/// measurement here is of the screen the goldens picture. The boundary is the
/// only difference: `toImage` needs one, and the application installs none of
/// its own above the router.
Future<void> pumpMeasuredApp(
  WidgetTester tester, {
  required Size window,
  required Brightness brightness,
  double textScale = 1.0,
  String location = AppRoutes.setup,
  bool signedIn = true,
  GoldenRepository? repository,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  tester.platformDispatcher.platformBrightnessTestValue = brightness;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

  final TestSession session = TestSession(signedIn: signedIn);
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    RepaintBoundary(
      key: verificationBoundary,
      child: SpecimenDigitizationApp(
        session: session,
        repository: repository ?? GoldenRepository(),
        initialLocation: location,
        motionPreferences: MemoryMotionPreferenceStore(),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await settleImages(tester);
}

/// The pixels currently under [verificationBoundary].
Future<ByteData> capturePixels(WidgetTester tester) async {
  final RenderRepaintBoundary boundary = tester
      .renderObject<RenderRepaintBoundary>(find.byKey(verificationBoundary));
  ByteData? bytes;
  await tester.runAsync(() async {
    final ui.Image image = await boundary.toImage();
    bytes = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    image.dispose();
  });
  return bytes!;
}

/// The contrast of one drawn text run against the ground it landed on.
///
/// `textContrastGuideline` builds a histogram over a node's whole rectangle
/// and takes the most frequent colour on each side of a luminance threshold.
/// That is right for a label on a flat fill and wrong twice over in this
/// product: a node whose rectangle is much wider than its glyphs reports two
/// shades of the background, and a gradient ground reports two shades of the
/// gradient. Both were seen in this sweep. This reads the same pixels and
/// asks the question the guideline means to ask: what is the most common
/// colour behind the words, and how far from it is the furthest pixel the
/// words put on screen.
///
/// Returns the ratio, the ground it measured against and the run it found.
Future<({double ratio, int ground, int run})> measurePair(
  WidgetTester tester,
  Rect rect,
) async {
  final ByteData pixels = await capturePixels(tester);
  final Size size = tester.getSize(find.byKey(verificationBoundary));
  final int width = size.width.round();
  final Uint8List rgba = pixels.buffer.asUint8List();
  final Map<int, int> counts = <int, int>{};
  final List<int> found = <int>[];
  final int left = rect.left.ceil().clamp(0, width - 1);
  final int right = rect.right.floor().clamp(0, width);
  final int top = rect.top.ceil().clamp(0, size.height.round() - 1);
  final int bottom = rect.bottom.floor().clamp(0, size.height.round());
  for (int y = top; y < bottom; y++) {
    for (int x = left; x < right; x++) {
      final int base = (y * width + x) * 4;
      if (base + 3 >= rgba.length) continue;
      final int value =
          0xFF000000 |
          (rgba[base] << 16) |
          (rgba[base + 1] << 8) |
          rgba[base + 2];
      counts[value] = (counts[value] ?? 0) + 1;
      found.add(value);
    }
  }
  if (found.isEmpty) return (ratio: 0.0, ground: 0, run: 0);
  int ground = found.first;
  int best = 0;
  counts.forEach((int value, int count) {
    if (count > best) {
      best = count;
      ground = value;
    }
  });
  final double groundLuminance = _luminanceOf(ground);
  int run = ground;
  double furthest = 0;
  for (final int value in found) {
    final double distance = (_luminanceOf(value) - groundLuminance).abs();
    if (distance > furthest) {
      furthest = distance;
      run = value;
    }
  }
  return (ratio: contrastOf(run, ground), ground: ground, run: run);
}

/// The WCAG 2.2 contrast ratio between two opaque packed colours.
double contrastOf(int a, int b) {
  final double first = _luminanceOf(a);
  final double second = _luminanceOf(b);
  final double lighter = first > second ? first : second;
  final double darker = first > second ? second : first;
  return (lighter + 0.05) / (darker + 0.05);
}

double _luminanceOf(int value) => Color(value).computeLuminance();

/// A packed colour as `#rrggbb`.
String hexOf(int value) =>
    '#${(value & 0xFFFFFF).toRadixString(16).padLeft(6, '0')}';

/// How many separate marks on screen are painted in the accent.
///
/// A connected run of pixels within [accentTolerance] of [accentValue], of at
/// least [accentRegionFloor] pixels, counts as one use. This is a measurement
/// of what was painted rather than a count of widgets that were asked to
/// paint it, because the rule in 09 is about what a reviewer's eye lands on.
Future<int> accentRegions(WidgetTester tester) async {
  final ByteData pixels = await capturePixels(tester);
  final Size size = tester.getSize(find.byKey(verificationBoundary));
  final int width = size.width.round();
  final int height = size.height.round();
  final Uint8List rgba = pixels.buffer.asUint8List();
  if (rgba.length < width * height * 4) return 0;

  const int targetR = (accentValue >> 16) & 0xFF;
  const int targetG = (accentValue >> 8) & 0xFF;
  const int targetB = accentValue & 0xFF;

  final Uint8List mask = Uint8List(width * height);
  for (int i = 0; i < width * height; i++) {
    final int base = i * 4;
    if (rgba[base + 3] < 0xF0) continue;
    if ((rgba[base] - targetR).abs() > accentTolerance) continue;
    if ((rgba[base + 1] - targetG).abs() > accentTolerance) continue;
    if ((rgba[base + 2] - targetB).abs() > accentTolerance) continue;
    mask[i] = 1;
  }

  int regions = 0;
  final List<int> stack = <int>[];
  for (int start = 0; start < mask.length; start++) {
    if (mask[start] != 1) continue;
    int area = 0;
    stack
      ..clear()
      ..add(start);
    mask[start] = 2;
    while (stack.isNotEmpty) {
      final int index = stack.removeLast();
      area++;
      final int x = index % width;
      final int y = index ~/ width;
      for (int dy = -1; dy <= 1; dy++) {
        for (int dx = -1; dx <= 1; dx++) {
          if (dx == 0 && dy == 0) continue;
          final int nx = x + dx;
          final int ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          final int next = ny * width + nx;
          if (mask[next] != 1) continue;
          mask[next] = 2;
          stack.add(next);
        }
      }
    }
    if (area >= accentRegionFloor) regions++;
  }
  return regions;
}
