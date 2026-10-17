// The compact top bar is one component and one surface on every tab and every
// platform (10 section 4.4, `UiTopBar` in its workspace form; 14 section 3).
//
// It used to be declared twice in `shell.dart`: a row inside the Specimens
// list on `paper`, and `UiScaffold.header` above Intake on `ground`. On a
// phone with a status bar that left a seam under the status strip on one tab
// and a different ground on the other. The owner, 2026-10-17: "why does the
// insects dropdown backround behave differently? has it been created twice?
// that whole top thing I thought is same ?" and "i hope we arent duplicating
// and hand-codring hardcoding. we should have a working design system + ui
// components given we're on flutter at a cross-platform level with behaviors
// in different circumstances".
//
// What is asserted. The same widget, the same rectangle and the same painted
// colour on Specimens and on Intake, on iOS and on Android, with a non-zero top
// inset, measured in pixels rather than read from a decoration. And the
// geometry the owner called accurate on Specimens, held to the numbers it had
// before the change (measured on the previous code: the switcher at 8 dp from
// the start and 8 dp under the inset, 48 dp tall; the account at 8 dp from the
// end; the bar 8 + 48 + 8 = 64 dp under the inset, 80.25 at 200 percent text).
import 'dart:io';
import 'dart:ui' as dart_ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../widget_test.dart' show TestSession;

const Size _window = Size(390, 844);

final Finder _bar = find.byKey(const ValueKey<String>('shell-top-bar'));
final Finder _switcher = find.byKey(
  const ValueKey<String>('collection-sheet-trigger'),
);
final Finder _account = find.byWidgetPredicate(
  (Widget widget) =>
      widget is UiMenuTrigger &&
      widget.semanticsLabel.startsWith('Account menu'),
);
final Finder _environment = find.bySemanticsLabel(RegExp('environment'));

/// What one destination looked like, for comparing destinations and platforms.
class _Look {
  _Look({
    required this.bar,
    required this.switcher,
    required this.account,
    required this.environment,
    required this.column,
  });

  final Rect bar;
  final Rect switcher;
  final Rect account;
  final Rect environment;

  /// The painted colour of a column of pixels, from the window's top edge to
  /// the first row below the bar, as ARGB values.
  final List<int> column;

  @override
  String toString() =>
      'bar $bar switcher $switcher account $account env $environment';
}

