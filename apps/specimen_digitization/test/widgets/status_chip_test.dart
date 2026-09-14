// The status chip: glyph plus word, one merged node, both themes.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/specimen_status.dart';
import 'package:specimen_digitization/src/widgets/status_chip.dart';

import 'harness.dart';

void main() {
  testWidgets('renders the word and a glyph, never color alone', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, const StatusChip(SpecimenStatus.cleared));
    expect(find.text('Cleared'), findsOneWidget);
    expect(find.byType(Icon), findsOneWidget);
  });

  testWidgets('every status renders in both themes', (
    WidgetTester tester,
  ) async {
    for (final MapEntry<String, ThemeData> entry in productThemes.entries) {
      for (final SpecimenStatus status in SpecimenStatus.values) {
        await pumpComponent(tester, StatusChip(status), theme: entry.value);
        expect(
          find.text(status.label),
          findsOneWidget,
          reason: '${status.name} in ${entry.key}',
        );
      }
    }
  });

  testWidgets('the chip is one merged semantics node', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, const StatusChip(SpecimenStatus.needsReview));
    expect(find.bySemanticsLabel('Queue: needs human review'), findsOneWidget);
    // The visible word is not a second node.
    expect(find.bySemanticsLabel('Needs human review'), findsNothing);
    handle.dispose();
  });

  testWidgets('a count reaches both the word and the phrase', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(
      tester,
      const StatusChip(SpecimenStatus.deferred, count: 12),
    );
    expect(find.text('Deferred 12'), findsOneWidget);
    expect(find.bySemanticsLabel('Queue: deferred, 12'), findsOneWidget);
    handle.dispose();
  });

  testWidgets('the dense variant still renders the word', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const StatusChip(SpecimenStatus.blocked, dense: true),
    );
    expect(find.text('Processing blocked'), findsOneWidget);
  });

  testWidgets('a presented chip can carry a determinate ring', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      Builder(
        builder: (BuildContext context) {
          final StatusPresentation base = SpecimenStatus.processing
              .presentation(context);
          return StatusChip.presented(
            StatusPresentation(
              content: base.content,
              fill: base.fill,
              onFill: base.onFill,
              icon: base.icon,
              fill01: base.fill01,
              label: 'Uploading',
              semanticsLabel: 'Upload: uploading',
              progress: 0.5,
            ),
          );
        },
      ),
    );
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.byType(Icon), findsNothing);
  });

  testWidgets('meets the tap target and label guidelines', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const Wrap(
        children: <Widget>[
          StatusChip(SpecimenStatus.cleared),
          StatusChip(SpecimenStatus.unresolved),
        ],
      ),
    );
    await expectAccessible(tester);
  });
}
