// Fit: measurement, the variant chooser and the one line label
// (11 section 3.3; 10 section 2 clause 13).
//
// These are what wave G converts the controls onto, so the properties pinned
// here are the ones a control will rely on: a measurement that tracks the
// text scale, a chooser that never shrinks a control below what it declared,
// and a label that ellipsises where it used to break between its letters.

import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// The label the gallery saw broken into letters in a 300 dp column.
const String _long = 'Open the region editor and correct the coverage';

/// The one paragraph on screen.
///
/// `allRenderObjects` walks elements, so every widget between the `Text` and
/// its paragraph reports the same one again; the set is what makes "one
/// paragraph" mean one.
RenderParagraph _paragraph(WidgetTester tester) =>
    tester.allRenderObjects.whereType<RenderParagraph>().toSet().single;

/// How many lines the one paragraph on screen laid out.
int _lines(WidgetTester tester) {
  final RenderParagraph paragraph = _paragraph(tester);
  final String plain = paragraph.text.toPlainText(
    includeSemanticsLabels: false,
  );
  final List<TextBox> boxes = paragraph.getBoxesForSelection(
    TextSelection(baseOffset: 0, extentOffset: plain.length),
  );
  return <int>{for (final TextBox box in boxes) (box.top * 4).round()}.length;
}

/// Pumps [child] in a column [width] wide.
Future<void> _inColumn(
  WidgetTester tester,
  double width,
  Widget child, {
  double scale = 1,
}) async {
  await tester.pumpWidget(
    uiHarness(
      size: Size(width, 800),
      textScaler: TextScaler.linear(scale),
      child: SizedBox(width: width, child: child),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('measureLabel', () {
    testWidgets('it reports the width one unbroken line needs', (
      WidgetTester tester,
    ) async {
      late Size short;
      late Size long;
      await _inColumn(
        tester,
        200,
        Builder(
          builder: (BuildContext context) {
            final TextStyle style = context.ui.type.label;
            short = measureLabel(context, 'Queue', style);
            long = measureLabel(context, _long, style);
            return const SizedBox.shrink();
          },
        ),
      );
      expect(short.width, greaterThan(0));
      expect(
        long.width,
        greaterThan(200),
        reason: 'the measurement is the intrinsic width, not the column',
      );
      expect(long.width, greaterThan(short.width));
    });

    testWidgets('it grows with the text scale', (WidgetTester tester) async {
      late double one;
      late double large;
      Widget probe(void Function(double) record) => Builder(
        builder: (BuildContext context) {
          record(measureLabel(context, 'Queue', context.ui.type.label).width);
          return const SizedBox.shrink();
        },
      );

      await _inColumn(tester, 400, probe((double w) => one = w));
      await _inColumn(tester, 400, probe((double w) => large = w), scale: 2);
      expect(large, greaterThan(one * 1.8));
    });

    testWidgets('its height is the line box the type scale promises', (
      WidgetTester tester,
    ) async {
      late double measured;
      late double promised;
      await _inColumn(
        tester,
        400,
        Builder(
          builder: (BuildContext context) {
            final TextStyle style = context.ui.type.body;
            measured = measureLabel(context, 'Queue', style).height;
            promised = UiType.lineHeightOf(style, context);
            return const SizedBox.shrink();
          },
        ),
      );
      expect(measured, closeTo(promised, 0.5));
    });
  });

  group('FitBuilder', () {
    List<FitVariant> variants(List<String> drawn) => <FitVariant>[
      FitVariant(
        intrinsicWidth: 300,
        builder: (BuildContext context, bool lastResort) {
          drawn.add('full $lastResort');
          return const SizedBox.shrink();
        },
      ),
      FitVariant(
        intrinsicWidth: 150,
        builder: (BuildContext context, bool lastResort) {
          drawn.add('compact $lastResort');
          return const SizedBox.shrink();
        },
      ),
    ];

    testWidgets('it draws the first variant that fits', (
      WidgetTester tester,
    ) async {
      final List<String> drawn = <String>[];
      await _inColumn(tester, 400, FitBuilder(variants: variants(drawn)));
      expect(drawn, <String>['full false']);

      drawn.clear();
      await _inColumn(tester, 200, FitBuilder(variants: variants(drawn)));
      expect(drawn, <String>['compact false']);
    });

    testWidgets('it draws the last with the last resort flag when none fits', (
      WidgetTester tester,
    ) async {
      final List<String> drawn = <String>[];
      await _inColumn(tester, 100, FitBuilder(variants: variants(drawn)));
      expect(drawn, <String>['compact true']);
    });

    testWidgets('an unbounded parent is asking for the intrinsic width', (
      WidgetTester tester,
    ) async {
      final List<String> drawn = <String>[];
      await tester.pumpWidget(
        uiHarness(
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              SizedBox(
                height: 48,
                child: FitBuilder(variants: variants(drawn)),
              ),
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        drawn,
        <String>['full false'],
        reason: 'a control never shrinks itself (11 section 3.3, rule 2)',
      );
    });
  });

  group('UiLabel', () {
    testWidgets('it stays on one line in the column that broke it', (
      WidgetTester tester,
    ) async {
      for (final double width in <double>[480, 360, 280, 200]) {
        await _inColumn(tester, width, const UiLabel(_long));
        expect(_lines(tester), 1, reason: '$_long wrapped at $width dp');
      }
    });

    testWidgets('it ellipsises rather than growing a second line', (
      WidgetTester tester,
    ) async {
      await _inColumn(tester, 200, const UiLabel(_long));
      final RenderParagraph paragraph = _paragraph(tester);
      expect(paragraph.didExceedMaxLines, isTrue);
      expect(paragraph.overflow, TextOverflow.ellipsis);
      expect(paragraph.softWrap, isFalse);
      expect(paragraph.maxLines, 1);
    });

    testWidgets('the full text goes to the tooltip only when it overflows', (
      WidgetTester tester,
    ) async {
      final List<String> asked = <String>[];
      Widget label() => UiLabel(
        _long,
        tooltip: (BuildContext context, String message, Widget label) {
          asked.add(message);
          return label;
        },
      );

      await _inColumn(tester, 200, label());
      expect(asked, <String>[_long]);

      asked.clear();
      await _inColumn(tester, 900, label());
      expect(
        asked,
        isEmpty,
        reason: 'a label the reviewer can read whole carries no tooltip',
      );
    });

    testWidgets('the semantics label is the whole label when it is cut', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await _inColumn(tester, 200, const UiLabel(_long));
      expect(find.bySemanticsLabel(_long), findsOneWidget);
      handle.dispose();
    });

    testWidgets('a control that already set a foreground keeps it', (
      WidgetTester tester,
    ) async {
      late Color seen;
      await _inColumn(
        tester,
        400,
        Builder(
          builder: (BuildContext context) => DefaultTextStyle(
            style: context.ui.type.label.copyWith(
              color: context.ui.color.inkSecondary,
            ),
            child: const UiLabel('Queue'),
          ),
        ),
      );
      seen = _paragraph(tester).text.style!.color!;
      expect(seen, UiColor.light.inkSecondary);
    });
  });
}
