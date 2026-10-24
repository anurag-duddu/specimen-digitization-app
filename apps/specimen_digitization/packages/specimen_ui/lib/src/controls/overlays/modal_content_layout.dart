/// Shared content budgeting for the dialog and sheet chrome.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

/// Keeps headings readable and reserves room for both content and actions.
///
/// Ordinary content scrolls together with its heading. A caller-owned scroll
/// view keeps its own bounded viewport; only an oversized heading or footer
/// needs an independent scroll region.
class ModalContentLayout extends StatelessWidget {
  /// Arranges the semantic heading, caller content and optional actions.
  const ModalContentLayout({
    super.key,
    required this.heading,
    required this.body,
    required this.gap,
    required this.scrollBody,
    this.actions,
  });

  /// The complete, wrapping heading.
  final Widget heading;

  /// Ordinary content or a caller-owned scroll view.
  final Widget body;

  /// Persistent actions, scrollable when their complete height does not fit.
  final Widget? actions;

  /// Token spacing between the content regions.
  final double gap;

  /// Whether heading and body share a scroll view.
  final bool scrollBody;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      // Match the rich modal panel: an unusually large footer cannot consume
      // the whole window and make its title or form unreachable.
      final gaps = (scrollBody ? 0 : gap) + (actions == null ? 0 : gap);
      final chromeLimit = math.max(0.0, constraints.maxHeight - gaps) * .4;
      Widget boundedChrome(Widget child) => ConstrainedBox(
        constraints: BoxConstraints(maxHeight: chromeLimit),
        child: SingleChildScrollView(child: child),
      );
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (scrollBody)
            Flexible(
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    heading,
                    SizedBox(height: gap),
                    body,
                  ],
                ),
              ),
            )
          else ...[
            boundedChrome(heading),
            SizedBox(height: gap),
            Flexible(child: body),
          ],
          if (actions != null) ...[
            SizedBox(height: gap),
            boundedChrome(actions!),
          ],
        ],
      );
    },
  );
}
