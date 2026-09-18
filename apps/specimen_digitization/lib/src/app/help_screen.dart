/// Help, shortcuts and glossary (screen blueprints, section 10).
///
/// One sheet over whatever route is open, so every "ask your administrator"
/// string has somewhere to point.
library;

import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../administrator_contact.dart';
import '../glossary.dart';
import '../vocabulary.dart';
import '../widgets/widgets.dart';
import '../workspace.dart';

/// A first review, in the order a reviewer does it (screen blueprints,
/// section 10; pass criteria 10.1 and 10.4).
///
/// Five steps, because a walkthrough nobody finishes is a walkthrough nobody
/// read. Every control is named by the exact words on it, in single quotes,
/// so a first-time reviewer can match the step to the screen without
/// guessing which button the sentence meant. `test/screens/help_test.dart`
/// holds the naming: each quoted control has to exist in the product.
const List<String> reviewWalkthrough = <String>[
  "Open a record from the queue: tap its row, or press Enter on it. The "
      "photograph is the evidence; everything else is a claim about it.",
  "Read the two readings side by side under 'Readings'. Where they differ, "
      "the difference is counted rather than hinted at.",
  "Correct what is wrong under 'Fields': tap a layer, then 'Keep this "
      "correction'. Corrections collect rather than sending one at a time.",
  "Open the blockers line at the top of the record. Every entry in that list "
      "goes to the control that resolves it.",
  "Finish on the decision bar: save the pending changes, which names the "
      "exact count, then 'Approve record' or 'Confirm label coverage'. Each "
      "asks for a reason, and none can be taken back.",
];

/// The controls [reviewWalkthrough] names, in the words the product uses.
///
/// Listed once so the walkthrough and the screens cannot drift: a control
/// renamed without this list being renamed fails the help test.
const List<String> walkthroughControls = <String>[
  'Readings',
  'Fields',
  'Keep this correction',
  'Approve record',
  'Confirm label coverage',
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

/// The help sheet as a route page: a scrim, and a pane that is a sheet on a
/// compact window and a centered dialog everywhere else.
Page<void> helpPage(BuildContext context) {
  final MotionTokens motion = context.ui.motion;
  return CustomTransitionPage<void>(
    opaque: false,
    barrierDismissible: true,
    barrierColor: context.ui.color.scrim,
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

  /// What the control that closes the panel is called.
  static const String closeLabel = 'Close help';

  /// The sheet never covers the whole window, so the route beneath it stays
  /// visible and the sheet reads as temporary.
  static const double maxHeightFactor = 0.85;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final bool compact = WindowClass.of(context).isCompact;

    return SafeArea(
      child: Align(
        alignment: compact
            ? AlignmentDirectional.bottomCenter
            : AlignmentDirectional.center,
        child: Padding(
          // No side gutter on a phone: the sheet is the screen there, and a
          // centred pane with a scrim around it gives the glossary less
          // measure than the window has (finding V-14).
          padding: compact
              ? EdgeInsetsDirectional.only(top: ui.space.s4)
              : EdgeInsetsDirectional.all(ui.space.s4),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: compact ? double.infinity : DialogWidths.standard,
              maxHeight: MediaQuery.sizeOf(context).height * maxHeightFactor,
            ),
            child: GlassSurface(
              level: GlassLevel.modal,
              radius: compact ? ui.shape.sheet : ui.shape.tile,
              child: const _HelpBody(),
            ),
          ),
        ),
      ),
    );
  }
}

