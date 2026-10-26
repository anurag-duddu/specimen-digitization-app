import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void _noop() {}

Rect _capsule(WidgetTester tester) => tester.getRect(
  find
      .descendant(
        of: find.byType(UiButton),
        matching: find.byType(DecoratedBox),
      )
      .first,
);

Rect _visibleContents(WidgetTester tester, String label) {
  final text = find.byWidgetPredicate(
    (widget) => widget is RichText && widget.text.toPlainText() == label,
  );
  final paragraph = tester.renderObject<RenderParagraph>(text);
  final origin = tester.getTopLeft(text);
  final boxes = paragraph.getBoxesForSelection(
    TextSelection(baseOffset: 0, extentOffset: label.length),
  );
  var bounds = boxes.first.toRect().shift(origin);
  for (final box in boxes.skip(1)) {
    bounds = bounds.expandToInclude(box.toRect().shift(origin));
  }
  for (final element
      in find
          .descendant(
            of: find.byType(UiButton),
            matching: find.byWidgetPredicate(
              (widget) => widget is UiIcon || widget is UiProgress,
            ),
          )
          .evaluate()) {
    bounds = bounds.expandToInclude(
      tester.getRect(find.byWidget(element.widget)),
    );
  }
  return bounds;
}

void main() {
  testWidgets(
    'labelled glyphs follow text size without growing the hit box alone',
    (tester) async {
      for (final size in UiSize.values) {
        for (final scale in [1.0, 2.0]) {
          await tester.pumpWidget(
            uiHarness(
              textScaler: TextScaler.linear(scale),
              child: UiButton(
                label: 'Save',
                size: size,
                leading: UiIcons.save,
                onPressed: _noop,
              ),
            ),
          );
          await tester.pump();
          final glyph = tester.getRect(find.byType(UiIcon));
          expect(glyph.height, (size == UiSize.lg ? 20 : 16) * scale);
          final capsule = _capsule(tester);
          expect(capsule.contains(glyph.topLeft), isTrue);
          expect(capsule.contains(glyph.bottomRight), isTrue);
          expect(
            tester.getSize(find.byType(UiButton)).height,
            greaterThanOrEqualTo(48),
          );
          expect(tester.takeException(), isNull);
        }
      }
    },
  );

  testWidgets('local busy feedback paints below text and inside the capsule', (
    tester,
  ) async {
    for (final size in UiSize.values) {
      for (final scale in [1.0, 2.0, 4.0]) {
        for (final width in [48.0, 240.0]) {
          await tester.pumpWidget(
            uiHarness(
              textScaler: TextScaler.linear(scale),
              disableAnimations: true,
              child: SizedBox(
                width: width,
                child: UiButton(
                  label: 'Save',
                  size: size,
                  loading: true,
                  onPressed: _noop,
                ),
              ),
            ),
          );
          await tester.pump();
          final progress = tester.getRect(find.byType(UiProgress));
          final capsule = _capsule(tester);
          final text = tester.getRect(find.text('Save'));
          expect(capsule.contains(progress.topLeft), isTrue);
          expect(
            capsule.contains(progress.bottomRight - const Offset(.01, .01)),
            isTrue,
          );
          expect(progress.top, greaterThanOrEqualTo(text.bottom));
          final stack = tester.getRect(
            find
                .ancestor(
                  of: find.byType(UiProgress),
                  matching: find.byType(Stack),
                )
                .first,
          );
          expect(stack.contains(progress.topLeft), isTrue);
          expect(
            stack.contains(progress.bottomRight - const Offset(.01, .01)),
            isTrue,
          );
          expect(tester.takeException(), isNull);
        }
      }
    }
  });

  testWidgets(
    'tight buttons preserve readable action space before decorative icons',
    (tester) async {
      for (final direction in TextDirection.values) {
        for (final size in UiSize.values) {
          for (final width in [48.0, 80.0, 96.0, 104.0]) {
            for (final loading in [false, true]) {
              await tester.pumpWidget(
                uiHarness(
                  textDirection: direction,
                  textScaler: const TextScaler.linear(2),
                  disableAnimations: true,
                  child: SizedBox(
                    width: width,
                    child: UiButton(
                      label: 'Save corrections',
                      busyLabel: 'Saving corrections',
                      leading: UiIcons.add,
                      trailing: UiIcons.next,
                      size: size,
                      loading: loading,
                      onPressed: _noop,
                    ),
                  ),
                ),
              );
              await tester.pump();
              expect(
                tester.takeException(),
                isNull,
                reason: '$direction / $size / $width / loading $loading',
              );
              final text = find.text(
                loading ? 'Saving corrections' : 'Save corrections',
              );
              expect(tester.getSize(text).width, greaterThan(0));
              expect(tester.getSize(find.byType(UiButton)).width, width);
              expect(
                tester.widget<UiTooltip>(find.byType(UiTooltip)).message,
                loading ? 'Saving corrections' : 'Save corrections',
              );
            }
          }
        }
      }
    },
  );

  testWidgets('pending content keeps intrinsic width in an unbounded row', (
    tester,
  ) async {
    for (final expand in [false, true]) {
      double? width;
      for (final loading in [false, true]) {
        await tester.pumpWidget(
          uiHarness(
            disableAnimations: true,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                UiButton(
                  label: 'Save',
                  busyLabel: 'Saving correction',
                  loading: loading,
                  expand: expand,
                  onPressed: _noop,
                ),
              ],
            ),
          ),
        );
        await tester.pump();
        width ??= _capsule(tester).width;
        expect(_capsule(tester).width, width);
        expect(
          _visibleContents(
            tester,
            loading ? 'Saving correction' : 'Save',
          ).center.dx,
          closeTo(_capsule(tester).center.dx, 1.1),
        );
        expect(tester.takeException(), isNull);
      }
    }
  });

  testWidgets('loading reservation centers visible content in both states', (
    tester,
  ) async {
    for (final direction in TextDirection.values) {
      for (final scale in [1.0, 2.0]) {
        for (final icons in [0, 1, 2, 3]) {
          for (final labels in [
            ('Save', 'Saving correction'),
            ('Save this correction', 'Saving'),
          ]) {
            double? restingWidth;
            for (final loading in [false, true]) {
              await tester.pumpWidget(
                uiHarness(
                  textDirection: direction,
                  textScaler: TextScaler.linear(scale),
                  disableAnimations: true,
                  child: UiButton(
                    label: labels.$1,
                    busyLabel: labels.$2,
                    loading: loading,
                    leading: icons & 1 != 0 ? UiIcons.add : null,
                    trailing: icons & 2 != 0 ? UiIcons.next : null,
                    onPressed: _noop,
                  ),
                ),
              );
              await tester.pump();
              final capsule = _capsule(tester);
              final contents = _visibleContents(
                tester,
                loading ? labels.$2 : labels.$1,
              );
              expect(
                contents.center.dx,
                closeTo(capsule.center.dx, 1.1),
                reason:
                    '$direction / $scale / icons $icons / $labels / loading $loading: center visible content, not an empty future slot',
              );
              restingWidth ??= capsule.width;
              expect(
                capsule.width,
                restingWidth,
                reason:
                    'An explicit pending label keeps the action group stable.',
              );
              final button = tester.widget<UiButton>(find.byType(UiButton));
              expect(
                tester.getSize(find.byType(UiButton)).width,
                closeTo(
                  button.intrinsicWidth(tester.element(find.byType(UiButton))),
                  0.5,
                ),
              );
              expect(tester.takeException(), isNull);
            }
          }
        }
      }
    }
  });

  testWidgets('expanded and narrow pending buttons center their actual row', (
    tester,
  ) async {
    for (final direction in TextDirection.values) {
      for (final width in [140.0, 360.0]) {
        for (final loading in [false, true]) {
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              disableAnimations: true,
              child: SizedBox(
                width: width,
                child: UiButton(
                  label: 'Save',
                  busyLabel: 'Saving correction',
                  loading: loading,
                  expand: true,
                  onPressed: _noop,
                ),
              ),
            ),
          );
          await tester.pump();
          expect(_capsule(tester).width, width);
          if (!loading || width == 360) {
            expect(
              _visibleContents(
                tester,
                loading ? 'Saving correction' : 'Save',
              ).center.dx,
              closeTo(_capsule(tester).center.dx, 1.1),
            );
          }
          if (loading && width == 140) {
            expect(
              tester.widget<UiTooltip>(find.byType(UiTooltip)).message,
              'Saving correction',
            );
          }
          expect(tester.takeException(), isNull);
        }
      }
    }
  });

  testWidgets(
    'label and icon changes resize the capsule without reserved loading space',
    (tester) async {
      final widths = <double>[];
      for (final label in ['Save', 'Save correction']) {
        for (final leading in [null, UiIcons.add]) {
          await tester.pumpWidget(
            uiHarness(
              child: UiButton(label: label, leading: leading, onPressed: _noop),
            ),
          );
          await tester.pump();
          widths.add(_capsule(tester).width);
          expect(
            _visibleContents(tester, label).center.dx,
            closeTo(_capsule(tester).center.dx, 0.5),
          );
        }
      }
      expect(widths[1], greaterThan(widths[0]));
      expect(widths[2], greaterThan(widths[0]));
      expect(widths[3], greaterThan(widths[2]));
    },
  );
}
