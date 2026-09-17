// The evidence drawer: one control on the page, and the raw payload behind a
// modal that only opens when the reviewer asks for it (10 section 5).

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/evidence_drawer.dart';

import '../ui_finders.dart';
import 'harness.dart';

const Map<String, Object?> _payload = <String, Object?>{
  'phase': 'transcription',
  'latency_seconds': 1.4,
  'finish_state': 'complete',
};

void main() {
  testWidgets('is closed by default and labelled Technical detail', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, const EvidenceDrawer(payload: _payload));
    expect(find.text('Technical detail'), findsOneWidget);
    expect(find.textContaining('transcription'), findsNothing);
  });

  testWidgets('opens to pretty printed JSON with a copy control', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, const EvidenceDrawer(payload: _payload));
    await tester.tap(uiButton(EvidenceDrawer.defaultTitle));
    await tester.pumpAndSettle();
    expect(find.textContaining('"phase": "transcription"'), findsOneWidget);
    expect(uiIconButton(EvidenceDrawer.copyLabel), findsOneWidget);
  });

  testWidgets('the payload is not in the semantics tree while closed', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, const EvidenceDrawer(payload: _payload));
    expect(
      find.bySemanticsLabel(RegExp('transcription')),
      findsNothing,
      reason: 'a closed drawer holds nothing a reader has to walk past',
    );

    await tester.tap(uiButton(EvidenceDrawer.defaultTitle));
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel(RegExp('"phase": "transcription"')),
      findsOneWidget,
      reason: 'an open drawer exposes the real text, not a synthetic label',
    );
    handle.dispose();
  });

  testWidgets('the trigger names the section its payload belongs to', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(
      tester,
      const EvidenceDrawer(payload: _payload, section: 'Parse'),
    );
    // Every drawer carries the same visible word, so the section is what
    // tells one from another when a panel draws a dozen of them.
    expect(find.text(EvidenceDrawer.defaultTitle), findsOneWidget);
    expect(
      find.bySemanticsLabel('${EvidenceDrawer.defaultTitle}, Parse'),
      findsOneWidget,
    );
    handle.dispose();
  });

  testWidgets('the copy control writes the payload to the clipboard', (
    WidgetTester tester,
  ) async {
    final List<MethodCall> calls = <MethodCall>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (MethodCall call) async {
        if (call.method == 'Clipboard.setData') calls.add(call);
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );

    await pumpComponent(tester, const EvidenceDrawer(payload: _payload));
    await tester.tap(uiButton(EvidenceDrawer.defaultTitle));
    await tester.pumpAndSettle();
    await tester.tap(uiIconButton(EvidenceDrawer.copyLabel));
    await tester.pumpAndSettle();

    expect(calls, hasLength(1));
    expect(
      (calls.single.arguments as Map<Object?, Object?>)['text'],
      contains('"phase": "transcription"'),
    );
  });

  testWidgets('an empty payload says so instead of showing a copy control', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, const EvidenceDrawer(payload: null));
    await tester.tap(uiButton(EvidenceDrawer.defaultTitle));
    await tester.pumpAndSettle();
    expect(find.text('No raw payload for this phase'), findsOneWidget);
    expect(uiIconButton(EvidenceDrawer.copyLabel), findsNothing);
  });

  testWidgets('under reduced motion the drawer opens without an animation', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const EvidenceDrawer(payload: _payload),
      reduceMotion: true,
    );
    await tester.tap(uiButton(EvidenceDrawer.defaultTitle));
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('"phase": "transcription"'), findsOneWidget);
  });

  testWidgets('renders open in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(
        tester,
        const EvidenceDrawer(payload: _payload),
        theme: theme,
      );
      await tester.tap(uiButton(EvidenceDrawer.defaultTitle));
      await tester.pumpAndSettle();
      await expectAccessible(tester);
    }
  });
}
