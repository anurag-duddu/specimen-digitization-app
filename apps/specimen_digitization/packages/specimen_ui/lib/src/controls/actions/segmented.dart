/// The segmented control (10 section 4.1, `UiSegmented`; 11 section 3.3).
library;

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/fit.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';
import '../inputs/select.dart';
import '../overlays/tooltip.dart';
import 'button.dart';

/// One segment of a segmented control.
@immutable
class UiSegment<T> {
  /// Binds [value] to the word the reviewer reads.
  const UiSegment({
    required this.value,
    required this.label,
    this.icon,
    this.semanticsLabel,
  });

  /// What [UiSegmented.onChanged] reports when this segment is chosen.
  final T value;

  /// The visible label. Sentence case, one or two words.
  final String label;

  /// An optional glyph for this segment.
  ///
  /// The icon only variant of 11 section 3.3 is available only when every
  /// segment carries one: a track that drew glyphs for some segments and
  /// words for the rest would be two controls in one row.
  final IconSpec? icon;

  /// Overrides the label a screen reader reads, where the visible one does
  /// not stand alone out of context (02 section 4.16).
  final String? semanticsLabel;

  /// What a screen reader announces.
  String get spokenLabel => semanticsLabel ?? label;
}

/// The resolved paint of one segmented control.
@immutable
class UiSegmentedStyle {
  /// Binds every token a segmented control draws with.
  const UiSegmentedStyle({
    required this.track,
    required this.trackSide,
    required this.thumb,
    required this.selectedLabel,
    required this.label,
    required this.labelStyle,
    required this.overlay,
    required this.trackHeight,
    required this.outerHeight,
    required this.inset,
    required this.segmentPadding,
    required this.minSegmentWidth,
    required this.glyphSize,
  });

  /// The track's fill, by state.
  final WidgetStateProperty<Color> track;

  /// The track's edge, by state.
  final WidgetStateProperty<BorderSide> trackSide;

  /// The gliding thumb's fill, by state.
  final WidgetStateProperty<Color> thumb;

  /// The label colour on the thumb.
  final WidgetStateProperty<Color> selectedLabel;

  /// The label colour off the thumb.
  final WidgetStateProperty<Color> label;

  /// What the state layer lifts a segment toward.
  ///
  /// The chosen segment sits on the `ink` thumb, so its layer lifts toward
  /// `paper`; the others sit on the `paper` track and lift toward `ink`.
  /// Without the split, hovering the chosen segment shows nothing at all.
  final WidgetStateProperty<Color> overlay;

  /// The label's type role. `label` at every size, which is why the height
  /// below derives from that role rather than from the button's.
  final TextStyle labelStyle;

  /// The track's visual height, grown with the text (11 section 2.2).
  final double trackHeight;

  /// The row's height, which is the hit box when the track is shorter.
  final double outerHeight;

  /// How far the thumb sits inside the track.
  final double inset;

  /// The padding inside one segment.
  final EdgeInsetsGeometry segmentPadding;

  /// The narrowest a segment may be, so every one clears the hit box.
  final double minSegmentWidth;

  /// The glyph an icon only segment draws, at `inline`.
  final double glyphSize;

