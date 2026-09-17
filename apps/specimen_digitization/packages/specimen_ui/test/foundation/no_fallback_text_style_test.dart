// The `no_fallback_text_style` gate (10 section 8; 11 section 5).
//
// `MaterialApp` installs a `DefaultTextStyle` on `WidgetsApp.textStyle` that
// draws in red monospace at 48 with a double yellow underline: the "you
// forgot a Material" style. `Material` is what normally replaces it, and this
// system has no `Material` on a screen. So a route pushed on the root
// navigator, a popover hung on the overlay and a toast raised over a page all
// used to inherit it, which is how a dialog came to draw its title underlined
// twice in yellow.
//
// The fix is one publication, `UiTheme`'s, with the overlay frames publishing
// it again so the package is correct in a host that resets the style below
// it. This gate holds both halves: every gallery page and every overlay those
// pages offer, in a host that installs the hostile style on purpose.

import 'dart:async' show unawaited;

// The delegate only, as 10 section 1.3 keeps it: `FieldCore`'s `TextField`
// reads its selection toolbar strings from `MaterialLocalizations`, and a
// host built on `WidgetsApp` has to mount the delegate itself.
import 'package:flutter/material.dart' show DefaultMaterialLocalizations;
// `rendering.dart` for `RenderParagraph`: the gate reads what the engine was
// handed, not what a widget declared.
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The framework's fallback text style, as far as anything here can read it.
///
/// Reconstructed rather than imported: `_errorTextStyle` is private to
/// `material/app.dart`, and a gate that imported Material to reach it would
/// be testing Material rather than this package. The colours are left off
/// because nothing below reads them; what the gate reads is the label the
/// framework stamps on the style and the double underline it draws, which are
/// the two things a paragraph carries away when it inherits one.
const TextStyle frameworkFallback = TextStyle(
  fontFamily: 'monospace',
  fontSize: 48,
  fontWeight: FontWeight.w900,
  decoration: TextDecoration.underline,
  decorationStyle: TextDecorationStyle.double,
  debugLabel: 'fallback style; consider putting your text in a Material',
);

/// The window every page is pumped at.
const Size _window = Size(1180, 820);

/// Where the gate looks for its evidence: the string the framework stamps on
/// its fallback, which survives every `merge` into the paragraph's own style.
const String _fallbackMark = 'fallback style';

/// What a host built on `WidgetsApp` has to mount for the inputs family.
const List<LocalizationsDelegate<dynamic>> _localizations =
    <LocalizationsDelegate<dynamic>>[
      DefaultMaterialLocalizations.delegate,
      DefaultWidgetsLocalizations.delegate,
    ];

/// The route `home` is pushed onto.
///
/// `WidgetsApp` has no default one: `MaterialApp` supplies the Material page
/// route and this package supplies nothing, so a host built on `WidgetsApp`
/// names its own.
PageRoute<T> _route<T>(RouteSettings settings, WidgetBuilder builder) =>
    PageRouteBuilder<T>(
      settings: settings,
      pageBuilder:
          (
            BuildContext context,
            Animation<double> animation,
            Animation<double> secondary,
          ) => builder(context),
    );

/// A host that installs [frameworkFallback] and publishes the tokens the way
/// `main.dart` does, inside the application's builder.
///
/// This is the arrangement that produced the defect: the fallback is above
/// everything the application draws, and the only thing between it and a page
/// is [UiTheme].
Widget _hostWithFallbackAboveTheTokens(Widget page) => WidgetsApp(
  color: const Color(0xFF000000),
  debugShowCheckedModeBanner: false,
  textStyle: frameworkFallback,
  localizationsDelegates: _localizations,
  pageRouteBuilder: _route,
  builder: (BuildContext context, Widget? child) => UiTheme(
    data: UiThemeData.light(),
    child: child ?? const SizedBox.shrink(),
  ),
  home: page,
);

/// A host that installs [frameworkFallback] *below* the tokens.
///
/// The case the overlay frames exist for. A host may publish a style of its
/// own inside [UiTheme], and an overlay built from the navigator's own
/// context then inherits that rather than the product's. Only a frame that
/// publishes the style again from `context.ui` is correct here.
Widget _hostWithFallbackBelowTheTokens(Widget page) => UiTheme(
  data: UiThemeData.light(),
  child: WidgetsApp(
    color: const Color(0xFF000000),
    debugShowCheckedModeBanner: false,
    textStyle: frameworkFallback,
    localizationsDelegates: _localizations,
    pageRouteBuilder: _route,
    home: page,
  ),
);

/// Every style in [root] and its descendants.
List<TextStyle> _stylesOf(InlineSpan root) {
  final List<TextStyle> found = <TextStyle>[];
  void collect(InlineSpan span) {
    final TextStyle? style = span.style;
    if (style != null) found.add(style);
    if (span is TextSpan) span.children?.forEach(collect);
  }

  collect(root);
  return found;
}

/// True for a style that is drawn with two underlines.
bool _doubleUnderlined(TextStyle style) =>
    (style.decoration?.contains(TextDecoration.underline) ?? false) &&
    style.decorationStyle == TextDecorationStyle.double;

/// Fails when any paragraph on screen carries the framework fallback.
void expectNoFallbackTextStyle(WidgetTester tester, String where) {
  // Once each: `allRenderObjects` walks elements, and every widget between a
  // `Text` and its paragraph reports the same paragraph again.
  final Set<RenderParagraph> paragraphs = tester.allRenderObjects
      .whereType<RenderParagraph>()
      .toSet();
  expect(
    paragraphs,
    isNotEmpty,
    reason: 'nothing was drawn at $where, so the gate proved nothing',
  );
  for (final RenderParagraph paragraph in paragraphs) {
    final String text = paragraph.text.toPlainText(
      includeSemanticsLabels: false,
    );
    for (final TextStyle style in _stylesOf(paragraph.text)) {
      expect(
        style.debugLabel ?? '',
        isNot(contains(_fallbackMark)),
        reason:
            '"$text" at $where is drawn in the framework fallback. The style '
            'it inherited is ${style.debugLabel} (11 section 5).',
      );
      expect(
        _doubleUnderlined(style),
        isFalse,
        reason:
            '"$text" at $where is underlined twice, which nothing in this '
            'system draws (11 section 5).',
      );
    }
  }
}

