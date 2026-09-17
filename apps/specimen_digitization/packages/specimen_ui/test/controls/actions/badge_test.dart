// `UiBadge` and `UiKeyCap` are the two entries of the actions family that are
// not interactive, so the control contract does not apply to them: they have
// no role, no focus and no hit box of their own. What they owe instead is a
// label that stands alone and type that holds its shape.

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets('a count badge reads its number and its label stands alone', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const UiBadge(4, semanticsLabel: '4 records waiting'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('4'), findsOneWidget);
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('4 records waiting'))
          .getSemanticsData()
          .label,
      '4 records waiting',
    );
    handle.dispose();
  });

  testWidgets('a count is set in tabular figures, so a changed digit moves '
      'nothing', (WidgetTester tester) async {
    final UiThemeData ui = UiThemeData.light();
    final UiBadgeStyle style = UiBadgeStyle.resolve(ui);
    expect(
      style.label.fontFeatures,
      contains(const FontFeature.tabularFigures()),
    );
    Future<double> widthOf(int count) async {
      await tester.pumpWidget(
        uiHarness(child: UiBadge(count, semanticsLabel: '$count waiting')),
      );
      await tester.pumpAndSettle();
      return tester.getSize(find.text('$count')).width;
    }

    expect(await widthOf(111), closeTo(await widthOf(888), 0.01));
  });

  testWidgets('a single digit is at least as wide as it is tall, so it reads '
      'as a disc', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(child: const UiBadge(4, semanticsLabel: '4 records waiting')),
    );
    await tester.pumpAndSettle();
    final Size size = tester.getSize(find.byType(UiBadge));
    expect(size.width, greaterThanOrEqualTo(size.height));
    expect(size.height, UiBadgeStyle.resolve(UiThemeData.light()).minHeight);
  });

  testWidgets('a dot carries its meaning in its label', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const UiBadge.dot(semanticsLabel: 'Unread decisions')),
    );
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Unread decisions'), findsOneWidget);
    expect(find.byType(Text), findsNothing);
    final UiBadgeStyle style = UiBadgeStyle.resolve(UiThemeData.light());
    expect(
      tester.getSize(find.byType(UiBadge)),
      Size(style.dotSize, style.dotSize),
    );
  });

  testWidgets('a status badge takes the triple content and keeps paper text '
      'in both modes', (WidgetTester tester) async {
    for (final Brightness mode in Brightness.values) {
      final UiThemeData ui = mode == Brightness.dark
          ? UiThemeData.dark()
          : UiThemeData.light();
      final UiBadgeStyle plain = UiBadgeStyle.resolve(ui);
      final UiBadgeStyle blocked = UiBadgeStyle.resolve(
        ui,
        status: ui.color.status.blocked,
      );
      expect(plain.background, ui.color.ink);
      expect(blocked.background, ui.color.status.blocked.content);
      expect(blocked.foreground, ui.color.paper);
    }
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        child: const UiBadge(128, semanticsLabel: '128 records waiting'),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(
      tester.getSize(find.byType(UiBadge)).height,
      greaterThan(UiBadgeStyle.resolve(UiThemeData.light()).minHeight),
      reason: 'the capsule grows with the type rather than clipping it',
    );
  });

  testWidgets('the capsule is the token at rest and the derived height '
      'above it', (WidgetTester tester) async {
    final UiThemeData ui = UiThemeData.light();
    for (final double scale in <double>[1, 1.3, 2]) {
      await tester.pumpWidget(
        uiHarness(
          textScaler: TextScaler.linear(scale),
          child: const UiBadge(128, semanticsLabel: '128 records waiting'),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.getSize(find.byType(UiBadge)).height,
        UiType.heightAroundAt(
          ui.space.s5,
          ui.type.labelSmall,
          TextScaler.linear(scale),
        ),
        reason:
            'the height a count sits in derives from the count\'s own role '
            'at $scale, never from a constant (11 section 2.2)',
      );
    }
  });

  testWidgets('nothing about it animates, in either motion mode', (
    WidgetTester tester,
  ) async {
    for (final bool reduced in <bool>[false, true]) {
      await tester.pumpWidget(
        uiHarness(
          disableAnimations: reduced,
          child: const UiBadge(7, semanticsLabel: '7 records waiting'),
        ),
      );
      await tester.pump();
      expect(tester.binding.transientCallbackCount, 0);
    }
  });
}
