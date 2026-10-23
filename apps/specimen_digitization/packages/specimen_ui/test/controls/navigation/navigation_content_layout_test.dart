import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const _status = 'Noch nicht vollständig zur Veröffentlichung freigegeben';
const _shortcut = 'Steuerung + Umschalttaste + Eingabetaste';

RenderParagraph _paragraph(WidgetTester tester, String text) =>
    tester.renderObject<RenderParagraph>(
      find.descendant(of: find.text(text), matching: find.byType(RichText)),
    );

void _expectComplete(WidgetTester tester, String text) {
  final RenderParagraph paragraph = _paragraph(tester, text);
  final TextPainter complete = TextPainter(
    text: paragraph.text,
    textDirection: paragraph.textDirection,
    textScaler: paragraph.textScaler,
    strutStyle: paragraph.strutStyle,
  )..layout(maxWidth: paragraph.size.width);
  expect(paragraph.didExceedMaxLines, isFalse, reason: text);
  expect(paragraph.size.height, greaterThanOrEqualTo(complete.height - .01));
  complete.dispose();
}

Finder _controlFor(String text) =>
    find.ancestor(of: find.text(text), matching: find.byType(Pressable)).first;

void main() {
  for (final TextDirection direction in TextDirection.values) {
    testWidgets('navigation reflows a long badge at 2x $direction', (
      tester,
    ) async {
      String? selected;
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          textScaler: const TextScaler.linear(2),
          child: SizedBox(
            width: 280,
            height: 500,
            child: UiNavigationMenu(
              sections: const [
                UiNavigationSection(
                  items: [
                    UiNavigationItem(
                      id: 'pending',
                      label: 'Pending',
                      icon: UiIcons.record,
                      badge: _status,
                    ),
                    UiNavigationItem(id: 'history', label: 'History'),
                  ],
                ),
              ],
              selectedId: null,
              expandedIds: const {},
              onSelected: (value) => selected = value,
              onExpandedChanged: (_) {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      _expectComplete(tester, _status);
      final Rect row = tester.getRect(_controlFor('Pending'));
      final Rect badge = tester.getRect(find.text(_status));
      expect(row.contains(badge.topLeft), isTrue);
      expect(row.contains(badge.bottomRight - const Offset(.01, .01)), isTrue);
      expect(
        badge.top,
        greaterThan(tester.getRect(find.text('Pending')).bottom),
      );
      expect(row.width, tester.getSize(_controlFor('History')).width);
      expect(row.height, greaterThanOrEqualTo(UiDensity.hitBox));
      await tester.tap(find.text('Pending'));
      expect(selected, 'pending');
    });

    testWidgets('vertical tabs reflow supporting badge at 2x $direction', (
      tester,
    ) async {
      final selected = ValueNotifier(0);
      addTearDown(selected.dispose);
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          textScaler: const TextScaler.linear(2),
          child: SizedBox(
            width: 240,
            height: 500,
            child: UiTabs(
              selected: selected,
              axis: Axis.vertical,
              semanticsLabel: 'Record panes',
              tabs: const [
                UiTab(label: 'Pending', icon: UiIcons.record, badge: _status),
                UiTab(label: 'History'),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      _expectComplete(tester, _status);
      final Rect row = tester.getRect(_controlFor('Pending'));
      final Rect badge = tester.getRect(find.text(_status));
      expect(badge.left, greaterThanOrEqualTo(row.left));
      expect(badge.right, lessThanOrEqualTo(row.right));
      expect(badge.bottom, lessThanOrEqualTo(row.bottom));
      expect(
        badge.top,
        greaterThan(tester.getRect(find.text('Pending')).bottom),
      );
      await tester.tap(find.text('History'));
      expect(selected.value, 1);
    });

    testWidgets('popover reflows a localized shortcut at 2x $direction', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(320, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      var selected = 0;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 900),
          textDirection: direction,
          textScaler: const TextScaler.linear(2),
          child: Align(
            alignment: Alignment.topCenter,
            child: UiMenuTrigger(
              label: 'Actions',
              semanticsLabel: 'Record actions',
              items: [
                UiMenuItem(
                  label: 'Export specimens',
                  icon: UiIcons.record,
                  shortcut: _shortcut,
                  onSelected: () => selected++,
                ),
              ],
            ),
          ),
        ),
      );
      await tester.tap(find.text('Actions'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      _expectComplete(tester, 'Export specimens');
      _expectComplete(tester, _shortcut);
      final Rect row = tester.getRect(_controlFor('Export specimens'));
      final Rect shortcut = tester.getRect(find.text(_shortcut));
      expect(shortcut.left, greaterThanOrEqualTo(row.left));
      expect(shortcut.right, lessThanOrEqualTo(row.right));
      expect(shortcut.bottom, lessThanOrEqualTo(row.bottom));
      expect(
        shortcut.top,
        greaterThan(tester.getRect(find.text('Export specimens')).bottom),
      );
      expect(row.height, greaterThanOrEqualTo(UiDensity.hitBox));
      await tester.tap(find.text('Export specimens'));
      await tester.pumpAndSettle();
      expect(selected, 1);
      expect(find.text(_shortcut), findsNothing);
    });

    testWidgets('first breadcrumb reserves no absent separator $direction', (
      tester,
    ) async {
      double lineHeight = 0;
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          textScaler: const TextScaler.linear(2),
          child: Builder(
            builder: (context) {
              final TextPainter painter = TextPainter(
                text: TextSpan(text: 'Research', style: context.ui.type.label),
                textDirection: direction,
                textScaler: MediaQuery.textScalerOf(context),
              )..layout();
              lineHeight = painter.height;
              final double width = painter.width + context.ui.space.s1;
              painter.dispose();
              return SizedBox(
                width: width,
                child: const UiBreadcrumbs(
                  items: [UiBreadcrumb(label: 'Research')],
                ),
              );
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(
        _paragraph(tester, 'Research').size.height,
        closeTo(lineHeight, .01),
      );
    });

    testWidgets('wide workspace bounds measured navigation at 2x $direction', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(1180, 700);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final selected = ValueNotifier(0);
      addTearDown(selected.dispose);
      const tabs = [
        UiTab(label: 'Collection administration'),
        UiTab(label: 'Photographic evidence'),
        UiTab(label: 'Research history'),
      ];
      await tester.pumpWidget(
        uiHarness(
          size: const Size(1180, 700),
          textDirection: direction,
          textScaler: const TextScaler.linear(2),
          child: Builder(
            builder: (context) => UiWorkspaceHeader(
              identity: const Text('Museum'),
              compactIdentity: const Text('Museum'),
              navigationWidth: UiTabStyle.resolve(
                context.ui,
                textScaler: MediaQuery.textScalerOf(context),
              ).intrinsicWidth(context, tabs),
              navigation: UiTabs(
                tabs: tabs,
                selected: selected,
                semanticsLabel: 'Workspace destinations',
              ),
              actions: [
                UiIconButton(
                  semanticsLabel: 'Account',
                  icon: UiIcons.settings,
                  onPressed: () {},
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      final Rect navigation = tester.getRect(find.byType(UiTabs));
      final Rect account = tester.getRect(find.byType(UiIconButton));
      if (direction == TextDirection.ltr) {
        expect(navigation.right, lessThanOrEqualTo(account.left));
      } else {
        expect(navigation.left, greaterThanOrEqualTo(account.right));
      }
      selected.value = 2;
      await tester.pumpAndSettle();
      expect(find.text('Research history').hitTestable(), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets(
      'horizontal tabs keep equal slots and scale-aware height $direction',
      (tester) async {
        final selected = ValueNotifier(0);
        addTearDown(selected.dispose);
        await tester.pumpWidget(
          uiHarness(
            textDirection: direction,
            textScaler: const TextScaler.linear(2),
            child: SizedBox(
              width: 500,
              child: UiTabs(
                selected: selected,
                semanticsLabel: 'Record panes',
                tabs: const [
                  UiTab(label: 'All'),
                  UiTab(label: 'Saved', icon: UiIcons.record, badge: '4'),
                ],
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        final Size plain = tester.getSize(_controlFor('All'));
        final Size decorated = tester.getSize(_controlFor('Saved'));
        expect(plain, decorated);
        expect(plain.height, greaterThanOrEqualTo(UiDensity.hitBox));
        _expectComplete(tester, 'All');
        _expectComplete(tester, 'Saved');
        await tester.tap(find.text('Saved'));
        expect(selected.value, 1);
      },
    );
  }
}
