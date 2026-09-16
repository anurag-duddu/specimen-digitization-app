// The mark's specimen sheet (09 section 9).
//
// Both variants at the three sizes the product draws the mark at: 24, the
// size 09 states it at; 40, a decorative glyph's size (09 section 7); and 96,
// where the geometry is large enough to read by eye. Light and dark, because
// the monochrome variant inverts with the mode while the accent one does not,
// and that difference is the thing a reviewer is being shown.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

const Key _sheet = Key('mark specimen');
const Size _window = Size(280, 280);
const List<double> _sizes = <double>[24, 40, 96];
const double _gutter = 24;

Widget _row({required bool mono}) => Row(
  mainAxisAlignment: MainAxisAlignment.center,
  children: <Widget>[
    for (final double size in _sizes) ...<Widget>[
      if (size != _sizes.first) const SizedBox(width: _gutter),
      if (mono)
        UiMark.mono(label: 'Specimen Digitization', size: size)
      else
        UiMark(label: 'Specimen Digitization', size: size),
    ],
  ],
);

Widget _specimen() => Center(
  key: _sheet,
  child: Column(
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[
      _row(mono: false),
      const SizedBox(height: _gutter),
      _row(mono: true),
    ],
  ),
);

void main() {
  for (final Brightness mode in Brightness.values) {
    final String name = mode == Brightness.dark ? 'dark' : 'light';
    testWidgets('mark-$name', (WidgetTester tester) async {
      await goldenGalleryPage(
        tester,
        _specimen(),
        mode: mode,
        window: _window,
      );
      await expectLater(
        find.byKey(_sheet),
        matchesGoldenFile('goldens/mark-$name.png'),
      );
    });
  }
}
