/// Help, shortcuts and glossary (screen blueprints, section 10).
///
/// One sheet over whatever route is open, so every "ask your administrator"
/// string has somewhere to point.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../administrator_contact.dart';
import '../models.dart';
import '../theme/icons.dart';
import '../theme/motion.dart';
import '../theme/motion_preference.dart';
import '../vocabulary.dart';
import '../widgets/widgets.dart';
import '../workspace.dart';

/// A first review, in the order a reviewer does it (screen blueprints,
/// section 10; pass criteria 10.1 and 10.4).
///
/// Five steps, because a walkthrough nobody finishes is a walkthrough nobody
/// read. Each names the control it is about, in the words that control uses,
/// so the step and the screen agree.
const List<String> reviewWalkthrough = <String>[
  'Open a record from the queue. The photograph is the evidence; everything '
      'else is a claim about it.',
  'Read the two independent readings side by side. Where they differ, the '
      'difference is counted rather than hinted at.',
  'Correct what is wrong in Fields. Corrections collect, and save together '
      'under one reason.',
  'Check what blocks clearance. Every entry in that list goes to the control '
      'that resolves it.',
  'Approve the record, or confirm label coverage. Both ask for a reason, and '
      'neither can be taken back.',
];

/// What this build is, for a message to an administrator.
///
/// Passed in at build time rather than read from a package, because this
/// client has no platform channel for it on every target it ships to. A build
/// that was not stamped says so rather than naming a version it invented.
const String appBuild = String.fromEnvironment(
  'APP_BUILD',
  defaultValue: 'Not stamped by the build',
);

/// The shortcuts this step of the redesign ships, in the order they are
/// learned (screen blueprints, section 3; responsive, section 4).
const Map<String, String> queueShortcuts = <String, String>{
  'J or down arrow': 'Next record',
  'K or up arrow': 'Previous record',
  'Enter': 'Open the selected record',
  '/': 'Focus the search field',
  'F': 'Open filters',
};

/// The help sheet as a route page: a scrim, and a panel that is a sheet on a
/// compact window and a centered dialog everywhere else.
Page<void> helpPage(BuildContext context) {
  final MotionTokens motion = MotionTokens.of(context);
  return CustomTransitionPage<void>(
    opaque: false,
    barrierDismissible: true,
    barrierColor: Theme.of(context).colorScheme.scrim.withValues(alpha: 0.4),
    transitionDuration: motion.standard,
    reverseTransitionDuration: motion.quick,
    child: const HelpScreen(),
    transitionsBuilder:
        (
          BuildContext context,
          Animation<double> animation,
          Animation<double> secondary,
          Widget child,
        ) => FadeTransition(
          opacity: CurvedAnimation(
            parent: animation,
            curve: MotionTokens.enterCurve,
          ),
          child: child,
        ),
  );
}

/// The help panel.
class HelpScreen extends StatelessWidget {
  const HelpScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final bool compact = WindowClass.of(context).isCompact;
    final Widget panel = Material(
      color: Theme.of(context).colorScheme.surface,
      borderRadius: BorderRadius.circular(
        compact ? context.shape.radiusLg : context.shape.radiusMd,
      ),
      clipBehavior: Clip.antiAlias,
      child: const _HelpBody(),
    );

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Align(
          alignment: compact ? Alignment.bottomCenter : Alignment.center,
          child: Padding(
            // No side gutter on a phone: the sheet is the screen there, and a
            // centred card with a scrim around it gives the glossary less
            // measure than the window has (finding V-14).
            padding: compact
                ? EdgeInsets.only(top: context.space.space4)
                : EdgeInsets.all(context.space.space4),
            child: ConstrainedBox(
              constraints: BoxConstraints(
                maxWidth: compact ? double.infinity : DialogWidths.standard,
                maxHeight: MediaQuery.sizeOf(context).height * _maxHeightFactor,
              ),
              child: panel,
            ),
          ),
        ),
      ),
    );
  }

  /// The sheet never covers the whole window, so the route beneath it stays
  /// visible and the sheet reads as temporary.
  static const double _maxHeightFactor = 0.85;
}

