/// The disclosure (10 section 4.3, `UiDisclosure`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';

/// The resolved paint of one disclosure.
@immutable
class UiDisclosureStyle {
  /// Binds every token a disclosure draws with.
  const UiDisclosureStyle({
    required this.title,
    required this.summary,
    required this.titleColor,
    required this.summaryColor,
    required this.caretColor,
    required this.padding,
    required this.bodyPadding,
    required this.gap,
    required this.minHeight,
    required this.radius,
  });

  /// The title's type role.
  final TextStyle title;

  /// The summary's type role.
  final TextStyle summary;

  /// The title's colour.
  final Color titleColor;

  /// The summary's colour.
  final Color summaryColor;

  /// The caret's colour.
  final Color caretColor;

  /// Padding inside the header row.
  final EdgeInsetsGeometry padding;

  /// Padding around the body.
  final EdgeInsetsGeometry bodyPadding;

  /// The gap between the text column and the caret.
  final double gap;

  /// The header row's visual height, from density.
  ///
  /// The hit box is the 48 dp of clause 2 in both densities, applied by
  /// `Pressable`; in pointer density the difference is transparent slop
  /// around this.
  final double minHeight;

  /// The header row's corner radius, for its state layer and focus ring.
  final double radius;

  /// The style a disclosure draws with in [ui].
  static UiDisclosureStyle resolve(UiThemeData ui) => UiDisclosureStyle(
    title: ui.type.title,
    summary: ui.type.bodySmall,
    titleColor: ui.color.ink,
    summaryColor: ui.color.inkSecondary,
    caretColor: ui.color.inkSecondary,
    padding: EdgeInsetsDirectional.symmetric(
      horizontal: ui.space.s3,
      vertical: ui.space.s2,
    ),
    bodyPadding: EdgeInsetsDirectional.fromSTEB(
      ui.space.s3,
      0,
      ui.space.s3,
      ui.space.s3,
    ),
    gap: ui.space.s3,
    minHeight: ui.density.rowHeight,
    radius: ui.shape.inner,
  );

  /// Half a turn. The caret points down when closed and up when open, and the
  /// glyph is the same one either way so the two states are one object moving
  /// rather than two glyphs swapping (09 section 8).
  static const double caretTurns = 0.5;

  /// The most lines the summary takes before it ellipsises.
  ///
  /// Two, the same as a list row's subtitle: the summary is the row's second
  /// line and is content rather than a label (11 section 3.3).
  static const int summaryMaxLines = 2;
}

/// A row that reveals a body.
///
/// Retires `ExpansionTile`, and with it the Material chevron row 09 section 11
/// rejects by name. The body is never glass: a disclosure is content inside a
/// pane, not a pane of its own (09 section 3.3).
class UiDisclosure extends StatefulWidget {
  /// A disclosure titled [title] that reveals [child].
  const UiDisclosure({
    super.key,
    required this.title,
    required this.child,
    this.summary,
    this.initiallyExpanded = false,
    this.onExpansionChanged,
    this.semanticsLabel,
    this.style,
  });

  /// The row's title. A noun phrase, no period (02 section 4.2).
  final String title;

  /// What the row reveals.
  final Widget child;

  /// A second line under the title, saying what is behind the row.
  final String? summary;

  /// True to build the disclosure open.
  final bool initiallyExpanded;

  /// Called with the new state whenever the reviewer toggles the row.
  final ValueChanged<bool>? onExpansionChanged;

  /// Overrides the label a screen reader reads. Defaults to [title], or to
  /// the title and the summary as one phrase where there is a summary.
  final String? semanticsLabel;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiDisclosureStyle? style;

  @override
  State<UiDisclosure> createState() => _UiDisclosureState();
}

class _UiDisclosureState extends State<UiDisclosure> {
  late bool _open = widget.initiallyExpanded;

  void _toggle() {
    setState(() => _open = !_open);
    widget.onExpansionChanged?.call(_open);
  }

  String get _label {
    final String? given = widget.semanticsLabel;
    if (given != null) return given;
    final String? summary = widget.summary;
    return summary == null ? widget.title : '${widget.title}. $summary';
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiDisclosureStyle style =
        widget.style ?? UiDisclosureStyle.resolve(ui);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        // The header publishes its own node so that it carries `expanded`,
        // which `Pressable` has no enum member for. The body keeps its own
        // semantics, which is why only the header is wrapped.
        Semantics(
          container: true,
          excludeSemantics: true,
          button: true,
          label: _label,
          expanded: _open,
          onTap: _toggle,
          child: Pressable(
            semanticsLabel: _label,
            onPressed: _toggle,
            radius: style.radius,
            // The primitive's own 48 dp floor, not the density row. A header
            // whose title fits one line is `density.rowHeight` tall, which is
            // 44 in pointer, and clause 2 sets 48 in both densities; the
            // header used to publish the 44 and fail every tap target
            // guideline a screen with a disclosure on it ran. The visual row
            // keeps its density height and the difference is transparent
            // slop inside the control's own box, so a column of disclosures
            // still tiles without gaps.
            excludeFromSemantics: true,
            builder: (BuildContext context, Set<WidgetState> states) =>
                ConstrainedBox(
                  constraints: BoxConstraints(minHeight: style.minHeight),
                  child: Padding(
                    padding: style.padding,
                    child: Row(
                      children: <Widget>[
                        Expanded(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              UiLabel(
                                widget.title,
                                style: style.title.copyWith(
                                  color: style.titleColor,
                                ),
                              ),
                              // The summary is content, not a label: it is
                              // the row's second line, the same object a
                              // list row's subtitle is, so it wraps to two
                              // lines before it is cut (11 section 3.3).
                              if (widget.summary != null)
                                Text(
                                  widget.summary!,
                                  style: style.summary.copyWith(
                                    color: style.summaryColor,
                                  ),
                                  maxLines: UiDisclosureStyle.summaryMaxLines,
                                  overflow: TextOverflow.ellipsis,
                                ),
                            ],
                          ),
                        ),
                        SizedBox(width: style.gap),
                        AnimatedRotation(
                          turns: _open ? UiDisclosureStyle.caretTurns : 0,
                          duration: ui.motion.short,
                          curve: MotionTokens.standardCurve,
                          child: UiIcon(
                            UiIcons.expand,
                            size: UiIconSize.inline,
                            color: style.caretColor,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
          ),
        ),
        // Under reduced motion the body appears at its full height with no
        // size animation, which is what 04 section 2.5 collapses an expand
        // to. `AnimatedSize` is left out of the tree rather than given a zero
        // duration: a zero duration makes its controller notify inside its own
        // `performLayout`, and the framework asserts on a render object that
        // re-dirties itself while being laid out.
        if (ui.motion.reduced)
          _open
              ? Padding(padding: style.bodyPadding, child: widget.child)
              : const SizedBox(width: double.infinity)
        else
          AnimatedSize(
            alignment: AlignmentDirectional.topStart,
            duration: ui.motion.standard,
            curve: MotionTokens.standardCurve,
            child: _open
                ? Padding(padding: style.bodyPadding, child: widget.child)
                : const SizedBox(width: double.infinity),
          ),
      ],
    );
  }
}
