/// The gallery: every token and every component, in every state.
///
/// Separate from the main barrel because it is a review surface, not part of
/// the product's runtime. The application mounts it at `/gallery` outside
/// release builds.
library;

export 'src/gallery/gallery_shell.dart';
