import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/google_sign_in.dart';

class GoogleAccessFixture implements GoogleSignInAccess {
  @override
  bool googleSignInAvailable = true;
  int calls = 0;
  String? hint;
  Future<GoogleSignInOutcome> Function()? next;

  @override
  Future<GoogleSignInOutcome> signInWithGoogle({String? emailHint}) {
    calls++;
    hint = emailHint;
    return next?.call() ?? Future.value(GoogleSignInOutcome.signedIn);
  }
}

void main() {
  test('Google button needs no email and reports success', () async {
    final access = GoogleAccessFixture();
    final controller = GoogleSignInController(access: access);
    addTearDown(controller.dispose);
    expect(await controller.signIn(), GoogleSignInOutcome.signedIn);
    expect(access.hint, isNull);
    expect(controller.lastOutcome, GoogleSignInOutcome.signedIn);
    expect(controller.busy, false);
    expect(controller.failure, isNull);
  });

  test('unavailable does not dispatch authentication', () async {
    final access = GoogleAccessFixture()..googleSignInAvailable = false;
    final controller = GoogleSignInController(access: access);
    addTearDown(controller.dispose);
    expect(await controller.signIn(), isNull);
    expect(access.calls, 0);
    expect(controller.failure?.kind, GoogleSignInFailureKind.unavailable);
  });

  test('busy prevents duplicate submission and pretend cancellation', () async {
    final pending = Completer<GoogleSignInOutcome>();
    final access = GoogleAccessFixture()..next = () => pending.future;
    final controller = GoogleSignInController(access: access);
    addTearDown(controller.dispose);
    final first = controller.signIn(emailHint: 'staff@fieldmuseum.org');
    controller.reset();
    expect(controller.busy, true);
    expect(await controller.signIn(), isNull);
    expect(access.calls, 1);
    expect(access.hint, 'staff@fieldmuseum.org');
    pending.complete(GoogleSignInOutcome.cancelled);
    expect(await first, GoogleSignInOutcome.cancelled);
    expect(controller.lastOutcome, GoogleSignInOutcome.cancelled);
    expect(controller.failure, isNull);
    expect(controller.busy, false);
  });

  test('provider cancellation can retry without an error', () async {
    final access = GoogleAccessFixture()
      ..next = () async => GoogleSignInOutcome.cancelled;
    final controller = GoogleSignInController(access: access);
    addTearDown(controller.dispose);
    await controller.signIn();
    controller.reset();
    expect(controller.lastOutcome, isNull);
    access.next = null;
    expect(await controller.signIn(), GoogleSignInOutcome.signedIn);
    expect(access.calls, 2);
  });

  test('typed error remains bounded and clears on retry', () async {
    final access = GoogleAccessFixture()
      ..next = () async => throw const GoogleSignInFailure(
        GoogleSignInFailureKind.unverifiedEmail,
      );
    final controller = GoogleSignInController(access: access);
    addTearDown(controller.dispose);
    await controller.signIn();
    expect(controller.failure?.kind, GoogleSignInFailureKind.unverifiedEmail);
    access.next = null;
    await controller.signIn();
    expect(controller.failure, isNull);
  });

  test('unexpected errors never expose raw details', () async {
    final access = GoogleAccessFixture()
      ..next = () async => throw StateError('private-provider-detail');
    final controller = GoogleSignInController(access: access);
    addTearDown(controller.dispose);
    await controller.signIn();
    expect(controller.failure?.kind, GoogleSignInFailureKind.unknown);
    expect(controller.failure?.message, isNot(contains('private-provider')));
  });

  test(
    'disposed late result cannot notify or be accepted by controller',
    () async {
      final pending = Completer<GoogleSignInOutcome>();
      final access = GoogleAccessFixture()..next = () => pending.future;
      final controller = GoogleSignInController(access: access);
      var notices = 0;
      controller.addListener(() => notices++);
      final result = controller.signIn();
      expect(notices, 1);
      controller.dispose();
      pending.complete(GoogleSignInOutcome.signedIn);
      expect(await result, isNull);
      expect(notices, 1);
      expect(await controller.signIn(), isNull);
      expect(access.calls, 1);
    },
  );
}
