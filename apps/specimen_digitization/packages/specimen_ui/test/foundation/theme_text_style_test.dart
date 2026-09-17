// The one text style source (11 section 5).
//
// `UiTheme` publishes the product's ambient text style with its tokens. The
// `no_fallback_text_style` gate beside this file proves that no page and no
// overlay ends up in the framework fallback; this proves what they end up in
// instead, which is the half a gate written as a negative cannot say.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The style a `Text` with no style of its own is drawn in, under [data].
Future<TextStyle> _published(WidgetTester tester, UiThemeData data) async {
  late TextStyle seen;
  await tester.pumpWidget(
    UiTheme(
      data: data,
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: Builder(
          builder: (BuildContext context) {
            seen = DefaultTextStyle.of(context).style;
            return const SizedBox.shrink();
          },
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return seen;
}

void main() {
  for (final (String mode, UiThemeData Function() build) in <(
    String,
    UiThemeData Function(),
  )>[('light', UiThemeData.light), ('dark', UiThemeData.dark)]) {
    testWidgets('$mode publishes body in ink with no decoration', (
      WidgetTester tester,
    ) async {
      final UiThemeData ui = build();
      final TextStyle style = await _published(tester, ui);
      expect(style.fontFamily, ui.type.body.fontFamily);
      expect(style.fontSize, ui.type.body.fontSize);
      expect(style.height, ui.type.body.height);
      expect(style.leadingDistribution, TextLeadingDistribution.even);
      expect(style.color, ui.color.ink);
      expect(
        style.decoration,
        TextDecoration.none,
        reason:
            'a style that leaves the decoration unset keeps whatever the '
            'host had in scope, which is the defect (11 section 5)',
      );
      expect(style, ui.defaultTextStyle);
    });
  }

  testWidgets('a glyph beside a label is still the colour of the label', (
    WidgetTester tester,
  ) async {
    // `UiIcon` takes its colour from the ambient text style, so moving the
    // publication from the application into the package must not move a
    // single glyph.
    final UiThemeData ui = UiThemeData.light();
    await tester.pumpWidget(
      UiTheme(
        data: ui,
        child: const Directionality(
          textDirection: TextDirection.ltr,
          child: UiIcon(UiIcons.queue),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.widget<Icon>(find.byType(Icon)).color, ui.color.ink);
  });

  testWidgets('the tokens still reach a context through one lookup', (
    WidgetTester tester,
  ) async {
    // The style is published in the constructor rather than in a `build`, so
    // `UiTheme` is still the inherited widget itself and `context.ui` is one
    // hop rather than two.
    late UiThemeData seen;
    final UiThemeData ui = UiThemeData.dark();
    await tester.pumpWidget(
      UiTheme(
        data: ui,
        child: Directionality(
          textDirection: TextDirection.ltr,
          child: Builder(
            builder: (BuildContext context) {
              seen = context.ui;
              return const SizedBox.shrink();
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(seen.color.ground, ui.color.ground);
    expect(seen.isDark, isTrue);
    expect(
      tester.element(find.byType(SizedBox)).getInheritedWidgetOfExactType<UiTheme>(),
      isNotNull,
    );
  });
}
