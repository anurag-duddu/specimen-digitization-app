/// The shared component library for the Specimen Digitization client.
///
/// One component, learned once (design system, principle 1.8). Screens import
/// this barrel; nothing outside `lib/src/theme/` names a color, a size, a
/// radius or a duration of its own.
library;

export '../layout/window_class.dart';
export 'adaptive_form.dart';
export 'authority_candidate_card.dart';
export 'caveat_text.dart';
export 'diff_text.dart';
export 'empty_state.dart';
export 'environment_banner.dart';
export 'evidence_drawer.dart';
export 'field_row.dart';
export 'first_pass_summary.dart';
export 'group_heading.dart';
export 'in_flight_glyph.dart';
export 'measured_height.dart';
export 'motion_reveal.dart';
export 'not_calibrated_chip.dart';
export 'product_modal.dart';
export 'queue_row.dart';
export 'reading_card.dart';
export 'reading_comparison.dart';
export 'reason_sheet.dart';
export 'region_overlay.dart';
export 'selectable_evidence.dart';
export 'risk_meter.dart';
export 'selection_bar.dart';
export 'skeleton.dart';
export 'specimen_status.dart';
export 'status_chip.dart';
export 'term_text.dart';
export 'thumbnail.dart';
export 'upload_item.dart';
