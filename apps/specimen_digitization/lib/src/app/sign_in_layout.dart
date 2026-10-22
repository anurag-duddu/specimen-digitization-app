/// The task surface for sign-in, email return and collection access.
///
/// The product masthead is separate from the current task. A wider window
/// frames that task on paper; a compact window leaves it on the page. Both
/// use one scroll and the same element tree, so resizing does not replace a
/// focused field. See design/13 section 7 for the login composition amendment.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../widgets/adaptive_form.dart';

/// A responsive, single-task layout for the complete sign-in journey.
///
/// Callers own authentication state, field focus and action availability.
/// [children] and [footer] must not introduce another vertical scroll. Keep
/// identity summaries as rows rather than nesting another card in this stage.
class SignInLayout extends StatelessWidget {
  const SignInLayout({
    super.key,
    required this.title,
    this.purpose,
    this.icon,
    required this.children,
    this.footer,
    this.onBack,
    this.busy = false,
  });

  /// The current task, announced when it changes.
  final String title;

  /// One short instruction. Supporting help belongs in [footer].
  final String? purpose;

  /// A recognizable state symbol, supported by the visible [title].
  final IconSpec? icon;

  /// The field, identity summary and actions for the current task.
  final List<Widget> children;

  /// Contextual help below the task, in the same scroll order.
  final Widget? footer;

  /// Returns from the current task. Omit when there is nowhere to return to.
  final VoidCallback? onBack;

  /// Replaces the state symbol with progress and disables the back control.
  ///
  /// The caller must also disable its own conflicting actions. The existing
  /// progress primitive respects reduced motion without changing this layout.
  final bool busy;

  /// One-field task width, reused from the product's existing form measure.
  static const double stageWidth = DialogWidths.standard;

  /// The product and institution, each named once in the masthead.
  static const String productName = 'Specimen Digitization';
  static const String institutionName = 'Field Museum';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SafeArea(
      child: LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final bool compact = WindowClass.fromWidth(
            constraints.maxWidth,
          ).isCompact;
          final double gutter = compact ? ui.space.s4 : ui.space.s6;
          final double stageInset = compact ? ui.space.s0 : ui.space.s8;
          return FocusTraversalGroup(
            policy: ReadingOrderTraversalPolicy(),
            child: CustomScrollView(
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              slivers: <Widget>[
                SliverPadding(
                  padding: EdgeInsetsDirectional.fromSTEB(
                    gutter,
                    compact ? ui.space.s6 : ui.space.s10,
                    gutter,
                    gutter + MediaQuery.viewInsetsOf(context).bottom,
                  ),
                  sliver: SliverToBoxAdapter(
                    child: Align(
                      alignment: AlignmentDirectional.topCenter,
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: stageWidth),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          mainAxisSize: MainAxisSize.min,
                          children: <Widget>[
                            _masthead(ui),
                            SizedBox(height: ui.space.s8),
                            // Keep this wrapper at both widths so changing
                            // the frame does not remount fields or their focus.
                            // At compact it paints the page with no edge or
                            // inset; there is no nested visual card.
                            Surface(
                              key: const ValueKey<String>('sign-in-stage'),
                              role: compact
                                  ? SurfaceRole.ground
                                  : SurfaceRole.paper,
                              radius: compact ? ui.shape.none : ui.shape.tile,
                              hairline: !compact,
                              padding: EdgeInsets.all(stageInset),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                mainAxisSize: MainAxisSize.min,
                                children: <Widget>[
                                  if (onBack != null) ...<Widget>[
                                    Align(
                                      alignment:
                                          AlignmentDirectional.centerStart,
                                      child: UiButton(
                                        label: 'Back',
                                        semanticsLabel: 'Back to sign-in',
                                        leading: UiIcons.back,
                                        variant: UiButtonVariant.ghost,
                                        onPressed: busy ? null : onBack,
                                        disabledReason: busy
                                            ? 'Wait for sign-in to finish.'
                                            : null,
                                      ),
                                    ),
                                    SizedBox(height: ui.space.s4),
                                  ],
                                  if (icon != null || busy) ...<Widget>[
                                    Align(
                                      alignment:
                                          AlignmentDirectional.centerStart,
                                      child: ExcludeSemantics(
                                        child: busy
                                            ? UiProgress.ring(
                                                semanticsLabel: title,
                                                size: UiProgressSize.large,
                                              )
                                            : UiIcon(
                                                icon!,
                                                size: UiIconSize.display,
                                                color: ui.color.ink,
                                              ),
                                      ),
                                    ),
                                    SizedBox(height: ui.space.s4),
                                  ],
                                  Semantics(
                                    header: true,
                                    liveRegion: true,
                                    child: Text(
                                      title,
                                      key: const ValueKey<String>(
                                        'sign-in-stage-title',
                                      ),
                                      style: ui.type.headline.copyWith(
                                        color: ui.color.ink,
                                      ),
                                    ),
                                  ),
                                  if (purpose != null) ...<Widget>[
                                    SizedBox(height: ui.space.s2),
                                    Text(
                                      purpose!,
                                      style: ui.type.body.copyWith(
                                        color: ui.color.inkSecondary,
                                      ),
                                    ),
                                  ],
                                  if (children.isNotEmpty) ...<Widget>[
                                    SizedBox(height: ui.space.s6),
                                    ...children,
                                  ],
                                ],
                              ),
                            ),
                            if (footer != null) ...<Widget>[
                              SizedBox(height: ui.space.s4),
                              Padding(
                                padding: EdgeInsetsDirectional.symmetric(
                                  horizontal: stageInset,
                                ),
                                child: footer!,
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _masthead(UiThemeData ui) => Row(
    crossAxisAlignment: CrossAxisAlignment.center,
    children: <Widget>[
      const ExcludeSemantics(child: UiMark.mono(label: productName)),
      SizedBox(width: ui.space.s3),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              productName,
              style: ui.type.title.copyWith(color: ui.color.ink),
            ),
            SizedBox(height: ui.space.s1),
            Text(
              institutionName,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          ],
        ),
      ),
    ],
  );
}
