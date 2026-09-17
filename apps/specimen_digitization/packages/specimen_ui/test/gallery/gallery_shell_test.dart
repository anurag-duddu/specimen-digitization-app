// The gallery shell's two arrangements (11 section 3.5).
//
// Below `medium` the page list is a `UiSelect` above the content and the
// content takes the full width; from `medium` up the sidebar stays. A 220 dp
// sidebar beside a 360 dp window leaves 130 dp for the page, which is the
// column the wrapping labels of 11 section 0 were first seen in, so the
// arrangement is not a nicety.
//
// The shell is the first consumer of `Adaptive`, and these are the boundary
// and the keyboard: a reviewer moves between pages with the keys in either
// arrangement, or the gallery is unreachable to half the people reviewing it.

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// Three pages with nothing on them.
///
/// Built here rather than taken from `galleryPages` so that what another slot
/// draws on its family page cannot change what this file asserts. A body of
/// one `Text` also means the only focusable widgets on screen are the page
/// list's own, which is what makes the tab counting below exact.
List<GalleryPage> _pages() => <GalleryPage>[
  GalleryPage(
    id: 'one',
    title: 'First page',
    summary: 'What the first page is evidence of.',
    builder: (BuildContext context) => const Text('the first body'),
  ),
  GalleryPage(
    id: 'two',
    title: 'Second page',
    summary: 'What the second page is evidence of.',
    builder: (BuildContext context) => const Text('the second body'),
  ),
  GalleryPage(
    id: 'three',
    title: 'Third page',
    summary: 'What the third page is evidence of.',
    builder: (BuildContext context) => const Text('the third body'),
  ),
];

Future<void> _pumpShell(WidgetTester tester, {required double width}) async {
  final Size window = Size(width, 800);
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    uiHarness(
      size: window,
      child: SizedBox.fromSize(
        size: window,
        child: UiGallery(pages: _pages()),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// The select the compact arrangement draws its page list as.
Finder get _pageSelect => find.byType(UiSelect<int>);

void main() {
  testWidgets('below medium the page list is a select above the content', (
    WidgetTester tester,
  ) async {
    await _pumpShell(tester, width: 360);
    expect(_pageSelect, findsOneWidget);
    final UiThemeData ui = UiThemeData.light();
    expect(
      tester.getSize(find.byType(Surface)).width,
      360 - 2 * ui.space.s4,
      reason:
          'the content takes the whole window but its gutters, which is the '
          'other half of 11 section 3.5: a sidebar here would leave 130 dp '
          'for the page',
    );
    expect(
      tester.getTopLeft(find.byType(Surface)).dx,
      ui.space.s4,
      reason: 'nothing stands where the sidebar used to be',
    );
  });

  testWidgets('from medium up the page list is the sidebar', (
    WidgetTester tester,
  ) async {
    await _pumpShell(tester, width: 700);
    expect(_pageSelect, findsNothing);
    final List<GalleryPage> pages = _pages();
    expect(
      find.text(pages.first.title),
      findsNWidgets(2),
      reason: 'the open page is a row of the list and the heading above it',
    );
    for (final GalleryPage page in pages.skip(1)) {
      expect(
        find.text(page.title),
        findsOneWidget,
        reason: 'every other page is a row of the list, at ${page.id}',
      );
    }
    expect(
      tester.getTopLeft(find.byType(Surface)).dx,
      220,
      reason: 'the content starts where the 220 dp sidebar ends',
    );
  });

  testWidgets('the arrangement changes at the medium boundary', (
    WidgetTester tester,
  ) async {
    await _pumpShell(tester, width: WindowClass.mediumMin - 1);
    expect(_pageSelect, findsOneWidget, reason: '599 is compact');
    await _pumpShell(tester, width: WindowClass.mediumMin);
    expect(_pageSelect, findsNothing, reason: '600 is medium');
  });

  testWidgets('the sidebar moves between pages from the keyboard', (
    WidgetTester tester,
  ) async {
    await _pumpShell(tester, width: 1000);
    expect(find.text('What the first page is evidence of.'), findsOneWidget);
    // One tab per row: the list is the only focusable thing on screen.
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(
      find.text('What the second page is evidence of.'),
      findsOneWidget,
      reason: 'Tab reached the second row and Enter opened it',
    );
  });

  testWidgets('the select moves between pages from the keyboard', (
    WidgetTester tester,
  ) async {
    await _pumpShell(tester, width: 360);
    expect(find.text('What the first page is evidence of.'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    // The first Down moves into the list, on the option already chosen; the
    // second moves off it, which is the part that has to change the page.
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(
      find.text('What the first page is evidence of.'),
      findsNothing,
      reason:
          'Tab reached the select, Enter opened it, Down moved through the '
          'list and Enter picked, so the content is another page',
    );
    expect(
      find.textContaining('is evidence of.'),
      findsOneWidget,
      reason: 'exactly one page is shown, whichever one was picked',
    );
  });

  testWidgets('the shell publishes no text style of its own', (
    WidgetTester tester,
  ) async {
    await _pumpShell(tester, width: 1000);
    final BuildContext body = tester.element(find.text('the first body'));
    expect(
      DefaultTextStyle.of(body).style.fontSize,
      UiThemeData.light().type.body.fontSize,
      reason:
          'the ambient style under the shell is the one UiTheme publishes '
          '(11 section 5), and the shell no longer publishes a second copy '
          'of it',
    );
  });
}
