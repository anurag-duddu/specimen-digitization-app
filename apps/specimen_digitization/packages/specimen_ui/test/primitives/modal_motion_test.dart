import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

enum _Presentation { dialog, sheet, drawerStart, drawerEnd }

const _viewport = Size(1180, 720);
const _paneKey = ValueKey('modal-motion-content');

Future<void> _show(BuildContext context, _Presentation presentation) {
  Widget pane(BuildContext context) => SizedBox(
    key: _paneKey,
    width: 280,
    height: 180,
    child: Center(
      child: UiButton(
        label: 'Close panel',
        onPressed: () => Navigator.of(context).pop(),
      ),
    ),
  );

  return switch (presentation) {
    _Presentation.dialog => showUiDialog<void>(
      context: context,
      builder: pane,
      semanticsLabel: 'Record details',
      dismissLabel: 'Dismiss record details',
    ),
    _Presentation.sheet => showUiSheet<void>(
      context: context,
      builder: pane,
      semanticsLabel: 'Record details',
      dismissLabel: 'Dismiss record details',
    ),
    _Presentation.drawerStart || _Presentation.drawerEnd => showUiDrawer<void>(
      context: context,
      builder: pane,
      semanticsLabel: 'Record details',
      dismissLabel: 'Dismiss record details',
      fromStart: presentation == _Presentation.drawerStart,
    ),
  };
}

Future<void> _pumpHost(
  WidgetTester tester,
  _Presentation presentation,
  TextDirection direction, {
  bool reduced = false,
}) async {
  tester.view.physicalSize = _viewport;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    uiHarness(
      size: _viewport,
      textDirection: direction,
      disableAnimations: reduced,
      child: Builder(
        builder: (context) => UiButton(
          label: 'Open panel',
          onPressed: () => _show(context, presentation),
        ),
      ),
    ),
  );
  await tester.tap(find.text('Open panel'));
  await tester.pump();
}

void _expectFullScrim(WidgetTester tester) {
  expect(
    tester.getRect(find.byType(Scrim)),
    Offset.zero & _viewport,
    reason: 'the dimming and dismissal area must cover the whole viewport',
  );
}

void main() {
  for (final presentation in _Presentation.values) {
    for (final direction in TextDirection.values) {
      testWidgets(
        '$presentation $direction keeps its scrim fixed while the panel travels',
        (tester) async {
          await _pumpHost(tester, presentation, direction);
          _expectFullScrim(tester);
          final initial = tester.getRect(find.byKey(_paneKey));
          await tester.pump(const Duration(milliseconds: 100));
          _expectFullScrim(tester);
          final entering = tester.getRect(find.byKey(_paneKey));
          await tester.pumpAndSettle();
          _expectFullScrim(tester);
          final settled = tester.getRect(find.byKey(_paneKey));
          final drawer =
              presentation == _Presentation.drawerStart ||
              presentation == _Presentation.drawerEnd;
          if (drawer) {
            final towardLeft =
                (direction == TextDirection.rtl) !=
                (presentation == _Presentation.drawerStart);
            final distance = settled.width * MotionTokens.sheetEntranceRise;
            expect(
              initial.left - settled.left,
              closeTo(towardLeft ? -distance : distance, .001),
            );
            expect(initial.top, settled.top);
            expect(
              (entering.left - settled.left).abs(),
              inExclusiveRange(0, distance),
            );
          } else {
            final distance =
                settled.height *
                (presentation == _Presentation.sheet
                    ? MotionTokens.sheetEntranceRise
                    : MotionTokens.dialogEntranceRise);
            expect(initial.top - settled.top, closeTo(distance, .001));
            expect(initial.left, settled.left);
            expect(entering.top - settled.top, inExclusiveRange(0, distance));
          }

          // The uncovered corner remains an active dismiss target, including
          // drawers attached to either physical edge in either reading order.
          final corner = settled.left == 0
              ? Offset(_viewport.width - 1, 1)
              : const Offset(1, 1);
          await tester.tapAt(corner);
          await tester.pump();
          await tester.pump(const Duration(milliseconds: 100));
          _expectFullScrim(tester);
          final leaving = tester.getRect(find.byKey(_paneKey));
          expect(leaving.topLeft, isNot(settled.topLeft));
          await tester.pumpAndSettle();
          expect(find.byKey(_paneKey), findsNothing);
          expect(tester.takeException(), isNull);
        },
      );

      testWidgets(
        '$presentation $direction has no travel with reduced motion',
        (tester) async {
          await _pumpHost(tester, presentation, direction, reduced: true);
          _expectFullScrim(tester);
          final initial = tester.getRect(find.byKey(_paneKey));
          await tester.pumpAndSettle();
          expect(tester.getRect(find.byKey(_paneKey)), initial);
          expect(
            find.ancestor(
              of: find.byKey(_paneKey),
              matching: find.byType(SlideTransition),
            ),
            findsNothing,
          );
          expect(tester.takeException(), isNull);
        },
      );
    }
  }
}
