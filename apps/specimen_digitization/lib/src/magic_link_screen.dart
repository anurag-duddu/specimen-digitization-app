import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'email_link_browser.dart';
import 'app/auth_layout.dart';
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

class MagicLinkSignInScreen extends StatefulWidget {
  const MagicLinkSignInScreen({
    super.key,
    required this.access,
    this.controller,
    this.google,
    @visibleForTesting this.applePersonalDemoConfigured,
    @visibleForTesting this.platform,
    @visibleForTesting this.clipboardReader,
  });
  final EmailLinkAccess access;
  final MagicLinkController? controller;
  final GoogleSignInAccess? google;
  final bool? applePersonalDemoConfigured;
  final TargetPlatform? platform;
  final Future<String?> Function()? clipboardReader;
  @override
  State<MagicLinkSignInScreen> createState() => _MagicLinkSignInScreenState();
}

class _MagicLinkSignInScreenState extends State<MagicLinkSignInScreen> {
  final _email = TextEditingController();
  String? _emailError;
  late final MagicLinkController controller;
  Timer? _timer;
  bool _readingClipboard = false;
  bool _googleBusy = false;
  bool _helpExpanded = false;
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

  /// The primary button's label for the state the controller is in.
  ///
  /// One function, so the `AnimatedSwitcher`'s key and the text it draws can
  /// never disagree and leave the label frozen mid-request.
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
    final UiThemeData ui = context.ui;
    final bool confirm = controller.handlingLink;
    final bool sent = controller.sent && !confirm;
    final bool pasteDemo = applePersonalDemoPasteEnabled(
      configured: widget.applePersonalDemoConfigured,
      platform: widget.platform,
    );
    final int cooldown = controller.cooldownSeconds;
    final bool disabled =
        !controller.initialized ||
        controller.busy ||
        _googleBusy ||
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
              ? 'Enter the email address that received this link.'
              : sent
              ? 'Open the sign-in link sent to:'
              : 'Use your fieldmuseum.org email. No password needed.',
          children: <Widget>[
            if (sent)
              Semantics(
                container: true,
                liveRegion: true,
                child: Text(
                  controller.email,
                  key: const ValueKey<String>('email-link-recipient'),
                  style: ui.type.title.copyWith(color: ui.color.ink),
                ),
              )
            else
              UiField(
                label: 'Email address',
                controller: _email,
                enabled: !controller.busy && !_googleBusy,
                errorText: _emailError,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.done,
                autofillHints: const <String>[AutofillHints.email],
                autocorrect: false,
                onChanged: (_) {
                  if (_emailError != null) setState(() => _emailError = null);
                },
                onSubmitted: (_) {
                  if (!disabled) _submit();
                },
              ),
            // The announcement is what tells a screen reader user; the
            // reveal only keeps the column from snapping (04 section 4,
            // row 5).
            MotionReveal(
              visible: controller.hasError,
              child: Padding(
                padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s4),
                child: Semantics(
                  container: true,
                  liveRegion: true,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
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
            SizedBox(height: ui.space.s6),
            UiButton(
              label: _submitLabel(controller, confirm: confirm),
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
            if (pasteDemo && controller.sent && !confirm) ...<Widget>[
              SizedBox(height: ui.space.s3),
              Text(
                'For this iPhone demo, copy the full sign-in link from the email, then paste it here.',
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
              UiButton(
                label: 'Paste link from email',
                variant: UiButtonVariant.ghost,
                loading: _readingClipboard,
                onPressed: controller.busy || _googleBusy || _readingClipboard
                    ? null
                    : () => unawaited(_pasteSignInLink()),
                disabledReason: controller.busy
                    ? 'Sign-in is already in progress.'
                    : _readingClipboard
                    ? 'Reading the sign-in link from the clipboard.'
                    : null,
              ),
            ],
            if (controller.sent || confirm || controller.message != null)
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: UiButton(
                  label: confirm ? 'Cancel sign-in' : 'Change email',
                  variant: UiButtonVariant.ghost,
                  onPressed: controller.busy || _googleBusy || _readingClipboard
                      ? null
                      : () => unawaited(controller.changeEmail()),
                  disabledReason: _readingClipboard
                      ? 'Finish reading the sign-in link before changing email.'
                      : null,
                ),
              ),
            // A warm email link can arrive during a provider attempt. Keep the
            // option alive until its completion releases the shared busy guard.
            if (widget.google != null &&
                ((!controller.sent && !confirm) || _googleBusy)) ...<Widget>[
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
                  if (mounted) setState(() => _googleBusy = busy);
                },
              ),
            ],
            SizedBox(height: ui.space.s4),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: MergeSemantics(
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
            ),
            if (_helpExpanded) ...<Widget>[
              SizedBox(height: ui.space.s2),
              Text(
                sent
                    ? 'Check your spam folder, or request a new link when the timer ends.'
                    : 'Your first sign-in creates your account. Your collection administrator grants collection access.',
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
              SizedBox(height: ui.space.s3),
              const AdministratorContactLine(),
            ],
          ],
        ),
      ),
    );
  }
}
