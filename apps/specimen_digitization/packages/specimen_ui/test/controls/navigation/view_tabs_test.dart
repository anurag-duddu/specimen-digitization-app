import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const _views = [
  UiViewTab(value: 'review', label: 'Needs review', icon: UiIcons.needsReview),
  UiViewTab(value: 'deferred', label: 'Deferred', icon: UiIcons.deferred),
  UiViewTab(value: 'cleared', label: 'Cleared', icon: UiIcons.cleared),
];

class _Host extends StatefulWidget {
  const _Host({this.all = false, this.onChanged});
  final bool all;
  final ValueChanged<String>? onChanged;
  @override
  State<_Host> createState() => _HostState();
}

class _HostState extends State<_Host> {
  late String value = widget.all ? 'all' : 'review';
  @override
  Widget build(BuildContext context) => UiViewTabs<String>(
    views: [
      if (value == 'all')
        const UiViewTab(
          value: 'all',
          label: 'All specimens',
          icon: UiIcons.queue,
        ),
      ..._views,
    ],
    value: value,
    semanticsLabel: 'Queue view',
    onChanged: (next) {
      widget.onChanged?.call(next);
      setState(() => value = next);
    },
  );
}

Finder _tab(String label) => find.byWidgetPredicate(
  (widget) => widget is Pressable && widget.semanticsLabel == label,
);

void main() {
  for (final width in [160.0, 272.0, 320.0, 390.0]) {
    for (final scale in [1.0, 2.0]) {
      for (final brightness in Brightness.values) {
        testWidgets('view names and icons fit $width / $scale / $brightness', (
          tester,
        ) async {
          final semantics = tester.ensureSemantics();
          await tester.pumpWidget(
            uiHarness(
              brightness: brightness,
              textScaler: TextScaler.linear(scale),
              child: Center(
                child: SizedBox(width: width, child: const _Host()),
              ),
            ),
          );
          await tester.pumpAndSettle();
          expect(find.text('Needs review'), findsOneWidget);
          expect(find.text('Deferred'), findsNothing);
          expect(find.text('Cleared'), findsNothing);
          final paragraph = tester.renderObject<RenderParagraph>(
            find.text('Needs review'),
          );
          expect(paragraph.didExceedMaxLines, isFalse);
          for (final view in _views) {
            final target = tester.getRect(_tab(view.label));
            expect(target.width, greaterThanOrEqualTo(48));
            expect(target.height, greaterThanOrEqualTo(48));
            final glyph = tester.getRect(
              find.descendant(
                of: _tab(view.label),
                matching: find.byType(UiIcon),
              ),
            );
            expect(glyph.left, greaterThanOrEqualTo(target.left));
            expect(glyph.right, lessThanOrEqualTo(target.right));
            expect(find.bySemanticsLabel(view.label), findsOneWidget);
            expect(
              tester
                  .getSemantics(find.bySemanticsLabel(view.label))
                  .getSemanticsData()
                  .flagsCollection
                  .isSelected
                  .toBoolOrNull(),
              view.value == 'review',
            );
          }
          expect(
            tester.getSemantics(_tab('Needs review')),
            containsSemantics(isSelected: true),
          );
          expect(tester.takeException(), isNull);
          semantics.dispose();
        });
      }
    }
  }

  for (final direction in TextDirection.values) {
    testWidgets('arrows, Home and End select named views in $direction', (
      tester,
    ) async {
      final selected = <String>[];
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          child: Center(child: _Host(onChanged: selected.add)),
        ),
      );
      await tester.pumpAndSettle();
      tester.widget<Pressable>(_tab('Needs review')).focusNode!.requestFocus();
      await tester.pump();
      await tester.sendKeyEvent(
        direction == TextDirection.ltr
            ? LogicalKeyboardKey.arrowRight
            : LogicalKeyboardKey.arrowLeft,
      );
      await tester.pumpAndSettle();
      expect(selected.last, 'deferred');
      expect(find.text('Deferred'), findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.end);
      await tester.pumpAndSettle();
      expect(selected.last, 'cleared');
      await tester.sendKeyEvent(LogicalKeyboardKey.home);
      await tester.pumpAndSettle();
      expect(selected.last, 'review');
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('removing the temporary All view preserves focused identity', (
    tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const Center(child: _Host(all: true))),
    );
    await tester.pumpAndSettle();
    final review = tester.widget<Pressable>(_tab('Needs review')).focusNode!;
    tester.widget<Pressable>(_tab('All specimens')).focusNode!.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(find.text('All specimens'), findsNothing);
    expect(FocusManager.instance.primaryFocus, same(review));
    expect(
      tester.widget<Pressable>(_tab('Needs review')).focusNode,
      same(review),
    );
    expect(
      tester.widget<Pressable>(_tab('Deferred')).focusNode!.skipTraversal,
      isTrue,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('shared control contract', (tester) async {
    await expectControlContract(
      tester,
      (_) => const Center(child: SizedBox(width: 320, child: _Host())),
      semanticsLabel: 'Needs review',
      wrappingContent: {'Needs review'},
      geometryFromType: true,
    );
  });

  testWidgets('keyboard reveals an offscreen view without scrolling its page', (
    tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const Center(child: SizedBox(width: 160, child: _Host())),
      ),
    );
    await tester.pumpAndSettle();
    tester.widget<Pressable>(_tab('Needs review')).focusNode!.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.end);
    await tester.pumpAndSettle();
    expect(find.text('Cleared'), findsOneWidget);
    expect(_tab('Cleared').hitTestable(), findsOneWidget);
    expect(
      tester.state<ScrollableState>(find.byType(Scrollable)).position.pixels,
      greaterThan(0),
    );
    expect(tester.takeException(), isNull);
  });
}
