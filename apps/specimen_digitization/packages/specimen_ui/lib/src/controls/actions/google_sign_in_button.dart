/// The Sign in with Google button (10 section 4.1, `UiGoogleSignInButton`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/google_sign_in_brand.dart';
import '../../foundation/palette.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/pressable.dart';
import '../overlays/tooltip.dart';

/// The resolved paint and measurements of one Sign in with Google button
/// (10 section 1.5).
///
/// The colours are Google's Light and Dark themes, chosen by the mode the app
/// is in; every measurement is the figure of Google's page held in
/// [GoogleSignInBrand]. Nothing here reads the platform.
@immutable
class UiGoogleSignInButtonStyle {
  /// Binds everything the button draws with.
  const UiGoogleSignInButtonStyle({
    required this.fill,
    required this.edge,
    required this.foreground,
    required this.label,
    required this.height,
    required this.inset,
    required this.paddingStart,
    required this.gap,
    required this.paddingEnd,
    required this.iconSize,
    required this.disabledOpacity,
  });

  /// The button's fill: Google's `#FFFFFF` in light and `#131314` in dark.
  final Color fill;

  /// The 1 px outline, drawn inside the edge: `#747775` in light and
  /// `#8E918F` in dark.
  final BorderSide edge;

  /// The label colour, `#1F1F1F` in light and `#E3E3E3` in dark. The state
  /// layer lifts the button toward it, so hover and press are visible on
  /// Google's fill and change none of Google's colours at rest.
  final Color foreground;

  /// Google Sans Medium 14/20, the label's whole role.
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

  /// How much of its paint a disabled button keeps.
  final double disabledOpacity;

  /// The style for [ui] at [textScaler].
  static UiGoogleSignInButtonStyle resolve(
    UiThemeData ui, {
    TextScaler textScaler = TextScaler.noScaling,
  }) {
    final bool dark = ui.color.brightness == Brightness.dark;
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
      color: dark
          ? GoogleSignInPalette.labelDark
          : GoogleSignInPalette.labelLight,
    );
    return UiGoogleSignInButtonStyle(
      fill: dark ? GoogleSignInPalette.fillDark : GoogleSignInPalette.fillLight,
      edge: BorderSide(
        color: dark
            ? GoogleSignInPalette.borderDark
            : GoogleSignInPalette.borderLight,
        width: GoogleSignInBrand.strokeWidth,
      ),
      foreground: label.color!,
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
      disabledOpacity: GoogleSignInBrand.disabledOpacity,
    );
  }
}

/// Google's "Sign in with Google" button, the same on every platform.
///
/// One component with one appearance: the pill of Google's own drawing, which
/// is also the system's capsule (09 section 5), in Google's Light theme in a
/// light window and its Dark theme in a dark one, with the standard colour "G"
/// and the label set in Google Sans Medium 14/20. Padding, size and colours
/// are the figures of Google's "Sign in with Google branding guidelines"
/// (<https://developers.google.com/identity/branding-guidelines>, the custom
/// button section, updated 2026-07-07), held in [GoogleSignInBrand] with their
/// source. The button reads no platform, so an iPhone, an Android phone and a
/// browser draw the same pixels (09 section 2, principle 5: behaviour adapts,
/// identity does not). Where the sign-in is offered is the caller's decision,
/// not this control's.
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
/// The button takes the width its content needs and does not stretch.
///
/// A button that is working is [busy], not forbidden: it refuses activation
/// and keeps its enabled paint, like `UiButton.loading`. A button with a null
/// [onPressed] that is not busy is disabled, and draws at
/// [GoogleSignInBrand.disabledOpacity]; [disabledReason] is on its semantics
/// hint and, when the button is disabled, on a tooltip (03 section 3.6).
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
      textScaler: MediaQuery.textScalerOf(context),
    );
    if (onPressed == null && !busy && disabledReason != null) {
      return UiTooltip.reason(
        reason: disabledReason,
        builder: (BuildContext context, ValueChanged<String> report) =>
            _button(ui, style, onDisabledReason: report),
      );
    }
    return _button(ui, style);
  }

  Widget _button(
    UiThemeData ui,
    UiGoogleSignInButtonStyle style, {
    ValueChanged<String>? onDisabledReason,
  }) {
    final ShapeBorder shape = ui.shape.capsule.copyWith(side: style.edge);
    return Pressable(
      semanticsLabel: GoogleSignInBrand.label,
      onPressed: busy ? null : onPressed,
      busy: busy,
      disabledReason: disabledReason,
      onDisabledReason: onDisabledReason,
      capsule: true,
      stateLayerColour: style.foreground,
      focusNode: focusNode,
      autofocus: autofocus,
      statesController: statesController,
      builder: (BuildContext context, Set<WidgetState> states) {
        final Widget face = DecoratedBox(
          decoration: ShapeDecoration(shape: shape, color: style.fill),
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
                    child: Text(
                      GoogleSignInBrand.label,
                      textAlign: TextAlign.center,
                      style: style.label,
                      strutStyle: UiType.strutOf(style.label),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
        // Busy is not disabled: the pressable reports `disabled` for both
        // because neither responds, and only the one with no work in flight
        // fades.
        return states.contains(WidgetState.disabled) && !busy
            ? Opacity(opacity: style.disabledOpacity, child: face)
            : face;
      },
    );
  }
}
