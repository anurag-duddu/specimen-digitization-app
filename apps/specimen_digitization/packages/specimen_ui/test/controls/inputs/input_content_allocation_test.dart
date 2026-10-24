import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  for (final direction in TextDirection.values) {
    for (final scale in [1.0, 2.0]) {
      testWidgets('domain affixes use their natural single-line width '
          '${direction.name} ${scale}x', (tester) async {
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            textScaler: TextScaler.linear(scale),
            child: SizedBox(
              width: 286 * scale,
              child: const UiField(
                label: 'Website',
                showLabel: false,
                prefixText: 'https://',
                suffixText: '.museum',
              ),
            ),
          ),
        );
        for (final value in ['https://', '.museum']) {
          final paragraph = tester.renderObject<RenderParagraph>(
            find.text(value),
          );
          final natural = TextPainter(
            text: paragraph.text,
            textDirection: paragraph.textDirection,
            textAlign: paragraph.textAlign,
            textHeightBehavior: paragraph.textHeightBehavior,
            textWidthBasis: paragraph.textWidthBasis,
            locale: paragraph.locale,
            textScaler: paragraph.textScaler,
            strutStyle: paragraph.strutStyle,
          )..layout();
          expect(paragraph.size.width, closeTo(natural.width, .01));
          expect(paragraph.size.height, closeTo(natural.height, .01));
          natural.dispose();
        }
        final prefix = tester.getRect(find.text('https://'));
        final suffix = tester.getRect(find.text('.museum'));
        final editor = tester.getRect(find.byType(EditableText));
        final gap = tester.element(find.byType(UiField)).ui.space.s2;
        final between = direction == TextDirection.ltr
            ? suffix.left - prefix.right
            : prefix.left - suffix.right;
        expect(editor.width, closeTo(between - 2 * gap, .01));
        expect(editor.width, greaterThanOrEqualTo(80 * scale));
        await tester.enterText(find.byType(EditableText), 'field');
        expect(
          tester
              .widget<EditableText>(find.byType(EditableText))
              .controller
              .text,
          'field',
        );
        expect(tester.takeException(), isNull);
      });
    }
    for (final scale in [1.0, 2.0]) {
      testWidgets('short affixes leave remaining width to the editor '
          '${direction.name} ${scale}x', (tester) async {
        Future<void> show({String? prefix, String? suffix}) async {
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              textScaler: TextScaler.linear(scale),
              child: SizedBox(
                width: 400,
                child: UiField(
                  label: 'Measurement',
                  showLabel: false,
                  prefixText: prefix,
                  suffixText: suffix,
                ),
              ),
            ),
          );
          await tester.pump();
        }

        await show();
        final available = tester.getSize(find.byType(EditableText)).width;
        final gap = tester.element(find.byType(UiField)).ui.space.s2;
        for (final affixes in [(r'$', null), (null, 'kg'), (r'$', 'kg')]) {
          await show(prefix: affixes.$1, suffix: affixes.$2);
          var occupied = 0.0;
          for (final value in [affixes.$1, affixes.$2]) {
            if (value != null) {
              occupied += tester.getSize(find.text(value)).width + gap;
            }
          }
          expect(
            tester.getSize(find.byType(EditableText)).width,
            closeTo(available - occupied, .01),
            reason: 'Short affixes must not consume unused proportional slots.',
          );
          await tester.enterText(find.byType(EditableText), '12345');
          expect(
            tester
                .widget<EditableText>(find.byType(EditableText))
                .controller
                .text,
            '12345',
          );
          expect(tester.takeException(), isNull);
        }
      });
    }

    testWidgets('input group short actions leave remaining width to field '
        '${direction.name}', (tester) async {
      var actions = 0;
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          child: SizedBox(
            width: 720,
            child: UiInputGroup(
              leading: UiButton(label: 'USD', onPressed: () => actions++),
              field: const UiField(label: 'Amount', showLabel: false),
              trailing: UiButton(label: 'Apply', onPressed: () => actions++),
            ),
          ),
        ),
      );
      await tester.pump();
      final gap = tester.element(find.byType(UiInputGroup)).ui.space.s2;
      final buttons = tester.widgetList<UiButton>(find.byType(UiButton));
      var occupied = gap * 2;
      for (final button in buttons) {
        occupied += tester.getSize(find.byWidget(button)).width;
      }
      expect(
        tester.getSize(find.byType(UiField)).width,
        closeTo(720 - occupied, .01),
        reason: 'The editor receives space left after actual action widths.',
      );
      await tester.tap(find.text('USD'));
      await tester.tap(find.text('Apply'));
      expect(actions, 2);
      await tester.enterText(find.byType(EditableText), '42');
      expect(
        tester.widget<EditableText>(find.byType(EditableText)).controller.text,
        '42',
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('long affixes wrap without taking the editor room '
        '${direction.name}', (tester) async {
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          textScaler: const TextScaler.linear(2),
          child: const SizedBox(
            width: 320,
            child: UiField(
              label: 'Measurement',
              showLabel: false,
              prefixText: 'US dollars',
              suffixText: 'per item',
            ),
          ),
        ),
      );
      final editor = tester.getRect(find.byType(EditableText));
      final prefixWidth = tester.getSize(find.text('US dollars')).width;
      final suffixWidth = tester.getSize(find.text('per item')).width;
      final usable = editor.width + prefixWidth + suffixWidth;
      expect(editor.width, greaterThanOrEqualTo(UiDensity.hitBox));
      expect(editor.width, closeTo(usable / 3, .01));
      for (final label in ['US dollars', 'per item']) {
        final paragraph = tester.renderObject<RenderParagraph>(
          find.text(label),
        );
        expect(paragraph.didExceedMaxLines, isFalse);
        expect(paragraph.size.width, lessThanOrEqualTo(usable / 3 + .01));
        expect(paragraph.size.height, greaterThan(40));
      }
      await tester.enterText(find.byType(EditableText), '12');
      expect(
        tester.widget<EditableText>(find.byType(EditableText)).controller.text,
        '12',
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('short affix gives unused budget to the longer affix '
        '${direction.name}', (tester) async {
      for (final shortFirst in [true, false]) {
        const short = 'kg';
        const long = 'measurement in United States dollars';
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            textScaler: const TextScaler.linear(2),
            child: SizedBox(
              width: 320,
              child: UiField(
                label: 'Measurement',
                showLabel: false,
                prefixText: shortFirst ? short : long,
                suffixText: shortFirst ? long : short,
              ),
            ),
          ),
        );
        final shortParagraph = tester.renderObject<RenderParagraph>(
          find.text(short),
        );
        final longParagraph = tester.renderObject<RenderParagraph>(
          find.text(long),
        );
        final natural = TextPainter(
          text: shortParagraph.text,
          textDirection: shortParagraph.textDirection,
          textAlign: shortParagraph.textAlign,
          textHeightBehavior: shortParagraph.textHeightBehavior,
          textWidthBasis: shortParagraph.textWidthBasis,
          locale: shortParagraph.locale,
          textScaler: shortParagraph.textScaler,
          strutStyle: shortParagraph.strutStyle,
        )..layout();
        expect(shortParagraph.size.width, closeTo(natural.width, .01));
        expect(shortParagraph.size.height, closeTo(natural.height, .01));
        natural.dispose();
        final editorWidth = tester.getSize(find.byType(EditableText)).width;
        final usable =
            editorWidth + shortParagraph.size.width + longParagraph.size.width;
        expect(editorWidth, closeTo(usable / 3, .01));
        expect(editorWidth, greaterThanOrEqualTo(UiDensity.hitBox));
        expect(
          longParagraph.size.width,
          closeTo(usable * 2 / 3 - shortParagraph.size.width, .01),
        );
        expect(longParagraph.didExceedMaxLines, isFalse);
        await tester.enterText(find.byType(EditableText), '12');
        expect(
          tester
              .widget<EditableText>(find.byType(EditableText))
              .controller
              .text,
          '12',
        );
        expect(tester.takeException(), isNull);
      }
    });

    testWidgets('input group bounds long sides and returns absent slot space '
        '${direction.name}', (tester) async {
      for (final sides in [0, 1, 2]) {
        var actions = 0;
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            child: SizedBox(
              width: 720,
              child: UiInputGroup(
                leading: sides > 0
                    ? UiButton(
                        label: 'United States dollars',
                        onPressed: () => actions++,
                      )
                    : null,
                field: const UiField(label: 'Amount', showLabel: false),
                trailing: sides > 1
                    ? UiButton(
                        label: 'Apply the chosen measurement',
                        onPressed: () => actions++,
                      )
                    : null,
              ),
            ),
          ),
        );
        final gap = tester.element(find.byType(UiInputGroup)).ui.space.s2;
        var occupied = sides * gap;
        for (final button in tester.widgetList<UiButton>(
          find.byType(UiButton),
        )) {
          final finder = find.byWidget(button);
          final width = tester.getSize(finder).width;
          expect(width, lessThanOrEqualTo((720 - sides * gap) / (3 + sides)));
          occupied += width;
          await tester.tap(finder);
        }
        expect(actions, sides);
        expect(
          tester.getSize(find.byType(UiField)).width,
          closeTo(720 - occupied, .01),
        );
        await tester.enterText(find.byType(EditableText), '42');
        expect(tester.takeException(), isNull);
      }
    });

    testWidgets('input group remains editable in narrow and unbounded parents '
        '${direction.name}', (tester) async {
      for (final scale in [1.0, 2.0]) {
        for (final unbounded in [false, true]) {
          var actions = 0;
          final group = UiInputGroup(
            leading: UiButton(label: 'USD', onPressed: () => actions++),
            field: const UiField(label: 'Amount', showLabel: false),
            trailing: UiButton(label: 'Apply', onPressed: () => actions++),
          );
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              textScaler: TextScaler.linear(scale),
              child: unbounded
                  ? Row(mainAxisSize: MainAxisSize.min, children: [group])
                  : SizedBox(width: 320, child: group),
            ),
          );
          final rect = tester.getRect(find.byType(UiInputGroup));
          expect(rect.width, unbounded ? 640 : 320);
          expect(
            tester.getSize(find.byType(EditableText)).width,
            greaterThan(100),
          );
          if (!unbounded || scale > 1.5) {
            expect(
              tester.getRect(find.text('USD')).bottom,
              lessThan(tester.getRect(find.byType(UiField)).top),
            );
            expect(
              tester.getRect(find.text('Apply')).top,
              greaterThan(tester.getRect(find.byType(UiField)).bottom),
            );
          }
          await tester.tap(find.text('USD'));
          await tester.tap(find.text('Apply'));
          expect(actions, 2);
          await tester.enterText(find.byType(EditableText), '72');
          expect(
            tester
                .widget<EditableText>(find.byType(EditableText))
                .controller
                .text,
            '72',
          );
          expect(tester.takeException(), isNull);
        }
      }
    });
  }
}