Future<void> _pump(
  WidgetTester tester,
  String location, {
  required double top,
  required Brightness brightness,
  double scale = 1,
}) async {
  tester.view.padding = FakeViewPadding(top: top);
  tester.view.viewPadding = FakeViewPadding(top: top);
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = _window;
  tester.platformDispatcher.platformBrightnessTestValue = brightness;
  tester.platformDispatcher.textScaleFactorTestValue = scale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  final TestSession session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    RepaintBoundary(
      key: const ValueKey<String>('top-bar-frame'),
      child: SpecimenDigitizationApp(
        session: session,
        repository: GoldenQueueRepository(goldenQueue(3)),
        initialLocation: location,
        motionPreferences: MemoryMotionPreferenceStore(),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await settleImages(tester);
}

/// The painted pixels of column [x], rows [0, rows), as ARGB.
Future<List<int>> _column(WidgetTester tester, int x, int rows) async {
  final RenderRepaintBoundary boundary = tester
      .renderObject<RenderRepaintBoundary>(
        find.byKey(const ValueKey<String>('top-bar-frame')),
      );
  return (await tester.runAsync(() async {
    final dart_ui.Image image = await boundary.toImage();
    try {
      final ByteData data = (await image.toByteData(
        format: dart_ui.ImageByteFormat.rawRgba,
      ))!;
      return <int>[
        for (int y = 0; y < rows; y++)
          dart_ui.Color.fromARGB(
            255,
            data.getUint8((y * image.width + x) * 4),
            data.getUint8((y * image.width + x) * 4 + 1),
            data.getUint8((y * image.width + x) * 4 + 2),
          ).toARGB32(),
      ];
    } finally {
      image.dispose();
    }
  }))!;
}

Future<_Look> _look(WidgetTester tester, double top) async {
  final Rect bar = tester.getRect(_bar);
  return _Look(
    bar: bar,
    switcher: tester.getRect(_switcher),
    account: tester.getRect(_account),
    environment: tester.getRect(_environment.first),
    column: await _column(tester, 3, (bar.bottom + 16).toInt()),
  );
}

Future<T> _on<T>(TargetPlatform platform, Future<T> Function() body) async {
  debugDefaultTargetPlatformOverride = platform;
  try {
    return await body();
  } finally {
    debugDefaultTargetPlatformOverride = null;
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  for (final Brightness brightness in Brightness.values) {
    for (final double top in <double>[47, 24]) {
      testWidgets(
        'Specimens and Intake draw the same top bar, one paper surface from '
        'the status strip down, on iOS and on Android, ${brightness.name}, '
        'inset $top',
        (WidgetTester tester) async {
          final Map<String, _Look> looks = <String, _Look>{};
          late int paper;
          for (final TargetPlatform platform in <TargetPlatform>[
            TargetPlatform.iOS,
            TargetPlatform.android,
          ]) {
            for (final MapEntry<String, String> destination in <String, String>{
              'specimens': goldenQueueLocation,
              'intake': goldenIntakeLocation,
            }.entries) {
              await _on(platform, () async {
                await _pump(
                  tester,
                  destination.value,
                  top: top,
                  brightness: brightness,
                );
                // One bar, one switcher, one account: nothing is declared
                // twice and nothing is drawn twice.
                expect(_bar, findsOneWidget);
                expect(
                  tester.widget<UiTopBar>(_bar).form,
                  UiTopBarForm.workspace,
                );
                expect(find.byType(UiTopBar), findsOneWidget);
                expect(_switcher, findsOneWidget);
                expect(_account, findsOneWidget);
                paper = tester.element(_bar).ui.color.paper.toARGB32();
                looks['${platform.name}/${destination.key}'] = await _look(
                  tester,
                  top,
                );
                await tester.pumpWidget(const SizedBox());
              });
            }
          }

          final _Look reference = looks.values.first;
          looks.forEach((String name, _Look look) {
            // The same rectangles everywhere: the bar, the switcher, the
            // account and the environment control.
            expect(look.bar, reference.bar, reason: name);
            expect(look.switcher, reference.switcher, reason: name);
            expect(look.account, reference.account, reason: name);
            expect(look.environment, reference.environment, reason: name);
            // And one painted colour from the first pixel row, inside the
            // status strip, through the whole bar to the body under it: that
            // colour is the theme's `paper`. A seam would show as a different
            // value somewhere in the column.
            expect(
              look.column.toSet(),
              <int>{paper},
              reason:
                  '$name has a seam: the column from the top edge to just '
                  'below the bar is not one paper surface',
            );
          });
        },
      );
    }
  }

  for (final TargetPlatform platform in <TargetPlatform>[
    TargetPlatform.iOS,
    TargetPlatform.android,
  ]) {
    for (final Brightness brightness in Brightness.values) {
      testWidgets(
        'there is no seam: the status strip and the header are one colour '
        'on both tabs, ${platform.name}, ${brightness.name}',
        (WidgetTester tester) async {
          // Pixels only, and no finder for the bar: this is the assertion the
          // owner's measurement describes, and it must hold whatever builds
          // the header. On the previous code Specimens was `ground` over its
          // status strip and `paper` in its header row (#111111 over #181818
          // in dark), and Intake the reverse.
          for (final String location in <String>[
            goldenQueueLocation,
            goldenIntakeLocation,
          ]) {
            await _on(platform, () async {
              await _pump(tester, location, top: 47, brightness: brightness);
              final int paper = tester
                  .element(find.byType(UiScaffold))
                  .ui
                  .color
                  .paper
                  .toARGB32();
              final List<int> column = await _column(tester, 3, 47 + 64 + 8);
              final Map<int, List<int>> rows = <int, List<int>>{};
              for (int y = 0; y < column.length; y++) {
                rows.putIfAbsent(column[y], () => <int>[]).add(y);
              }
              expect(
                column.toSet(),
                <int>{paper},
                reason:
                    '$location: the first 119 pixel rows are not one paper '
                    'surface, rows by colour: '
                    '${rows.map((int c, List<int> y) => MapEntry<String, String>('#${c.toRadixString(16)}', '${y.first}..${y.last}'))}',
              );
              await tester.pumpWidget(const SizedBox());
            });
          }
        },
      );
    }
  }

  testWidgets(
    'the geometry the owner approved on Specimens is unchanged: numbers',
    (WidgetTester tester) async {
      for (final double top in <double>[0, 24, 47]) {
        for (final String location in <String>[
          goldenQueueLocation,
          goldenIntakeLocation,
        ]) {
          await _pump(tester, location, top: top, brightness: Brightness.dark);
          final Rect bar = tester.getRect(_bar);
          expect(bar.left, 0);
          expect(bar.top, 0);
          expect(bar.width, 390);
          expect(bar.height, top + 64, reason: '8 + 48 + 8 under the inset');
          final Rect switcher = tester.getRect(_switcher);
          expect(switcher.left, 8, reason: 'switcher 8 dp from the start');
          expect(switcher.top, top + 8, reason: '8 dp under the inset');
          expect(switcher.height, 48);
          final Rect account = tester.getRect(_account);
          expect(account, Rect.fromLTWH(334, top + 8, 48, 48));
          expect(
            account.right,
            390 - 8,
            reason: 'the account is 8 dp from the end',
          );
          final Rect environment = tester.getRect(_environment.first);
          expect(environment, Rect.fromLTWH(286, top + 8, 48, 48));
          expect(
            environment.right,
            account.left,
            reason: 'the two controls touch',
          );
          expect(switcher.right, lessThanOrEqualTo(environment.left));
          await tester.pumpWidget(const SizedBox());
        }
      }
    },
  );

  testWidgets('at 200 percent text the bar grows with the switcher, not past '
      'its 8 dp of air', (WidgetTester tester) async {
    for (final String location in <String>[
      goldenQueueLocation,
      goldenIntakeLocation,
    ]) {
      await _pump(
        tester,
        location,
        top: 47,
        brightness: Brightness.dark,
        scale: 2,
      );
      final Rect bar = tester.getRect(_bar);
      final Rect switcher = tester.getRect(_switcher);
      expect(switcher.height, 64.25);
      expect(bar.height, 47 + 8 + 64.25 + 8);
      expect(switcher.top, 47 + 8);
      expect(bar.bottom - switcher.bottom, 8);
      final Rect account = tester.getRect(_account);
      expect(account.size, const Size(48, 48));
      expect(account.right, 390 - 8);
      expect(
        account.center.dy,
        closeTo(switcher.center.dy, 0.01),
        reason: 'the account is centred on the switcher',
      );
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    }
  });

  testWidgets('a record has no shell bar, and no second bar appears', (
    WidgetTester tester,
  ) async {
    await _pump(
      tester,
      goldenSpecimenLocation,
      top: 47,
      brightness: Brightness.light,
    );
    expect(_bar, findsNothing);
    expect(_switcher, findsNothing);
  });

  test('the compact switcher and account are declared once in the shell', () {
    final String source = File('lib/src/app/shell.dart').readAsStringSync();
    final String code = source.replaceAll(RegExp(r'//.*'), '');
    expect(code, isNot(contains('_mobileHeader')));
    // The compact row exists in one builder: a `UiTopBar` in its workspace
    // form that holds the sheet form of the switcher.
    expect(
      RegExp(r'_CollectionSwitcher\(\s*controller:').allMatches(code).length,
      2,
    );
    expect(RegExp(r'sheet:\s*true').allMatches(code).length, 1);
    expect(code, isNot(contains('sheet: !_docked')));
    expect('UiTopBar('.allMatches(code).length, 1);
    expect(code, contains('UiTopBarForm.workspace'));
    // The docked sidebar's header reuses the same switcher widget and has no
    // account or environment of its own: those belong to the compact bar and
    // the rail.
    final String sidebar = code.substring(
      code.indexOf('Widget _sidebar('),
      code.indexOf('Widget _rail('),
    );
    expect(sidebar, isNot(contains('ShellAccountMenu')));
    expect(sidebar, isNot(contains('_EnvironmentContext')));
  });
}
