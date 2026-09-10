import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/email_verification.dart';
import 'package:specimen_digitization/src/models.dart';

class ExistingAuth extends NoNetworkAuth {
  ExistingAuth(this.currentUser);
  @override
  final User currentUser;
}

class ExistingUser implements User {
  ExistingUser(this.email, {this.emailVerified = true});
  @override
  final String email;
  @override
  final bool emailVerified;
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('No token or mail expected');
}

class NoNetworkAuth implements FirebaseAuth {
  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected Firebase method in offline UI test');
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets(
    'existing foreign verified session cannot mount a collection or send verification',
    (tester) async {
      final session = FirebaseSession(
        ExistingAuth(ExistingUser('staff@elsewhere.org')),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: EmailVerificationGate(
            session: session,
            child: const Text('PRIVATE COLLECTION'),
          ),
        ),
      );
      expect(find.text('PRIVATE COLLECTION'), findsNothing);
      expect(find.text('Use a Field Museum account'), findsOneWidget);
      expect(find.text('Send verification email'), findsNothing);
      expect(find.text('Sign out'), findsOneWidget);
      await expectLater(session.token(), throwsA(isA<ApiFailure>()));
    },
  );
  testWidgets(
    'production sign-in offers a staff email link without passwords',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: SignInScreen(session: FirebaseSession(NoNetworkAuth())),
        ),
      );
      expect(find.text('Send sign-in link'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, 'Password'), findsNothing);
      expect(find.text('Reset password'), findsNothing);
      expect(find.textContaining('fieldmuseum.org'), findsWidgets);
    },
  );

  testWidgets('lookalike email is rejected before any Firebase request', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: SignInScreen(session: FirebaseSession(NoNetworkAuth())),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(TextFormField).first,
      'staff@fieldmuseum.org.attacker.test',
    );
    await tester.tap(find.text('Send sign-in link'));
    await tester.pump();
    expect(
      find.text('Use your fieldmuseum.org email address.'),
      findsOneWidget,
    );
  });
}
