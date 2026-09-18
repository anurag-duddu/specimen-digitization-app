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

import '../administrator_contact.dart';

/// The pilot this build serves, as a deployment stamped it in.
///
/// The server's own vocabulary has three modes and no fourth
/// (`create_app` in the backend takes exactly `synthetic`, `emulator` and
/// `production`), so nothing on the wire can say that a production deployment
/// is serving a bounded pilot rather than the museum's records. A deployment
/// knows, and stamps it here, the way it already stamps the administrator
/// contact and the API address.
///
/// The value is the scope in the reviewer's words, short enough for one line:
/// `Ten original specimens`. Empty by default, which is the honest state of a
/// build nobody stamped, and which is exactly the build that has always shown
/// no band in production.
const String pilotScopeDefine = String.fromEnvironment('SPECIMEN_PILOT_SCOPE');

/// A band naming the environment, hidden in production unless this deployment
/// is a bounded pilot.
class EnvironmentBanner extends StatelessWidget {
  const EnvironmentBanner({
    super.key,
    required this.environment,
    this.pilotScope = pilotScopeDefine,
    this.contactSentence,
  });

  /// The environment name the session reports, such as `synthetic`.
  final String environment;

  /// The bounded pilot this deployment serves, or empty for a full release.
  final String pilotScope;

  /// Who to ask, in the collection's own words.
  ///
  /// Null outside a collection, where there is no collection document to read
  /// one out of and the build stamp is the only source. A band drawn inside
  /// the collection shell passes the open collection's contact, because a
  /// collection that names its own administrator knows better than a build
  /// time default meant to cover every collection at once.
  final String? contactSentence;

  /// The contact the band appends, or null where nobody is named.
  ///
  /// `AdministratorContact` answers a sentence either way, and the sentence it
  /// answers for a build nobody stamped says where a contact would be
  /// published rather than naming one. That belongs in the help sheet
  /// (07 section 10), not in a band that is two lines at every text scale
  /// (finding V-15): a band that spends its second line explaining that it
  /// has no contact has spent it on nothing.
  static String? contactFor(String? sentence) {
    if (sentence != null) return sentence.trim().isEmpty ? null : sentence;
    final AdministratorContact stamped = AdministratorContact.fromBuild();
    return stamped.isKnown ? stamped.sentence : null;
  }

  /// The second clause as the band draws it, contact included.
  static String detailFor(
    String environment, {
    String scope = pilotScopeDefine,
    String? contactSentence,
  }) {
    final String body = isPilot(environment, scope: scope)
        ? pilotDetail
        : detail;
    final String? contact = contactFor(contactSentence);
    return contact == null ? body : '$body $contact';
  }

  /// The one environment that gets no band of its own.
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

  /// What the pilot band's disclosure control is called.
  static const String pilotDetailLabel = 'Show what this pilot covers';

  /// True when this environment shows a band of its own.
  ///
  /// A production build carrying a pilot stamp shows one too; ask
  /// [showsBand] rather than this where the stamp is in scope.
  static bool showsFor(String environment) =>
      environment.trim().toLowerCase() != production;

  /// True when a band is drawn at all: a test environment, or a production
  /// deployment serving a bounded pilot.
  static bool showsBand(
    String environment, {
    String scope = pilotScopeDefine,
  }) => showsFor(environment) || scope.trim().isNotEmpty;

  /// True when the band is the pilot band rather than the test band.
  ///
  /// A test build that also carries a pilot stamp shows the test band: it is
  /// the stronger statement, and two bands would be two regions saying one
  /// thing (13 section 2.4).
  static bool isPilot(String environment, {String scope = pilotScopeDefine}) =>
      !showsFor(environment) && scope.trim().isNotEmpty;

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

  /// The clause the pilot band always shows.
  ///
  /// The records are real, which is the whole difference from a test build,
  /// and the scope is bounded, which is what a reviewer needs before they
  /// read a record that is not in it. Nothing here claims the pilot is
  /// finished: the checklist that opens it is not this client's to close.
  static String pilotHeadlineFor(String scope) {
    final String named = scope.trim();
    return named.isEmpty
        ? 'Bounded pilot. Real records, limited scope.'
        : 'Bounded pilot: $named. Records here are real.';
  }

  /// The clause behind the disclosure.
  static const String detail =
      'Nothing here carries institutional approval. Each reading names the '
      'model and provider that produced it.';

  /// The clause behind the pilot band's disclosure.
  static const String pilotDetail =
      'Records outside this pilot are not loaded, and automated clearance is '
      'off, so every record is decided by a person.';

  /// The sentence the band carries. Sentence case, no shouting, no dashes.
  ///
  /// This is what the semantics node says in full, whether the band is open
  /// or closed, so truncating the visible line never costs a reviewer the
  /// statement.
  static String messageFor(String environment) =>
      '${headlineFor(environment)} $detail';

  /// The whole sentence a band carries, either kind, without the contact.
  static String sentenceFor(
    String environment, {
    String scope = pilotScopeDefine,
  }) => isPilot(environment, scope: scope)
      ? '${pilotHeadlineFor(scope)} $pilotDetail'
      : messageFor(environment);

  @override
  Widget build(BuildContext context) {
    if (!showsBand(environment, scope: pilotScope)) {
      return const SizedBox.shrink();
    }
    final bool pilot = isPilot(environment, scope: pilotScope);
    // The band names somebody where somebody is named. 07 section 10 makes
    // every "ask your administrator" string reach a person, and the band is
    // the one permanent statement a reviewer reads about the build they are
    // in, so the second clause carries the contact: the collection's own
    // where a caller passed one, and the build stamp where that names anyone.
    // No node of its own over the band. The v1 band published one label
    // carrying the whole sentence and excluded everything under it, which
    // also excluded its own disclosure: a screen reader could hear the
    // sentence and could not reach the control. `UiBanner` announces the
    // headline once, keeps the control a named 48 dp target, and puts the
    // second clause on its own node when it is opened.
    return UiBanner(
      message: pilot ? pilotHeadlineFor(pilotScope) : headlineFor(environment),
      // A pilot is attention rather than a build that is not production.
      tone: pilot ? UiBannerTone.needsReview : UiBannerTone.synthetic,
      detail: detailFor(
        environment,
        scope: pilotScope,
        contactSentence: contactSentence,
      ),
      detailLabel: pilot ? pilotDetailLabel : detailLabel,
    );
  }
}
