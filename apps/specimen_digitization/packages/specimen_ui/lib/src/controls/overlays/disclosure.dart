/// The disclosure (10 section 4.3, `UiDisclosure`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/fit.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';
import '../actions/chip.dart';

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
    this.trailing,
    this.hideSummaryWhenExpanded = false,
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

  /// A chip that qualifies the row: at the end of the header, before the
  /// caret, while the title fits beside it, and on a line of its own under the
  /// title and summary when it does not (11 section 3.3).
  ///
  /// A chip and never a control: it sits inside the header's press target, so
  /// a press on it toggles the row, and its own semantics are excluded with
  /// the rest of the header's. What it says must therefore be in
  /// [semanticsLabel] as well. It is a [UiChip] rather than any widget
  /// because the header measures it, through [UiChip.intrinsicWidthIn], to
  /// decide where it goes.
  final UiChip? trailing;

  /// Hides the summary from the header and its default semantics while open.
  ///
  /// Use when the body exposes the same information as the collapsed preview.
  final bool hideSummaryWhenExpanded;

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

  String? get _visibleSummary =>
      _open && widget.hideSummaryWhenExpanded ? null : widget.summary;

  void _toggle() {
    setState(() => _open = !_open);
    widget.onExpansionChanged?.call(_open);
  }

  String get _label {
    final String? given = widget.semanticsLabel;
    if (given != null) return given;
    final String? summary = _visibleSummary;
    return summary == null ? widget.title : '${widget.title}. $summary';
  }

  /// The title over its summary, which takes whatever the line has left, and
  /// [under] beneath both where the header has moved its trailing there.
  Widget _text(UiDisclosureStyle style, TextStyle title, {Widget? under}) =>
      Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          UiLabel(widget.title, style: title),
          // The summary is content, not a label: it is the row's second line,
          // the same object a list row's subtitle is, so it wraps to two
          // lines before it is cut (11 section 3.3).
          if (_visibleSummary != null)
            Text(
              _visibleSummary!,
              style: style.summary.copyWith(color: style.summaryColor),
              maxLines: UiDisclosureStyle.summaryMaxLines,
              overflow: TextOverflow.ellipsis,
            ),
          ?under,
        ],
      );

  /// True when the summary would run past its last line in [width].
  ///
  /// The summary is content and wraps, but only to
  /// [UiDisclosureStyle.summaryMaxLines]: a chip
  /// that took the width the summary needed would cut its last words off
  /// ("Required"), and the cut words are the review state.
  bool _summaryCut(
    BuildContext context,
    UiDisclosureStyle style,
    double width,
  ) {
    final String? summary = _visibleSummary;
    if (summary == null) return false;
    final TextPainter painter = TextPainter(
      text: TextSpan(
        text: summary,
        style: DefaultTextStyle.of(context).style.merge(style.summary),
      ),
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
      maxLines: UiDisclosureStyle.summaryMaxLines,
    )..layout(maxWidth: width);
    final bool cut = painter.didExceedMaxLines;
    painter.dispose();
    return cut;
  }

  /// The header's line: text, the optional trailing, and the caret.
  ///
  /// The trailing keeps the line while the whole of the title and the whole
  /// of the summary still fit beside it. A title is a label, which never
  /// wraps and never loses a word to a neighbour (11 section 3.3, rules 1 and
  /// 2), and a summary is content that wraps to two lines before it is cut,
  /// so when either would not fit beside the chip the chip moves under the
  /// text, at the start of its own line, rather than squeezing the words into
  /// an ellipsis.
  Widget _headerRow(UiThemeData ui, UiDisclosureStyle style) {
    final Widget caret = AnimatedRotation(
      turns: _open ? UiDisclosureStyle.caretTurns : 0,
      duration: ui.motion.short,
      curve: MotionTokens.standardCurve,
      child: UiIcon(
        UiIcons.expand,
        size: UiIconSize.inline,
        color: style.caretColor,
      ),
    );
    final TextStyle title = style.title.copyWith(color: style.titleColor);
    final UiChip? trailing = widget.trailing;
    if (trailing == null) {
      return Row(
        children: <Widget>[
          Expanded(child: _text(style, title)),
          SizedBox(width: style.gap),
          caret,
        ],
      );
    }
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints box) {
        final double titleWidth = measureLabel(
          context,
          widget.title,
          DefaultTextStyle.of(context).style.merge(title),
        ).width;
        // What the line owes to everything but the text: the gap before the
        // chip, the chip, the gap before the caret and the caret.
        final double beside =
            style.gap +
            trailing.intrinsicWidthIn(context) +
            style.gap +
            UiIconSize.inline.dimension;
        final double room = box.maxWidth - beside;
        if (titleWidth <= room && !_summaryCut(context, style, room)) {
          return Row(
            children: <Widget>[
              Expanded(child: _text(style, title)),
              SizedBox(width: style.gap),
              trailing,
              SizedBox(width: style.gap),
              caret,
            ],
          );
        }
        return Row(
          children: <Widget>[
            Expanded(
              child: _text(
                style,
                title,
                under: Padding(
                  padding: EdgeInsetsDirectional.only(top: ui.space.s1),
                  child: Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: trailing,
                  ),
                ),
              ),
            ),
            SizedBox(width: style.gap),
            caret,
          ],
        );
      },
    );
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
                    child: _headerRow(ui, style),
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
