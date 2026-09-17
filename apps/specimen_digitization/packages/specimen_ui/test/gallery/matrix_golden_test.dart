// The golden matrix (11 section 3.5; the `fit_matrix` gate of 10 section 8).
//
// Every page the gallery shows, at the four window classes and at text scales
// 1.0, 1.3 and 2.0, in both modes: twenty four goldens per page. The family
// goldens review a page at one comfortable window, which is the width every
// wrapping label of 11 section 0 looked correct at. This matrix is the other
// question: what the same page does when the window is a phone, or when the
// reviewer has asked for text at twice the size.
//
// One test per page rather than one per golden. A page is built twenty four
// times either way, but a single `WidgetTester` amortises the harness, and a
// failure still names the file it could not match.

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// The width each window class is drawn at (11 section 3.1).
///
/// One width per class, chosen inside it rather than at its boundary: 360 is a
/// phone, 700 a phone in landscape or a tablet in portrait, 1000 a tablet in
/// landscape, and 1400 a desktop window. `extraLarge` is left out because
/// nothing in the system declares an arrangement at 1600 that it does not
/// already have at 1200, so a fifth column would be a fifth of the goldens for
/// none of the evidence.
const Map<String, double> matrixClasses = <String, double>{
  'compact': 360,
  'medium': 700,
  'expanded': 1000,
  'large': 1400,
};

/// The text scales every page is drawn at (11 section 2.1).
///
/// The keys are what the file name carries, so a golden says its own scale.
const Map<String, double> matrixScales = <String, double>{
  '1.0': 1,
  '1.3': 1.3,
  '2.0': 2,
};

/// The height every window in the matrix is captured at.
///
/// Fixed, with the page scrolled to the top, rather than the height each page
/// needs. A page tall enough to hold every specimen at scale 1.0 is twice that
/// at 2.0, and twelve pages times twenty four goldens of that size is a
/// hundred megabytes of binary nobody reviews. What this matrix is evidence of
/// is arrangement: whether the shell switches, whether a control reflows,
/// whether anything is clipped or wrapped at the top of a page. Each family
/// page is already reviewed whole, at its own height, by its family golden.
const double matrixWindowHeight = 900;

/// The density every window in the matrix is drawn at.
///
/// Pointer, because a mouse is what a reviewer opens the gallery with and
/// because the 40 dp visual inside a 48 dp hit box is the tighter of the two
/// cases for a control given less width than it needs.
const UiDensityMode matrixDensity = UiDensityMode.pointer;

/// The file name of one matrix golden.
String matrixGoldenName(
  String page, {
  required String windowClass,
  required String scale,
  required Brightness mode,
}) =>
    '${page}_${windowClass}_${scale}_'
    '${mode == Brightness.dark ? 'dark' : 'light'}.png';

/// The overflows this matrix still catches, by the file at fault.
///
/// A control given less than its intrinsic width is supposed to switch to the
/// compact variant it declares and, when none fits, to end its label in an
/// ellipsis. Until a control has had its fit pass it does neither: a row of
/// children at their natural widths in a 200 dp column reports an overflow and
/// the golden draws the black and yellow stripes over it. That is the defect
/// this page exists to picture, so the matrix records it rather than refusing
/// to render it, and the record is a ratchet: a number may shrink and never
/// grow, and a line that has dropped to nothing is deleted rather than left
/// standing (10 section 8).
///
/// The number is how many reports the whole matrix drew, which is a count of
/// windows times specimens rather than of defects. What matters is the file,
/// and each one below is a control or a page that 11 section 3.3 still has to
/// be applied to:
///
/// - `controls/data/list_row.dart`: the row lays its title, its subtitle and
///   its trailing control out side by side at their natural widths, so the
///   trailing chip pushes past the end below about 300 dp. The table has the
///   trailing control drop its label and keep its glyph. Slot G2.
/// - `controls/overlays/sheet.dart`: `UiModalActions` is a row of two buttons
///   at their natural widths. The table stacks them, primary on top. Slots G1
///   and G2.
/// - `controls/overlays/toast.dart`: the capsule keeps its action beside the
///   message. The table moves the action under the text. Slot G2.
/// - `controls/navigation/pill_nav.dart`: the pill keeps every destination on
///   one line. Slot G2.
/// - `controls/data/data_tile.dart`: the numeral and its unit at 200 percent
///   text. The table steps the numeral down a display role at a time. Slot G2.
/// - `gallery/pages/shape_page.dart` and `gallery/pages/type_page.dart`: two
///   foundation pages lay their specimens out in a `Row` rather than a `Wrap`,
///   so the sheet itself overflows at 360 dp. Neither is a control and neither
///   is this slot's file; both are in the closeout as follow-ups.
const Map<String, int> overflowBacklog = <String, int>{};

/// What the matrix actually saw, filled in as the pages are captured.
final Map<String, int> observedOverflows = <String, int>{};

/// The file the framework names as the widget at fault in a report.
final RegExp _atFault = RegExp(r'packages/specimen_ui/lib/src/([\w/]+\.dart)');

