/// Help, shortcuts and glossary (screen blueprints, section 10).
///
/// One sheet over whatever route is open, so every "ask your administrator"
/// string has somewhere to point.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../models.dart';
import '../theme/icons.dart';
import '../theme/motion.dart';
import '../vocabulary.dart';
import '../widgets/widgets.dart';
import '../workspace.dart';

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
            padding: EdgeInsets.all(context.space.space4),
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
    final Json configuration =
        controller?.scope?.configuration ?? const <String, dynamic>{};
    final String contact = textOf(
      configuration['administrator_contact'],
      'Your collection administrator has not published a contact address.',
    );

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
              SizedBox(height: context.space.space6),
              Text('Administrator contact', style: theme.textTheme.titleMedium),
              SizedBox(height: context.space.space2),
              Text(contact),
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