  /// The style for [size] in [ui], at [textScaler].
  static UiSegmentedStyle resolve(
    UiThemeData ui,
    UiSize size, {
    TextScaler textScaler = TextScaler.noScaling,
  }) {
    Color trackFill(Set<WidgetState> states) =>
        states.contains(WidgetState.disabled)
        ? ui.color.disabledFill
        : ui.color.paper;

    BorderSide edge(Set<WidgetState> states) => BorderSide(
      color: states.contains(WidgetState.disabled)
          ? ui.color.disabledOutline
          : ui.color.hairline,
      width: states.contains(WidgetState.disabled)
          ? ui.shape.stroke.boundary
          : ui.shape.stroke.hairline,
    );

    Color thumbFill(Set<WidgetState> states) =>
        states.contains(WidgetState.disabled)
        ? ui.color.disabledContent
        : ui.color.ink;

    final double trackHeight = UiType.heightAroundAt(
      UiButtonStyle.restingHeightOf(ui, size),
      ui.type.label,
      textScaler,
    );
    return UiSegmentedStyle(
      track: WidgetStateProperty.resolveWith(trackFill),
      trackSide: WidgetStateProperty.resolveWith(edge),
      thumb: WidgetStateProperty.resolveWith(thumbFill),
      // `paper` on the thumb in both modes, the same inversion the primary
      // button makes and for the same reason: the thumb is `ink`, so its
      // label has to be the other end of the pair.
      selectedLabel: WidgetStateProperty.all<Color>(ui.color.paper),
      label: WidgetStateProperty.resolveWith(
        (Set<WidgetState> states) => states.contains(WidgetState.disabled)
            ? ui.color.disabledContent
            : ui.color.ink,
      ),
      overlay: WidgetStateProperty.resolveWith(
        (Set<WidgetState> states) => states.contains(WidgetState.selected)
            ? ui.color.paper
            : ui.color.ink,
      ),
      labelStyle: ui.type.label,
      trackHeight: trackHeight,
      outerHeight: math.max(trackHeight, UiDensity.hitBox),
      inset: ui.space.s1,
      segmentPadding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s3),
      minSegmentWidth: UiDensity.hitBox,
      glyphSize: ui.space.iconInline,
    );
  }
}

/// One capsule track with 2 to 5 equal segments and a thumb that glides.
///
/// Retires `SegmentedButton`.
///
/// Arrow keys move focus and `Enter` selects, which is the WAI-ARIA manual
/// activation pattern: a reviewer arrowing past a segment does not switch the
/// pane under them on the way through.
///
/// **Fit** (11 section 3.3). Its intrinsic width is the number of segments
/// times the widest label plus a segment's padding, plus the track's insets;
/// every segment is drawn at that one width, so the thumb travels an even
/// step. Given less, in order: icon only segments with a tooltip each, when
/// every segment carries a glyph; a [UiSelect] over the same options, when
/// the track has been given a [label] to offer them under; and, when neither
/// exists, the segments themselves with their labels ellipsised and the whole
/// word on a tooltip.
class UiSegmented<T> extends StatefulWidget {
  /// A track of [segments] with [value] chosen.
  const UiSegmented({
    super.key,
    required this.segments,
    required this.value,
    required this.onChanged,
    this.label,
    this.size = UiSize.md,
    this.disabledReason,
  });

  /// The fewest segments a track may carry.
  static const int minSegments = 2;

  /// The most segments a track may carry.
  static const int maxSegments = 5;

  /// The segments, in the order they are drawn.
  final List<UiSegment<T>> segments;

  /// Which segment is chosen.
  final T value;

  /// Reports the newly chosen value. Null disables the control.
  final ValueChanged<T>? onChanged;

  /// What the track chooses: "Pane", "Sort order".
  ///
  /// The name the [UiSelect] variant offers the options under, and the only
  /// thing that variant needs that a track does not. A track without one
  /// keeps its segments at every width and ellipsises them, which is what a
  /// tab strip wants: `UiTabs` publishes `SemanticsRole.tabBar` with
  /// `explicitChildNodes`, and a select under that node is a child of a tab
  /// bar that is not a tab, which the SDK's own check fails rather than
  /// degrades.
  final String? label;

  /// The size the track is drawn at.
  final UiSize size;

  /// Why the control is disabled, in the reviewer's words.
  final String? disabledReason;

  @override
  State<UiSegmented<T>> createState() => _UiSegmentedState<T>();
}

class _UiSegmentedState<T> extends State<UiSegmented<T>> {
  List<FocusNode> _nodes = <FocusNode>[];

  @override
  void initState() {
    super.initState();
    _syncNodes();
  }

