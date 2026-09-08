import 'dart:async';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

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

class FirebaseSession implements SessionAccess {
  FirebaseSession(this.auth);
  final FirebaseAuth auth;
  @override
  Stream<bool> get changes => auth.authStateChanges().map((u) => u != null);
  @override
  bool get signedIn => auth.currentUser != null;
  @override
  String get userId => auth.currentUser?.uid ?? '';
  @override
  String get displayName => auth.currentUser?.email ?? 'Signed in';
  @override
  Future<String?> token() async => auth.currentUser?.getIdToken();
  @override
  Future<void> signIn(String email, String password) async {
    await auth.signInWithEmailAndPassword(
      email: email.trim(),
      password: password,
    );
  }

  @override
  Future<void> signOut() => auth.signOut();
  @override
  Future<void> resetPassword(String email) =>
      auth.sendPasswordResetEmail(email: email.trim());
}

class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key, required this.session});
  final SessionAccess session;
  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  String? _message;
  bool _busy = false;
  bool _obscure = true;
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
    } catch (_) {
      if (mounted) {
        setState(
          () => _message =
              'Sign-in could not be completed. Check your credentials and connection, or contact your administrator.',
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
                        ? 'SYNTHETIC ONLY. Enter any test email and the local server fixture token. No Firebase or live model processing.'
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
                      labelText: 'Password',
                      suffixIcon: IconButton(
                        tooltip: _obscure ? 'Show password' : 'Hide password',
                        onPressed: () => setState(() => _obscure = !_obscure),
                        icon: Icon(
                          _obscure ? Icons.visibility : Icons.visibility_off,
                        ),
                      ),
                    ),
                    validator: (s) =>
                        s == null || s.isEmpty ? 'Enter your password' : null,
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
                    child: Text(_busy ? 'Signing in…' : 'Sign in'),
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
  String? _bearer;
  final _controller = StreamController<bool>.broadcast();
  @override
  Stream<bool> get changes => _controller.stream;
  @override
  bool get signedIn => _bearer != null;
  @override
  String get userId => 'synthetic-reviewer';
  @override
  String get displayName => 'Local synthetic reviewer';
  @override
  Future<String?> token() async => _bearer;
  @override
  Future<void> signIn(String email, String password) async {
    _bearer = password;
    _controller.add(true);
  }

  @override
  Future<void> signOut() async {
    _bearer = null;
    _controller.add(false);
  }

  @override
  Future<void> resetPassword(String email) async =>
      throw UnsupportedError('Local fixture access has no password reset.');
}
