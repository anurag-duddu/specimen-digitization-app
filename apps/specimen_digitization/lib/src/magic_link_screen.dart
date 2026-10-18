import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'email_link_browser.dart';
import 'app/sign_in_layout.dart';
import 'email_handoff.dart';
import 'magic_link.dart';
import 'google_sign_in.dart';
import 'google_sign_in_option.dart';
import 'administrator_contact.dart';
import 'widgets/motion_reveal.dart';

const bool _applePersonalDemoConfigured = bool.fromEnvironment(
  'SPECIMEN_APPLE_PERSONAL_DEMO',
);

/// The manual-paste seam exists only for an opted-in debug iPhone demo.
/// Optional inputs let source tests prove every gate without weakening the
/// release-build [kDebugMode] requirement.
bool applePersonalDemoPasteEnabled({
  @visibleForTesting bool? debug,
  bool? configured,
  bool? web,
  TargetPlatform? platform,
}) =>
    kDebugMode &&
    (debug ?? true) &&
    !(web ?? kIsWeb) &&
    (platform ?? defaultTargetPlatform) == TargetPlatform.iOS &&
    (configured ?? _applePersonalDemoConfigured);

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
    this.google,
    this.inboxLauncher = const UrlEmailInboxLauncher(),
    @visibleForTesting this.applePersonalDemoConfigured,
    @visibleForTesting this.platform,
    @visibleForTesting this.clipboardReader,
  });
  final EmailLinkAccess access;
  final MagicLinkController? controller;
  final GoogleSignInAccess? google;
  final EmailInboxLauncher inboxLauncher;
  final bool? applePersonalDemoConfigured;
  final TargetPlatform? platform;
  final Future<String?> Function()? clipboardReader;
  @override
  State<MagicLinkSignInScreen> createState() => _MagicLinkSignInScreenState();
}

