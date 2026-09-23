// `UiTimeline` (10 section 4.5) is not interactive; a child inside an entry
// may be, and that child carries its own contract. What the timeline owes is
// the order, the marker, the connector between entries and none after the
// last, a phrase per entry that stands alone, and a layout that survives a
// narrow window at 200 percent text and a right-to-left one.

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

/// Three lookups the way the record's thread lists them: one neutral, one
/// with a glyph and a tone, one with a trailing word and a child.
List<UiTimelineEntry> _lookups(UiThemeData ui, {VoidCallback? onShow}) =>
    <UiTimelineEntry>[
      const UiTimelineEntry(
        title: 'Name check, Global Names Verifier',
        meta: 'Attempt 1',
      ),
      UiTimelineEntry(
        title: 'Species match, GBIF Backbone',
        meta: 'Attempt 1',
        glyph: UiIcons.authority,
        tone: ui.color.status.authority,
      ),
      UiTimelineEntry(
        title: 'Place lookup, Google Maps',
        meta: 'Attempt 2',
        glyph: UiIcons.blocked,
        tone: ui.color.status.blocked,
        trailing: const Text('Timed out'),
        child: onShow == null
            ? null
            : UiButton(label: 'Show the response', onPressed: onShow),
      ),
    ];

Future<UiThemeData> _pump(
  WidgetTester tester, {
  List<UiTimelineEntry> Function(UiThemeData ui)? entries,
  String? semanticsLabel,
  Brightness brightness = Brightness.light,
  TextDirection textDirection = TextDirection.ltr,
  TextScaler textScaler = TextScaler.noScaling,
  Size size = const Size(800, 600),
  VoidCallback? onShow,
}) async {
  final UiThemeData ui = brightness == Brightness.dark
      ? UiThemeData.dark()
      : UiThemeData.light();
  await tester.pumpWidget(
    uiHarness(
      brightness: brightness,
      textDirection: textDirection,
      textScaler: textScaler,
      size: size,
      child: SingleChildScrollView(
        child: UiTimeline(
          semanticsLabel: semanticsLabel,
          entries:
              (entries ?? (UiThemeData ui) => _lookups(ui, onShow: onShow))(ui),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return ui;
}

/// The stroke colour of every marker disc, in reading order.
List<Color> _markerStrokes(WidgetTester tester) => tester
    .widgetList<DecoratedBox>(
      find.descendant(
        of: find.byType(UiTimeline),
        matching: find.byType(DecoratedBox),
      ),
    )
    .map((DecoratedBox box) => box.decoration)
    .whereType<ShapeDecoration>()
    .where((ShapeDecoration d) => d.shape is CircleBorder)
    .map((ShapeDecoration d) => (d.shape as CircleBorder).side.color)
    .toList();

void main() {
  testWidgets('an entry reads title, then meta, then its child', (
    WidgetTester tester,
  ) async {
    await _pump(tester, onShow: () {});
    final double title = tester
        .getTopLeft(find.text('Place lookup, Google Maps'))
        .dy;
    final double meta = tester.getTopLeft(find.text('Attempt 2')).dy;
    final double child = tester.getTopLeft(find.byType(UiButton)).dy;
    expect(title, lessThan(meta));
    expect(meta, lessThan(child));
  });

  testWidgets('entries are drawn in the order given', (
    WidgetTester tester,
  ) async {
    await _pump(tester);
    final List<double> tops = <String>[
      'Name check, Global Names Verifier',
      'Species match, GBIF Backbone',
      'Place lookup, Google Maps',
    ].map((String t) => tester.getTopLeft(find.text(t)).dy).toList();
    expect(tops, orderedEquals(<double>[...tops]..sort()));
  });

  testWidgets('a marker without a glyph shows the entry position', (
    WidgetTester tester,
  ) async {
    await _pump(tester);
    expect(find.text('1'), findsOneWidget);
    expect(
      find.text('2'),
      findsNothing,
      reason: 'the second entry has a glyph, which replaces its number',
    );
    final Iterable<UiIcon> glyphs = tester.widgetList<UiIcon>(
      find.descendant(
        of: find.byType(UiTimeline),
        matching: find.byType(UiIcon),
      ),
    );
    expect(glyphs.map((UiIcon icon) => icon.spec), <IconSpec>[
      UiIcons.authority,
      UiIcons.blocked,
    ]);
    expect(
      glyphs.map((UiIcon icon) => icon.size),
      everyElement(UiIconSize.small),
    );
  });

  testWidgets('the marker takes the tone, and no tone is inkSecondary', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = await _pump(tester);
    expect(_markerStrokes(tester), <Color>[
      ui.color.inkSecondary,
      ui.color.status.authority.content,
      ui.color.status.blocked.content,
    ]);
  });

  testWidgets('every marker is the same disc on paper', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = await _pump(tester);
    final Iterable<ShapeDecoration> discs = tester
        .widgetList<DecoratedBox>(
          find.descendant(
            of: find.byType(UiTimeline),
            matching: find.byType(DecoratedBox),
          ),
        )
        .map((DecoratedBox box) => box.decoration)
        .whereType<ShapeDecoration>()
        .where((ShapeDecoration d) => d.shape is CircleBorder);
    expect(discs, hasLength(3));
    for (final ShapeDecoration disc in discs) {
      expect(disc.color, ui.color.paper);
    }
    final Iterable<Element> sizes = find
        .descendant(
          of: find.byType(UiTimeline),
          matching: find.byWidgetPredicate(
            (Widget w) =>
                w is DecoratedBox &&
                w.decoration is ShapeDecoration &&
                (w.decoration as ShapeDecoration).shape is CircleBorder,
          ),
        )
        .evaluate();
    for (final Element disc in sizes) {
      expect(disc.size, Size.square(ui.space.iconAction));
    }
  });

  testWidgets('a connector joins each entry to the next, none after the last', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = await _pump(tester);
    final Finder connectors = find.descendant(
      of: find.byType(UiTimeline),
      matching: find.byWidgetPredicate(
        (Widget w) => w is ColoredBox && w.color == ui.color.hairline,
      ),
    );
    expect(connectors, findsNWidgets(2));
    final double lastTitle = tester
        .getTopLeft(find.text('Place lookup, Google Maps'))
        .dy;
    for (final Element connector in connectors.evaluate()) {
      final RenderBox box = connector.renderObject! as RenderBox;
      expect(
        box.localToGlobal(Offset.zero).dy,
        lessThan(lastTitle),
        reason: 'no connector hangs below the last entry',
      );
    }
  });

  testWidgets('the trailing sits beside the title, and under it when narrow', (
    WidgetTester tester,
  ) async {
    await _pump(tester);
    final Rect wideTitle = tester.getRect(
      find.text('Place lookup, Google Maps'),
    );
    final Rect wideTrailing = tester.getRect(find.text('Timed out'));
    expect(wideTrailing.left, greaterThan(wideTitle.right));
    expect(wideTrailing.center.dy, closeTo(wideTitle.center.dy, 4));

    await _pump(tester, size: const Size(240, 900));
    final Rect narrowTitle = tester.getRect(
      find.text('Place lookup, Google Maps'),
    );
    final Rect narrowTrailing = tester.getRect(find.text('Timed out'));
    expect(narrowTrailing.top, greaterThanOrEqualTo(narrowTitle.bottom));
  });

  testWidgets('the timeline is a list and each entry a list item', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await _pump(tester, semanticsLabel: 'Lookups');
    final SemanticsNode list = tester.getSemantics(
      find.bySemanticsLabel('Lookups'),
    );
    expect(list.getSemanticsData().role, SemanticsRole.list);
    for (final String phrase in <String>[
      '1 of 3: Name check, Global Names Verifier, Attempt 1',
      '2 of 3: Species match, GBIF Backbone, Attempt 1',
      '3 of 3: Place lookup, Google Maps, Attempt 2',
    ]) {
      final SemanticsNode item = tester.getSemantics(
        find.bySemanticsLabel(phrase),
      );
      expect(item.getSemanticsData().role, SemanticsRole.listItem);
    }
    handle.dispose();
  });

  testWidgets('a phrase the caller gives replaces the default', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await _pump(
      tester,
      entries: (UiThemeData ui) => const <UiTimelineEntry>[
        UiTimelineEntry(
          title: 'Species match, GBIF Backbone',
          meta: 'Attempt 1',
          semanticsLabel: 'Species match in GBIF Backbone found one name',
        ),
      ],
    );
    expect(
      find.bySemanticsLabel('Species match in GBIF Backbone found one name'),
      findsOneWidget,
    );
    expect(find.bySemanticsLabel(RegExp('1 of 1')), findsNothing);
    handle.dispose();
  });

  testWidgets('a control in a child keeps its own node', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    int shown = 0;
    await _pump(tester, onShow: () => shown++);
    expect(find.bySemanticsLabel('Show the response'), findsOneWidget);
    await tester.tap(find.byType(UiButton));
    await tester.pump();
    expect(shown, 1);
    handle.dispose();
  });

  testWidgets('right to left puts the rail on the right', (
    WidgetTester tester,
  ) async {
    await _pump(tester, textDirection: TextDirection.rtl);
    final double marker = tester.getCenter(find.text('1')).dx;
    final double title = tester
        .getCenter(find.text('Name check, Global Names Verifier'))
        .dx;
    expect(marker, greaterThan(title));
  });

  testWidgets('a narrow window at 200 percent text wraps and keeps the disc', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = await _pump(
      tester,
      size: const Size(320, 1600),
      textScaler: const TextScaler.linear(2),
      onShow: () {},
    );
    expect(tester.takeException(), isNull);
    final Element disc = find
        .descendant(
          of: find.byType(UiTimeline),
          matching: find.byWidgetPredicate(
            (Widget w) =>
                w is DecoratedBox &&
                w.decoration is ShapeDecoration &&
                (w.decoration as ShapeDecoration).shape is CircleBorder,
          ),
        )
        .evaluate()
        .first;
    expect(disc.size, Size.square(ui.space.iconAction));
    final Rect title = tester.getRect(
      find.text('Name check, Global Names Verifier'),
    );
    expect(title.right, lessThanOrEqualTo(320));
  });

  testWidgets('both modes resolve', (WidgetTester tester) async {
    final UiThemeData dark = await _pump(tester, brightness: Brightness.dark);
    expect(tester.takeException(), isNull);
    expect(_markerStrokes(tester).first, dark.color.inkSecondary);
  });

  testWidgets('an empty timeline draws nothing', (WidgetTester tester) async {
    await _pump(tester, entries: (UiThemeData ui) => const <UiTimelineEntry>[]);
    expect(tester.getSize(find.byType(UiTimeline)), Size.zero);
    expect(
      find.descendant(of: find.byType(UiTimeline), matching: find.byType(Text)),
      findsNothing,
    );
  });

  test('the style binds every token it draws with', () {
    final UiThemeData ui = UiThemeData.light();
    final UiTimelineStyle style = UiTimelineStyle.resolve(ui);
    expect(style.markerSize, ui.space.iconAction);
    expect(style.stroke, ui.shape.stroke.emphasis);
    expect(style.markerFill, ui.color.paper);
    expect(style.connectorColor, ui.color.hairline);
    expect(style.neutralTone, ui.color.inkSecondary);
    expect(style.titleColor, ui.color.ink);
    expect(style.metaColor, ui.color.inkSecondary);
    expect(style.railGap, ui.space.s3);
    expect(style.entryGap, ui.space.s4);
    expect(style.childGap, ui.space.s2);
  });
}
