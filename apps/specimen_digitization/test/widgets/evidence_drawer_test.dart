// The evidence drawer: closed by default, and silent while it is closed.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/evidence_drawer.dart';

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
    await tester.tap(find.text('Technical detail'));
    await tester.pumpAndSettle();
    expect(find.textContaining('"phase": "transcription"'), findsOneWidget);
    expect(find.byTooltip('Copy the raw payload'), findsOneWidget);
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

    await tester.tap(find.text('Technical detail'));
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel(RegExp('"phase": "transcription"')),
      findsOneWidget,
      reason: 'an open drawer exposes the real text, not a synthetic label',
    );
    handle.dispose();
  });

  testWidgets('the trigger reports its expanded state', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, const EvidenceDrawer(payload: _payload));
    expect(
      tester.getSemantics(find.bySubtype<TextButton>()),
      containsSemantics(label: 'Technical detail', isExpanded: false),
    );
    await tester.tap(find.text('Technical detail'));
    await tester.pumpAndSettle();
    expect(
      tester.getSemantics(find.bySubtype<TextButton>()),
      containsSemantics(label: 'Technical detail', isExpanded: true),
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
    await tester.tap(find.text('Technical detail'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Copy the raw payload'));
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
    await tester.tap(find.text('Technical detail'));
    await tester.pumpAndSettle();
    expect(find.text('No raw payload for this phase'), findsOneWidget);
    expect(find.byTooltip('Copy the raw payload'), findsNothing);
  });

  testWidgets('under reduced motion the drawer opens without an animation', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const EvidenceDrawer(payload: _payload),
      reduceMotion: true,
    );
    await tester.tap(find.text('Technical detail'));
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
      await tester.tap(find.text('Technical detail'));
      await tester.pumpAndSettle();
      await expectAccessible(tester);
    }
  });
}
