import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/app/help_screen.dart';
import 'package:specimen_digitization/src/app/sign_in_layout.dart';
import 'package:specimen_ui/specimen_ui.dart';

Widget _harness(Widget child, Size size, {bool dark = false}) => MaterialApp(
  home: MediaQuery(
    data: MediaQueryData(size: size, textScaler: const TextScaler.linear(2)),
    child: Directionality(
      textDirection: TextDirection.rtl,
      child: UiTheme(
        data: dark ? UiThemeData.dark() : UiThemeData.light(),
        child: child,
      ),
    ),
  ),
);

void main() {
  testWidgets(
    'brand sign-in layout preserves an editing field across device widths',
    (WidgetTester tester) async {
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final TextEditingController text = TextEditingController(
        text: 'reviewer@example.org',
      );
      final FocusNode focus = FocusNode();
      addTearDown(text.dispose);
      addTearDown(focus.dispose);
      Widget layout() => UiScaffold(
        body: SignInLayout(
          title: 'Sign in to your collection',
          purpose: 'Use the email address provided by your museum.',
          children: <Widget>[
            UiField(label: 'Email address', controller: text, focusNode: focus),
            UiButton(label: 'Continue', onPressed: () {}),
          ],
        ),
      );
      for (final double width in <double>[320, 390, 768, 1180, 1440]) {
        final Size size = Size(width, 1000);
        tester.view.physicalSize = size;
        await tester.pumpWidget(_harness(layout(), size));
        await tester.pump();
        if (width == 320) {
          focus.requestFocus();
          await tester.pump();
        }
        expect(focus.hasFocus, isTrue);
        expect(text.text, 'reviewer@example.org');
        expect(find.byType(UiBrandAccent), findsOneWidget);
        expect(find.text(SignInLayout.productName), findsOneWidget);
        expect(tester.takeException(), isNull, reason: 'width $width');
      }
    },
  );

  testWidgets(
    'Help shortcuts remain readable on a small phone at double text scale',
    (WidgetTester tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 900);
      addTearDown(tester.view.reset);
      for (final bool dark in <bool>[false, true]) {
        await tester.pumpWidget(
          _harness(const HelpScreen(), const Size(320, 900), dark: dark),
        );
        await tester.pump();
        for (final String label in queueShortcuts.keys) {
          await tester.scrollUntilVisible(
            find.text(label),
            100,
            scrollable: find.byType(Scrollable).first,
          );
          await tester.pump();
          expect(
            tester
                .renderObject<RenderParagraph>(find.text(label))
                .didExceedMaxLines,
            isFalse,
          );
          expect(tester.takeException(), isNull, reason: '$label dark=$dark');
        }
        await tester.pumpWidget(const SizedBox());
      }
    },
  );
}