class _MagicLinkSignInScreenState extends State<MagicLinkSignInScreen> {
  final _email = TextEditingController();
  bool _openingInbox = false;
  String? _inboxError;
  int _inboxAttempt = 0;
  String? _emailError;
  late final MagicLinkController controller;
  Timer? _timer;
  bool _readingClipboard = false;
  bool _googleBusy = false;
  bool _helpExpanded = false;
  String? _lastRemembered;
  bool _lastHandlingLink = false;
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
    _lastHandlingLink = controller.handlingLink;
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
      _inboxAttempt++;
      _openingInbox = false;
      _inboxError = null;
    }
    if (controller.handlingLink != _lastHandlingLink) {
      _lastHandlingLink = controller.handlingLink;
      _inboxAttempt++;
      _openingInbox = false;
      _inboxError = null;
    }
    setState(() {});
  }

  @override
  void dispose() {
    _timer?.cancel();
    controller.removeListener(_changed);
    if (widget.controller == null) controller.dispose();
    _inboxAttempt++;
    _email.dispose();
    super.dispose();
  }

  void _submit() {
    if (!controller.initialized || controller.busy || _googleBusy) return;
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

  Future<void> _pasteSignInLink() async {
    if (_readingClipboard || controller.busy || !controller.initialized) return;
    final String startingEmail = controller.email;
    final bool startingSent = controller.sent;
    setState(() => _readingClipboard = true);
    String? link;
    try {
      link = widget.clipboardReader != null
          ? await widget.clipboardReader!()
          : (await Clipboard.getData(Clipboard.kTextPlain))?.text;
    } catch (_) {
      // Clipboard errors can include private platform details. The controller
      // presents the same safe guidance as an empty clipboard.
    } finally {
      if (mounted) setState(() => _readingClipboard = false);
    }
    if (!mounted ||
        controller.busy ||
        controller.email != startingEmail ||
        controller.sent != startingSent) {
      return;
    }
    controller.acceptPastedLink(link ?? '');
  }

  Future<void> _openInbox() async {
    if (_openingInbox || !controller.sent || controller.handlingLink) return;
    final attempt = ++_inboxAttempt;
    final recipient = controller.email;
    setState(() {
      _openingInbox = true;
      _inboxError = null;
    });
    bool opened = false;
    try {
      // Dispatch before the first await to retain browser user activation.
      opened = await widget.inboxLauncher.openInbox();
    } catch (_) {
      // A platform failure must not expose raw URLs or account details.
    }
    if (!mounted || attempt != _inboxAttempt) return;
    setState(() {
      _openingInbox = false;
      if (!opened &&
          controller.sent &&
          !controller.handlingLink &&
          recipient == controller.email) {
        _inboxError =
            "Couldn't open Gmail. Open your inbox in a browser and use the sign-in link.";
      }
    });
  }

  static String _submitLabel(
    MagicLinkController controller, {
    required bool confirm,
  }) {
    if (controller.busy) return confirm ? 'Signing in…' : 'Sending link…';
    if (confirm) return 'Sign in';
    return controller.sent ? 'Resend link' : 'Send link';
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final confirm = controller.handlingLink;
    final sent = controller.sent && !confirm;
    final pasteDemo = applePersonalDemoPasteEnabled(
      configured: widget.applePersonalDemoConfigured,
      platform: widget.platform,
    );
    final cooldown = controller.cooldownSeconds;
    final busy = controller.busy || _googleBusy;
    final disabled =
        !controller.initialized || busy || (!confirm && cooldown > 0);
    return UiScaffold(
      body: AutofillGroup(
        child: SignInLayout(
          title: confirm
              ? 'Confirm your email'
              : sent
              ? 'Check your email'
              : controller.hasError
              ? 'Sign-in could not finish'
              : 'Sign in to your collection',
          purpose: confirm
              ? 'Use the email address that received this link.'
              : sent
              ? 'Use the sign-in link in your email.'
              : 'Use your fieldmuseum.org email or an approved account.',
          icon: controller.hasError
              ? UiIcons.error
              : sent
              ? UiIcons.email
              : UiIcons.locked,
          busy: controller.busy && confirm,
          footer: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: Semantics(
                  expanded: _helpExpanded,
                  child: UiButton(
                    label: 'Sign-in help',
                    variant: UiButtonVariant.ghost,
                    trailing: _helpExpanded ? UiIcons.collapse : UiIcons.expand,
                    onPressed: () =>
                        setState(() => _helpExpanded = !_helpExpanded),
                  ),
                ),
              ),
              if (_helpExpanded) ...[
                Text(
                  sent
                      ? 'Check spam, use the latest link, or request a new one.'
                      : 'Your first sign-in creates your account. Your administrator grants collection access.',
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
                SizedBox(height: ui.space.s3),
                const AdministratorContactLine(),
              ],
            ],
          ),
          children: [
            if (sent) ...[
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Link sent to',
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                  SizedBox(height: ui.space.s1),
                  Semantics(
                    container: true,
                    liveRegion: true,
                    child: Text(
                      controller.email,
                      key: const ValueKey<String>('email-link-recipient'),
                      style: ui.type.body.copyWith(color: ui.color.ink),
                    ),
                  ),
                  Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: UiButton(
                      label: 'Change email',
                      variant: UiButtonVariant.ghost,
                      onPressed: busy || _readingClipboard
                          ? null
                          : () => unawaited(controller.changeEmail()),
                    ),
                  ),
                ],
              ),
              SizedBox(height: ui.space.s6),
              UiButton(
                label: 'Open Gmail',
                expand: true,
                leading: UiIcons.email,
                size: UiSize.lg,
                loading: _openingInbox,
                onPressed: busy || _openingInbox
                    ? null
                    : () => unawaited(_openInbox()),
              ),
              if (_inboxError != null) ...[
                SizedBox(height: ui.space.s3),
                Semantics(
                  liveRegion: true,
                  child: Text(
                    _inboxError!,
                    key: const ValueKey<String>('email-inbox-error'),
                    style: ui.type.bodySmall.copyWith(color: ui.color.ink),
                  ),
                ),
              ],
            ] else
              UiField(
                label: 'Email address',
                controller: _email,
                enabled: !busy,
                errorText: _emailError,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.done,
                autofillHints: const [AutofillHints.email],
                autocorrect: false,
                onChanged: (_) {
                  if (_emailError != null) setState(() => _emailError = null);
                },
                onSubmitted: (_) {
                  if (!disabled) _submit();
                },
              ),
            MotionReveal(
              visible: controller.hasError,
              child: Padding(
                padding: EdgeInsets.symmetric(vertical: ui.space.s4),
                child: Semantics(
                  container: true,
                  liveRegion: true,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const UiIcon(UiIcons.error),
                      SizedBox(width: ui.space.s2),
                      Expanded(
                        child: Text(
                          controller.hasError ? controller.message! : '',
                          key: const ValueKey<String>('email-link-error'),
                          style: ui.type.body.copyWith(color: ui.color.ink),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            SizedBox(height: ui.space.s4),
            UiButton(
              label: _submitLabel(controller, confirm: confirm),
              expand: !sent,
              semanticsLabel: controller.busy
                  ? _submitLabel(controller, confirm: confirm)
                  : confirm
                  ? 'Sign in with this email link'
                  : sent
                  ? 'Resend link to sign in'
                  : 'Send link to sign in',
              variant: sent
                  ? UiButtonVariant.secondary
                  : UiButtonVariant.primary,
              size: UiSize.lg,
              loading: controller.busy,
              onPressed: disabled ? null : _submit,
              disabledReason: !confirm && cooldown > 0
                  ? 'You can request another link in ${cooldown}s.'
                  : null,
            ),
            if (!confirm && cooldown > 0)
              Padding(
                padding: EdgeInsets.only(top: ui.space.s3),
                child: Text(
                  'You can request another link in ${cooldown}s.',
                  style: ui.type.bodySmall.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
              ),
            if (pasteDemo && sent) ...[
              SizedBox(height: ui.space.s3),
              UiButton(
                label: 'Paste link from email',
                variant: UiButtonVariant.ghost,
                loading: _readingClipboard,
                onPressed: busy || _readingClipboard
                    ? null
                    : () => unawaited(_pasteSignInLink()),
              ),
            ],
            if (!sent && (confirm || controller.message != null))
              UiButton(
                label: confirm ? 'Cancel sign-in' : 'Change email',
                variant: UiButtonVariant.ghost,
                onPressed: busy || _readingClipboard
                    ? null
                    : () => unawaited(controller.changeEmail()),
              ),
            // Keep an active provider attempt mounted if a warm email link arrives.
            if (widget.google != null &&
                ((!controller.sent && !confirm) || _googleBusy)) ...[
              SizedBox(height: ui.space.s4),
              Text(
                'Or',
                textAlign: TextAlign.center,
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
              SizedBox(height: ui.space.s4),
              GoogleSignInOption(
                key: const ValueKey<String>('google-sign-in-option'),
                access: widget.google!,
                enabled:
                    !controller.busy &&
                    controller.initialized &&
                    !controller.sent &&
                    !confirm,
                onBusyChanged: (busy) {
                  if (busy) controller.beginAlternateSignIn();
                  if (mounted) setState(() => _googleBusy = busy);
                },
              ),
            ],
          ],
        ),
      ),
    );
  }
}
