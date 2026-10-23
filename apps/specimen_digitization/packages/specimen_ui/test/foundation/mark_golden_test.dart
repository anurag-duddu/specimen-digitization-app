// All three treatments of the supplied mark at 24, 40 and 96 dp.
// Primary and mono adapt to the theme; app-icon artwork keeps Obsidian and
// its Amber tip on a Paper plate in both modes.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

const Key _sheet = Key('mark specimen');
const Size _window = Size(320, 420);
const List<double> _sizes = <double>[24, 40, 96];
const double _gutter = 24;

Widget _row(UiMarkVariant variant) => Builder(
  builder: (context) => Row(
    mainAxisAlignment: MainAxisAlignment.center,
    children: <Widget>[
      for (final double size in _sizes) ...<Widget>[
        if (size != _sizes.first) const SizedBox(width: _gutter),
        switch (variant) {
          UiMarkVariant.accent => UiMark(label: 'Primary mark', size: size),
          UiMarkVariant.mono => UiMark.mono(
            label: 'Monochrome mark',
            size: size,
          ),
          UiMarkVariant.appIcon => DecoratedBox(
            decoration: BoxDecoration(
              color: context.ui.brand.paper,
              borderRadius: BorderRadius.circular(context.ui.shape.tile),
            ),
            child: Padding(
              padding: EdgeInsets.all(context.ui.space.s3),
              child: UiMark.appIcon(label: 'App icon', size: size),
            ),
          ),
        },
      ],
    ],
  ),
);

Widget _specimen() => Center(
  key: _sheet,
  child: Column(
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[
      _row(UiMarkVariant.accent),
      const SizedBox(height: _gutter),
      _row(UiMarkVariant.mono),
      const SizedBox(height: _gutter),
      _row(UiMarkVariant.appIcon),
    ],
  ),
);

void main() {
  for (final Brightness mode in Brightness.values) {
    final String name = mode == Brightness.dark ? 'dark' : 'light';
    testWidgets('mark-$name', (WidgetTester tester) async {
      await goldenGalleryPage(tester, _specimen(), mode: mode, window: _window);
      await expectLater(
        find.byKey(_sheet),
        matchesGoldenFile('goldens/mark-$name.png'),
      );
    });
  }
}
