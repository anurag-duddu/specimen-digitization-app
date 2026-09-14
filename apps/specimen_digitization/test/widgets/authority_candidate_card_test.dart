// The authority candidate: name, identifier, relation, reason, one action.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/authority_candidate_card.dart';
import 'package:specimen_digitization/src/widgets/evidence_drawer.dart';

import 'harness.dart';

Widget _card({VoidCallback? onUse, bool selected = false, Object? raw}) =>
    SizedBox(
      width: 500,
      child: AuthorityCandidateCard(
        name: 'Asclepias syriaca L.',
        identifier: 'urn:lsid:ipni.org:names:94382-1',
        relation: 'Accepted name',
        reason: 'The standardized value matched this record exactly.',
        authorityName: 'International Plant Names Index',
        onUse: onUse,
        selected: selected,
        raw: raw,
      ),
    );

void main() {
  testWidgets('renders the name, identifier, relation and reason', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _card(onUse: () {}));
    expect(find.text('Asclepias syriaca L.'), findsOneWidget);
    expect(find.text('urn:lsid:ipni.org:names:94382-1'), findsOneWidget);
    expect(find.text('Accepted name'), findsOneWidget);
    expect(
      find.text('The standardized value matched this record exactly.'),
      findsOneWidget,
    );
    expect(find.text('International Plant Names Index'), findsOneWidget);
  });

  testWidgets('the identifier is set in the monospace role', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _card(onUse: () {}));
    final Text identifier = tester.widget<Text>(
      find.text('urn:lsid:ipni.org:names:94382-1'),
    );
    expect(identifier.style?.fontFamilyFallback, contains('monospace'));
  });

  testWidgets('the action is labelled and fires', (WidgetTester tester) async {
    int used = 0;
    await pumpComponent(tester, _card(onUse: () => used++));
    expect(find.text(AuthorityCandidateCard.useLabel), findsOneWidget);
    await tester.tap(find.text(AuthorityCandidateCard.useLabel));
    await tester.pumpAndSettle();
    expect(used, 1);
  });

  testWidgets('the action disables when the record is not editable', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _card());
    expect(
      tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
      isNull,
    );
  });

  testWidgets('a raw payload gets a closed drawer', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      _card(onUse: () {}, raw: const <String, Object?>{'rank': 'species'}),
    );
    expect(find.byType(EvidenceDrawer), findsOneWidget);
    expect(find.textContaining('"rank"'), findsNothing);
    await tester.tap(find.text('Technical detail'));
    await tester.pumpAndSettle();
    expect(find.textContaining('"rank": "species"'), findsOneWidget);
  });

  testWidgets('a card with no raw payload has no drawer', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, _card(onUse: () {}));
    expect(find.byType(EvidenceDrawer), findsNothing);
  });

  testWidgets('the selected state reaches the semantics tree', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpComponent(tester, _card(onUse: () {}, selected: true));
    expect(
      tester.getSemantics(find.byType(AuthorityCandidateCard)),
      containsSemantics(isSelected: true),
    );
    handle.dispose();
  });

  testWidgets('renders in both themes and meets the guidelines', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      await pumpComponent(tester, _card(onUse: () {}), theme: theme);
      await expectAccessible(tester);
    }
  });
}
