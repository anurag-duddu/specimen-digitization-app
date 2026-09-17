// What the band says about the build a reviewer is in, and what the entry
// screens say when Firebase Auth refuses them (07 sections 1.3 and 2; slot
// B3, item 3).
//
// Three states, not two. Production has always shown no band, because the
// condition it would name is the normal one. A bounded pilot is a third
// condition: the records are real, which is the whole difference from a test
// build, and the scope is limited, which a reviewer has to know before they
// look for a record that is not in it. The server's own vocabulary has no
// word for it (the backend's `create_app` takes exactly `synthetic`,
// `emulator` and `production`), so a deployment stamps it in, the way it
// already stamps the administrator contact and the API address.

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/administrator_contact.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/magic_link.dart';
import 'package:specimen_digitization/src/widgets/environment_banner.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'widgets/harness.dart';

/// The scope a pilot deployment stamps in.
const String pilot = 'Ten original specimens';

/// The contact a deployment stamps in, as `administrator_contact.dart`
/// documents the spellings.
const String stampedContact = 'Alex Mwangi <alex@example.org>';

void main() {
  group('the three states of the band', () {
    testWidgets('production with no pilot draws nothing at all', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const EnvironmentBanner(environment: 'production', pilotScope: ''),
      );
      expect(find.byType(Text), findsNothing);
      expect(find.byType(UiBanner), findsNothing);
    });

    testWidgets('a test environment names itself and claims nothing more', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const EnvironmentBanner(environment: 'synthetic', pilotScope: ''),
      );
      expect(
        find.text('Test environment. Not approved museum records.'),
        findsOneWidget,
      );
    });

    testWidgets('a bounded pilot says the records are real', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const EnvironmentBanner(environment: 'production', pilotScope: pilot),
      );
      expect(
        find.text('Bounded pilot: $pilot. Records here are real.'),
        findsOneWidget,
      );
    });

    test('an unstamped pilot still says what it is', () {
      expect(
        EnvironmentBanner.pilotHeadlineFor(''),
        'Bounded pilot. Real records, limited scope.',
      );
    });

    test('a test build carrying a pilot stamp shows the test band', () {
      // The stronger statement wins, and two bands would be two regions
      // saying one thing (13 section 2.4).
      expect(EnvironmentBanner.isPilot('synthetic', scope: pilot), isFalse);
      expect(EnvironmentBanner.isPilot('production', scope: pilot), isTrue);
      expect(EnvironmentBanner.isPilot('production', scope: '  '), isFalse);
    });

    test('the band is drawn for exactly the states that have one', () {
      expect(EnvironmentBanner.showsBand('production', scope: ''), isFalse);
      expect(EnvironmentBanner.showsBand('production', scope: pilot), isTrue);
      expect(EnvironmentBanner.showsBand('synthetic', scope: ''), isTrue);
      expect(EnvironmentBanner.showsBand('emulator', scope: ''), isTrue);
      expect(EnvironmentBanner.showsBand(' Production ', scope: ''), isFalse);
    });
  });

  group('every band names somebody', () {
    testWidgets('the test band carries the contact behind its disclosure', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const EnvironmentBanner(
          environment: 'synthetic',
          pilotScope: '',
          contactSentence: 'Ask Alex Mwangi at alex@example.org.',
        ),
      );
      await tester.tap(find.bySemanticsLabel(EnvironmentBanner.detailLabel));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Ask Alex Mwangi at alex@example.org.'),
        findsOneWidget,
      );
    });

    testWidgets('the pilot band carries it too, under its own control', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        const EnvironmentBanner(
          environment: 'production',
          pilotScope: pilot,
          contactSentence: 'Ask Alex Mwangi at alex@example.org.',
        ),
      );
      await tester.tap(
        find.bySemanticsLabel(EnvironmentBanner.pilotDetailLabel),
      );
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Ask Alex Mwangi at alex@example.org.'),
        findsOneWidget,
      );
      expect(
        find.textContaining('every record is decided by a person'),
        findsOneWidget,
      );
    });

    testWidgets('a build that names nobody spends no line saying so', (
      WidgetTester tester,
    ) async {
      // The entry screens are raised before any collection is resolved, so
      // the build stamp is the only source there, and an unstamped build has
      // no contact to give. `AdministratorContact` still answers a sentence,
      // and that sentence says where a contact would be published rather than
      // naming one; that belongs in the help sheet, not on a band that is two
      // lines at every text scale.
      await pumpComponent(
        tester,
        const EnvironmentBanner(environment: 'synthetic', pilotScope: ''),
      );
      await tester.tap(find.bySemanticsLabel(EnvironmentBanner.detailLabel));
      await tester.pumpAndSettle();
      expect(find.text(EnvironmentBanner.detail), findsOneWidget);
      expect(
        find.textContaining('listed in the collection configuration'),
        findsNothing,
      );
    });

    test('the second clause composes the same way for either band', () {
      expect(
        EnvironmentBanner.detailFor('synthetic', scope: ''),
        EnvironmentBanner.detail,
      );
      expect(
        EnvironmentBanner.detailFor(
          'synthetic',
          scope: '',
          contactSentence: 'Ask Alex Mwangi at alex@example.org.',
        ),
        '${EnvironmentBanner.detail} Ask Alex Mwangi at alex@example.org.',
      );
      expect(
        EnvironmentBanner.detailFor(
          'production',
          scope: pilot,
          contactSentence: 'Ask Alex Mwangi at alex@example.org.',
        ),
        '${EnvironmentBanner.pilotDetail} '
        'Ask Alex Mwangi at alex@example.org.',
      );
      // Whitespace is not a contact.
      expect(EnvironmentBanner.contactFor('   '), isNull);
    });

    test('an unstamped build says where the contact would be published', () {
      expect(
        AdministratorContact.fromBuild(define: '').sentence,
        contains('listed in the collection configuration'),
      );
      expect(
        AdministratorContact.fromBuild(define: stampedContact).sentence,
        'Ask Alex Mwangi at alex@example.org.',
      );
    });
  });

  group('the sentence stays one sentence at every scale', () {
    test('the band never exceeds two lines, whichever kind it is', () {
      expect(EnvironmentBanner.maxLines, 2);
    });

    test('the whole statement is on the semantics node either way', () {
      expect(
        EnvironmentBanner.sentenceFor('synthetic', scope: ''),
        contains(EnvironmentBanner.detail),
      );
      expect(
        EnvironmentBanner.sentenceFor('production', scope: pilot),
        contains(EnvironmentBanner.pilotDetail),
      );
    });
  });

  group('the Firebase Auth codes the entry screens have to answer', () {
    /// Every code `emailLinkError` names, which is the set the magic link
    /// flow can receive. Each maps to a sentence a reviewer can act on.
    const Map<String, String> linkCodes = <String, String>{
      'expired-action-code': 'Request a new link.',
      'invalid-action-code': 'Request a new link.',
      'invalid-credential': 'Request a new link.',
      'network-request-failed': 'Check your connection',
      'too-many-requests': 'Wait a few minutes',
      'operation-not-allowed': 'Ask your administrator.',
      'unauthorized-continue-uri': 'Ask your administrator.',
      'invalid-continue-uri': 'Ask your administrator.',
      'user-disabled': 'Ask your administrator.',
    };

    test('every magic link code answers with its own recovery', () {
      for (final MapEntry<String, String> code in linkCodes.entries) {
        final String message = emailLinkError(
          FirebaseAuthException(code: code.key),
        );
        expect(
          message,
          contains(code.value),
          reason: '${code.key} does not tell the reviewer what to do next',
        );
        expect(message, isNot(contains('FirebaseAuthException')));
        expect(message, isNot(contains(code.key)));
      }
    });

    test('a code nobody has seen still gets a recovery', () {
      final String message = emailLinkError(
        FirebaseAuthException(code: 'a-code-from-a-later-sdk'),
      );
      expect(message, contains('Request a new link'));
      expect(message, isNot(contains('a-code-from-a-later-sdk')));
    });

    test('a failure that is not a Firebase one is still answered', () {
      expect(
        emailLinkError(Exception('socket closed')),
        contains('Check your connection'),
      );
      expect(
        authErrorMessage(Exception('socket closed')),
        contains('Check your connection'),
      );
    });

    test('the sign in codes answer for sign in and for a reset alike', () {
      for (final String code in <String>[
        'network-request-failed',
        'too-many-requests',
        'operation-not-allowed',
        'invalid-email',
        'user-disabled',
      ]) {
        final String signIn = authErrorMessage(
          FirebaseAuthException(code: code),
        );
        final String reset = authErrorMessage(
          FirebaseAuthException(code: code),
          reset: true,
        );
        expect(signIn.trim(), isNotEmpty);
        expect(reset.trim(), isNotEmpty);
        expect(signIn, isNot(contains(code)));
        expect(reset, isNot(contains(code)));
      }
    });

    test('an invalid address names the address a museum account has', () {
      expect(
        authErrorMessage(FirebaseAuthException(code: 'invalid-email')),
        contains('@fieldmuseum.org'),
      );
    });

    test(
      'the four codes that void a stored link are the four that are void',
      () {
        // A link that is expired, already used, refused or attached to a
        // disabled account cannot be retried, so the controller drops it and
        // asks for a new one rather than leaving a dead link on the screen.
        for (final String code in <String>[
          'expired-action-code',
          'invalid-action-code',
          'invalid-credential',
          'user-disabled',
        ]) {
          expect(
            emailLinkError(FirebaseAuthException(code: code)),
            anyOf(
              contains('Request a new link'),
              contains('Ask your administrator'),
            ),
          );
        }
      },
    );
  });
}
