/// Composable modal content for forms, confirmations and media previews.
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/modal_routes.dart';
import '../actions/icon_button.dart';

/// Header arrangement without changing modal routing or focus behavior.
enum UiModalLayout {
  /// Featured content above a leading-aligned title.
  stacked,

  /// Featured content and header text are centered.
  centered,

  /// Featured content beside text when room permits.
  horizontal,
}

/// Rich modal anatomy composed with the same owned modal route primitives.
///
/// Header and body share a scroll viewport to remain reachable on short screens
/// and with a keyboard. Footer actions remain outside it; an oversized footer
/// scrolls within 40 percent of the available height so the body stays reachable.
/// Hosts provide real
/// controls and caller-owned state for input, upload, invitation, profile,
/// payment, plans and media recipes; this component performs no service calls.
class UiModalPanel extends StatelessWidget {
  /// Builds a modal with a required title and optional semantic content slots.
  const UiModalPanel({
    super.key,
    required this.title,
    this.description,
    this.leading,
    this.media,
    this.child,
    this.footer,
    this.layout = UiModalLayout.stacked,
    this.onDismiss,
    this.dismissLabel = 'Close dialog',
  });

  /// Accessible heading.
  final String title;

  /// Supporting copy.
  final String? description;

  /// Featured icon, avatar or compact artwork.
  final Widget? leading;

  /// Edge-to-edge media, carousel or preview before the header.
  final Widget? media;

  /// Form, detail or confirmation content.
  final Widget? child;

  /// Persistent actions, optionally including a checkbox or explanatory text.
  final Widget? footer;

  /// Title and leading-content arrangement.
  final UiModalLayout layout;

  /// Requests dismissal from the visible close control.
  final VoidCallback? onDismiss;

  /// Accessible close-control name.
  final String dismissLabel;

  /// Pushes the panel with focus containment, Escape and safe-area handling.
  static Future<T?> show<T>({
    required BuildContext context,
    required String semanticsLabel,
    required WidgetBuilder builder,
    bool dismissible = true,
    String? dismissLabel,
  }) => showUiDialog<T>(
    context: context,
    semanticsLabel: semanticsLabel,
    builder: builder,
    dismissible: dismissible,
    dismissLabel: dismissLabel,
  );
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final centered = layout == UiModalLayout.centered;
    final text = Column(
      crossAxisAlignment: centered
          ? CrossAxisAlignment.center
          : CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(
          header: true,
          child: Text(
            title,
            textAlign: centered ? TextAlign.center : TextAlign.start,
            style: ui.type.title.copyWith(color: ui.color.ink),
          ),
        ),
        if (description != null) ...[
          SizedBox(height: ui.space.s2),
          Text(
            description!,
            textAlign: centered ? TextAlign.center : TextAlign.start,
            style: ui.type.body.copyWith(color: ui.color.inkSecondary),
          ),
        ],
      ],
    );
    return LayoutBuilder(
      builder: (context, constraints) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Flexible(
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ?media,
                  Padding(
                    padding: EdgeInsets.all(ui.space.s5),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: centered
                          ? CrossAxisAlignment.center
                          : CrossAxisAlignment.stretch,
                      children: [
                        if (onDismiss != null)
                          Align(
                            alignment: AlignmentDirectional.centerEnd,
                            child: UiIconButton(
                              icon: UiIcons.close,
                              semanticsLabel: dismissLabel,
                              onPressed: onDismiss,
                            ),
                          ),
                        LayoutBuilder(
                          builder: (context, constraints) {
                            if (layout == UiModalLayout.horizontal &&
                                leading != null &&
                                constraints.maxWidth >=
                                    ui.space.modalHorizontalMin &&
                                MediaQuery.textScalerOf(context).scale(1) <
                                    1.5) {
                              return Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  ConstrainedBox(
                                    constraints: BoxConstraints(
                                      maxWidth: ui.space.modalLeadingMax,
                                    ),
                                    child: leading!,
                                  ),
                                  SizedBox(width: ui.space.s4),
                                  Expanded(child: text),
                                ],
                              );
                            }
                            return Column(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: centered
                                  ? CrossAxisAlignment.center
                                  : CrossAxisAlignment.start,
                              children: [
                                if (leading != null) ...[
                                  leading!,
                                  SizedBox(height: ui.space.s4),
                                ],
                                text,
                              ],
                            );
                          },
                        ),
                        if (child != null) ...[
                          SizedBox(height: ui.space.s4),
                          child!,
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (footer != null)
            ConstrainedBox(
              constraints: BoxConstraints(
                maxHeight: constraints.maxHeight * .4,
              ),
              child: SingleChildScrollView(
                child: Padding(
                  padding: EdgeInsets.all(ui.space.s4),
                  child: footer!,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
