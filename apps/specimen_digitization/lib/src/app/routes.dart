/// Every location in the client, in one place (screen blueprints, 1.1).
///
/// A path is built here or not at all, so a link in the app and a link in a
/// bookmark are the same string.
library;

/// The route table.
abstract final class AppRoutes {
  /// Where a window with no session lands.
  static const String signIn = '/sign-in';

  /// Where a session with an unverified address lands.
  static const String verify = '/verify';

  /// Where a session with no collection to open lands. Not in the blueprint's
  /// table: it covers the states the table has no screen for, which are an
  /// unconfigured build, an account with no collection, and a denied recheck.
  static const String setup = '/setup';

  /// Shortcuts, glossary and administrator contact, over any route.
  static const String help = '/help';

  /// The path pattern for the collection branch.
  static const String collectionPrefix = '/c';

  /// The path parameter carrying the collection.
  static const String collectionParameter = 'collection';

  /// The path parameter carrying the specimen.
  static const String specimenParameter = 'specimen';

  /// The queue for one collection. [routeKey] is already encoded.
  static String queueOf(String routeKey) => '$collectionPrefix/$routeKey/queue';

  /// One record in one collection.
  static String specimenOf(String routeKey, String specimenId) =>
      '${queueOf(routeKey)}/${Uri.encodeComponent(specimenId)}';

  /// Intake for one collection.
  static String intakeOf(String routeKey) =>
      '$collectionPrefix/$routeKey/intake';

  /// The collection route key inside [location], or null when it names no
  /// collection.
  static String? collectionKeyIn(Uri location) {
    final List<String> segments = location.pathSegments;
    if (segments.length < 2 || segments.first != 'c') return null;
    return segments[1];
  }

  /// True when [location] is one of the screens shown before a collection.
  static bool isEntryLocation(String location) =>
      location == signIn || location == verify || location == setup;

  /// True when [location] belongs to no collection and is reachable from
  /// every screen.
  ///
  /// These are the routes that open over whatever the reviewer was doing.
  /// They name no collection, so the redirect must not read one out of them
  /// and must not send them home: doing that is what made "Help and
  /// shortcuts" a control that closed itself for every signed-in reviewer.
  static bool isGlobalLocation(String location) => location == help;
}
