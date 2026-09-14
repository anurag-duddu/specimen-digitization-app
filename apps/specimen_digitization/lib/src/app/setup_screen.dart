/// The screen for every state that has no collection to show yet
/// (screen blueprints, sections 1.1 and 11).
///
/// Four states share one layout, because they share one shape: the account is
/// fine, the collection is not, and there is exactly one thing to do next.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../auth.dart';
import '../theme/icons.dart';
import '../widgets/widgets.dart';
import '../workspace.dart';
import 'auth_layout.dart';

/// The message shown while a build has a session but no collection API.
const String collectionSetupMessage =
    'Ask your administrator to finish setting up sign-in and the collection API.';

/// What the setup screen is currently reporting.
enum SetupState {
  /// The build has no sign-in or no collection API.
  unconfigured,

  /// The collection list has been asked for and not yet answered.
  checking,

  /// The server answered with no collection for this account.
  unassigned,

  /// The server refused, so collection access is unproven.
  unverified,
}

/// The collection setup and access screen.
class SetupScreen extends StatefulWidget {
  const SetupScreen({
    super.key,
    this.session,
    this.setupMessage,
    this.controller,
  });

  /// The signed in account, when there is one.
  final SessionAccess? session;

  /// What the build already knows is missing.
  final String? setupMessage;

  /// The collection controller, when the build has a collection API.
  final WorkspaceController? controller;

  /// Which state the inputs describe.
  static SetupState stateOf({
    required WorkspaceController? controller,
    required SessionAccess? session,
  }) {
    if (session == null || controller == null) return SetupState.unconfigured;
    if (!controller.scopesLoaded) return SetupState.checking;
    return controller.scopesVerified
        ? SetupState.unassigned
        : SetupState.unverified;
  }

  @override
  State<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends State<SetupScreen> {
  bool _signingOut = false;
  String? _message;

  Future<void> _signOut() async {
    setState(() {
      _signingOut = true;
      _message = null;
    });
    try {
      await widget.session!.signOut();
    } catch (error) {
      if (mounted) setState(() => _message = authErrorMessage(error));
    } finally {
      if (mounted) setState(() => _signingOut = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final WorkspaceController? controller = widget.controller;
    // This screen sits outside the collection shell, so it subscribes to the
    // controller itself rather than through `WorkspaceScope`.
    return controller == null
        ? _screen(context, null)
        : ListenableBuilder(
            listenable: controller,
            builder: (BuildContext context, Widget? child) =>
                _screen(context, controller),
          );
  }

  Widget _screen(BuildContext context, WorkspaceController? controller) {
    final SetupState state = SetupScreen.stateOf(
      controller: controller,
      session: widget.session,
    );
    final ThemeData theme = Theme.of(context);
    final String title = switch (state) {
      SetupState.unconfigured => 'Collection connection required',
      SetupState.checking => 'Checking collection access',
      SetupState.unassigned => 'You have no collection assigned',
      SetupState.unverified => 'Collection access could not be verified',
    };
    final String body = switch (state) {
      SetupState.unconfigured => widget.setupMessage ?? collectionSetupMessage,
      SetupState.checking =>
        'The server is answering which collections this account may open.',
      SetupState.unassigned =>
        'Ask your administrator to assign one, then check again.',
      SetupState.unverified =>
        'Reconnect or sign in again, then check access again.',
    };

    return Scaffold(
      body: AuthLayout(
        title: title,
        children: <Widget>[
          Text(body, style: theme.textTheme.bodyMedium),
          if (state == SetupState.checking) ...<Widget>[
            SizedBox(height: context.space.space4),
            const LoadingAnnouncement(
              thing: 'collection access',
              visible: true,
            ),
          ],
          if (controller?.error != null) ...<Widget>[
            SizedBox(height: context.space.space4),
            Semantics(
              liveRegion: true,
              child: Text(
                controller!.error!.message,
                style: theme.textTheme.bodySmall,
              ),
            ),
          ],
          if (_message != null) ...<Widget>[
            SizedBox(height: context.space.space4),
            Semantics(liveRegion: true, child: Text(_message!)),
          ],
          if (controller != null && state != SetupState.checking) ...<Widget>[
            SizedBox(height: context.space.space6),
            FilledButton(
              onPressed: controller.loading
                  ? null
                  : () => unawaited(controller.checkAccess()),
              child: const Text('Check access again'),
            ),
          ],
          if (widget.session != null) ...<Widget>[
            SizedBox(height: context.space.space4),
            Text(
              'Account: ${widget.session!.displayName}',
              style: theme.textTheme.bodySmall,
            ),
            TextButton(
              onPressed: _signingOut ? null : _signOut,
              child: Text(_signingOut ? 'Signing out…' : 'Sign out'),
            ),
          ],
        ],
      ),
    );
  }
}
