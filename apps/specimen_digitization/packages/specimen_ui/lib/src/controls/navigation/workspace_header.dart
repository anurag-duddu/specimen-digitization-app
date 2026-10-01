/// Persistent workspace context and navigation, separate from page commands.
library;

import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/theme.dart';
import '../../foundation/window.dart';
import '../data/hairline.dart';

/// A quiet application header with a distinct context, navigation and utility
/// zone. Compact layouts keep a visible context control above navigation. Navigation owns horizontal overflow at large text sizes.
class UiWorkspaceHeader extends StatelessWidget {
  /// Binds the persistent workspace header zones.
  const UiWorkspaceHeader({
    super.key,
    required this.identity,
    required this.compactIdentity,
    required this.navigation,
    required this.navigationWidth,
    this.actions = const <Widget>[],
  });

  /// Expanded collection identity.
  final Widget identity;

  /// Visible collection context for a narrow header.
  final Widget compactIdentity;

  /// The primary workspace destinations.
  final Widget navigation;

  /// Measured width of the navigation at the current text scale.
  final double navigationWidth;

  /// Contextual status and account actions.
  final List<Widget> actions;

  /// Bounds context so a long collection name never crowds navigation.
  static const double identityWidth = 280;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return ColoredBox(
      color: ui.color.ground,
      child: SafeArea(
        bottom: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Padding(
              padding: EdgeInsets.symmetric(horizontal: ui.space.s4),
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: UiDensity.hitBox),
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final bool wide =
                        constraints.maxWidth >=
                        WindowClass.expandedMin - 2 * ui.space.s4;
                    if (!wide) {
                      return Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Row(
                            children: <Widget>[
                              Expanded(
                                child: Align(
                                  alignment: AlignmentDirectional.centerStart,
                                  child: compactIdentity,
                                ),
                              ),
                              ...actions,
                            ],
                          ),
                          ConstrainedBox(
                            constraints: BoxConstraints(
                              maxWidth: navigationWidth,
                            ),
                            child: navigation,
                          ),
                        ],
                      );
                    }
                    return Row(
                      children: <Widget>[
                        SizedBox(width: identityWidth, child: identity),
                        SizedBox(width: ui.space.s6),
                        SizedBox(width: navigationWidth, child: navigation),
                        const Spacer(),
                        ...actions,
                      ],
                    );
                  },
                ),
              ),
            ),
            const UiHairline(),
          ],
        ),
      ),
    );
  }
}
