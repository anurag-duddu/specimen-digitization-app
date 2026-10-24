/// The Sign in with Google button (10 section 4.1, `UiGoogleSignInButton`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/google_sign_in_brand.dart';
import '../../foundation/palette.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/focus_ring.dart';
import '../../primitives/pressable.dart';
import '../overlays/tooltip.dart';

/// The resolved paint and measurements of one Sign in with Google button
/// (10 section 1.5).
///
/// The colours are Google's Light and Dark themes, chosen by the mode the app
/// is in; every measurement is the figure of Google's page held in
/// [GoogleSignInBrand]. A disabled button reads the system's disabled tokens
/// for its label and its outline, as `UiButton` does (03 section 3.6), and
/// keeps Google's fill and the "G" as they are. Nothing here reads the
/// platform.
@immutable
class UiGoogleSignInButtonStyle {
  /// Binds everything the button draws with.
  const UiGoogleSignInButtonStyle({
    required this.fill,
    required this.edge,
    required this.foreground,
    required this.overlay,
    required this.label,
    required this.height,
    required this.inset,
    required this.paddingStart,
    required this.gap,
    required this.paddingEnd,
    required this.iconSize,
  });

  /// The button's fill, in every state: Google's `#FFFFFF` in light and
  /// `#131314` in dark.
  final Color fill;

  /// The 1 px outline, drawn inside the edge, by state: `#747775` in light and
  /// `#8E918F` in dark, and `disabled.outline` when the button is disabled.
  final WidgetStateProperty<BorderSide> edge;

  /// The label colour by state: `#1F1F1F` in light and `#E3E3E3` in dark, and
  /// `disabled.content` when the button is disabled.
  final WidgetStateProperty<Color> foreground;

  /// What the state layer lifts the button toward: the enabled label colour,
  /// so hover and press are visible on Google's fill and change none of
  /// Google's colours at rest.
  final Color overlay;

  /// Google Sans Medium 14/20, the label's whole role, in its enabled colour.
  final TextStyle label;

  /// The button's height at the text size it was resolved for.
  ///
  /// `max(40, scaled line box + 2 * inset)` (11 section 2.2): 40 at normal
  /// text and 60 at 200 percent, so a larger text size grows the button and
  /// never clips the label.
  final double height;

  /// The space above and below the label's line box: half of what Google's 40
  /// leaves around its 20, which is 10.
  final double inset;

  /// The padding before the "G".
  final double paddingStart;

  /// The space between the "G" and the label.
  final double gap;

  /// The padding after the label.
  final double paddingEnd;

  /// The "G"'s box, a square.
  final double iconSize;

  /// The style for [ui] at [textScaler].
  ///
  /// [busy] keeps the enabled paint while the button refuses activation: a
  /// button that is working is busy, not forbidden, and `UiButton.loading`
  /// does the same.
  static UiGoogleSignInButtonStyle resolve(
    UiThemeData ui, {
    bool busy = false,
    TextScaler textScaler = TextScaler.noScaling,
  }) {
    final bool dark = ui.color.brightness == Brightness.dark;
    bool off(Set<WidgetState> states) =>
        states.contains(WidgetState.disabled) && !busy;
    final Color text = dark
        ? GoogleSignInPalette.labelDark
        : GoogleSignInPalette.labelLight;
    final Color outline = dark
        ? GoogleSignInPalette.borderDark
        : GoogleSignInPalette.borderLight;
    final TextStyle label = TextStyle(
      // Not the product face and not the ambient style: Google's button is
      // set in Google's font whatever it is placed in.
      inherit: false,
      fontFamily: GoogleSignInBrand.fontFamily,
      package: GoogleSignInBrand.package,
      fontSize: GoogleSignInBrand.fontSize,
      fontWeight: GoogleSignInBrand.fontWeight,
      height: GoogleSignInBrand.lineHeight / GoogleSignInBrand.fontSize,
      leadingDistribution: TextLeadingDistribution.even,
      color: text,
    );
    return UiGoogleSignInButtonStyle(
      fill: dark ? GoogleSignInPalette.fillDark : GoogleSignInPalette.fillLight,
      edge: WidgetStateProperty.resolveWith(
        (Set<WidgetState> states) => BorderSide(
          color: off(states) ? ui.color.disabledOutline : outline,
          width: GoogleSignInBrand.strokeWidth,
        ),
      ),
      foreground: WidgetStateProperty.resolveWith(
        (Set<WidgetState> states) =>
            off(states) ? ui.color.disabledContent : text,
      ),
      overlay: text,
      label: label,
      height: UiType.heightAroundAt(
        GoogleSignInBrand.height,
        label,
        textScaler,
      ),
      inset: UiType.insetAround(GoogleSignInBrand.height, label),
      paddingStart: GoogleSignInBrand.paddingStart,
      gap: GoogleSignInBrand.iconGap,
      paddingEnd: GoogleSignInBrand.paddingEnd,
      iconSize: GoogleSignInBrand.iconSize,
    );
  }
}

