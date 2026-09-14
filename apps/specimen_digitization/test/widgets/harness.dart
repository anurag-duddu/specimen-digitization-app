// Shared scaffolding for the component tests.
//
// Every component is pumped inside the real product theme, because a
// component that reads tokens cannot be tested against a default theme, and a
// component that renders correctly in light but not in dark has not been
// tested.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

/// The two themes every component is checked against.
final Map<String, ThemeData> productThemes = <String, ThemeData>{
  'light': AppTheme.light(),
  'dark': AppTheme.dark(),
};

/// Pumps [child] on the product theme, in a scaffold, at a known window size.
///
/// [reduceMotion] drives `MediaQuery.disableAnimationsOf`, which is the
/// Android signal and the one a widget test can set.
Future<void> pumpComponent(
  WidgetTester tester,
  Widget child, {
  ThemeData? theme,
  Size size = const Size(1000, 800),
  bool reduceMotion = false,
  TargetPlatform platform = TargetPlatform.android,
}) async {
  tester.view.physicalSize = size * tester.view.devicePixelRatio;
  tester.view.devicePixelRatio = tester.view.devicePixelRatio;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    MaterialApp(
      theme: (theme ?? AppTheme.light()).copyWith(platform: platform),
      home: Builder(
        builder: (BuildContext context) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(disableAnimations: reduceMotion),
          child: Scaffold(body: Center(child: child)),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// Runs the tap target and label guidelines over whatever is on screen.
///
/// These are the two guidelines that apply to every component in this
/// library: a target a finger can hit, and a name a screen reader can read.
Future<void> expectAccessible(WidgetTester tester) async {
  final SemanticsHandle handle = tester.ensureSemantics();
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  handle.dispose();
}
