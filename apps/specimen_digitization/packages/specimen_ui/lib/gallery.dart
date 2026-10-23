/// The gallery: every token and every component, in every state.
///
/// Separate from the main barrel because it is a review surface, not part of
/// the product's runtime. The application mounts it at `/gallery` outside
/// release builds.
library;

export 'src/gallery/gallery_shell.dart';

export 'src/gallery/pages/control_states_page.dart';
export 'src/gallery/pages/brand_overview_page.dart';
export 'src/gallery/pages/content_patterns_page.dart';
export 'src/gallery/pages/advanced_inputs_page.dart';
export 'src/gallery/pages/data_patterns_page.dart';
