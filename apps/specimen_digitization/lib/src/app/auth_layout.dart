/// The one layout every screen before the collection uses
/// (07 section 2; 05 section 3.1).
///
/// A single centered column, 400 logical pixels wide at every window class,
/// that scrolls with the software keyboard so the primary button stays
/// reachable on a phone. There is no second pane at any width: a split screen
/// would read as consumer chrome on an evidentiary tool.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../widgets/adaptive_form.dart';

/// The centered entry column.
class AuthLayout extends StatelessWidget {
  const AuthLayout({
    super.key,
    required this.title,
    required this.children,
    this.purpose,
    this.wordmark = true,
  });

  /// The screen's own heading, under the mark.
  final String title;

  /// One line saying what this screen is for.
  final String? purpose;

  /// The form, the actions and at most one secondary line.
  final List<Widget> children;

  /// False on a screen that already names the product above it.
  final bool wordmark;

  /// The product name, spelled once.
  static const String productName = 'Specimen Digitization';

  /// The column's width, at every window class (05 section 3.1).
  static const double columnWidth = DialogWidths.narrow;

  /// The mark's size where it heads an entry screen.
  ///
  /// The display glyph size, which is what the v1 header glyph occupied and
  /// what a screen with nothing else above the fold can carry.
  static const double markSize = 48;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: EdgeInsetsDirectional.fromSTEB(
            ui.space.s6,
            ui.space.s6,
            ui.space.s6,
            // Lift the column clear of the software keyboard.
            ui.space.s6 + MediaQuery.viewInsetsOf(context).bottom,
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: columnWidth),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (wordmark) ...<Widget>[
                  const Center(
                    child: UiMark(label: productName, size: markSize),
                  ),
                  SizedBox(height: ui.space.s4),
                  Text(
                    productName,
                    style: ui.type.headline.copyWith(color: ui.color.ink),
                    textAlign: TextAlign.center,
                  ),
                  SizedBox(height: ui.space.s6),
                ],
                Text(
                  title,
                  style: ui.type.titleLarge.copyWith(color: ui.color.ink),
                ),
                if (purpose != null) ...<Widget>[
                  SizedBox(height: ui.space.s2),
                  Text(
                    purpose!,
                    style: ui.type.body.copyWith(color: ui.color.inkSecondary),
                  ),
                ],
                SizedBox(height: ui.space.s6),
                ...children,
              ],
            ),
          ),
        ),
      ),
    );
  }
}
