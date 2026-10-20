/// The verification gate (07 section 2).
///
/// Email verification is a client gate as well as a server policy.
/// Constructing the child does not mount it or start repository requests until
/// the address is verified.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'administrator_contact.dart';
import 'app/sign_in_layout.dart';
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
        body: SignInLayout(
          title: 'Use a Field Museum account',
          purpose: 'Sign in with your fieldmuseum.org email address.',
          icon: UiIcons.account,
          busy: _busy,
          footer: _busy ? null : const AdministratorContactLine(),
          children: <Widget>[
            _identity(ui, access.displayName),
            SizedBox(height: ui.space.s6),
            if (_message != null) ...<Widget>[
              UiBanner(message: _message!, tone: UiBannerTone.blocked),
              SizedBox(height: ui.space.s4),
            ],
            UiButton(
              label: 'Sign out',
              loading: _busy,
              onPressed: _busy
                  ? null
                  : () => _act(access.signOut, 'Signed out.'),
            ),
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
      body: SignInLayout(
        title: 'Verify your account',
        purpose: 'Open your verification email, then check again.',
        icon: UiIcons.email,
        busy: _busy,
        footer: !_busy && _message != null
            ? const AdministratorContactLine()
            : null,
        children: <Widget>[
          _identity(ui, access.displayName),
          if (_message != null) ...<Widget>[
            SizedBox(height: ui.space.s4),
            UiBanner(message: _message!),
            SizedBox(height: ui.space.s4),
          ],
          SizedBox(height: ui.space.s4),
          UiButton(
            label: _busy ? 'Checking…' : 'Check verification again',
            expand: true,
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
        ],
      ),
    );
  }

  Widget _identity(UiThemeData ui, String name) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      const ExcludeSemantics(child: UiIcon(UiIcons.account)),
      SizedBox(width: ui.space.s2),
      Expanded(
        child: Text(
          'Account: $name',
          style: ui.type.body.copyWith(color: ui.color.ink),
        ),
      ),
    ],
  );
}
