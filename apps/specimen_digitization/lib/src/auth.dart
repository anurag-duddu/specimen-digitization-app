import 'dart:async';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'api_repository.dart';
import 'models.dart';
import 'magic_link.dart';
import 'magic_link_screen.dart';

abstract class SessionAccess {
  Stream<bool> get changes;
  bool get signedIn;
  String get userId;
  String get displayName;
  Future<String?> token();
  Future<void> signIn(String email, String password);
  Future<void> signOut();
  Future<void> resetPassword(String email);
}

abstract class VerifiedEmailAccess {
  bool get emailVerified;
  Future<void> refreshVerification();
  Future<void> sendVerification();
}

class FirebaseSession
    implements SessionAccess, VerifiedEmailAccess, EmailLinkAccess {
  FirebaseSession(this.auth);
  final FirebaseAuth auth;
  @override
  Stream<bool> get changes => auth.userChanges().map((u) => u != null);
  @override
  bool get signedIn => auth.currentUser != null;
  @override
  String get userId => auth.currentUser?.uid ?? '';
  @override
  String get displayName => auth.currentUser?.email ?? 'Signed in';
  @override
  Future<String?> token() async {
    if (!staffEmailAllowed) {
      throw const ApiFailure(
        staffEmailMessage,
        code: 'staff_email_required',
        status: 403,
      );
    }
    if (!emailVerified) {
      throw const ApiFailure(
        'Verify your email address before opening a collection.',
        code: 'email_unverified',
        status: 403,
      );
    }
    return auth.currentUser?.getIdToken();
  }

  @override
  bool get emailVerified => auth.currentUser?.emailVerified == true;
  bool get staffEmailAllowed =>
      normalizedStaffEmail(auth.currentUser?.email ?? '') != null;
  @override
  Future<void> refreshVerification() async {
    await auth.currentUser?.reload();
    await auth.currentUser?.getIdToken(true);
  }

  @override
  Future<void> sendVerification() async {
    final user = auth.currentUser;
    if (user == null) throw StateError('Sign in again.');
    await user.sendEmailVerification();
  }

  @override
  bool isSignInWithEmailLink(String link) => auth.isSignInWithEmailLink(link);

  @override
  Future<void> sendSignInLink(String email) async {
    final normalized = normalizedStaffEmail(email);
    if (normalized == null) throw const FormatException(staffEmailMessage);
    await auth.sendSignInLinkToEmail(
      email: normalized,
      actionCodeSettings: ActionCodeSettings(
        url: emailLinkReturnUrl,
        handleCodeInApp: true,
      ),
    );
  }

  @override
  Future<void> completeEmailLink(String email, String link) async {
    final normalized = normalizedStaffEmail(email);
    if (normalized == null) throw const FormatException(staffEmailMessage);
    if (!auth.isSignInWithEmailLink(link)) {
      throw FirebaseAuthException(code: 'invalid-action-code');
    }
    await auth.signInWithEmailLink(email: normalized, emailLink: link);
  }

  @override
  Future<void> signIn(String email, String password) async =>
      throw UnsupportedError('Use an email sign-in link.');
  @override
  Future<void> resetPassword(String email) async =>
      throw UnsupportedError('Use an email sign-in link.');
  @override
  Future<void> signOut() => auth.signOut();
}

class SignInScreen extends StatelessWidget {
  const SignInScreen({super.key, required this.session, this.magicLink});
  final SessionAccess session;
  final MagicLinkController? magicLink;
  @override
  Widget build(BuildContext context) => session is EmailLinkAccess
      ? MagicLinkSignInScreen(
          access: session as EmailLinkAccess,
          controller: magicLink,
        )
      : _FixtureSignInScreen(session: session);
}

