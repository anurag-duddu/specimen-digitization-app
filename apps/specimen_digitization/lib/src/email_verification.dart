import 'package:flutter/material.dart';
import 'auth.dart';

/// Email verification is a client gate as well as a server policy. Constructing
/// the child does not mount it or start repository requests until verified.
class EmailVerificationGate extends StatefulWidget {
  const EmailVerificationGate({
    super.key,
    required this.session,
    required this.child,
  });
  final SessionAccess session;
  final Widget child;
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
    if (access is! VerifiedEmailAccess ||
        ((access as VerifiedEmailAccess).emailVerified &&
            !_busy &&
            !_refreshRequired)) {
      return widget.child;
    }
    final verification = access as VerifiedEmailAccess;
    return Scaffold(
      appBar: AppBar(title: const Text('Verify your account')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.mark_email_unread_outlined, size: 48),
                const SizedBox(height: 16),
                Text(
                  'Verify ${access.displayName}',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 12),
                const Text(
                  'Open the verification link in your email, then check again. Collection access remains locked until your email and assigned role are verified.',
                ),
                if (_message != null)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: Semantics(liveRegion: true, child: Text(_message!)),
                  ),
                FilledButton(
                  onPressed: _busy
                      ? null
                      : () => _act(
                          () async {
                            _refreshRequired = true;
                            await verification.refreshVerification();
                            _refreshRequired = false;
                          },
                          'Email is not yet verified. Open the verification link and check again.',
                        ),
                  child: Text(
                    _busy ? 'Checking…' : 'I verified my email — check again',
                  ),
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
                  onPressed: _busy
                      ? null
                      : () => _act(access.signOut, 'Signed out.'),
                  child: const Text('Sign out'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
