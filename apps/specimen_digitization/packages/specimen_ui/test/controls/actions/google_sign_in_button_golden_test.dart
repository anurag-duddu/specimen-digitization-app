// The Sign in with Google button's specimen sheet (10 section 4.1).
//
// Two sheets, each in light and dark: the states at normal text, and the
// button at 200 percent text in a column too narrow to hold its label on one
// line. The first is what a reviewer compares with Google's drawing; the
// second is the one place this control departs from the system's labels, and
// a picture is the evidence that it wraps whole instead of being cut.
//
// The sheets are drawn with the target platform at its default. That the same
// pixels come out on every `TargetPlatform` is asserted in
// `google_sign_in_button_test.dart`, not pictured here.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const Key _sheet = Key('google sign-in specimen');

void _noop() {}

/// One state of the button under a caption that names it.
Widget _state(
  BuildContext context,
  String caption,
  UiGoogleSignInButton button,
) {
  final UiThemeData ui = context.ui;
  return Padding(
    padding: EdgeInsets.only(bottom: ui.space.s4),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          caption,
          style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
        ),
        SizedBox(height: ui.space.s1),
        button,
      ],
    ),
  );
}

Widget _states() => Builder(
  builder: (BuildContext context) => Padding(
    padding: EdgeInsets.all(context.ui.space.s4),
    child: Column(
      key: _sheet,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _state(context, 'Rest', const UiGoogleSignInButton(onPressed: _noop)),
        _state(
          context,
          'Hover',
          UiGoogleSignInButton(
            onPressed: _noop,
            statesController: WidgetStatesController(<WidgetState>{
              WidgetState.hovered,
            }),
          ),
        ),
        _state(
          context,
          'Pressed',
          UiGoogleSignInButton(
            onPressed: _noop,
            statesController: WidgetStatesController(<WidgetState>{
              WidgetState.pressed,
            }),
          ),
        ),
        _state(
          context,
          'Keyboard focus',
          const UiGoogleSignInButton(onPressed: _noop, autofocus: true),
        ),
        _state(
          context,
          'Busy, paint unchanged',
          const UiGoogleSignInButton(busy: true),
        ),
        _state(
          context,
          'Disabled, 38 percent',
          const UiGoogleSignInButton(
            disabledReason: 'Email sign-in is already in progress.',
          ),
        ),
      ],
    ),
  ),
);

Widget _wrapped() => Builder(
  builder: (BuildContext context) => Padding(
    padding: EdgeInsets.all(context.ui.space.s4),
    child: const SizedBox(
      key: _sheet,
      width: 280,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[UiGoogleSignInButton(onPressed: _noop)],
      ),
    ),
  ),
);

/// Pumps [page] in a window of [size], waits for the "G" to decode, and
/// settles.
Future<void> _pumpSheet(
  WidgetTester tester,
  Widget page, {
  required Brightness mode,
  required Size size,
  double textScale = 1,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    uiHarness(
      brightness: mode,
      size: size,
      textScaler: TextScaler.linear(textScale),
      child: SizedBox.fromSize(
        size: size,
        child: Center(child: page),
      ),
    ),
  );
  await tester.runAsync(() async {
    for (final Element element in tester.elementList(find.byType(Image))) {
      await precacheImage((element.widget as Image).image, element);
    }
  });
  await tester.pumpAndSettle();
}

void main() {
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  for (final Brightness mode in Brightness.values) {
    final String name = mode == Brightness.dark ? 'dark' : 'light';

    testWidgets('google-sign-in-button-$name', (WidgetTester tester) async {
      await _pumpSheet(
        tester,
        _states(),
        mode: mode,
        size: const Size(320, 640),
      );
      expect(
        tester.widgetList<Image>(find.byType(Image)),
        hasLength(6),
        reason: 'six states, six logos, all of them decoded',
      );
      await expectLater(
        find.byKey(_sheet),
        matchesGoldenFile('goldens/google-sign-in-button-$name.png'),
      );
    });

    testWidgets('google-sign-in-button-wrapped-$name', (
      WidgetTester tester,
    ) async {
      await _pumpSheet(
        tester,
        _wrapped(),
        mode: mode,
        size: const Size(320, 240),
        textScale: 2,
      );
      await expectLater(
        find.byKey(_sheet),
        matchesGoldenFile('goldens/google-sign-in-button-wrapped-$name.png'),
      );
    });
  }
}
