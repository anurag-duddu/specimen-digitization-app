import 'package:flutter/material.dart';
import 'administrator_contact.dart';
import 'app/auth_layout.dart';
import 'auth.dart';
import 'theme/icons.dart';

/// Email verification is a client gate as well as a server policy. Constructing
/// the child does not mount it or start repository requests until verified.
class EmailVerificationGate extends StatefulWidget {
  const EmailVerificationGate({
    super.key,
    required this.session,
    required this.child,
    this.refreshVerification,
  });
  final SessionAccess session;
  final Widget child;
  final Future<void> Function()? refreshVerification;
  @override
  State<EmailVerificationGate> createState() => _EmailVerificationGateState();
}

class _EmailVerificationGateState extends State<EmailVerificationGate> {
  bool _busy = false;
  bool _refreshRequired = false;
  String? _message;
  Future<void> _act(Future<void> Function() action, String message) async {
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await action();
      if (mounted) setState(() => _message = message);
    } catch (e) {
      if (mounted) setState(() => _message = authErrorMessage(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final access = widget.session;
    if (access is FirebaseSession && !access.staffEmailAllowed) {
      return Scaffold(
        body: AuthLayout(
          title: 'Use a Field Museum account',
          purpose: 'Sign in with your fieldmuseum.org email address.',
          children: <Widget>[
            if (_message != null)
              Semantics(liveRegion: true, child: Text(_message!)),
            TextButton(
              onPressed: _busy
                  ? null
                  : () => _act(access.signOut, 'Signed out.'),
              child: const Text('Sign out'),
            ),
            const AdministratorContactLine(),
          ],
        ),
      );
    }
    if (access is! VerifiedEmailAccess ||
        ((access as VerifiedEmailAccess).emailVerified &&
            !_busy &&
            !_refreshRequired)) {
      return widget.child;
    }
    final verification = access as VerifiedEmailAccess;
    return Scaffold(
      appBar: AppBar(title: const Text('Verify your account')),
      body: AuthLayout(
        wordmark: false,
        title: 'Verify ${access.displayName}',
        purpose:
            'Open the link sent to ${access.displayName}, then check again.',
        children: <Widget>[
          Text(
            'Your collection role is checked separately after verification.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (_message != null)
            Padding(
              padding: EdgeInsets.symmetric(vertical: context.space.space4),
              child: Semantics(liveRegion: true, child: Text(_message!)),
            ),
          FilledButton(
            onPressed: _busy
                ? null
                : () => _act(
                    () async {
                      _refreshRequired = true;
                      await (widget.refreshVerification ??
                          verification.refreshVerification)();
                      _refreshRequired = false;
                    },
                    'Email is not yet verified. Open the verification link and check again.',
                  ),
            child: Text(_busy ? 'Checking…' : 'Check verification again'),
          ),
          TextButton(
            onPressed: _busy
                ? null
                : () => _act(
                    verification.sendVerification,
                    'Verification email requested. Check your inbox and spam folder.',
                  ),
            child: const Text('Send verification email'),
          ),
          TextButton(
            onPressed: _busy ? null : () => _act(access.signOut, 'Signed out.'),
            child: const Text('Sign out'),
          ),
          // Verification is raised before a collection is resolved, so the
          // contact here can only come from the build stamp
          // (pass criterion 10.3).
          const AdministratorContactLine(),
        ],
      ),
    );
  }
}
