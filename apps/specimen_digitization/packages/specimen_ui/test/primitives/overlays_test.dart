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
  const _PopoverHost({this.placement = PopoverPlacement.below});

  final PopoverPlacement placement;

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
      width: 200,
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

    testWidgets('it rings on focus and not before', (
      WidgetTester tester,
    ) async {
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
      expect(tester.widget<FocusRing>(find.byType(FocusRing)).visible, isFalse);
      node.requestFocus();
      await tester.pumpAndSettle();
      expect(tester.widget<FocusRing>(find.byType(FocusRing)).visible, isTrue);
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
