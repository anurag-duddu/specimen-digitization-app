// The record's panels at 200 percent text (11 section 2; control contract
// clause 14).
//
// One test per panel, at the two window classes the fit rules name as the
// hard cases: a phone, where the record shares the height with the
// photograph, and an expanded window, where the panels share the width with
// it. The assertion is the one the rules make: no exception, and no
// `RenderFlex` laid out past its box. A panel that overflows at 200 percent
// is content a reviewer cannot read, which is pass criterion 8.5 failing.

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/workbench.dart';

import '../ui_finders.dart';
import '../widget_test.dart' show fixture;
import '../workbench_harness.dart';

/// The errors the frames of one test reported.
///
/// Collected rather than thrown: an overflow is reported once per frame, and
/// `flutter_test` folds a second exception into a summary that no longer says
/// what either of them was. Everything collected is inspected below.
List<String> _errors = <String>[];
FlutterExceptionHandler? _previous;

void _capture() {
  _previous = FlutterError.onError;
  _errors = <String>[];
  FlutterError.onError = (FlutterErrorDetails details) =>
      _errors.add(details.exceptionAsString());
  addTearDown(_release);
}

void _release() {
  if (_previous == null) return;
  FlutterError.onError = _previous;
  _previous = null;
}

/// Asserts that nothing laid out past its box while the panel was on screen.
void _expectNoOverflow(String where) {
  _release();
  expect(
    _errors,
    isEmpty,
    reason: '$where reported a layout error at 200 percent text: $_errors',
  );
}

Future<void> _pump(WidgetTester tester, Size window) async {
  useWindow(tester, window);
  tester.platformDispatcher.textScaleFactorTestValue = 2;
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  await tester.pumpWidget(
    workbenchHost(
      ReviewWorkbench(
        specimen: fixture,
        onChange: (_) async => false,
        onRetry: (_) async {},
        onRefresh: () {},
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  for (final MapEntry<String, Size> window in <String, Size>{
    'compact': compactWindow,
    'expanded': expandedWindow,
  }.entries) {
    for (final WorkbenchSegment segment in WorkbenchSegment.values) {
      testWidgets(
        '${segment.label} lays out at 200 percent text on a ${window.key} '
        'window',
        (WidgetTester tester) async {
          await _pump(tester, window.value);
          final Finder tab = find.descendant(
            of: uiTabs(evidenceTabsLabel),
            matching: find.text(segment.label),
          );
          expect(
            tab,
            findsOneWidget,
            reason: 'the strip scrolls rather than dropping a panel',
          );
          // The capture starts after the panel is chosen, because the
          // assertion is about the panel rather than about the tap.
          await tester.tap(tab);
          await tester.pumpAndSettle();
          _capture();
          await tester.pump();
          await tester.pumpAndSettle();
          _expectNoOverflow('${segment.label} at ${window.key}');
        },
      );
    }
  }
}
