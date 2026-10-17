import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'administrator_contact.dart';
import 'google_sign_in.dart';

/// An optional provider action within the email-link entry form.
class GoogleSignInOption extends StatefulWidget {
  const GoogleSignInOption({
    super.key,
    required this.access,
    this.enabled = true,
    this.onBusyChanged,
    this.controller,
  });

  final GoogleSignInAccess access;
  final bool enabled;
  final ValueChanged<bool>? onBusyChanged;
  final GoogleSignInController? controller;

  @override
  State<GoogleSignInOption> createState() => _GoogleSignInOptionState();
}

class _GoogleSignInOptionState extends State<GoogleSignInOption> {
  late GoogleSignInController _controller;
  int _attempt = 0;

  @override
  void initState() {
    super.initState();
    _controller =
        widget.controller ?? GoogleSignInController(access: widget.access);
    _controller.addListener(_changed);
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void didUpdateWidget(GoogleSignInOption oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (identical(widget.access, oldWidget.access) &&
        identical(widget.controller, oldWidget.controller)) {
      return;
    }
    final bool wasBusy = _controller.busy;
    final int epoch = ++_attempt;
    _controller.removeListener(_changed);
    if (oldWidget.controller == null) _controller.dispose();
    _controller =
        widget.controller ?? GoogleSignInController(access: widget.access);
    _controller.addListener(_changed);
    if (wasBusy) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && epoch == _attempt) widget.onBusyChanged?.call(false);
      });
    }
  }

  Future<void> _signIn() async {
    if (!widget.enabled || _controller.busy) return;
    final int epoch = ++_attempt;
    widget.onBusyChanged?.call(true);
    try {
      // Preserve the browser's user activation for the provider popup.
      await _controller.signIn();
    } finally {
      if (mounted && epoch == _attempt) widget.onBusyChanged?.call(false);
    }
  }

  @override
  void dispose() {
    _controller.removeListener(_changed);
    if (widget.controller == null) _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final GoogleSignInFailure? failure = _controller.failure;
    final bool needsContact = switch (failure?.kind) {
      GoogleSignInFailureKind.unavailable ||
      GoogleSignInFailureKind.unverifiedEmail ||
      GoogleSignInFailureKind.accountConflict ||
      GoogleSignInFailureKind.policyBlocked => true,
      _ => false,
    };
    final String? status = _controller.busy
        ? 'Opening Google…'
        : _controller.lastOutcome == GoogleSignInOutcome.cancelled
        ? 'Google sign-in cancelled. You can try again or use an email link.'
        : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _GoogleSignInButton(
          busy: _controller.busy,
          onPressed: widget.enabled && !_controller.busy
              ? () => unawaited(_signIn())
              : null,
          disabledReason: _controller.busy
              ? 'Finish or cancel in the Google sign-in window.'
              : !widget.enabled
              ? 'Email sign-in is already in progress.'
              : null,
        ),
        if (status != null || failure != null) ...<Widget>[
          SizedBox(height: ui.space.s3),
          Semantics(
            container: true,
            liveRegion: true,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                if (_controller.busy) ...<Widget>[
                  const UiProgress.ring(semanticsLabel: 'Opening Google'),
                  SizedBox(width: ui.space.s2),
                ],
                Expanded(
                  child: Text(
                    failure?.message ?? status!,
                    key: const ValueKey<String>('google-feedback'),
                    style: ui.type.body.copyWith(color: ui.color.ink),
                  ),
                ),
              ],
            ),
          ),
        ],
        if (needsContact) ...<Widget>[
          SizedBox(height: ui.space.s3),
          const AdministratorContactLine(),
        ],
      ],
    );
  }
}

/// Google's prescribed appearance with scalable text and our interaction
/// primitive. The official mark and font sources are bundled with the assets.
class _GoogleSignInButton extends StatelessWidget {
  const _GoogleSignInButton({
    required this.busy,
    this.onPressed,
    this.disabledReason,
  });

  final bool busy;
  final VoidCallback? onPressed;
  final String? disabledReason;

  // These dimensions belong to the provider's branding, not product controls.
  static const double _radius = 4;
  static const double _iconSize = 20;
  static const double _fontSize = 14;
  static const double _lineHeight = 20 / 14;

  @override
  Widget build(BuildContext context) {
    final bool dark = context.ui.color.brightness == Brightness.dark;
    final bool ios = !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;
    final Color label = dark
        ? GoogleSignInPalette.labelDark
        : GoogleSignInPalette.labelLight;
    const BorderRadius radius = BorderRadius.all(Radius.circular(_radius));
    return Pressable(
      semanticsLabel: 'Sign in with Google',
      busy: busy,
      onPressed: onPressed,
      disabledReason: disabledReason,
      radius: _radius,
      shape: const RoundedRectangleBorder(borderRadius: radius),
      stateLayerColour: label,
      builder: (BuildContext context, Set<WidgetState> states) => DecoratedBox(
        decoration: BoxDecoration(
          color: dark
              ? GoogleSignInPalette.fillDark
              : GoogleSignInPalette.fillLight,
          borderRadius: radius,
          border: Border.all(
            color: dark
                ? GoogleSignInPalette.borderDark
                : GoogleSignInPalette.borderLight,
          ),
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 48),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: ios ? 16 : 12,
              vertical: 12,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Image.asset(
                  'assets/google-sign-in/google-g.png',
                  width: _iconSize,
                  height: _iconSize,
                  fit: BoxFit.contain,
                  excludeFromSemantics: true,
                ),
                SizedBox(width: ios ? 12 : 10),
                Flexible(
                  child: Text(
                    'Sign in with Google',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      // Do not inherit the product font's package prefix.
                      // This provider font belongs to the application bundle.
                      inherit: false,
                      fontFamily: 'GoogleSignInSans',
                      fontSize: _fontSize,
                      height: _lineHeight,
                      fontWeight: FontWeight.w500,
                      color: label,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
