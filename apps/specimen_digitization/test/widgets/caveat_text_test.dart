import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/caveat_text.dart';

const String _label = 'Not calibrated';
const String _why =
    'A risk score orders the queue. It is not a probability that the record '
    'is wrong.';

Widget _host({bool disableAnimations = false}) => MaterialApp(
  theme: AppTheme.light(),
  home: Builder(
    builder: (context) => MediaQuery(
      data: MediaQuery.of(
        context,
      ).copyWith(disableAnimations: disableAnimations),
      child: const Scaffold(
        body: CaveatText(label: _label, why: _why),
      ),
    ),
  ),
);

void main() {
  testWidgets('the label is visible and the body is not, until Why is used', (
    tester,
  ) async {
    await tester.pumpWidget(_host());
    expect(find.text(_label), findsOneWidget);
    expect(find.text('Why'), findsOneWidget);
    expect(find.text(_why), findsNothing);

    await tester.tap(find.text('Why'));
    await tester.pumpAndSettle();
    expect(find.text(_why), findsOneWidget);

    await tester.tap(find.text('Why'));
    await tester.pumpAndSettle();
    expect(find.text(_why), findsNothing);
  });

  testWidgets('the expanded state is announced', (tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(_host());
    expect(
      tester.getSemantics(find.text('Why')),
      containsSemantics(hasExpandedState: true, isExpanded: false),
    );

    await tester.tap(find.text('Why'));
    await tester.pumpAndSettle();
    expect(
      tester.getSemantics(find.text('Why')),
      containsSemantics(hasExpandedState: true, isExpanded: true),
    );
    handle.dispose();
  });

  testWidgets('reduced motion discloses the body without a transition', (
    tester,
  ) async {
    await tester.pumpWidget(_host(disableAnimations: true));
    expect(find.byType(AnimatedSize), findsNothing);
    await tester.tap(find.text('Why'));
    // One frame, no settle: the disclosure is a synchronous jump rather than
    // a 200 ms size transition.
    await tester.pump();
    expect(find.text(_why), findsOneWidget);
    await tester.pumpAndSettle();
  });

  testWidgets('the caveat never uses the error colour', (tester) async {
    await tester.pumpWidget(_host());
    await tester.tap(find.text('Why'));
    await tester.pumpAndSettle();
    final ThemeData theme = AppTheme.light();
    for (final Text text in tester.widgetList<Text>(find.byType(Text))) {
      expect(text.style?.color, isNot(theme.colorScheme.error));
    }
  });
}