/// Runs [pump] with the framework's error handler diverted, and tallies the
/// overflows it reported against the file each one names.
///
/// A layout overflow is reported rather than thrown, so the only way to hold
/// one against a backlog is to catch it here. Anything that is not an overflow
/// is handed straight back to the framework, which fails the test with it:
/// this is a record of one known defect, not a place for errors to go quiet.
/// A report that names no file of ours is tallied as `unattributed`, which no
/// backlog line covers, so it fails rather than disappearing.
Future<void> _tallyOverflowsDuring(Future<void> Function() pump) async {
  final List<FlutterErrorDetails> reported = <FlutterErrorDetails>[];
  final FlutterExceptionHandler? previous = FlutterError.onError;
  FlutterError.onError = reported.add;
  try {
    await pump();
  } finally {
    FlutterError.onError = previous;
  }
  for (final FlutterErrorDetails details in reported) {
    if (!details.exceptionAsString().contains('overflowed')) {
      FlutterError.reportError(details);
      continue;
    }
    final String file =
        _atFault.firstMatch(details.toString())?.group(1) ?? 'unattributed';
    observedOverflows[file] = (observedOverflows[file] ?? 0) + 1;
  }
}

/// Pumps one page at one window, one scale and one mode.
///
/// The page is drawn inside the shell, so the matrix reviews the shell's own
/// arrangement as well as the page's: below `medium` the page list is a select
/// above the content and the content takes the full width (11 section 3.5).
/// The shell is given this page alone, the way a family golden is, so that
/// registering a page moves that page's twenty four files and nobody else's.
Future<void> _pumpMatrix(
  WidgetTester tester,
  GalleryPage page, {
  required double width,
  required double scale,
  required Brightness mode,
}) async {
  final Size window = Size(width, matrixWindowHeight);
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  // A fresh tree for every capture. A `RenderFlex` reports an overflow once
  // per render object and then stays quiet until the overflow changes, so a
  // tree reused between two captures reports the defect against whichever of
  // them happened to be pumped first. Unmounting between captures makes the
  // record a property of the page rather than of the loop's order.
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pumpWidget(
    uiHarness(
      brightness: mode,
      density: matrixDensity,
      textScaler: TextScaler.linear(scale),
      // Reduced motion, because a matrix of this size cannot wait for a
      // transition and because a golden of a half finished one says nothing.
      disableAnimations: true,
      size: window,
      child: SizedBox.fromSize(
        size: window,
        child: UiGallery(pages: <GalleryPage>[page]),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  // The same condition the family goldens are captured under: a golden presses
  // no key, so a specimen that draws its ring only under keyboard focus draws
  // nothing unless the mode is stated.
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  for (final GalleryPage page in galleryPages) {
    testWidgets('${page.id}, four classes by three scales by two modes', (
      WidgetTester tester,
    ) async {
      addTearDown(tester.view.reset);
      for (final MapEntry<String, double> windowClass
          in matrixClasses.entries) {
        for (final MapEntry<String, double> scale in matrixScales.entries) {
          for (final Brightness mode in Brightness.values) {
            final String name = matrixGoldenName(
              page.id,
              windowClass: windowClass.key,
              scale: scale.key,
              mode: mode,
            );
            await _tallyOverflowsDuring(
              () => _pumpMatrix(
                tester,
                page,
                width: windowClass.value,
                scale: scale.value,
                mode: mode,
              ),
            );
            // The gallery is one window like any other and the budget holds at
            // every class. A page that states a larger number is a specimen
            // sheet saying so out loud (10 section 6).
            expectGlassBudget(
              tester,
              maxPanes: page.maxGlassPanes,
              window: name,
            );
            await expectLater(
              find.byType(UiGallery),
              matchesGoldenFile('goldens/matrix/$name'),
            );
          }
        }
      }
    });
  }

  // Last, because it reads what every test above recorded. Tests in one file
  // run in the order they are declared.
  test('the overflow backlog only shrinks', () {
    final List<MapEntry<String, int>> sorted =
        observedOverflows.entries.toList()..sort(
          (MapEntry<String, int> a, MapEntry<String, int> b) =>
              a.key.compareTo(b.key),
        );
    final String seen = sorted.isEmpty
        ? 'nothing overflowed anywhere in the matrix'
        : sorted
              .map((MapEntry<String, int> e) => "  '${e.key}': ${e.value},")
              .join('\n');
    for (final MapEntry<String, int> entry in observedOverflows.entries) {
      expect(
        overflowBacklog[entry.key] ?? 0,
        greaterThanOrEqualTo(entry.value),
        reason:
            '${entry.key} overflowed ${entry.value} times across the matrix '
            'and the backlog allows ${overflowBacklog[entry.key] ?? 0}. '
            'Something that overflows where it did not before has lost its '
            'fit policy (11 section 3.3). What the matrix saw:\n$seen',
      );
    }
    for (final String file in overflowBacklog.keys) {
      expect(
        observedOverflows.containsKey(file),
        isTrue,
        reason:
            '$file no longer overflows anywhere in the matrix, so its line in '
            'overflowBacklog is spent and has to be deleted. A backlog that '
            'keeps a closed entry stops being a ratchet. What the matrix '
            'saw:\n$seen',
      );
    }
  });
}
