import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/auth.dart';
import 'package:specimen_digitization/src/email_verification.dart';
import 'widget_test.dart' show TestSession;

class VerificationSession extends TestSession implements VerifiedEmailAccess {
  @override
  bool emailVerified = false;
  int sent = 0;
  final refreshed = Completer<void>();
  @override
  Future<void> sendVerification() async {
    sent++;
  }

  @override
  Future<void> refreshVerification() async {
    emailVerified = true;
    await refreshed.future;
  }
}

void main() {
  testWidgets('failed token refresh keeps verified email locked', (
    tester,
  ) async {
    final session = VerificationSession();
    addTearDown(session.controller.close);
    await tester.pumpWidget(
      MaterialApp(
        home: EmailVerificationGate(
          session: session,
          child: const Text('protected workspace'),
        ),
      ),
    );
    await tester.tap(find.text('I verified my email — check again'));
    await tester.pump();
    session.refreshed.completeError(StateError('Token refresh failed'));
    await tester.pumpAndSettle();
    expect(session.emailVerified, true);
    expect(find.text('protected workspace'), findsNothing);
    expect(find.text('I verified my email — check again'), findsOneWidget);
  });
  testWidgets(
    'verification is explicit and workspace waits for token refresh',
    (tester) async {
      final session = VerificationSession();
      addTearDown(session.controller.close);
      await tester.pumpWidget(
        MaterialApp(
          home: EmailVerificationGate(
            session: session,
            child: const Text('protected workspace'),
          ),
        ),
      );
      expect(find.text('protected workspace'), findsNothing);
      expect(session.sent, 0);
      await tester.tap(find.text('Send verification email'));
      await tester.pumpAndSettle();
      expect(session.sent, 1);
      expect(find.text('protected workspace'), findsNothing);
      await tester.tap(find.text('I verified my email — check again'));
      await tester.pump();
      expect(session.emailVerified, true);
      expect(find.text('protected workspace'), findsNothing);
      session.refreshed.complete();
      await tester.pumpAndSettle();
      expect(find.text('protected workspace'), findsOneWidget);
    },
  );
}
