import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'email_link_browser.dart';
import 'app/auth_layout.dart';
import 'magic_link.dart';
import 'widgets/motion_reveal.dart';
import 'widgets/caveat_text.dart';

class EmailLinkEntry extends StatefulWidget {
  const EmailLinkEntry({
    super.key,
    required this.access,
    required this.browser,
    required this.builder,
  });
  final EmailLinkAccess access;
  final EmailLinkBrowser browser;
  final Widget Function(BuildContext, MagicLinkController) builder;
  @override
  State<EmailLinkEntry> createState() => _EmailLinkEntryState();
}

class _EmailLinkEntryState extends State<EmailLinkEntry> {
  late final MagicLinkController controller;
  @override
  void initState() {
    super.initState();
    controller = MagicLinkController(
      access: widget.access,
      browser: widget.browser,
    )..addListener(_changed);
    unawaited(controller.initialize());
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    controller.removeListener(_changed);
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => !controller.initialized
      ? const UiScaffold(
          body: Center(
            child: UiProgress.ring(
              semanticsLabel: 'Opening the sign-in link',
              size: UiProgressSize.large,
            ),
          ),
        )
      : widget.builder(context, controller);
}

class MagicLinkSignInScreen extends StatefulWidget {
  const MagicLinkSignInScreen({
    super.key,
    required this.access,
    this.controller,
  });
  final EmailLinkAccess access;
  final MagicLinkController? controller;
  @override
  State<MagicLinkSignInScreen> createState() => _MagicLinkSignInScreenState();
}

class _MagicLinkSignInScreenState extends State<MagicLinkSignInScreen> {
  final _email = TextEditingController();
  String? _emailError;
  late final MagicLinkController controller;
  Timer? _timer;
  String? _lastRemembered;
  int _lastCooldown = 0;
  @override
  void initState() {
    super.initState();
    controller =
        widget.controller ??
        MagicLinkController(
          access: widget.access,
          browser: createEmailLinkBrowser(),
        );
    controller.addListener(_changed);
    _email.text = controller.email;
    _lastRemembered = controller.email;
    _lastCooldown = controller.cooldownSeconds;
    unawaited(controller.initialize());
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      final cooldown = controller.cooldownSeconds;
      if (mounted && cooldown != _lastCooldown) {
        setState(() => _lastCooldown = cooldown);
      }
    });
  }

  void _changed() {
    if (!mounted) return;
    _lastCooldown = controller.cooldownSeconds;
    if (controller.email != _lastRemembered) {
      _email.text = controller.email;
      _lastRemembered = controller.email;
    }
    setState(() {});
  }

  @override
  void dispose() {
    _timer?.cancel();
    controller.removeListener(_changed);
    if (widget.controller == null) controller.dispose();
    _email.dispose();
    super.dispose();
  }

  void _submit() {
    if (!controller.initialized || controller.busy) return;
    final String? error = normalizedStaffEmail(_email.text) == null
        ? staffEmailMessage
        : null;
    setState(() => _emailError = error);
    if (error != null) return;
    unawaited(
      controller.handlingLink
          ? controller.complete(_email.text)
          : controller.send(_email.text),
    );
  }

  /// The primary button's label for the state the controller is in.
  ///
  /// One function, so the `AnimatedSwitcher`'s key and the text it draws can
  /// never disagree and leave the label frozen mid-request.
  static String _submitLabel(
    MagicLinkController controller, {
    required bool confirm,
  }) {
    if (controller.busy) return confirm ? 'Signing in…' : 'Sending link…';
    if (confirm) return 'Confirm and sign in';
    return controller.sent ? 'Resend sign-in link' : 'Send sign-in link';
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final bool confirm = controller.handlingLink;
    final int cooldown = controller.cooldownSeconds;
    final bool disabled =
        !controller.initialized ||
        controller.busy ||
        (!confirm && cooldown > 0);
    return UiScaffold(
      body: AutofillGroup(
        child: AuthLayout(
          title: confirm
              ? 'Confirm your email'
              : controller.sent
              ? 'Check your email'
              : 'Sign in to your collection',
          purpose: confirm
              ? 'Enter the fieldmuseum.org address that received this link.'
              : 'Use your fieldmuseum.org email to get a sign-in link. '
                    'No password needed.',
          children: <Widget>[
            UiField(
              label: 'Email address',
              controller: _email,
              enabled: !controller.busy,
              errorText: _emailError,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              onSubmitted: (_) {
                if (!disabled) _submit();
              },
            ),
            // The announcement is what tells a screen reader user; the
            // reveal only keeps the column from snapping (04 section 4,
            // row 5).
            MotionReveal(
              visible: controller.message != null,
              child: Padding(
                padding: EdgeInsetsDirectional.symmetric(
                  vertical: ui.space.s4,
                ),
                child: UiBanner(message: controller.message ?? ''),
              ),
            ),
            SizedBox(height: ui.space.s6),
            UiButton(
              label: _submitLabel(controller, confirm: confirm),
              size: UiSize.lg,
              loading: controller.busy,
              onPressed: disabled ? null : _submit,
              disabledReason: !confirm && cooldown > 0
                  ? 'You can request another link in ${cooldown}s.'
                  : null,
            ),
            // A number changing once a second is a fact, not a transition,
            // so nothing here animates (04 section 4, row 6).
            if (!confirm && cooldown > 0)
              Padding(
                padding: EdgeInsetsDirectional.only(top: ui.space.s3),
                child: Text(
                  'You can request another link in ${cooldown}s.',
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
              ),
            if (controller.sent || confirm || controller.message != null)
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: UiButton(
                  label: confirm ? 'Cancel sign-in' : 'Use a different email',
                  variant: UiButtonVariant.ghost,
                  onPressed: controller.busy
                      ? null
                      : () => unawaited(controller.changeEmail()),
                ),
              ),
            SizedBox(height: ui.space.s4),
            const CaveatText(
              label:
                  'First time? Signing in with your verified staff email '
                  'creates your account.',
              why:
                  'Collection access is separate and is granted by your '
                  'collection administrator.',
            ),
          ],
        ),
      ),
    );
  }
}