class _HelpBody extends StatelessWidget {
  const _HelpBody();

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final WorkspaceController? controller = _controllerOf(context);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Padding(
          padding: EdgeInsets.fromLTRB(
            context.space.space4,
            context.space.space3,
            context.space.space2,
            context.space.space0,
          ),
          child: Row(
            children: <Widget>[
              Expanded(child: Text('Help', style: theme.textTheme.titleLarge)),
              IconButton(
                onPressed: () => Navigator.of(context).maybePop(),
                tooltip: 'Close help',
                icon: const Icon(Symbols.close),
              ),
            ],
          ),
        ),
        Flexible(
          child: ListView(
            shrinkWrap: true,
            padding: EdgeInsets.all(context.space.space4),
            children: <Widget>[
              Text('Keyboard shortcuts', style: theme.textTheme.titleMedium),
              SizedBox(height: context.space.space2),
              for (final MapEntry<String, String> entry
                  in queueShortcuts.entries)
                Padding(
                  padding: EdgeInsets.only(bottom: context.space.space1),
                  child: Text.rich(
                    TextSpan(
                      children: <InlineSpan>[
                        TextSpan(
                          text: entry.key,
                          style: context.mono.identifier,
                        ),
                        TextSpan(text: ': ${entry.value}'),
                      ],
                    ),
                  ),
                ),
              SizedBox(height: context.space.space6),
              Text('A first review', style: theme.textTheme.titleMedium),
              SizedBox(height: context.space.space2),
              for (final (int i, String step) in reviewWalkthrough.indexed)
                Padding(
                  padding: EdgeInsets.only(bottom: context.space.space2),
                  child: MergeSemantics(child: Text('${i + 1}. $step')),
                ),
              SizedBox(height: context.space.space6),
              Text('Glossary', style: theme.textTheme.titleMedium),
              SizedBox(height: context.space.space2),
              for (final MapEntry<String, String> entry
                  in userFacingTerms.entries)
                Padding(
                  padding: EdgeInsets.only(bottom: context.space.space1),
                  child: Text('${entry.value}: ${labelOf(entry.key)}'),
                ),
              SizedBox(height: context.space.space6),
              Text('This build', style: theme.textTheme.titleMedium),
              SizedBox(height: context.space.space2),
              Text(
                'Environment: ${environmentLabel(controller?.environment ?? '')}',
              ),
              Text(
                'Account: ${controller?.session.displayName ?? 'Not signed in'}',
              ),
              Text('Build: $appBuild'),
              SelectableText(
                'Service: ${controller?.repository.mode ?? 'none'}',
              ),
              SizedBox(height: context.space.space6),
              Text('Motion', style: theme.textTheme.titleMedium),
              SizedBox(height: context.space.space2),
              const ReduceMotionSetting(),
              SizedBox(height: context.space.space6),
              Text('Report a problem', style: theme.textTheme.titleMedium),
              SizedBox(height: context.space.space2),
              const Text(
                'Write to the contact below, with the build line above and '
                'the record identifier.',
              ),
              SizedBox(height: context.space.space6),
              Text('Administrator contact', style: theme.textTheme.titleMedium),
              SizedBox(height: context.space.space2),
              // Read from the collection document, which is the only place
              // the server publishes one (pass criterion 10.3).
              const AdministratorContactLine(dense: false),
            ],
          ),
        ),
      ],
    );
  }

  /// The help sheet is pushed over any route, including routes outside the
  /// collection shell, so the controller may be absent.
  WorkspaceController? _controllerOf(BuildContext context) {
    final WorkspaceScope? scope = context
        .getInheritedWidgetOfExactType<WorkspaceScope>();
    return scope?.notifier;
  }
}

/// The in-app "Reduce motion" switch (motion and microinteractions, 6.2b).
///
/// The fourth reduced-motion source, and the only one a reviewer on a managed
/// desktop can reach: an operating system accessibility setting may not be
/// theirs to change, and on this toolchain a browser preference never reaches
/// the framework at all.
class ReduceMotionSetting extends StatelessWidget {
  const ReduceMotionSetting({super.key});

  /// The switch label, fixed so the tests and the copy cannot drift.
  static const String label = 'Reduce motion';

  /// What turning it on does, and what it deliberately leaves alone.
  static const String helper =
      'Removes sliding and zooming. Progress bars keep moving.';

  @override
  Widget build(BuildContext context) {
    final MotionPreferenceController? controller = MotionPreference.maybeOf(
      context,
    );
    // Outside the application scope, such as a component test that pumps this
    // panel on a bare MaterialApp, there is no setting to offer.
    if (controller == null) return const SizedBox.shrink();
    return SwitchListTile(
      value: controller.forceReducedMotion,
      onChanged: (bool value) => unawaited(controller.set(value)),
      title: const Text(label),
      subtitle: const Text(helper),
      contentPadding: EdgeInsets.zero,
    );
  }
}
