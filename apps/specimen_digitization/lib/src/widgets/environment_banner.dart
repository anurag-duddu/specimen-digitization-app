/// The environment band (10 section 5; 02 section 5.1).
///
/// A full bleed strip that states a permanent condition of the build. It
/// never animates, because animating it would imply it just happened
/// (04 section 4, row 9), and it has no dismiss control, because the condition
/// it names does not go away.
///
/// It is `UiBanner` in its `synthetic` tone. Finding V-15, where the sentence
/// wrapped to eleven lines at 200 percent text and took half a phone, is held
/// by the control rather than by this file: a banner is one line or two at
/// every text scale and the whole sentence stays on its semantics node.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// A band naming the environment, hidden entirely in production.
class EnvironmentBanner extends StatelessWidget {
  const EnvironmentBanner({super.key, required this.environment});

  /// The environment name the session reports, such as `synthetic`.
  final String environment;

  /// The one environment that gets no band.
  static const String production = 'production';

  /// The most lines the band may ever occupy, open or closed.
  ///
  /// Not a style preference. It is the guarantee that replaces finding V-15:
  /// whatever the text scale, the band is one line or two.
  static const int maxLines = UiBannerStyle.maxLines;

  /// What the disclosure control is called.
  ///
  /// One name in both states, with `expanded` carrying which state it is in:
  /// a control that renames itself when it is pressed reads as two controls.
  static const String detailLabel = 'Show what a test environment means';

  /// True when this environment should show a band at all.
  static bool showsFor(String environment) =>
      environment.trim().toLowerCase() != production;

  /// The environment's own name, sentence case.
  ///
  /// `synthetic` is the build's internal word. A reviewer reads "test"
  /// (02 section 3, vocabulary row `synthetic`).
  static String nameFor(String environment) {
    final String name = environment.trim().toLowerCase();
    if (name.isEmpty) return 'This environment';
    if (name == 'synthetic') return 'Test environment';
    return '${name[0].toUpperCase()}${name.substring(1)} environment';
  }

  /// The clause the band always shows, short enough for one line.
  ///
  /// It carries only what the build can guarantee. The band cannot know
  /// whether a reading came from a fixture or from a real provider, because a
  /// non-production build can be wired to the real routes, so it does not say.
  /// Each reading already names its own model and provider, which is the
  /// honest place for that. 02 section 4.15: the label alone must be true for
  /// a reader who never opens the disclosure.
  static String headlineFor(String environment) =>
      '${nameFor(environment)}. Not approved museum records.';

  /// The clause behind the disclosure.
  static const String detail =
      'Nothing here carries institutional approval. Each reading names the '
      'model and provider that produced it.';

  /// The sentence the band carries. Sentence case, no shouting, no dashes.
  ///
  /// This is what the semantics node says in full, whether the band is open
  /// or closed, so truncating the visible line never costs a reviewer the
  /// statement.
  static String messageFor(String environment) =>
      '${headlineFor(environment)} $detail';

  @override
  Widget build(BuildContext context) {
    if (!showsFor(environment)) return const SizedBox.shrink();
    // No node of its own over the band. The v1 band published one label
    // carrying the whole sentence and excluded everything under it, which
    // also excluded its own disclosure: a screen reader could hear the
    // sentence and could not reach the control. `UiBanner` announces the
    // headline once, keeps the control a named 48 dp target, and puts the
    // second clause on its own node when it is opened.
    return UiBanner(
      message: headlineFor(environment),
      tone: UiBannerTone.synthetic,
      detail: detail,
      detailLabel: detailLabel,
    );
  }
}