  @override
  void didUpdateWidget(UiSegmented<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.segments.length != widget.segments.length) _syncNodes();
  }

  @override
  void dispose() {
    for (final FocusNode node in _nodes) {
      node.dispose();
    }
    super.dispose();
  }

  void _syncNodes() {
    for (final FocusNode node in _nodes) {
      node.dispose();
    }
    _nodes = List<FocusNode>.generate(
      widget.segments.length,
      (int index) => FocusNode(debugLabel: widget.segments[index].label),
      growable: false,
    );
  }

  int get _chosen {
    final int index = widget.segments.indexWhere(
      (UiSegment<T> segment) => segment.value == widget.value,
    );
    // A value no segment carries is a caller defect rather than a state to
    // draw: falling back to the first keeps the thumb somewhere real.
    return index < 0 ? 0 : index;
  }

  void _move(int step) {
    if (_nodes.isEmpty) return;
    final int from = _nodes.indexWhere((FocusNode node) => node.hasFocus);
    final int to = (from < 0 ? _chosen : from + step).clamp(
      0,
      _nodes.length - 1,
    );
    _nodes[to].requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    // Checked here rather than in the constructor, because a constructor
    // assert that reads `length` cannot be evaluated at compile time and
    // would make every `const UiSegmented(...)` a compile error.
    assert(
      widget.segments.length >= UiSegmented.minSegments &&
          widget.segments.length <= UiSegmented.maxSegments,
      'a segmented control carries 2 to 5 segments (10 section 4.1). Fewer is '
      'a toggle and more is a select.',
    );
    final UiThemeData ui = context.ui;
    final UiSegmentedStyle style = UiSegmentedStyle.resolve(
      ui,
      widget.size,
      textScaler: MediaQuery.textScalerOf(context),
    );
    final int count = widget.segments.length;
    // Every segment is drawn at the widest label's width, so the segments are
    // equal and the thumb's step is even. Measured rather than estimated, so
    // the declared width is the width the track actually needs at the
    // reviewer's text size.
    final double widest = widget.segments.fold<double>(
      0,
      (double so, UiSegment<T> segment) => math.max(
        so,
        measureLabel(context, segment.label, style.labelStyle).width,
      ),
    );
    final double labelled = math.max(
      style.minSegmentWidth,
      widest + style.segmentPadding.horizontal,
    );
    final double glyphs = math.max(
      style.minSegmentWidth,
      style.glyphSize + style.segmentPadding.horizontal,
    );
    double trackWidth(double segment) => count * segment + 2 * style.inset;
    final bool everySegmentHasGlyph = widget.segments.every(
      (UiSegment<T> segment) => segment.icon != null,
    );

    return FitBuilder(
      variants: <FitVariant>[
        FitVariant(
          intrinsicWidth: trackWidth(labelled),
          builder: (BuildContext context, bool _) =>
              _buildTrack(style, trackWidth(labelled), glyphsOnly: false),
        ),
        if (everySegmentHasGlyph && glyphs < labelled)
          FitVariant(
            intrinsicWidth: trackWidth(glyphs),
            builder: (BuildContext context, bool _) =>
                _buildTrack(style, trackWidth(glyphs), glyphsOnly: true),
          ),
        if (widget.label != null)
          // A select stretches to whatever it is given and ellipsises the
          // option it shows, so the hit box is the whole of what it needs.
          FitVariant(
            intrinsicWidth: UiDensity.hitBox,
            builder: (BuildContext context, bool _) => _buildSelect(),
          ),
      ],
    );
  }

  /// The same options in the same order, under the same name.
  ///
  /// The value and the callback are the track's own, so collapsing the track
  /// changes the form the reviewer is offered and nothing else: no selection
  /// moves, nothing is reported, and what a screen reader meets is a control
  /// of a different kind carrying the same word and the same chosen option.
  Widget _buildSelect() {
    final String label = widget.label!;
    return UiSelect<T>(
      label: label,
      // The track never drew the name, and the surface around it is what
      // named the choice; drawing one now would be the collapse adding a word
      // to the screen rather than changing a shape on it.
      showLabel: false,
      // Never seen: a track always has a chosen segment, so the trigger
      // always has an option to draw. It names the choice for the case where
      // a caller hands the control a value no segment carries.
      placeholder: label,
      options: <UiSelectOption<T>>[
        for (final UiSegment<T> segment in widget.segments)
          UiSelectOption<T>(
            value: segment.value,
            label: segment.label,
            leading: segment.icon,
          ),
      ],
      value: widget.value,
      onChanged: widget.onChanged,
      disabledReason: widget.disabledReason,
    );
  }

  /// The track itself, at [width], drawn with glyphs or with words.
  Widget _buildTrack(
    UiSegmentedStyle style,
    double width, {
    required bool glyphsOnly,
  }) {
    final UiThemeData ui = context.ui;
    final bool enabled = widget.onChanged != null;
    final Set<WidgetState> states = <WidgetState>{
      if (!enabled) WidgetState.disabled,
    };
    final bool rtl = Directionality.of(context) == TextDirection.rtl;
    final int count = widget.segments.length;
    final int chosen = _chosen;
    return FocusTraversalGroup(
      policy: WidgetOrderTraversalPolicy(),
      child: Shortcuts(
        shortcuts: _shortcuts,
        // The track is not a thing to focus; its segments are. Left on, the
        // default publishes a `focusable` node between the control and its
        // segments, which is one stop a screen reader does not need and, for
        // `UiTabs`, a child of `SemanticsRole.tabBar` that is not a tab: the
        // SDK's own check fails rather than degrading.
        includeSemantics: false,
        child: Actions(
          actions: <Type, Action<Intent>>{
            _MoveSegmentIntent: CallbackAction<_MoveSegmentIntent>(
              onInvoke: (_MoveSegmentIntent intent) {
                _move(intent.horizontal && rtl ? -intent.step : intent.step);
                return null;
              },
            ),
          },
          // The width the variant declared. A caller that binds the track
          // tightly keeps its own width, because a tight constraint wins over
          // this one; a caller with less room than this clamps it down, which
          // is the last resort the labels then ellipsise into.
          child: SizedBox(
            width: width,
            height: style.outerHeight,
            child: Stack(
              alignment: Alignment.center,
              children: <Widget>[
                Positioned.fill(
                  child: Center(
                    child: SizedBox(
                      width: double.infinity,
                      height: style.trackHeight,
                      child: DecoratedBox(
                        decoration: ShapeDecoration(
                          shape: StadiumBorder(
                            side: style.trackSide.resolve(states),
                          ),
                          color: style.track.resolve(states),
                        ),
                        child: Padding(
                          padding: EdgeInsetsDirectional.all(style.inset),
                          child: _Thumb(
                            colour: style.thumb.resolve(states),
                            count: count,
                            index: chosen,
                            motion: ui.motion,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                // The same inset the thumb sits at, so a label's centre and
                // the thumb's centre are the same point in every segment.
                // Without it the thumb, which is inset, and the segment,
                // which is not, disagree by the inset at both ends.
                Padding(
                  padding: EdgeInsetsDirectional.symmetric(
                    horizontal: style.inset,
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: <Widget>[
                      for (int i = 0; i < count; i++)
                        Expanded(
                          child: _Segment<T>(
                            segment: widget.segments[i],
                            style: style,
                            focusNode: _nodes[i],
                            selected: i == chosen,
                            glyphOnly: glyphsOnly,
                            disabledReason: widget.disabledReason,
                            onPressed: enabled
                                ? () => widget.onChanged!(
                                    widget.segments[i].value,
                                  )
                                : null,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Arrow keys move within the track.
  static const Map<ShortcutActivator, Intent> _shortcuts =
      <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.arrowRight): _MoveSegmentIntent(1),
        SingleActivator(LogicalKeyboardKey.arrowLeft): _MoveSegmentIntent(-1),
        SingleActivator(LogicalKeyboardKey.arrowDown): _MoveSegmentIntent(
          1,
          horizontal: false,
        ),
        SingleActivator(LogicalKeyboardKey.arrowUp): _MoveSegmentIntent(
          -1,
          horizontal: false,
        ),
      };
}

/// Move focus one segment along.
class _MoveSegmentIntent extends Intent {
  const _MoveSegmentIntent(this.step, {this.horizontal = true});

  final int step;
  final bool horizontal;
}

/// The ink capsule that slides behind the labels.
///
/// Signature motion 1 (09 section 8): `medium`, the emphasized curve. Under
/// reduced motion the duration is zero, so the thumb appears at the new
/// segment rather than travelling to it.
class _Thumb extends StatelessWidget {
  const _Thumb({
    required this.colour,
    required this.count,
    required this.index,
    required this.motion,
  });

  final Color colour;
  final int count;
  final int index;
  final MotionTokens motion;

  @override
  Widget build(BuildContext context) => AnimatedAlign(
    // Directional, so the thumb starts at the reading start in both
    // directions rather than always on the left.
    alignment: AlignmentDirectional(
      count <= 1 ? 0 : (2 * index / (count - 1)) - 1,
      0,
    ),
    duration: motion.navigationGlide,
    curve: MotionTokens.emphasizedCurve,
    child: FractionallySizedBox(
      widthFactor: 1 / count,
      heightFactor: 1,
      child: DecoratedBox(
        decoration: ShapeDecoration(
          shape: const StadiumBorder(),
          color: colour,
        ),
      ),
    ),
  );
}

/// One label and its target.
class _Segment<T> extends StatelessWidget {
  const _Segment({
    required this.segment,
    required this.style,
    required this.focusNode,
    required this.selected,
    required this.glyphOnly,
    required this.onPressed,
    required this.disabledReason,
  });

  final UiSegment<T> segment;
  final UiSegmentedStyle style;
  final FocusNode focusNode;
  final bool selected;
  final bool glyphOnly;
  final VoidCallback? onPressed;
  final String? disabledReason;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Widget target = Pressable(
      semanticsLabel: segment.spokenLabel,
      onPressed: onPressed,
      disabledReason: disabledReason,
      role: PressableRole.tab,
      selected: selected,
      capsule: true,
      focusNode: focusNode,
      stateLayerColour: style.overlay.resolve(<WidgetState>{
        if (selected) WidgetState.selected,
      }),
      // The track already spends the difference between the visual height and
      // the 48 dp target, so the segment fills the row it is given rather
      // than padding itself out of the track.
      minHitBox: 0,
      builder: (BuildContext context, Set<WidgetState> states) {
        final Color colour = selected
            ? style.selectedLabel.resolve(states)
            : style.label.resolve(states);
        return AnimatedDefaultTextStyle(
          duration: ui.motion.navigationGlide,
          curve: MotionTokens.emphasizedCurve,
          style: style.labelStyle.copyWith(color: colour),
          child: ConstrainedBox(
            constraints: BoxConstraints(minWidth: style.minSegmentWidth),
            child: Padding(
              padding: style.segmentPadding,
              child: Center(
                child: glyphOnly
                    ? UiIcon(
                        segment.icon!,
                        size: UiIconSize.inline,
                        color: colour,
                      )
                    : UiLabel(
                        segment.label,
                        textAlign: TextAlign.center,
                        // Per segment rather than per track: only the word
                        // that actually ran out of room carries a pane, and a
                        // tooltip that repeats a label already on screen is
                        // noise under the pointer (11 section 3.3, rule 4).
                        tooltip:
                            (
                              BuildContext context,
                              String message,
                              Widget label,
                            ) => UiTooltip(message: message, child: label),
                      ),
              ),
            ),
          ),
        );
      },
    );
    // Outside the `Pressable`, so a tap reaches the segment underneath rather
    // than the pane above it. A glyph on its own says nothing, so the word it
    // stands for is always one hover or one long press away.
    return glyphOnly
        ? UiTooltip(message: segment.label, child: target)
        : target;
  }
}
