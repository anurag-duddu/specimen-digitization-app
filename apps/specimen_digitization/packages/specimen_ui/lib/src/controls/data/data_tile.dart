/// The numeral tile (10 section 4.5, `UiDataTile`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/glass.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/fit.dart';
import '../../primitives/glass_surface.dart';
import '../../primitives/label.dart';

/// The resolved paint of one tile.
@immutable
class UiDataTileStyle {
  /// Binds every token a tile draws with.
  const UiDataTileStyle({
    required this.label,
    required this.numeralSteps,
    required this.unit,
    required this.footer,
    required this.padding,
    required this.radius,
    required this.labelGap,
    required this.unitGap,
    required this.footerGap,
    required this.childGap,
    required this.tick,
  });

  /// The label above the numeral.
  final TextStyle label;

  /// The numeral itself: the first, widest role of [numeralSteps].
  TextStyle get numeral => numeralSteps.first;

  /// The display roles the numeral steps down through, widest first
  /// (11 section 3.3).
  ///
  /// A hero tile starts at `display.hero` and a tile starts at
  /// `display.large`; both stop at `display.medium`, which is the smallest
  /// role 09 section 4.2 calls a display. Below that the last resort is a
  /// scale rather than a fourth size, because a numeral set in `headline`
  /// beside a tile set in `display.medium` reads as a different kind of
  /// measurement rather than the same one in less room.
  final List<TextStyle> numeralSteps;

  /// The unit beside the numeral's baseline.
  final TextStyle unit;

  /// The line under the numeral.
  final TextStyle footer;

  /// The padding inside the pane.
  final EdgeInsetsGeometry padding;

  /// The pane's corner radius.
  final double radius;

  /// Between the label and the numeral.
  final double labelGap;

  /// Between the numeral and its unit.
  final double unitGap;

  /// Between the numeral and the footer.
  final double footerGap;

  /// Between the footer and the child slot.
  final double childGap;

  /// How long the numeral takes to change.
  final Duration tick;

  /// The style in [ui]. [hero] takes the one hero role in the window.
  static UiDataTileStyle resolve(UiThemeData ui, {bool hero = false}) =>
      UiDataTileStyle(
        label: ui.type.label.copyWith(color: ui.color.inkSecondary),
        numeralSteps: <TextStyle>[
          if (hero) ui.type.displayHero,
          ui.type.displayLarge,
          ui.type.displayMedium,
        ].map((TextStyle role) => role.copyWith(color: ui.color.ink)).toList(),
        unit: ui.type.unit.copyWith(color: ui.color.inkTertiary),
        footer: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
        padding: EdgeInsetsDirectional.all(ui.density.tilePadding),
        radius: ui.shape.tile,
        labelGap: ui.space.s2,
        unitGap: ui.space.s2,
        footerGap: ui.space.s2,
        childGap: ui.space.s4,
        // Signature motion 3 (09 section 8): `short`, standard. Under
        // reduced motion the slide goes and the cross-fade stays, which is
        // the substitution 04 section 2.5 names for every axis move.
        tick: ui.motion.reduced ? MotionTokens.quickRaw : ui.motion.numeralTick,
      );

  /// The height a tile with a label and a numeral and no footer occupies.
  ///
  /// Derived from the tokens rather than measured, so `UiSkeleton.tile` holds
  /// open exactly the space the tile will take and the layout does not move
  /// when the placeholder becomes the content.
  static double labelAndNumeralHeight(UiThemeData ui) {
    final UiDataTileStyle style = resolve(ui);
    return ui.density.tilePadding * 2 +
        _lineHeight(style.label) +
        style.labelGap +
        _lineHeight(style.numeral);
  }

  static double _lineHeight(TextStyle style) =>
      (style.fontSize ?? 0) * (style.height ?? 1);
}

/// A numeral under its label, on one frosted pane.
///
/// Retires the ad hoc numeral containers the application grew.
///
/// [value] is a string, never a number, because the tile does not decide how
/// a measurement is written. A measurement nobody made is "Not measured" in
/// this slot, never a zero (02 section 4.14; 00, principle 2), and the tile
/// draws whatever it is given at the same size, in the same place.
///
/// The tile's tint never varies with its value (09 section 3.2). Every tile
/// is `glass.flat`, whatever it reports: a record count tile is not redder
/// when the count is higher, because a colour that encodes data anywhere but
/// a status triple is the defect that rule exists to prevent.
///
/// The tile publishes one semantics node reading the label, the value and the
/// unit as a sentence, so a screen reader hears the measurement rather than
/// three fragments. A [child] that carries a value of its own states it in
/// [semanticsLabel], because the child's own node is merged into this one.
class UiDataTile extends StatelessWidget {
  /// A tile reporting [value] under [label].
  const UiDataTile({
    super.key,
    required this.label,
    required this.value,
    this.unit,
    this.footer,
    this.child,
    this.hero = false,
    this.semanticsLabel,
  });

  /// What the numeral measures. Sentence case, no terminal period.
  final String label;

  /// The measurement, already written. Tabular, so its width holds as it
  /// changes.
  final String value;

  /// The unit beside the numeral's baseline, in the one upper case role.
  final String? unit;

  /// One line under the numeral: a comparison, a time, a caveat.
  final String? footer;

  /// A gauge or a trace under the numeral.
  final Widget? child;

