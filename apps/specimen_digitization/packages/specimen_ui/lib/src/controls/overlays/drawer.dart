/// A bounded side panel with persistent header and footer slots.
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/modal_routes.dart';
import '../actions/icon_button.dart';

/// A side panel for filters, details, messages and settings.
///
/// The body scrolls independently of its title and footer. Call [show] to use
/// the shared modal focus, safe-area, keyboard and dismissal behavior. Header and
/// footer contents scroll independently when either would consume more than
/// 40 percent of the available height, keeping the body and all actions reachable. The host
/// owns form state and saving; dismissing this surface never commits changes.
class UiDrawer extends StatelessWidget {
  /// Builds panel content. The parent must provide a finite height.
  const UiDrawer({
    super.key,
    required this.title,
    required this.child,
    this.description,
    this.header,
    this.footer,
    this.onClose,
    this.closeLabel = 'Close panel',
    this.scrollBody = true,
  });

  /// The panel's accessible and visible name.
  final String title;

  /// Optional supporting instructions below the title.
  final String? description;

  /// Additional fixed header content, such as tabs or a search field.
  final Widget? header;

  /// The main content; wrapped in a scroller unless [scrollBody] is false.
  final Widget child;

  /// Persistent actions or status below the scrolling content.
  final Widget? footer;

  /// Close affordance; omitted for a deliberately nondismissible panel.
  final VoidCallback? onClose;

  /// Accessible name for the close action.
  final String closeLabel;

  /// False when [child] manages its own scroll controller or lazy list.
  final bool scrollBody;

  /// Opens the panel with a result returned by the host's Navigator.pop call.
  static Future<T?> show<T>({
    required BuildContext context,
    required String title,
    required WidgetBuilder body,
    String? description,
    WidgetBuilder? header,
    WidgetBuilder? footer,
    bool dismissible = true,
    bool fromStart = false,
    bool scrollBody = true,
    String closeLabel = 'Close panel',
  }) => showUiDrawer<T>(
    context: context,
    semanticsLabel: title,
    dismissLabel: closeLabel,
    dismissible: dismissible,
    fromStart: fromStart,
    builder: (panelContext) => UiDrawer(
      title: title,
      description: description,
      header: header?.call(panelContext),
      footer: footer?.call(panelContext),
      onClose: dismissible ? () => Navigator.of(panelContext).maybePop() : null,
      closeLabel: closeLabel,
      scrollBody: scrollBody,
      child: body(panelContext),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final heading = Padding(
      padding: EdgeInsets.all(ui.space.s4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Semantics(
                  header: true,
                  child: Text(title, style: ui.type.title),
                ),
              ),
              if (onClose != null)
                UiIconButton(
                  icon: UiIcons.close,
                  semanticsLabel: closeLabel,
                  onPressed: onClose,
                ),
            ],
          ),
          if (description != null) ...[
            SizedBox(height: ui.space.s2),
            Text(description!, style: ui.type.body),
          ],
          if (header != null) ...[SizedBox(height: ui.space.s4), header!],
        ],
      ),
    );
    return LayoutBuilder(
      builder: (context, constraints) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ConstrainedBox(
            constraints: BoxConstraints(maxHeight: constraints.maxHeight * .4),
            child: SingleChildScrollView(child: heading),
          ),
          Expanded(
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: ui.space.s4),
              child: scrollBody ? SingleChildScrollView(child: child) : child,
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
