import 'dart:async';
import 'package:flutter/material.dart';
import 'email_link_browser.dart';
import 'app/auth_layout.dart';
import 'magic_link.dart';
import 'theme/icons.dart';
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
      ? const Scaffold(body: Center(child: CircularProgressIndicator()))
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
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
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
    if (!controller.initialized ||
        controller.busy ||
        !_form.currentState!.validate()) {
      return;
    }
    unawaited(
      controller.handlingLink
          ? controller.complete(_email.text)
          : controller.send(_email.text),
    );
  }

  @override
  Widget build(BuildContext context) {
    final confirm = controller.handlingLink;
    final cooldown = controller.cooldownSeconds;
    final disabled =
        !controller.initialized ||
        controller.busy ||
        (!confirm && cooldown > 0);
    return Scaffold(
      body: Form(
        key: _form,
        child: AutofillGroup(
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
              TextFormField(
                controller: _email,
                enabled: !controller.busy,
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                autofillHints: const [AutofillHints.email],
                decoration: const InputDecoration(labelText: 'Email address'),
                validator: (value) => normalizedStaffEmail(value ?? '') == null
                    ? staffEmailMessage
                    : null,
                onFieldSubmitted: (_) {
                  if (!disabled) _submit();
                },
              ),
              if (controller.message != null)
                Padding(
                  padding: EdgeInsets.symmetric(vertical: context.space.space4),
                  child: Semantics(
                    liveRegion: true,
                    child: Text(controller.message!),
                  ),
                ),
              SizedBox(height: context.space.space6),
              FilledButton(
                onPressed: disabled ? null : _submit,
                child: Text(
                  controller.busy
                      ? (confirm ? 'Signing in…' : 'Sending link…')
                      : confirm
                      ? 'Confirm and sign in'
                      : controller.sent
                      ? 'Resend sign-in link'
                      : 'Send sign-in link',
                ),
              ),
              if (!confirm && cooldown > 0)
                Padding(
                  padding: EdgeInsets.only(top: context.space.space3),
                  child: Text('You can request another link in ${cooldown}s.'),
                ),
              if (controller.sent || confirm || controller.message != null)
                TextButton(
                  onPressed: controller.busy
                      ? null
                      : () => unawaited(controller.changeEmail()),
                  child: Text(
                    confirm ? 'Cancel sign-in' : 'Use a different email',
                  ),
                ),
              SizedBox(height: context.space.space4),
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
      ),
    );
  }
}
