import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

Finder _target(String label) =>
    find.ancestor(of: find.text(label), matching: find.byType(Pressable)).first;

Rect _visibleText(WidgetTester tester, String text) {
  final paragraph = tester.renderObject<RenderParagraph>(
    find.descendant(of: find.text(text), matching: find.byType(RichText)),
  );
  final boxes = paragraph.getBoxesForSelection(
    TextSelection(baseOffset: 0, extentOffset: text.length),
  );
  var bounds = boxes.first.toRect();
  for (final box in boxes.skip(1)) {
    bounds = bounds.expandToInclude(box.toRect());
  }
  return bounds.shift(paragraph.localToGlobal(Offset.zero));
}

void _expectCompleteParagraph(WidgetTester tester, String text) {
  final paragraph = tester.renderObject<RenderParagraph>(
    find.descendant(of: find.text(text), matching: find.byType(RichText)),
  );
  final full = TextPainter(
    text: paragraph.text,
    textDirection: paragraph.textDirection,
    textAlign: paragraph.textAlign,
    textHeightBehavior: paragraph.textHeightBehavior,
    textWidthBasis: paragraph.textWidthBasis,
    locale: paragraph.locale,
    textScaler: paragraph.textScaler,
    strutStyle: paragraph.strutStyle,
  )..layout(maxWidth: paragraph.size.width);
  expect(paragraph.didExceedMaxLines, isFalse);
  expect(paragraph.size.height, greaterThanOrEqualTo(full.height - .01));
  full.dispose();
}