  /// True for the window's one hero numeral, which the caller is
  /// responsible for keeping to one (09 section 4.2).
  final bool hero;

  /// Overrides the sentence a screen reader reads.
  final String? semanticsLabel;

  /// The sentence this tile publishes.
  String get _label {
    if (semanticsLabel != null) return semanticsLabel!;
    final String? measure = unit;
    return measure == null ? '$label, $value' : '$label, $value $measure';
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiDataTileStyle style = UiDataTileStyle.resolve(ui, hero: hero);
    final String? measure = unit;
    final String? under = footer;
    final Widget? slot = child;
    return Semantics(
      label: _label,
      excludeSemantics: true,
      child: GlassSurface(
        // In flow, and one pane per tile. A tile group sharing one pane is
        // the caller's composition; the tile itself is the object a reviewer
        // reads as one thing (09 section 3.3).
        level: GlassLevel.flat,
        radius: style.radius,
        padding: style.padding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            UiLabel(label, style: style.label),
            SizedBox(height: style.labelGap),
            _measurement(ui, style, measure),
            if (under != null) ...<Widget>[
              SizedBox(height: style.footerGap),
              Text(under, style: style.footer),
            ],
            if (slot != null) ...<Widget>[
              SizedBox(height: style.childGap),
              slot,
            ],
          ],
        ),
      ),
    );
  }

  /// The numeral beside its unit, at the widest role that fits
  /// (11 section 3.3).
  ///
  /// The tile steps the numeral down one display role at a time and then
  /// scales what is left. The unit's role never changes: it is the one upper
  /// case role in the product and a smaller one would read as a different
  /// unit rather than the same unit in less room.
  ///
  /// The last resort scales the numeral and the unit together rather than the
  /// numeral alone. A `FittedBox` reports its child's unscaled baseline to
  /// the row above it, so a unit aligned to a scaled numeral's baseline would
  /// float above the digits it belongs to; scaling the pair keeps the two on
  /// one baseline and leaves that baseline inside the box.
  Widget _measurement(
    UiThemeData ui,
    UiDataTileStyle style,
    String? measure,
  ) => Builder(
    builder: (BuildContext context) {
      Widget line(TextStyle numeral) => Row(
        // The unit sits on the numeral's baseline, not on its box.
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Flexible(child: _numeral(ui, style, numeral)),
          if (measure != null) ...<Widget>[
            SizedBox(width: style.unitGap),
            Text(measure, style: style.unit, maxLines: 1, softWrap: false),
          ],
        ],
      );

      double widthOf(TextStyle numeral) =>
          measureLabel(context, value, numeral).width +
          (measure == null
              ? 0
              : style.unitGap + measureLabel(context, measure, style.unit).width);

      return FitBuilder(
        variants: <FitVariant>[
          for (final TextStyle numeral in style.numeralSteps)
            FitVariant(
              intrinsicWidth: widthOf(numeral),
              builder: (BuildContext context, bool lastResort) => lastResort
                  ? FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: AlignmentDirectional.centerStart,
                      child: line(numeral),
                    )
                  : line(numeral),
            ),
        ],
      );
    },
  );

  /// The numeral, cross-fading and sliding 6 dp upward when it changes.
  ///
  /// Both numerals travel the same way, because the tick is one number
  /// turning over rather than two numbers passing each other: the value
  /// leaving rises out of the slot while the value arriving rises into it.
  Widget _numeral(UiThemeData ui, UiDataTileStyle style, TextStyle numeral) {
    final bool reduced = ui.motion.reduced;
    return AnimatedSwitcher(
      duration: style.tick,
      switchInCurve: MotionTokens.standardCurve,
      switchOutCurve: MotionTokens.standardCurve,
      layoutBuilder: (Widget? current, List<Widget> previous) => Stack(
        // Start aligned rather than centred: a numeral that does change
        // width grows from the edge it is read from, and tabular figures
        // keep it from changing width at all for a digit swap.
        alignment: AlignmentDirectional.centerStart,
        children: <Widget>[...previous, ?current],
      ),
      transitionBuilder: (Widget child, Animation<double> animation) {
        final Widget faded = FadeTransition(opacity: animation, child: child);
        if (reduced) return faded;
        return AnimatedBuilder(
          animation: animation,
          builder: (BuildContext context, Widget? built) {
            // A transition builder is called once per value, before that
            // value is known to be leaving, so the direction is read from
            // the animation rather than from the widget: a leaving value
            // runs its animation in reverse.
            final double travel =
                MotionTokens.numeralTickRise * (1 - animation.value);
            final bool leaving =
                animation.status == AnimationStatus.reverse ||
                animation.status == AnimationStatus.dismissed;
            return Transform.translate(
              offset: Offset(0, leaving ? -travel : travel),
              child: built,
            );
          },
          child: faded,
        );
      },
      // One line at every role. A numeral never wraps, and the tile no longer
      // needs it to: 11 section 3.3 gives the tile a step down and then a
      // scale, so "Not measured" arrives at a size that fits rather than on a
      // second line (amends the wave 1 reading of 02 section 4.14, which had
      // no third option).
      child: Text(
        value,
        key: ValueKey<String>(value),
        style: numeral,
        maxLines: 1,
        softWrap: false,
      ),
    );
  }
}
