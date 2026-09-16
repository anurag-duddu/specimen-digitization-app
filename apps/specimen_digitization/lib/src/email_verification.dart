/// The verification gate (07 section 2).
///
/// Email verification is a client gate as well as a server policy.
/// Constructing the child does not mount it or start repository requests until
/// the address is verified.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'administrator_contact.dart';
import 'app/auth_layout.dart';
import 'auth.dart';

/// The screen a session with an unverified address sees.
class EmailVerificationGate extends StatefulWidget {
  const EmailVerificationGate({
    super.key,
    required this.session,
    required this.child,
    this.refreshVerification,
  });

  /// The signed-in account.
  final SessionAccess session;

  /// What is rendered once the address is verified.
  final Widget child;

  /// Overrides how verification is re-read, for a test.
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
    } catch (error) {
      if (mounted) setState(() => _message = authErrorMessage(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final SessionAccess access = widget.session;
    if (access is FirebaseSession && !access.staffEmailAllowed) {
      return UiScaffold(
        body: AuthLayout(
          title: 'Use a Field Museum account',
          purpose: 'Sign in with your fieldmuseum.org email address.',
          children: <Widget>[
            if (_message != null) ...<Widget>[
              UiBanner(message: _message!, tone: UiBannerTone.blocked),
              SizedBox(height: ui.space.s4),
            ],
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiButton(
                label: 'Sign out',
                variant: UiButtonVariant.ghost,
                onPressed: _busy
                    ? null
                    : () => _act(access.signOut, 'Signed out.'),
              ),
            ),
            SizedBox(height: ui.space.s4),
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
    final VerifiedEmailAccess verification = access as VerifiedEmailAccess;
    return UiScaffold(
      topBar: const UiTopBar(title: 'Verify your account'),
      body: AuthLayout(
        wordmark: false,
        title: 'Verify ${access.displayName}',
        purpose:
            'Open the link sent to ${access.displayName}, then check again.',
        children: <Widget>[
          Text(
            'Your collection role is checked separately after verification.',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
          if (_message != null) ...<Widget>[
            SizedBox(height: ui.space.s4),
            UiBanner(message: _message!),
            SizedBox(height: ui.space.s4),
          ],
          SizedBox(height: ui.space.s4),
          UiButton(
            label: _busy ? 'Checking…' : 'Check verification again',
            loading: _busy,
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
          ),
          SizedBox(height: ui.space.s2),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiButton(
              label: 'Send verification email',
              variant: UiButtonVariant.ghost,
              onPressed: _busy
                  ? null
                  : () => _act(
                      verification.sendVerification,
                      'Verification email requested. Check your inbox and spam folder.',
                    ),
            ),
          ),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: UiButton(
              label: 'Sign out',
              variant: UiButtonVariant.ghost,
              onPressed: _busy
                  ? null
                  : () => _act(access.signOut, 'Signed out.'),
            ),
          ),
          // Verification is raised before a collection is resolved, so the
          // contact here can only come from the build stamp
          // (pass criterion 10.3).
          SizedBox(height: ui.space.s4),
          const AdministratorContactLine(),
        ],
      ),
    );
  }
}