void main() {
  for (final direction in TextDirection.values) {
    testWidgets(
      'narrow action variants preserve readable content in ${direction.name}',
      (tester) async {
        for (final size in UiActionSize.values) {
          for (final width in [80.0, 96.0, 104.0]) {
            for (final busy in [false, true]) {
              for (final dot in [false, true]) {
                for (final hierarchy in [
                  UiActionHierarchy.filled,
                  UiActionHierarchy.outline,
                ]) {
                  var actions = 0;
                  await tester.pumpWidget(
                    uiHarness(
                      textDirection: direction,
                      textScaler: const TextScaler.linear(2),
                      disableAnimations: true,
                      child: SingleChildScrollView(
                        child: SizedBox(
                          width: width,
                          child: UiActionButton(
                            label: 'Save',
                            leading: UiIcons.add,
                            leadingDot: dot,
                            trailing: UiIcons.next,
                            size: size,
                            hierarchy: hierarchy,
                            busy: busy,
                            onPressed: () => actions++,
                          ),
                        ),
                      ),
                    ),
                  );
                  await tester.pump();
                  expect(
                    tester.takeException(),
                    isNull,
                    reason: '$size / $width / $hierarchy / $busy / $dot',
                  );
                  _expectCompleteParagraph(tester, 'Save');
                  expect(
                    tester.getSize(find.text('Save')).width,
                    greaterThan(0),
                  );
                  final bounds = tester.getRect(find.byType(UiActionButton));
                  final text = _visibleText(tester, 'Save');
                  expect(text.left, greaterThanOrEqualTo(bounds.left));
                  expect(text.right, lessThanOrEqualTo(bounds.right));
                  expect(text.bottom, lessThanOrEqualTo(bounds.bottom));
                  if (busy) {
                    expect(find.byType(UiProgress), findsOneWidget);
                    final progress = tester.getRect(find.byType(UiProgress));
                    expect(progress.left, greaterThanOrEqualTo(bounds.left));
                    expect(progress.right, lessThanOrEqualTo(bounds.right));
                    expect(progress.bottom, lessThanOrEqualTo(bounds.bottom));
                  }
                  await tester.tap(find.byType(UiActionButton));
                  expect(actions, busy ? 0 : 1);
                }
              }
            }
          }
        }
      },
    );

    testWidgets(
      'action variants keep natural wide anatomy in ${direction.name}',
      (tester) async {
        for (final busy in [false, true]) {
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              disableAnimations: true,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  UiActionButton(
                    label: 'Save',
                    leading: UiIcons.add,
                    trailing: UiIcons.next,
                    busy: busy,
                    onPressed: () {},
                  ),
                ],
              ),
            ),
          );
          await tester.pump();
          final context = tester.element(find.byType(UiActionButton));
          final ui = context.ui;
          final textWidth = measureLabel(context, 'Save', ui.type.label).width;
          final leadingWidth = busy
              ? UiProgressSize.small.diameter
              : ui.space.iconInline;
          expect(
            tester.getSize(find.byType(UiActionButton)).width,
            closeTo(
              ui.space.s4 * 2 +
                  leadingWidth +
                  ui.space.s2 * 2 +
                  textWidth +
                  ui.space.iconInline,
              .01,
            ),
          );
          expect(find.byType(UiIcon), findsNWidgets(busy ? 1 : 2));
          if (busy) expect(find.byType(UiProgress), findsOneWidget);
          expect(tester.takeException(), isNull);
        }
      },
    );

    testWidgets(
      'icon-only action keeps its identifying content in ${direction.name}',
      (tester) async {
        final semantics = tester.ensureSemantics();
        for (final busy in [false, true]) {
          var actions = 0;
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              disableAnimations: true,
              child: SizedBox(
                width: 48,
                child: UiActionButton(
                  label: 'Save',
                  leading: UiIcons.add,
                  iconOnly: true,
                  hierarchy: UiActionHierarchy.outline,
                  busy: busy,
                  onPressed: () => actions++,
                ),
              ),
            ),
          );
          await tester.pump();
          expect(find.text('Save'), findsNothing);
          expect(find.byType(busy ? UiProgress : UiIcon), findsOneWidget);
          // The icon tooltip merges the inner Pressable into one published
          // action. Inspect that accessible node rather than its merged child.
          final accessibleAction = find.bySemanticsLabel('Save');
          expect(accessibleAction, findsOneWidget);
          final data = tester.getSemantics(accessibleAction).getSemanticsData();
          expect(data.label, 'Save');
          expect(data.flagsCollection.isButton, isTrue);
          expect(data.hasAction(SemanticsAction.tap), !busy);
          await tester.tap(find.byType(UiActionButton));
          expect(actions, busy ? 0 : 1);
          expect(tester.takeException(), isNull);
        }
        semantics.dispose();
      },
    );

    testWidgets(
      'unselected choices center visible content in ${direction.name}',
      (tester) async {
        int? value;
        final changes = <int?>[];
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            textScaler: const TextScaler.linear(2),
            child: SizedBox(
              width: 320,
              child: StatefulBuilder(
                builder: (context, setState) => UiChoiceGroup<int>(
                  label: 'Review state',
                  choices: const [
                    UiChoice(value: 1, label: 'Review'),
                    UiChoice(value: 2, label: 'Ready'),
                  ],
                  value: value,
                  onChanged: (next) {
                    changes.add(next);
                    setState(() => value = next);
                  },
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        final resting = tester.getRect(_target('Review'));
        expect(
          _visibleText(tester, 'Review').center.dx,
          closeTo(resting.center.dx, .01),
        );
        expect(find.byType(UiIcon), findsNothing);
        await tester.tap(find.text('Review'));
        await tester.pumpAndSettle();
        expect(changes, [1]);
        expect(tester.getRect(_target('Review')).size, resting.size);
        final check = tester.getRect(
          find.descendant(of: _target('Review'), matching: find.byType(UiIcon)),
        );
        final content = check.expandToInclude(_visibleText(tester, 'Review'));
        expect(
          content.center.dx,
          closeTo(tester.getRect(_target('Review')).center.dx, .01),
        );
        await tester.tap(find.text('Reset view'));
        await tester.pumpAndSettle();
        expect(changes, [1, null]);
        expect(tester.getRect(_target('Review')).size, resting.size);
        expect(
          _visibleText(tester, 'Review').center.dx,
          closeTo(tester.getRect(_target('Review')).center.dx, .01),
        );
        expect(tester.takeException(), isNull);
      },
    );

    testWidgets('joined short labels keep full targets in ${direction.name}', (
      tester,
    ) async {
      var selected = '';
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          child: SizedBox(
            width: 200,
            child: UiButtonGroup(
              label: 'Commands',
              items: [
                for (final label in ['A', 'B', 'C'])
                  UiButtonGroupItem(
                    label: label,
                    onPressed: () => selected = label,
                  ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      for (final label in ['A', 'B', 'C']) {
        final bounds = tester.getRect(_target(label));
        expect(bounds.width, greaterThanOrEqualTo(UiDensity.hitBox));
        expect(bounds.height, greaterThanOrEqualTo(UiDensity.hitBox));
        expect(
          _visibleText(tester, label).center.dx,
          closeTo(bounds.center.dx, .01),
        );
      }
      await tester.tap(find.text('B'));
      expect(selected, 'B');
      expect(tester.takeException(), isNull);
    });

    testWidgets(
      'joined group includes its separators at the fit boundary in ${direction.name}',
      (tester) async {
        final stroke = UiThemeData.light().shape.stroke.hairline;
        final required = UiDensity.hitBox * 2 + stroke * 3;
        for (final fits in [true, false]) {
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              child: SizedBox(
                width: fits ? required : required - stroke,
                child: UiButtonGroup(
                  label: 'View commands',
                  iconOnly: true,
                  items: [
                    UiButtonGroupItem(
                      label: 'Inspect',
                      icon: UiIcons.search,
                      onPressed: () {},
                    ),
                    UiButtonGroupItem(
                      label: 'Close',
                      icon: UiIcons.close,
                      onPressed: () {},
                    ),
                  ],
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          final targets = find.byType(Pressable);
          final first = tester.getRect(targets.at(0));
          final second = tester.getRect(targets.at(1));
          if (fits) {
            expect(first.top, second.top);
          } else {
            expect(second.top, greaterThanOrEqualTo(first.bottom));
          }
          expect(tester.takeException(), isNull);
        }
      },
    );

    testWidgets(
      'decision bar measures itself in an unbounded ${direction.name} row',
      (tester) async {
        for (final count in <String?>[null, '2 of 4']) {
          var decided = 0;
          await tester.pumpWidget(
            uiHarness(
              size: const Size(1180, 800),
              textDirection: direction,
              textScaler: const TextScaler.linear(2),
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: UiDecisionBar(
                  count: count,
                  primary: UiButton(
                    label: 'Save record',
                    onPressed: () => decided++,
                  ),
                  secondary: UiButton(label: 'Cancel', onPressed: () {}),
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          final size = tester.getSize(find.byType(UiDecisionBar));
          expect(size.width.isFinite, isTrue);
          _expectCompleteParagraph(tester, 'Save record');
          _expectCompleteParagraph(tester, 'Cancel');
          if (count != null) _expectCompleteParagraph(tester, count);
          await tester.tap(find.text('Save record'));
          expect(decided, 1);
        }
      },
    );

    testWidgets(
      'short tag counts leave the remaining width for the label in ${direction.name}',
      (tester) async {
        const label = 'Long records';
        var removals = 0;
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            child: SizedBox(
              width: 200,
              child: UiTag(label: label, count: 1, onRemove: () => removals++),
            ),
          ),
        );
        await tester.pumpAndSettle();
        final paragraph = tester.renderObject<RenderParagraph>(
          find.descendant(
            of: find.text(label),
            matching: find.byType(RichText),
          ),
        );
        final singleLine = TextPainter(
          text: paragraph.text,
          textDirection: paragraph.textDirection,
          textAlign: paragraph.textAlign,
          textHeightBehavior: paragraph.textHeightBehavior,
          textWidthBasis: paragraph.textWidthBasis,
          locale: paragraph.locale,
          textScaler: paragraph.textScaler,
          strutStyle: paragraph.strutStyle,
        )..layout();
        expect(paragraph.size.width, greaterThanOrEqualTo(singleLine.width));
        expect(paragraph.size.height, closeTo(singleLine.height, .01));
        singleLine.dispose();
        _expectCompleteParagraph(tester, label);
        _expectCompleteParagraph(tester, '1');
        await tester.tap(find.bySemanticsLabel('Remove $label'));
        expect(removals, 1);
        expect(tester.takeException(), isNull);
      },
    );

    testWidgets(
      'tag count reflows without clipping at 400 percent ${direction.name}',
      (tester) async {
        const count = 1234567890123456789;
        var removals = 0;
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            textScaler: const TextScaler.linear(4),
            child: SingleChildScrollView(
              child: SizedBox(
                width: 200,
                child: UiTag(
                  label: 'Records',
                  count: count,
                  onRemove: () => removals++,
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        _expectCompleteParagraph(tester, '$count');
        _expectCompleteParagraph(tester, 'Records');
        final tag = tester.getRect(find.byType(UiTag));
        for (final label in ['Records', '$count']) {
          final text = _visibleText(tester, label);
          expect(text.left, greaterThanOrEqualTo(tag.left));
          expect(text.right, lessThanOrEqualTo(tag.right));
          expect(text.bottom, lessThanOrEqualTo(tag.bottom));
        }
        await tester.ensureVisible(find.bySemanticsLabel('Remove Records'));
        await tester.tap(find.bySemanticsLabel('Remove Records'));
        expect(removals, 1);
      },
    );
  }
}
