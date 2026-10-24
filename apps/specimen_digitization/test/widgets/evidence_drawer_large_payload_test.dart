import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/evidence_drawer.dart';
import 'package:specimen_digitization/src/widgets/selectable_evidence.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import 'harness.dart';

const _notice = 'Preview shortened. Copy includes the full payload.';
const _tail = 'retained-payload-tail-must-only-be-copied';

Finder get _code => find.descendant(
  of: find.byType(SelectableEvidence),
  matching: find.byType(Text),
);

String _renderedPreview(WidgetTester tester) =>
    tester.widget<Text>(_code).data!;

Future<void> _open(
  WidgetTester tester,
  Object payload, {
  Size size = const Size(1000, 800),
  double textScale = 1,
  ThemeData? theme,
}) async {
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  await pumpComponent(
    tester,
    UiToastHost(
      child: SizedBox.expand(
        child: Center(
          child: EvidenceDrawer(
            payload: payload,
            title: 'Retained version data',
          ),
        ),
      ),
    ),
    size: size,
    theme: theme,
  );
  await tester.tap(uiButton('Retained version data'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('small payload retains full selectable text and its copy icon', (
    tester,
  ) async {
    // Exactly the character limit, including JSON's surrounding quotes.
    final payload = 'x' * 4094;
    await _open(tester, payload);
    expect(_renderedPreview(tester), EvidenceDrawer.pretty(payload));
    expect(find.text(_notice), findsNothing);
    expect(uiIconButton(EvidenceDrawer.copyLabel), findsOneWidget);
    expect(uiButton('Copy full payload'), findsNothing);
  });

  testWidgets('many short lines have bounded real text and semantics', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    final payload = <Object>[...List<int>.generate(10000, (i) => i), _tail];
    final full = EvidenceDrawer.pretty(payload);
    await _open(tester, payload);

    final preview = _renderedPreview(tester);
    expect(preview.split('\n'), hasLength(80));
    expect(preview.length, lessThanOrEqualTo(4096));
    expect(full, startsWith(preview));
    expect(find.text(_notice), findsOneWidget);
    expect(find.bySemanticsLabel(preview), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp(_tail)), findsNothing);
    expect(find.text(full), findsNothing);
    expect(uiIconButton(EvidenceDrawer.copyLabel), findsNothing);
    expect(uiButton('Copy full payload'), findsOneWidget);
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });

  testWidgets('a huge single line is bounded without exposing its tail', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    final payload = '${'x' * 1000000}$_tail';
    final full = EvidenceDrawer.pretty(payload);
    await _open(tester, payload);

    final preview = _renderedPreview(tester);
    expect(preview.length, 4096);
    expect(preview, isNot(contains('\n')));
    expect(full, startsWith(preview));
    expect(find.bySemanticsLabel(preview), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp(_tail)), findsNothing);
    expect(find.text(full), findsNothing);
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });

  for (final cluster in <String>['🦋', 'e\u0301', '👩🏽‍🔬', '🇺🇸']) {
    for (var cut = 0; cut <= cluster.length; cut++) {
      testWidgets('preview preserves $cluster at UTF-16 cut $cut', (
        tester,
      ) async {
        // Include the opening JSON quote when positioning every possible cut
        // before, within and immediately after this complete grapheme.
        final prefix = 'x' * (4095 - cut);
        final payload = '$prefix$cluster$_tail';
        final full = EvidenceDrawer.pretty(payload);
        await _open(tester, payload);

        final preview = _renderedPreview(tester);
        expect(preview, '"$prefix${cut == cluster.length ? cluster : ''}');
        expect(preview.length, lessThanOrEqualTo(4096));
        expect(full, startsWith(preview));
        expect(preview.runes, isNot(contains(0xfffd)));
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets('an oversized combining sequence cannot escape the bound', (
    tester,
  ) async {
    final payload = 'e${'\u0301' * 10000}$_tail';
    await _open(tester, payload);
    expect(_renderedPreview(tester), '"');
    expect(find.text(_notice), findsOneWidget);
    expect(uiButton('Copy full payload'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  for (final entry in productThemes.entries) {
    for (final size in <Size>[const Size(390, 844), const Size(1000, 800)]) {
      testWidgets('large payload copies exactly and Close stays reachable '
          '${entry.key} ${size.width.toInt()} at 200% text', (tester) async {
        final semantics = tester.ensureSemantics();
        final copies = <String>[];
        tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          SystemChannels.platform,
          (call) async {
            if (call.method == 'Clipboard.setData') {
              copies.add((call.arguments as Map)['text'] as String);
            }
            return null;
          },
        );
        addTearDown(
          () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
            SystemChannels.platform,
            null,
          ),
        );
        final payload = <String, Object>{
          'unicode': '🦋 e\u0301 👩🏽‍🔬',
          'records': List<int>.generate(10000, (i) => i),
          'retained': _tail,
        };
        final full = EvidenceDrawer.pretty(payload);
        await _open(
          tester,
          payload,
          size: size,
          textScale: 2,
          theme: entry.value,
        );

        expect(copies, isEmpty, reason: 'opening must not copy the payload');
        expect(uiButton('Close').hitTestable(), findsOneWidget);
        final closeBefore = tester.getRect(uiButton('Close'));
        expect(closeBefore.bottom, lessThanOrEqualTo(size.height));
        await tester.ensureVisible(uiButton('Copy full payload'));
        expect(find.bySemanticsLabel('Copy full payload'), findsOneWidget);
        await tester.tap(uiButton('Copy full payload'));
        await tester.pumpAndSettle();
        expect(copies, <String>[full]);
        expect(copies.single, contains(_tail));
        expect(
          tester
              .state<UiToastHostState>(find.byType(UiToastHost))
              .current
              ?.message,
          EvidenceDrawer.copiedMessage,
        );

        // Scroll through the bounded preview; its persistent modal footer
        // must remain available without walking back through the JSON.
        final previewBefore = tester.getRect(_code);
        await tester.dragFrom(
          Offset(size.width / 2, size.height * .55),
          const Offset(0, -300),
        );
        await tester.pumpAndSettle();
        expect(tester.getRect(_code).top, lessThan(previewBefore.top));
        expect(uiButton('Close').hitTestable(), findsOneWidget);
        expect(tester.getRect(uiButton('Close')), closeBefore);
        await expectAccessible(tester);
        await tester.tap(uiButton('Close'));
        await tester.pumpAndSettle();
        expect(find.text(_notice), findsNothing);
        expect(find.byType(SelectableEvidence), findsNothing);
        expect(tester.takeException(), isNull);
        semantics.dispose();
      });
    }
  }
}
