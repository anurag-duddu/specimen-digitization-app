/// A disclosure trigger that is a 48 dp target at every density.
///
/// fe/polish-2: `UiDisclosure` needs a hit box of its own. Its style takes
/// `minHeight` from the density row height, which is 44 dp at pointer
/// density, so `androidTapTargetGuideline` and `iOSTapTargetGuideline` both
/// fail on a trigger whose title fits one line. Every other control in the
/// system keeps a 48 dp hit box in both densities (10 section 2, clause 2);
/// the package fix is queued for the polish slot, and until it lands a screen
/// asks for the height the contract already promises.
library;

import 'package:specimen_ui/specimen_ui.dart';

/// [UiDisclosureStyle.resolve], with the trigger's target raised to 48 dp.
UiDisclosureStyle fullTargetDisclosure(UiThemeData ui) {
  final UiDisclosureStyle base = UiDisclosureStyle.resolve(ui);
  return UiDisclosureStyle(
    title: base.title,
    summary: base.summary,
    titleColor: base.titleColor,
    summaryColor: base.summaryColor,
    caretColor: base.caretColor,
    padding: base.padding,
    bodyPadding: base.bodyPadding,
    gap: base.gap,
    minHeight: UiDensity.hitBox,
    radius: base.radius,
  );
}
