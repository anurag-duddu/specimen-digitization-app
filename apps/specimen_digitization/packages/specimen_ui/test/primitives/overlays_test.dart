// `Popover`, `ModalRoutes`, `FieldCore` and `Announcer`: the primitives that
// put something over the page or take something from the keyboard.

import 'dart:async';

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../harness/control_contract.dart';

/// A trigger with a popover attached, for the popover tests.
class _PopoverHost extends StatefulWidget {
  const _PopoverHost({
    this.placement = PopoverPlacement.below,
    this.paneWidth = 200,
  });

  final PopoverPlacement placement;

  /// How wide the pane asks to be.
  final double paneWidth;

  @override
  State<_PopoverHost> createState() => _PopoverHostState();
}

class _PopoverHostState extends State<_PopoverHost> {
  final PopoverController controller = PopoverController();

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Popover(
    controller: controller,
    placement: widget.placement,
    semanticsLabel: 'Collection menu',
    overlayBuilder: (BuildContext context) => SizedBox(
      width: widget.paneWidth,
      height: 120,
      child: Center(
        child: UiButton(label: 'Insects', onPressed: controller.close),
      ),
    ),
    child: UiButton(label: 'Collection', onPressed: controller.toggle),
  );
}

void main() {
  group('Popover', () {
    testWidgets('opens on the trigger and closes on an outside tap', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(uiHarness(child: const _PopoverHost()));
      expect(find.text('Insects'), findsNothing);

      await tester.tap(find.text('Collection'));
      await tester.pumpAndSettle();
      expect(find.text('Insects'), findsOneWidget);

      await tester.tapAt(const Offset(10, 10));
      await tester.pumpAndSettle();
      expect(find.text('Insects'), findsNothing);
    });

    testWidgets('Escape closes it and focus returns to the trigger', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(uiHarness(child: const _PopoverHost()));
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      final FocusNode? trigger = FocusManager.instance.primaryFocus;
      expect(trigger, isNotNull);

      await tester.tap(find.text('Collection'));
      await tester.pumpAndSettle();
      expect(find.text('Insects'), findsOneWidget);

      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
      expect(find.text('Insects'), findsNothing);
      expect(
        FocusManager.instance.primaryFocus,
        trigger,
        reason:
            'clause 3 of the control contract: Escape dismisses an overlay '
            'and returns focus to what opened it',
      );
    });

    testWidgets('the pane is one floating glass pane, inside budget', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(uiHarness(child: const _PopoverHost()));
      await tester.tap(find.text('Collection'));
      await tester.pumpAndSettle();
      expect(glassPaneCount(), 1);
      expectGlassBudget(tester);
    });

    group('fits the overlay it opens in', () {
      const double inset = 16;
      Finder trigger() => find.widgetWithText(UiButton, 'Collection');
      Finder pane() => find.byType(GlassSurface);

      /// The window itself, not only the media query: a pane fits the
      /// overlay it is drawn in, and the overlay is the size of the view.
      void window(WidgetTester tester, Size size) {
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = size;
        addTearDown(tester.view.reset);
      }

      testWidgets('a trigger at the trailing edge keeps its pane inside', (
        WidgetTester tester,
      ) async {
        // The defect slot A3 measured: a trigger at the end of a bar opened
        // its menu off the window. The anchor mirrors, so the pane's trailing
        // edge meets the trigger's, in both directions and at both windows.
        for (final double width in <double>[390, 800]) {
          for (final TextDirection direction in TextDirection.values) {
            window(tester, Size(width, 600));
            await tester.pumpWidget(
              uiHarness(
                size: Size(width, 600),
                textDirection: direction,
                child: const Align(
                  alignment: AlignmentDirectional.centerEnd,
                  child: _PopoverHost(placement: PopoverPlacement.auto),
                ),
              ),
            );
            await tester.tap(trigger());
            await tester.pumpAndSettle();
            final Rect anchor = tester.getRect(trigger());
            final Rect drawn = tester.getRect(pane());
            final String where = '$width dp, ${direction.name}';
            expect(drawn.left, greaterThanOrEqualTo(0), reason: where);
            expect(drawn.right, lessThanOrEqualTo(width), reason: where);
            if (direction == TextDirection.ltr) {
              expect(
                drawn.right,
                moreOrLessEquals(anchor.right, epsilon: 0.5),
                reason: '$where: the trailing edges align once mirrored',
              );
            } else {
              expect(
                drawn.left,
                moreOrLessEquals(anchor.left, epsilon: 0.5),
                reason: '$where: the trailing edges align once mirrored',
              );
            }
            await tester.sendKeyEvent(LogicalKeyboardKey.escape);
            await tester.pumpAndSettle();
          }
        }
      });

      testWidgets('the leading edges align where there is room', (
        WidgetTester tester,
      ) async {
        for (final TextDirection direction in TextDirection.values) {
          window(tester, const Size(800, 600));
          await tester.pumpWidget(
            uiHarness(
              size: const Size(800, 600),
              textDirection: direction,
              child: const _PopoverHost(),
            ),
          );
          await tester.tap(trigger());
          await tester.pumpAndSettle();
          final Rect anchor = tester.getRect(trigger());
          final Rect drawn = tester.getRect(pane());
          if (direction == TextDirection.ltr) {
            expect(drawn.left, moreOrLessEquals(anchor.left, epsilon: 0.5));
          } else {
            expect(drawn.right, moreOrLessEquals(anchor.right, epsilon: 0.5));
          }
          await tester.sendKeyEvent(LogicalKeyboardKey.escape);
          await tester.pumpAndSettle();
        }
      });

      testWidgets('a pane wider than the room is clamped inside the padding', (
        WidgetTester tester,
      ) async {
        window(tester, const Size(390, 600));
        await tester.pumpWidget(
          uiHarness(
            size: const Size(390, 600),
            child: const _PopoverHost(paneWidth: 500),
          ),
        );
        await tester.tap(trigger());
        await tester.pumpAndSettle();
        final Rect drawn = tester.getRect(pane());
        expect(drawn.left, greaterThanOrEqualTo(inset));
        expect(drawn.right, lessThanOrEqualTo(390 - inset));
        expect(
          drawn.width,
          moreOrLessEquals(390 - 2 * inset, epsilon: 0.5),
          reason: 'neither anchor holds it, so it takes the room there is',
        );
      });

      testWidgets('a pane may come as close to an edge as its trigger', (
        WidgetTester tester,
      ) async {
        // A select flush with the window keeps its list flush under it: the
        // padding is what a pane keeps clear, not a rule that moves it away
        // from the control that opened it.
        window(tester, const Size(390, 600));
        await tester.pumpWidget(
          uiHarness(
            size: const Size(390, 600),
            child: const Align(
              alignment: Alignment.centerRight,
              child: _PopoverHost(),
            ),
          ),
        );
        await tester.tap(trigger());
        await tester.pumpAndSettle();
        expect(
          tester.getRect(pane()).right,
          moreOrLessEquals(tester.getRect(trigger()).right, epsilon: 0.5),
        );
      });

      testWidgets('auto still flips above in the bottom third', (
        WidgetTester tester,
      ) async {
        window(tester, const Size(800, 600));
        await tester.pumpWidget(
          uiHarness(
            size: const Size(800, 600),
            child: const Align(
              alignment: Alignment.bottomCenter,
              child: _PopoverHost(placement: PopoverPlacement.auto),
            ),
          ),
        );
        await tester.tap(trigger());
        await tester.pumpAndSettle();
        expect(
          tester.getRect(pane()).bottom,
          lessThanOrEqualTo(tester.getRect(trigger()).top),
          reason: 'the vertical rule is kept (10 section 3)',
        );
        // Closed before the second pump: `pumpWidget` updates the host's
        // state rather than rebuilding it, so a pane left open would be
        // toggled shut by the tap below.
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await tester.pumpAndSettle();

        await tester.pumpWidget(
          uiHarness(
            size: const Size(800, 600),
            child: const Align(
              alignment: Alignment.topCenter,
              child: _PopoverHost(placement: PopoverPlacement.auto),
            ),
          ),
        );
        await tester.tap(trigger());
        await tester.pumpAndSettle();
        expect(
          tester.getRect(pane()).top,
          greaterThanOrEqualTo(tester.getRect(trigger()).bottom),
        );
      });
    });

    testWidgets('every placement builds', (WidgetTester tester) async {
      for (final PopoverPlacement placement in PopoverPlacement.values) {
        await tester.pumpWidget(
          uiHarness(child: _PopoverHost(placement: placement)),
        );
        await tester.tap(find.text('Collection'));
        await tester.pumpAndSettle();
        expect(find.text('Insects'), findsOneWidget, reason: placement.name);
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await tester.pumpAndSettle();
      }
    });
  });

  group('ModalRoutes', () {
    testWidgets('a sheet on a compact window, a dialog above it', (
      WidgetTester tester,
    ) async {
      for (final (Size window, bool expectSheet) in <(Size, bool)>[
        (const Size(390, 844), true),
        (const Size(1180, 820), false),
      ]) {
        late BuildContext hostContext;
        await tester.pumpWidget(
          uiHarness(
            size: window,
            child: Builder(
              builder: (BuildContext context) {
                hostContext = context;
                return const SizedBox.shrink();
              },
            ),
          ),
        );
        expect(isCompactWindow(hostContext), expectSheet);

        unawaited(
          showUiModal<void>(
            context: hostContext,
            semanticsLabel: 'Record a reason',
            dismissLabel: 'Close',
            builder: (BuildContext context) =>
                const SizedBox(height: 200, child: Text('Reason')),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text('Reason'), findsOneWidget);

        final double paneWidth = tester
            .getSize(find.byType(GlassSurface))
            .width;
        if (expectSheet) {
          expect(
            paneWidth,
            greaterThan(window.width * 0.9),
            reason: 'a sheet is full width on a compact window',
          );
        } else {
          expect(
            paneWidth,
            lessThanOrEqualTo(UiSpace.standard.dialogMax),
            reason: 'a dialog is at most 560 wide',
          );
        }

        Navigator.of(hostContext, rootNavigator: true).pop();
        await tester.pumpAndSettle();
      }
    });

    testWidgets('a modal carries one glass pane and a scrim', (
      WidgetTester tester,
    ) async {
      late BuildContext hostContext;
      await tester.pumpWidget(
        uiHarness(
          child: Builder(
            builder: (BuildContext context) {
              hostContext = context;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      unawaited(
        showUiSheet<void>(
          context: hostContext,
          semanticsLabel: 'Record a reason',
          dismissLabel: 'Close',
          builder: (BuildContext context) =>
              const SizedBox(height: 200, child: Text('Reason')),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(Scrim), findsOneWidget);
      expect(glassPaneCount(), 1);
      expect(modalGlassPaneCount(), 1);
      expectGlassBudget(tester);
    });

    testWidgets('a tap on the scrim dismisses a dismissible modal', (
      WidgetTester tester,
    ) async {
      late BuildContext hostContext;
      await tester.pumpWidget(
        uiHarness(
          child: Builder(
            builder: (BuildContext context) {
              hostContext = context;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      unawaited(
        showUiDialog<void>(
          context: hostContext,
          semanticsLabel: 'Start a new run',
          dismissLabel: 'Close',
          builder: (BuildContext context) =>
              const SizedBox(height: 120, child: Text('Run')),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tapAt(const Offset(5, 5));
      await tester.pumpAndSettle();
      expect(find.text('Run'), findsNothing);
    });

    test('the compact threshold matches the window class', () {
      // The package cannot import `WindowClass` without inverting the
      // layering, so the two values are pinned here and in the application.
      expect(compactWindowMax, 600);
    });
  });

  group('FieldCore', () {
    testWidgets('edits text with no Material decoration', (
      WidgetTester tester,
    ) async {
      final TextEditingController controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 300,
            child: FieldCore(
              semanticsLabel: 'Reason',
              controller: controller,
              hintText: 'Why this changed',
            ),
          ),
        ),
      );
      await tester.enterText(find.byType(FieldCore), 'Label is torn');
      await tester.pumpAndSettle();
      expect(controller.text, 'Label is torn');
      expect(find.bySemanticsLabel('Reason'), findsOneWidget);
    });

    testWidgets('it paints text and nothing else', (WidgetTester tester) async {
      final FocusNode node = FocusNode();
      addTearDown(node.dispose);
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 300,
            child: FieldCore(semanticsLabel: 'Reason', focusNode: node),
          ),
        ),
      );
      node.requestFocus();
      await tester.pumpAndSettle();
      expect(
        find.descendant(
          of: find.byType(FieldCore),
          matching: find.byType(FocusRing),
        ),
        findsNothing,
        reason:
            'the ring belongs to the box that has the edge, and a core that '
            'drew one as well was the second of the three edges a focused '
            'field showed (11 section 4)',
      );
    });

    testWidgets('the placeholder is its own, and goes when the value comes', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      final TextEditingController controller = TextEditingController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 300,
            child: FieldCore(
              semanticsLabel: 'Reason',
              controller: controller,
              hintText: 'Say what you saw on the label',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Say what you saw on the label'), findsOneWidget);
      expect(
        find.bySemanticsLabel('Say what you saw on the label'),
        findsNothing,
        reason:
            'the control publishes the hint once, on its own node; the drawn '
            'placeholder is for the eye',
      );

      await tester.enterText(find.byType(FieldCore), 'The label is torn');
      await tester.pumpAndSettle();
      expect(
        find.text('Say what you saw on the label'),
        findsNothing,
        reason: 'the placeholder goes the moment the value is not empty',
      );

      controller.clear();
      await tester.pumpAndSettle();
      expect(find.text('Say what you saw on the label'), findsOneWidget);
      handle.dispose();
    });

    testWidgets('the placeholder sits where the value will sit', (
      WidgetTester tester,
    ) async {
      final TextEditingController controller = TextEditingController();
      addTearDown(controller.dispose);
      Widget build() => uiHarness(
        child: SizedBox(
          width: 300,
          child: FieldCore(
            semanticsLabel: 'Reason',
            controller: controller,
            hintText: 'Chicago, 1946',
          ),
        ),
      );
      await tester.pumpWidget(build());
      await tester.pumpAndSettle();
      final Offset placeholder = tester.getTopLeft(find.text('Chicago, 1946'));

      await tester.enterText(find.byType(FieldCore), 'Chicago, 1946');
      await tester.pumpAndSettle();
      final Offset value = tester.getTopLeft(find.byType(EditableText));
      expect(
        value.dy,
        moreOrLessEquals(placeholder.dy, epsilon: 0.5),
        reason:
            'the placeholder and the text it stands in for are one object '
            'with one style, on one baseline (11 section 4). A placeholder '
            'two pixels above the value is the word moving as the reviewer '
            'types the first character.',
      );
      expect(value.dx, moreOrLessEquals(placeholder.dx, epsilon: 0.5));
    });

    testWidgets('the caret and the selection are the system\'s own', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: const SizedBox(
            width: 300,
            child: FieldCore(semanticsLabel: 'Reason'),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final UiThemeData ui = tester.element(find.byType(FieldCore)).ui;
      final EditableText editable = tester.widget<EditableText>(
        find.byType(EditableText),
      );
      expect(editable.cursorColor, ui.color.ink);
      expect(editable.cursorWidth, ui.shape.stroke.emphasis);
      expect(
        editable.cursorRadius,
        Radius.circular(ui.shape.stroke.caretRadius),
      );
      expect(
        editable.selectionColor ??
            DefaultSelectionStyle.of(
              tester.element(find.byType(EditableText)),
            ).selectionColor,
        ui.color.selection,
        reason:
            'the selection is the accent at 35 percent, not the platform blue '
            '(11 section 4)',
      );
    });

    testWidgets('a read only field can be read and not edited', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      final TextEditingController controller = TextEditingController(
        // The first twelve characters of a checksum, which is what a read
        // only field in this product holds. Repetitive on purpose: a random
        // twelve hex characters reads as a high entropy string to the secret
        // scanner, and a fixture is not worth an allowlist entry.
        text: 'abababab1212',
      );
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        uiHarness(
          child: SizedBox(
            width: 300,
            child: FieldCore(
              semanticsLabel: 'Checksum',
              controller: controller,
              readOnly: true,
              obscureText: true,
            ),
          ),
        ),
      );
      final SemanticsData data = tester
          .getSemantics(find.bySemanticsLabel('Checksum'))
          .getSemanticsData();
      expect(data.flagsCollection.isTextField, isTrue);
      expect(data.flagsCollection.isObscured, isTrue);
      // Asserted by behaviour rather than by the flag: `EditableText`
      // publishes `isReadOnly` only for some combinations, and what the
      // reviewer actually needs is that the value cannot change.
      await tester.enterText(find.byType(FieldCore), 'something else');
      await tester.pumpAndSettle();
      expect(controller.text, 'abababab1212');
      handle.dispose();
    });
  });

  group('Announcer', () {
    testWidgets('a status that stays on screen is a live region', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await tester.pumpWidget(
        uiHarness(
          child: const Announcer(child: Text('Review recorded on version 4')),
        ),
      );
      final SemanticsData data = tester
          .getSemantics(find.byType(Announcer))
          .getSemanticsData();
      expect(data.flagsCollection.isLiveRegion, isTrue);
      handle.dispose();
    });

    testWidgets('a one-shot announcement is guarded by platform support', (
      WidgetTester tester,
    ) async {
      late BuildContext hostContext;
      await tester.pumpWidget(
        uiHarness(
          child: Builder(
            builder: (BuildContext context) {
              hostContext = context;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      // Empty is a no-op, and a platform with no support is never sent one.
      AnnounceOnce.send(hostContext, '');
      AnnounceOnce.send(hostContext, 'Review recorded on version 4');
      await tester.pumpAndSettle();
    });
  });
}