// Legacy SessionAccess adapters remain for isolated local fixtures/tests only.
// FirebaseSession always takes the email-link route above.
class _FixtureSignInScreen extends StatefulWidget {
  const _FixtureSignInScreen({required this.session});
  final SessionAccess session;
  @override
  State<_FixtureSignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<_FixtureSignInScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  String? _message;
  bool _busy = false;
  bool _obscure = true;
  bool _resetting = false;
  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit({bool reset = false}) async {
    if (reset ? !_email.text.contains('@') : !_form.currentState!.validate()) {
      if (reset) setState(() => _message = 'Enter your email address first.');
      return;
    }
    setState(() {
      _busy = true;
      _resetting = reset;
      _message = null;
    });
    try {
      if (reset) {
        await widget.session.resetPassword(_email.text);
        if (mounted) {
          setState(
            () => _message =
                'If this account is eligible, a password reset email will arrive shortly.',
          );
        }
      } else {
        await widget.session.signIn(_email.text, _password.text);
      }
    } catch (error) {
      if (mounted) {
        setState(
          () => _message =
              widget.session is LocalFixtureSession && error is ApiFailure
              ? error.message
              : authErrorMessage(error, reset: reset),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 440),
          child: AutofillGroup(
            child: Form(
              key: _form,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.biotech_outlined, size: 48),
                  const SizedBox(height: 24),
                  Text(
                    'Specimen Digitization',
                    style: Theme.of(context).textTheme.headlineMedium,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'From source pixels to supported records.',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 32),
                  Text(
                    widget.session is LocalFixtureSession
                        ? 'Local synthetic fixture access'
                        : 'Sign in to your collection',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    widget.session is LocalFixtureSession
                        ? 'SYNTHETIC ONLY. The email is a test label, not a museum account. Access requires a fixture token accepted by the local server. No Firebase or live model processing.'
                        : 'Use the account provided by your museum. Collection access is checked by the server.',
                  ),
                  const SizedBox(height: 24),
                  TextFormField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    autofillHints: const [AutofillHints.username],
                    decoration: const InputDecoration(
                      labelText: 'Email address',
                    ),
                    validator: (s) => s != null && s.contains('@')
                        ? null
                        : 'Enter a valid email address',
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _password,
                    obscureText: _obscure,
                    autofillHints: widget.session is LocalFixtureSession
                        ? null
                        : const [AutofillHints.password],
                    onFieldSubmitted: (_) {
                      if (!_busy) _submit();
                    },
                    decoration: InputDecoration(
                      labelText: widget.session is LocalFixtureSession
                          ? 'Fixture token'
                          : 'Password',
                      suffixIcon: IconButton(
                        tooltip: _obscure ? 'Show password' : 'Hide password',
                        onPressed: () => setState(() => _obscure = !_obscure),
                        icon: Icon(
                          _obscure ? Icons.visibility : Icons.visibility_off,
                        ),
                      ),
                    ),
                    validator: (s) => s == null || s.isEmpty
                        ? widget.session is LocalFixtureSession
                              ? 'Enter the fixture token'
                              : 'Enter your password'
                        : null,
                  ),
                  if (_message != null)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      child: Semantics(
                        liveRegion: true,
                        child: Text(_message!),
                      ),
                    ),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: _busy ? null : () => _submit(),
                    child: Text(
                      _busy
                          ? (_resetting ? 'Requesting reset…' : 'Signing in…')
                          : 'Sign in',
                    ),
                  ),
                  if (widget.session is! LocalFixtureSession)
                    const Padding(
                      padding: EdgeInsets.only(top: 16),
                      child: Text(
                        'Need an account or collection access? Ask your collection administrator to provide an account and assign a collection role. This app does not create accounts or grant roles.',
                      ),
                    ),
                  if (widget.session is! LocalFixtureSession)
                    TextButton(
                      onPressed: _busy ? null : () => _submit(reset: true),
                      child: const Text('Reset password'),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

/// Explicit local fixture access. Never used as a Firebase failure fallback.
/// The bearer stays in memory and is entered by the developer, not baked into a build.
class LocalFixtureSession implements SessionAccess {
  LocalFixtureSession({required Uri baseUrl, http.Client? client})
    : _baseUrl = baseUrl,
      _client = client ?? http.Client() {
    if (!['localhost', '127.0.0.1', '::1', '10.0.2.2'].contains(baseUrl.host)) {
      throw const ApiFailure(
        'Synthetic access requires a local API.',
        code: 'configuration',
      );
    }
  }
  final Uri _baseUrl;
  final http.Client _client;
  String? _bearer;
  String _userId = '';
  int _generation = 0;
  final _controller = StreamController<bool>.broadcast();
  @override
  Stream<bool> get changes => _controller.stream;
  @override
  bool get signedIn => _bearer != null;
  @override
  String get userId => _userId;
  @override
  String get displayName => 'Local synthetic reviewer';
  @override
  Future<String?> token() async => _bearer;
  @override
  Future<void> signIn(String email, String password) async {
    final generation = ++_generation;
    final wasSignedIn = signedIn;
    _bearer = null;
    _userId = '';
    if (wasSignedIn) _controller.add(false);
    if (password.isEmpty) {
      throw const ApiFailure(
        'Enter the local server fixture token.',
        code: 'unauthenticated',
      );
    }
    final probe = ApiSpecimenRepository(
      baseUrl: _baseUrl,
      client: _client,
      token: () async => password,
    );
    try {
      final result = await probe.request('GET', '/v1/session');
      if (generation != _generation) return;
      if (result['mode'] != 'synthetic' ||
          result['user_id'] is! String ||
          (result['user_id'] as String).isEmpty ||
          result['memberships'] is! List ||
          (result['memberships'] as List).any((row) => row is! Map)) {
        throw const ApiFailure(
          'The local server did not return a valid synthetic session. Check the demo configuration.',
          code: 'invalid_session',
        );
      }
      _userId = result['user_id'] as String;
      _bearer = password;
      _controller.add(true);
    } on ApiFailure catch (error) {
      if (generation != _generation) return;
      if (error.status == 401 || error.status == 403) {
        throw const ApiFailure(
          'The local server rejected the fixture token. Check the token and try again.',
          code: 'unauthenticated',
          status: 401,
        );
      }
      if (['network', 'timeout'].contains(error.code) ||
          (error.status ?? 0) >= 500) {
        throw const ApiFailure(
          'The local synthetic server is unavailable. Start or reconnect the demo server, then try again. You are not signed in.',
          code: 'server_unavailable',
        );
      }
      if (error.code == 'invalid_session') rethrow;
      throw const ApiFailure(
        'The local server could not validate this synthetic session. Check the demo configuration.',
        code: 'invalid_session',
      );
    }
  }

  @override
  Future<void> signOut() async {
    ++_generation;
    _bearer = null;
    _userId = '';
    _controller.add(false);
  }

  void dispose() {
    ++_generation;
    _client.close();
    _controller.close();
  }

  @override
  Future<void> resetPassword(String email) async =>
      throw UnsupportedError('Local fixture access has no password reset.');
}

String authErrorMessage(Object error, {bool reset = false}) {
  final action = reset ? 'Password reset' : 'Sign-in';
  if (error is FirebaseAuthException) {
    return switch (error.code) {
      'network-request-failed' =>
        '$action could not reach the sign-in service. Check your connection and retry.',
      'too-many-requests' =>
        'Too many attempts. Wait a few minutes before trying again.',
      'operation-not-allowed' =>
        '$action is not enabled for this app. Contact your administrator.',
      'invalid-email' => 'Enter a valid email address.',
      'user-disabled' =>
        'This account cannot sign in. Contact your administrator.',
      _ =>
        '$action could not be completed. Check your account details or contact your administrator.',
    };
  }
  return '$action could not be completed. Check your connection and retry.';
}
