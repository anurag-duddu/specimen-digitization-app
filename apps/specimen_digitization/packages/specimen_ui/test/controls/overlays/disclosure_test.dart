// `UiDisclosure` (10 section 4.3).

import 'dart:ui' show Tristate;

import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

const String _title = 'Label coverage';
const String _summary = 'Three regions, one unmeasured';
const String _body =
    'Region 3 has no measured area, so coverage is reported for two regions.';
const String _label = '$_title. $_summary';

Widget _disclosure({
  Key? key,
  bool initiallyExpanded = false,
  ValueChanged<bool>? onExpansionChanged,
}) => SizedBox(
  width: 360,
  child: UiDisclosure(
    key: key,
    title: _title,
    summary: _summary,
    initiallyExpanded: initiallyExpanded,
    onExpansionChanged: onExpansionChanged,
    child: const Text(_body),
  ),
);

void main() {
  testWidgets('the header keeps a 48 dp hit box in both densities', (
    WidgetTester tester,
  ) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: const UiDisclosure(title: _title, child: Text(_body)),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.getSize(find.byType(Pressable)).height,
        greaterThanOrEqualTo(UiDensity.hitBox),
        reason:
            'a header whose title fits one line is density.rowHeight tall, '
            'which is 44 in pointer, and clause 2 sets 48 in both densities: '
            'every tap target guideline on a screen with a disclosure failed '
            'on the 44',
      );
    }
  });

  testWidgets('the body is hidden until the row is pressed', (
    WidgetTester tester,
  ) async {
    final List<bool> changes = <bool>[];
    await tester.pumpWidget(
      uiHarness(child: _disclosure(onExpansionChanged: changes.add)),
    );
    expect(find.text(_body), findsNothing);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(find.text(_body), findsOneWidget);
    expect(changes, <bool>[true]);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(find.text(_body), findsNothing);
    expect(changes, <bool>[true, false]);
  });

  testWidgets('it can be built open', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(child: _disclosure(initiallyExpanded: true)),
    );
    await tester.pumpAndSettle();
    expect(find.text(_body), findsOneWidget);
    expect(
      find.text(_summary),
      findsOneWidget,
      reason: 'summary hiding is opt-in; existing callers keep their summary',
    );
    expect(find.bySemanticsLabel(_label), findsOneWidget);
  });

  for (final bool initiallyExpanded in <bool>[false, true]) {
    testWidgets(
      'opt-in summary appears once through toggles, initially open=$initiallyExpanded',
      (WidgetTester tester) async {
        final SemanticsHandle handle = tester.ensureSemantics();
        try {
          final List<bool> changes = <bool>[];
          await tester.pumpWidget(
            uiHarness(
              child: UiDisclosure(
                title: _title,
                summary: _summary,
                hideSummaryWhenExpanded: true,
                initiallyExpanded: initiallyExpanded,
                onExpansionChanged: changes.add,
                child: const Text(_summary),
              ),
            ),
          );
          await tester.pumpAndSettle();
          for (final bool expanded in <bool>[
            initiallyExpanded,
            !initiallyExpanded,
            initiallyExpanded,
          ]) {
            expect(find.text(_summary), findsOneWidget);
            final String headerLabel = expanded ? _title : _label;
            final SemanticsData header = tester
                .getSemantics(find.bySemanticsLabel(headerLabel))
                .getSemanticsData();
            expect(
              header.flagsCollection.isExpanded,
              expanded ? Tristate.isTrue : Tristate.isFalse,
            );
            expect(
              find.bySemanticsLabel(_summary),
              expanded ? findsOneWidget : findsNothing,
              reason: 'the open body owns the information, not the header',
            );
            await tester.tap(find.bySemanticsLabel(headerLabel));
            await tester.pumpAndSettle();
          }
          expect(changes, <bool>[
            !initiallyExpanded,
            initiallyExpanded,
            !initiallyExpanded,
          ]);
        } finally {
          handle.dispose();
        }
      },
    );
  }

  testWidgets('Space and Enter toggle it', (WidgetTester tester) async {
    for (final LogicalKeyboardKey key in <LogicalKeyboardKey>[
      LogicalKeyboardKey.space,
      LogicalKeyboardKey.enter,
    ]) {
      // A fresh key, so the second pass starts closed rather than reusing
      // the state the first one left open.
      await tester.pumpWidget(
        uiHarness(child: _disclosure(key: ValueKey<String>(key.keyLabel))),
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(key);
      await tester.pumpAndSettle();
      expect(find.text(_body), findsOneWidget, reason: key.keyLabel);
    }
  });

  testWidgets('the caret turns half a circle and the row reports expanded', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: _disclosure()));

    double turns() =>
        tester.widget<AnimatedRotation>(find.byType(AnimatedRotation)).turns;
    Tristate expanded() => tester
        .getSemantics(find.bySemanticsLabel(_label))
        .getSemanticsData()
        .flagsCollection
        .isExpanded;

    expect(turns(), 0);
    expect(expanded(), Tristate.isFalse);

    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pumpAndSettle();
    expect(turns(), UiDisclosureStyle.caretTurns);
    expect(expanded(), Tristate.isTrue);
    handle.dispose();
  });

  testWidgets('the body keeps its own semantics and is never glass', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: _disclosure(initiallyExpanded: true)),
    );
    await tester.pumpAndSettle();
    expect(
      find.text(_body),
      findsOneWidget,
      reason: 'the header wrapper must not swallow the body',
    );
    expect(
      glassPaneCount(),
      0,
      reason: 'a disclosure is content inside a pane, not a pane',
    );
    expectGlassBudget(tester);
  });

  testWidgets('it collapses its motion under reduced motion', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: _disclosure()),
    );
    await tester.tap(find.bySemanticsLabel(_label));
    await tester.pump();
    expect(find.text(_body), findsOneWidget);
    expect(tester.binding.transientCallbackCount, 0);
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    for (final (TextDirection direction, TextScaler scaler)
        in <(TextDirection, TextScaler)>[
          (TextDirection.rtl, TextScaler.noScaling),
          (TextDirection.ltr, const TextScaler.linear(2)),
        ]) {
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          textScaler: scaler,
          child: _disclosure(initiallyExpanded: true),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(_body), findsOneWidget);
    }
  });

  testWidgets('a trailing sits before the caret and leaves the header alone', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 360,
          child: UiDisclosure(
            title: _title,
            summary: _summary,
            trailing: UiChip(label: 'Derived'),
            semanticsLabel: '$_label. Basis: derived',
            child: Text(_body),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final Rect chip = tester.getRect(find.byType(UiChip));
    final Rect caret = tester.getRect(find.byType(AnimatedRotation));
    final Rect title = tester.getRect(find.text(_title));
    expect(chip.right, lessThan(caret.left), reason: 'the chip is before it');
    expect(title.right, lessThan(chip.left), reason: 'and after the text');
    expect(
      tester.getSize(find.byType(Pressable)).height,
      greaterThanOrEqualTo(UiDensity.hitBox),
    );
    // The header publishes one node, so the chip is read as part of the label
    // the caller gave, and a press on the chip toggles the row.
    expect(find.bySemanticsLabel('$_label. Basis: derived'), findsOneWidget);
    expect(find.bySemanticsLabel('Derived'), findsNothing);
    await tester.tap(find.byType(UiChip));
    await tester.pumpAndSettle();
    expect(find.text(_body), findsOneWidget);
    handle.dispose();
  });

  /// The text of [title], and whether the line it was drawn on cut it short.
  ///
  /// Compared against the width the same words take unbroken, so a label that
  /// was ellipsised is caught whether or not the framework reports an
  /// overflow.
  (double drawn, double needed, bool exceeded) titleFit(
    WidgetTester tester,
    String title,
  ) {
    final RenderParagraph paragraph = tester.renderObject<RenderParagraph>(
      find.text(title),
    );
    final TextPainter painter = TextPainter(
      text: paragraph.text,
      textDirection: TextDirection.ltr,
      textScaler: paragraph.textScaler,
      maxLines: 1,
    )..layout();
    final double needed = painter.width;
    painter.dispose();
    return (paragraph.size.width, needed, paragraph.didExceedMaxLines);
  }

  testWidgets('a trailing moves under the text when the title would not fit', (
    WidgetTester tester,
  ) async {
    const String long = 'Elevation from (m)';
    const UiChip chip = UiChip(label: 'As written');
    Widget at(double width) => uiHarness(
      textScaler: const TextScaler.linear(2),
      child: SizedBox(
        width: width,
        child: const UiDisclosure(
          title: long,
          summary: 'Supported 1950.72',
          trailing: chip,
          child: Text(_body),
        ),
      ),
    );

    // Wide enough for the title and the chip on one line.
    await tester.pumpWidget(at(640));
    await tester.pumpAndSettle();
    Rect title = tester.getRect(find.text(long));
    Rect box = tester.getRect(find.byType(UiChip));
    expect(box.left, greaterThan(title.right), reason: 'beside the title');
    expect(box.center.dy, lessThan(title.bottom + box.height));
    final double besideHeight = tester.getSize(find.byType(Pressable)).height;

    // Too narrow for both, at double text size: the chip goes under the text.
    await tester.pumpWidget(at(390));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    title = tester.getRect(find.text(long));
    box = tester.getRect(find.byType(UiChip));
    final Rect summary = tester.getRect(find.text('Supported 1950.72'));
    expect(box.left, title.left, reason: 'starts where the title starts');
    expect(box.top, greaterThanOrEqualTo(summary.bottom));
    expect(
      tester.getSize(find.byType(Pressable)).height,
      greaterThan(besideHeight),
      reason: 'the chip has a line of its own',
    );
    final (double drawn, double needed, bool exceeded) = titleFit(tester, long);
    expect(exceeded, isFalse, reason: 'the title keeps every letter');
    expect(drawn, greaterThanOrEqualTo(needed - 0.5));
  });

  testWidgets('a trailing never costs the title a letter, at any width', (
    WidgetTester tester,
  ) async {
    const String long = 'Province or state';
    for (final (double width, double scale) in <(double, double)>[
      (320, 1),
      (390, 1),
      (390, 2),
      (520, 2),
    ]) {
      await tester.pumpWidget(
        uiHarness(
          textScaler: TextScaler.linear(scale),
          child: SizedBox(
            width: width,
            child: const UiDisclosure(
              title: long,
              summary: 'Supported Davao',
              trailing: UiChip(label: 'As written'),
              child: Text(_body),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: '$width at ${scale}x');
      final (double drawn, double needed, bool exceeded) = titleFit(
        tester,
        long,
      );
      expect(exceeded, isFalse, reason: '$width at ${scale}x');
      expect(drawn, greaterThanOrEqualTo(needed - 0.5));
      expect(find.byType(UiChip), findsOneWidget);
    }
  });

  testWidgets('a trailing moves under the text rather than cut the summary', (
    WidgetTester tester,
  ) async {
    const String summary = 'Supported · Philippines · Required';
    Widget at(double width, double scale) => uiHarness(
      textScaler: TextScaler.linear(scale),
      child: SizedBox(
        width: width,
        child: const UiDisclosure(
          title: 'Country',
          summary: summary,
          trailing: UiChip(label: 'Derived'),
          child: Text(_body),
        ),
      ),
    );
    RenderParagraph paragraph() =>
        tester.renderObject<RenderParagraph>(find.text(summary));

    // At double text the title alone fits beside the chip, but the two lines
    // of summary the row has left would lose the review state.
    await tester.pumpWidget(at(390, 2));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(paragraph().didExceedMaxLines, isFalse, reason: 'the whole summary');
    expect(
      tester.getRect(find.byType(UiChip)).left,
      tester.getRect(find.text('Country')).left,
      reason: 'under the text, where the summary has the whole line',
    );

    // At normal text everything fits on the one line: the chip stays beside.
    await tester.pumpWidget(at(390, 1));
    await tester.pumpAndSettle();
    expect(paragraph().didExceedMaxLines, isFalse);
    expect(
      tester.getRect(find.byType(UiChip)).left,
      greaterThan(tester.getRect(find.text('Country')).right),
    );
  });

  testWidgets('it satisfies the control contract', (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _disclosure(),
      semanticsLabel: _label,
      labelsNeverWrap: true,
      wrappingContent: <String>{_summary},
      geometryFromType: true,
      fit: FitExpectation(
        check: (WidgetTester tester, double width) async {
          expect(find.text(_title), findsOneWidget);
        },
      ),
    );
  });
}