class _HelpBody extends StatelessWidget {
  const _HelpBody();

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final WorkspaceController? controller = _controllerOf(context);
    final TextStyle section = ui.type.title.copyWith(color: ui.color.ink);
    final TextStyle body = ui.type.body.copyWith(color: ui.color.ink);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Padding(
          padding: EdgeInsetsDirectional.fromSTEB(
            ui.space.s4,
            ui.space.s3,
            ui.space.s2,
            ui.space.s0,
          ),
          child: Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  'Help',
                  style: ui.type.titleLarge.copyWith(color: ui.color.ink),
                ),
              ),
              UiIconButton(
                icon: UiIcons.close,
                semanticsLabel: HelpScreen.closeLabel,
                tooltip: HelpScreen.closeLabel,
                onPressed: () => Navigator.of(context).maybePop(),
              ),
            ],
          ),
        ),
        // One scroll for the panel (13 section 4.6). The title row above is
        // the pane's own chrome, the way a sheet's title is, and everything
        // under it is the single scroll. It used to shrink wrap so it could
        // sit in a `Flexible`, which is the pair 13 section 2.1 names: a
        // shrink wrapped list exists to be nested. `Expanded` gives the list
        // what the pane's own maximum height leaves, so it scrolls itself.
        Expanded(
          child: ListView(
            padding: EdgeInsetsDirectional.all(ui.space.s4),
            children: <Widget>[
              Text('Keyboard shortcuts', style: section),
              SizedBox(height: ui.space.s2),
              for (final MapEntry<String, String> entry
                  in queueShortcuts.entries)
                Padding(
                  padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
                  child: MergeSemantics(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        UiKeyCap(label: entry.key),
                        SizedBox(width: ui.space.s2),
                        Expanded(child: Text(entry.value, style: body)),
                      ],
                    ),
                  ),
                ),
              SizedBox(height: ui.space.s6),
              Text('A first review', style: section),
              SizedBox(height: ui.space.s2),
              for (final (int i, String step) in reviewWalkthrough.indexed)
                Padding(
                  padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
                  child: MergeSemantics(
                    child: Text('${i + 1}. $step', style: body),
                  ),
                ),
              SizedBox(height: ui.space.s6),
              Text('Glossary', style: section),
              SizedBox(height: ui.space.s2),
              // One sentence per word, from `glossary.dart`, which is the
              // same text the term itself opens where it appears
              // (pass criterion 10.2). The old list paired each word with
              // the wire value it came from, which is a mapping rather than
              // a definition.
              for (final MapEntry<String, String> entry in glossary.entries)
                Padding(
                  padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
                  child: MergeSemantics(
                    child: Text.rich(
                      TextSpan(
                        children: <InlineSpan>[
                          TextSpan(
                            text: _sentenceCase(entry.key),
                            style: ui.type.label.copyWith(color: ui.color.ink),
                          ),
                          TextSpan(text: '. ${entry.value}'),
                        ],
                      ),
                      style: body,
                    ),
                  ),
                ),
              SizedBox(height: ui.space.s6),
              Text('This build', style: section),
              SizedBox(height: ui.space.s2),
              Text(
                'Environment: ${environmentLabel(controller?.environment ?? '')}',
                style: body,
              ),
              Text(
                'Account: ${controller?.session.displayName ?? 'Not signed in'}',
                style: body,
              ),
              Text('Build: $appBuild', style: body),
              _CopyableLine(
                label: 'Service',
                value: controller?.repository.mode ?? 'none',
              ),
              SizedBox(height: ui.space.s6),
              Text('Motion', style: section),
              SizedBox(height: ui.space.s2),
              const ReduceMotionSetting(),
              SizedBox(height: ui.space.s6),
              Text('Report a problem', style: section),
              SizedBox(height: ui.space.s2),
              Text(
                'Write to the contact below, with the build line above and '
                'the record identifier.',
                style: body,
              ),
              SizedBox(height: ui.space.s6),
              Text('Administrator contact', style: section),
              SizedBox(height: ui.space.s2),
              // Read from the collection document, which is the only place
              // the server publishes one (pass criterion 10.3).
              const AdministratorContactLine(dense: false),
            ],
          ),
        ),
      ],
    );
  }

  static String _sentenceCase(String value) =>
      value.isEmpty ? value : '${value[0].toUpperCase()}${value.substring(1)}';

  /// The help sheet is pushed over any route, including routes outside the
  /// collection shell, so the controller may be absent.
  WorkspaceController? _controllerOf(BuildContext context) {
    final WorkspaceScope? scope = context
        .getInheritedWidgetOfExactType<WorkspaceScope>();
    return scope?.notifier;
  }
}

/// A build line an operator can put into a message to their administrator.
///
/// The v1 line was a `SelectableText`, which is a Material component. A copy
/// control keeps the capability, names itself, and is a 48 dp target rather
/// than a drag a touch reviewer has to discover.
class _CopyableLine extends StatelessWidget {
  const _CopyableLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final String line = '$label: $value';
    return MergeSemantics(
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              line,
              style: ui.type.body.copyWith(color: ui.color.ink),
            ),
          ),
          UiIconButton(
            icon: UiIcons.copy,
            semanticsLabel: 'Copy the $label line',
            tooltip: 'Copy the $label line',
            onPressed: () =>
                unawaited(Clipboard.setData(ClipboardData(text: line))),
          ),
        ],
      ),
    );
  }
}

/// The in-app "Reduce motion" switch (04 section 6.2b).
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
    // panel on its own, there is no setting to offer.
    if (controller == null) return const SizedBox.shrink();
    return UiListRow(
      title: label,
      subtitle: helper,
      trailing: UiSwitch(
        label: label,
        showLabel: false,
        value: controller.forceReducedMotion,
        onChanged: (bool value) => unawaited(controller.set(value)),
      ),
    );
  }
}