/// Google's "Sign in with Google" button, the same on every platform.
///
/// One component with one appearance: Google's rectangular variant, in its Light
/// theme in a light window and its Dark theme in a dark one, with the standard
/// colour "G" and the label set in Google Sans Medium 14/20. Padding, size and
/// colours are the figures of Google's "Sign in with Google branding
/// guidelines" (<https://developers.google.com/identity/branding-guidelines>,
/// the custom button section, updated 2026-07-07), held in [GoogleSignInBrand]
/// with their source. The button reads no platform, so an iPhone, an Android
/// phone and a browser draw the same pixels (09 section 2, principle 5:
/// behaviour adapts, identity does not). Where the sign-in is offered is the
/// caller's decision, not this control's.
///
/// Google pre-approves both rectangular and pill shapes. This control uses
/// the 4 dp rounded rectangle in Google's HTML configurator, while retaining
/// Google's font, colours and logo. The focus and state layers follow that
/// same contour. Choosing the rectangle does not change the product's own
/// 8 dp superellipse command buttons.
///
/// The label is Google's call to action, [GoogleSignInBrand.label], and an
/// ellipsis would cut it to "Sign in with Go", which no longer says what the
/// button does. So, unlike every other label in the system, it wraps onto a
/// second line at a width or a text size that does not hold it (10 section 2
/// clause 13 is not claimed for this control). The "G" keeps its 20 by 20 box
/// at every size, because the page says its size is not to change. The height
/// derives from the label's line box and grows with the text; the 40 dp
/// visual sits inside the 48 dp hit box every control has.
///
/// The button fills its available bounded width, aligning with a form's field
/// and primary action. With unbounded width it takes the width of its content.
/// The logo stays 20 by 20 at the fixed start inset. The label is centred in
/// the remaining space, following the HTML configurator's default wide layout.
///
/// A button that is working is [busy], not forbidden: it refuses activation
/// and keeps its enabled paint, like `UiButton.loading`. A button with a null
/// [onPressed] that is not busy is disabled: its label is drawn in the
/// system's `disabled.content` and its outline in `disabled.outline`, the
/// tokens `UiButton` reads (03 section 3.6, which rejects a 38 percent fade
/// because it measures under 3:1), on Google's fill, with the "G" at full
/// colour. [disabledReason] is on its semantics hint and, when the button is
/// disabled, on a tooltip.
class UiGoogleSignInButton extends StatelessWidget {
  /// A Sign in with Google button that does [onPressed].
  const UiGoogleSignInButton({
    super.key,
    this.onPressed,
    this.busy = false,
    this.disabledReason,
    this.focusNode,
    this.autofocus = false,
    this.statesController,
  });

  /// What the button does. Null disables it.
  final VoidCallback? onPressed;

  /// True while the sign-in is in flight.
  ///
  /// The button refuses activation and keeps its enabled paint. Focus stays
  /// where it is. What is happening is the caller's to say, in a live region.
  final bool busy;

  /// Why the button cannot be pressed, in the reader's words.
  ///
  /// It is the semantics hint while [onPressed] is null or [busy] is set, and
  /// the tooltip on a disabled button that is not busy.
  final String? disabledReason;

  /// An external focus node, for a caller that moves focus itself.
  final FocusNode? focusNode;

  /// True to take focus when first built.
  final bool autofocus;

  /// An external states controller, for a caller that has to read the
  /// button's states from outside it.
  final WidgetStatesController? statesController;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiGoogleSignInButtonStyle style = UiGoogleSignInButtonStyle.resolve(
      ui,
      busy: busy,
      textScaler: MediaQuery.textScalerOf(context),
    );
    if (onPressed == null && !busy && disabledReason != null) {
      return UiTooltip.reason(
        reason: disabledReason,
        builder: (BuildContext context, ValueChanged<String> report) =>
            _button(style, onDisabledReason: report),
      );
    }
    return _button(style);
  }

  Widget _button(
    UiGoogleSignInButtonStyle style, {
    ValueChanged<String>? onDisabledReason,
  }) {
    return Pressable(
      semanticsLabel: GoogleSignInBrand.label,
      onPressed: busy ? null : onPressed,
      busy: busy,
      disabledReason: disabledReason,
      onDisabledReason: onDisabledReason,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.all(
          Radius.circular(GoogleSignInBrand.cornerRadius),
        ),
      ),
      radius: GoogleSignInBrand.cornerRadius,
      focusShape: FocusRingShape.roundedRectangle,
      stateLayerColour: style.overlay,
      focusNode: focusNode,
      autofocus: autofocus,
      statesController: statesController,
      builder: (BuildContext context, Set<WidgetState> states) {
        return LayoutBuilder(
          builder: (context, constraints) {
            final bool bounded = constraints.hasBoundedWidth;
            final Widget visual = DecoratedBox(
              decoration: ShapeDecoration(
                shape: RoundedRectangleBorder(
                  borderRadius: const BorderRadius.all(
                    Radius.circular(GoogleSignInBrand.cornerRadius),
                  ),
                  side: style.edge.resolve(states),
                ),
                color: style.fill,
              ),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: style.height),
                child: Padding(
                  padding: EdgeInsetsDirectional.fromSTEB(
                    style.paddingStart,
                    style.inset,
                    style.paddingEnd,
                    style.inset,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      // The "G" is drawn the same in every state: the page says
                      // its colour is not to change, so a disabled button does not
                      // fade it.
                      Image.asset(
                        GoogleSignInBrand.logoAsset,
                        package: GoogleSignInBrand.package,
                        width: style.iconSize,
                        height: style.iconSize,
                        fit: BoxFit.contain,
                        // The logo is drawn at a tenth of its file's size.
                        filterQuality: FilterQuality.medium,
                        excludeFromSemantics: true,
                      ),
                      SizedBox(width: style.gap),
                      Flexible(
                        fit: bounded ? FlexFit.tight : FlexFit.loose,
                        child: Text(
                          GoogleSignInBrand.label,
                          textAlign: TextAlign.center,
                          style: style.label.copyWith(
                            color: style.foreground.resolve(states),
                          ),
                          strutStyle: UiType.strutOf(style.label),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
            return SizedBox(
              width: bounded ? constraints.maxWidth : null,
              child: visual,
            );
          },
        );
      },
    );
  }
}