/// Pumps [page] and settles it, in a window the gallery is drawn at.
Future<void> _pumpPage(WidgetTester tester, Widget host) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = _window;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(host);
  await tester.pumpAndSettle();
}

/// The page body, scrollable so a specimen below the fold can still be
/// reached and tapped.
Widget _pageBody(GalleryPage page) => Directionality(
  textDirection: TextDirection.ltr,
  child: SizedBox(
    width: _window.width,
    child: SingleChildScrollView(child: Builder(builder: page.builder)),
  ),
);

/// Every specimen on a page that opens an overlay.
///
/// The gallery names them all the same way, which is what makes this
/// mechanical: a button that opens something says so in its label.
Finder get _openers => find.byWidgetPredicate(
  (Widget widget) => widget is UiButton && widget.label.startsWith('Open'),
);

void main() {
  // `galleryPages` is `foundationPages` plus every family page, so this walks
  // both lists. The pages are pumped on their own rather than inside
  // `UiGallery`, because the shell publishes a text style of its own and a
  // gate that ran inside it would be measuring the shell.
  for (final GalleryPage page in galleryPages) {
    testWidgets('the ${page.id} page draws no fallback text style', (
      WidgetTester tester,
    ) async {
      await _pumpPage(
        tester,
        _hostWithFallbackAboveTheTokens(_pageBody(page)),
      );
      expectNoFallbackTextStyle(tester, 'the ${page.id} page');

      final int openers = _openers.evaluate().length;
      for (int i = 0; i < openers; i++) {
        final Finder opener = _openers.at(i);
        final String label = tester.widget<UiButton>(opener).label;
        await tester.ensureVisible(opener);
        await tester.pumpAndSettle();
        await tester.tap(opener);
        await tester.pumpAndSettle();
        expectNoFallbackTextStyle(tester, '"$label" on the ${page.id} page');
        await tester.sendKeyEvent(LogicalKeyboardKey.escape);
        await tester.pumpAndSettle();
      }
    });
  }

  group('an overlay frame publishes the style in a host that resets it', () {
    testWidgets('a dialog', (WidgetTester tester) async {
      late BuildContext host;
      await _pumpPage(
        tester,
        _hostWithFallbackBelowTheTokens(
          Builder(
            builder: (BuildContext context) {
              host = context;
              return const SizedBox.expand();
            },
          ),
        ),
      );
      // The route outlives the test body on purpose: the pane has to be on
      // screen while the assertions run.
      unawaited(
        showUiDialog<void>(
          context: host,
          semanticsLabel: 'Record a reason',
          builder: (BuildContext context) => const Text('Record a reason'),
        ),
      );
      await tester.pumpAndSettle();
      expectNoFallbackTextStyle(tester, 'a dialog');
    });

    testWidgets('a sheet', (WidgetTester tester) async {
      late BuildContext host;
      await _pumpPage(
        tester,
        _hostWithFallbackBelowTheTokens(
          Builder(
            builder: (BuildContext context) {
              host = context;
              return const SizedBox.expand();
            },
          ),
        ),
      );
      unawaited(
        showUiSheet<void>(
          context: host,
          semanticsLabel: 'Choose a source',
          builder: (BuildContext context) => const Text('Choose a source'),
        ),
      );
      await tester.pumpAndSettle();
      expectNoFallbackTextStyle(tester, 'a sheet');
    });

    testWidgets('a popover', (WidgetTester tester) async {
      final PopoverController controller = PopoverController();
      addTearDown(controller.dispose);
      await _pumpPage(
        tester,
        _hostWithFallbackBelowTheTokens(
          Align(
            child: Popover(
              controller: controller,
              overlayBuilder: (BuildContext context) =>
                  const Text('Sorted by risk'),
              child: const SizedBox(width: 120, height: 48),
            ),
          ),
        ),
      );
      controller.open();
      await tester.pumpAndSettle();
      expectNoFallbackTextStyle(tester, 'a popover');
    });

    testWidgets('a tooltip', (WidgetTester tester) async {
      await _pumpPage(
        tester,
        _hostWithFallbackBelowTheTokens(
          Align(
            child: UiTooltip(
              message: 'Open the region editor',
              // Painted rather than empty: a bare `SizedBox` hit tests
              // nothing, and the tooltip reveals on a press of its child.
              child: SizedBox(
                key: const ValueKey<String>('trigger'),
                width: 120,
                height: 48,
                child: ColoredBox(color: UiColor.light.paper),
              ),
            ),
          ),
        ),
      );
      await tester.longPress(find.byKey(const ValueKey<String>('trigger')));
      await tester.pumpAndSettle();
      expect(
        find.text('Open the region editor'),
        findsOneWidget,
        reason: 'the tooltip did not open, so the gate proved nothing',
      );
      expectNoFallbackTextStyle(tester, 'a tooltip');
    });

    testWidgets('a toast', (WidgetTester tester) async {
      await _pumpPage(
        tester,
        _hostWithFallbackBelowTheTokens(
          const Align(
            child: UiToast(
              data: UiToastData(message: 'Decision recorded'),
            ),
          ),
        ),
      );
      expectNoFallbackTextStyle(tester, 'a toast');
    });
  });
}
