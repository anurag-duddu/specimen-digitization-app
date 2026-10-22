import 'dart:async';

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
        UiGoogleSignInButton(
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
