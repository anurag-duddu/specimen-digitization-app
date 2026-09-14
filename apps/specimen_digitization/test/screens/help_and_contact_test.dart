// Pass criteria 10.1, 10.3 and 10.4: the walkthrough names its controls, the
// glossary is definitions rather than a mapping, and every "ask your
// administrator" message names somebody.
//
// 10.4 itself is not verifiable from a repository: it asks for two people who
// have not seen the app to complete a first review. What is verifiable, and
// what these hold, is that the material such a reviewer needs is complete and
// that the controls it names are the controls that exist.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/administrator_contact.dart';
import 'package:specimen_digitization/src/app/help_screen.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/glossary.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/decision_bar.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';

import '../golden/golden_harness.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('the first review walkthrough', () {
    test('names controls that exist, in the words the product uses', () {
      final String text = reviewWalkthrough.join(' ');
      for (final String control in walkthroughControls) {
        expect(
          text,
          contains("'$control'"),
          reason: 'the walkthrough does not name $control',
        );
      }
      // The other half: the words it quotes are the words on the controls.
      expect(walkthroughControls, contains(WorkbenchSegment.readings.label));
      expect(walkthroughControls, contains(WorkbenchSegment.fields.label));
      expect(walkthroughControls, contains(WorkbenchDecisionBar.approveLabel));
      expect(walkthroughControls, contains(WorkbenchDecisionBar.coverageLabel));
    });

    test('is five steps and carries no dash', () {
      expect(reviewWalkthrough, hasLength(5));
      for (final String step in reviewWalkthrough) {
        expect(step, isNot(contains('—')));
        expect(step, isNot(contains('–')));
      }
    });

    testWidgets('the sheet carries it, the glossary and the build', (
      WidgetTester tester,
    ) async {
      await pumpGoldenApp(
        tester,
        window: const Size(390, 844),
        brightness: Brightness.light,
        location: AppRoutes.help,
      );
      final Finder sheet = find
          .descendant(
            of: find.byType(HelpScreen),
            matching: find.byType(Scrollable),
          )
          .first;
      Future<void> reach(Finder target) async {
        await tester.scrollUntilVisible(target, 120, scrollable: sheet);
        await tester.pumpAndSettle();
        expect(target, findsWidgets);
      }

      await reach(find.text('A first review'));
      for (final String step in reviewWalkthrough) {
        await reach(find.textContaining(step.substring(0, 24)));
      }
      await reach(find.text('Glossary'));
      await reach(find.text('This build'));
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the glossary is definitions, not a wire mapping', (
      WidgetTester tester,
    ) async {
      await pumpGoldenApp(
        tester,
        window: const Size(390, 844),
        brightness: Brightness.light,
        location: AppRoutes.help,
      );
      final Finder sheet = find
          .descendant(
            of: find.byType(HelpScreen),
            matching: find.byType(Scrollable),
          )
          .first;
      final Finder definition = find.textContaining(glossary['as written']!);
      await tester.scrollUntilVisible(definition, 200, scrollable: sheet);
      await tester.pumpAndSettle();
      expect(
        definition,
        findsWidgets,
        reason: 'the sheet lists the same sentence the term itself opens',
      );
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('the build-time administrator contact', () {
    test('an unstamped build names nobody, and says where one is listed', () {
      final AdministratorContact contact = AdministratorContact.fromBuild(
        collectionName: 'Insects',
        define: '',
      );
      expect(contact.isKnown, isFalse);
      expect(contact.sentence, contains('Insects'));
      expect(contact.mailtoFor(), isNull);
    });

    test('a name and a mail address in angle brackets', () {
      final AdministratorContact contact = AdministratorContact.fromBuild(
        define: 'Alex Mwangi <alex@example.org>',
      );
      expect(contact.name, 'Alex Mwangi');
      expect(contact.address, 'alex@example.org');
      expect(contact.sentence, 'Ask Alex Mwangi at alex@example.org.');
    });

    test('a name and a mail address separated by a comma', () {
      final AdministratorContact contact = AdministratorContact.fromBuild(
        define: 'The entomology data team, data@example.org',
      );
      expect(contact.name, 'The entomology data team');
      expect(contact.address, 'data@example.org');
    });

    test('a bare address, and a bare role', () {
      expect(
        AdministratorContact.fromBuild(define: 'data@example.org').address,
        'data@example.org',
      );
      expect(
        AdministratorContact.fromBuild(define: 'Your curator').name,
        'Your curator',
      );
    });

    test('the collection document still wins over the build stamp', () {
      final AdministratorContact contact = AdministratorContact.of(
        const CollectionScope(
          organizationId: 'org',
          collectionId: 'insects',
          name: 'Insects',
          configuration: <String, dynamic>{
            'administrator_contact': 'curator@example.org',
          },
        ),
      );
      expect(contact.address, 'curator@example.org');
    });

    test('the mail link carries the record when one is open', () {
      final AdministratorContact contact = AdministratorContact.fromBuild(
        collectionName: 'Insects',
        define: 'Alex Mwangi <alex@example.org>',
      );
      final String link = contact.mailtoFor(specimenId: 'fixture-001')!;
      expect(link, startsWith('mailto:alex@example.org?'));
      expect(Uri.parse(link).queryParameters['subject'], contains('Insects'));
      expect(
        Uri.parse(link).queryParameters['subject'],
        contains('fixture-001'),
      );
      expect(
        contact.mailtoFor(),
        isNot(contains('record')),
        reason: 'a link raised with no record open invents no record',
      );
    });
  });
}
