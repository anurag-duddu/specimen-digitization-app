/// The router (screen blueprints, section 1.1; responsive, section 6).
///
/// Every screen is a location, so the browser's address bar, the browser's
/// back button, a bookmark and an app link all name the same thing. Redirects
/// carry a window with no session to sign in, a session with an unverified
/// address to verification, and a session with no collection to the setup
/// screen, keeping the location it was trying to reach.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../auth.dart';
import '../email_verification.dart';
import '../intake.dart';
import '../magic_link.dart';
import '../models.dart';
import '../screens/queue/queue_screen.dart';
import '../screens/queue/workbench_screen.dart';
import '../screens/sources/source_controller.dart';
import '../screens/sources/source_screen.dart';
import '../screens/sources/sources_screen.dart';
import '../sources.dart';
import '../theme/motion.dart';
import '../widgets/widgets.dart';
import '../workspace.dart';
import 'help_screen.dart';
import 'routes.dart';
import 'session_notifier.dart';
import 'setup_screen.dart';

/// Builds the client's router.
///
/// [controller] is null until the build has both a session and a collection
/// API; the redirect then keeps every collection location out of reach.
GoRouter buildAppRouter({
  required AppSessionNotifier sessionNotifier,
  WorkspaceController? controller,
  String? setupMessage,
  MagicLinkController? magicLink,
  bool synthetic = false,
  String initialLocation = AppRoutes.setup,
  List<NavigatorObserver> observers = const <NavigatorObserver>[],
}) {
  final SessionAccess? session = sessionNotifier.session;
  final String environment = synthetic
      ? 'synthetic'
      : (controller?.environment ?? EnvironmentBanner.production);

  String? redirect(BuildContext context, GoRouterState state) {
    final String location = state.uri.path;
    final bool entry = AppRoutes.isEntryLocation(location);

    // The gallery is a review surface for the design system. It reads no
    // collection data and needs no session, so it sits above every redirect.
    if (!kReleaseMode && location == AppRoutes.gallery) return null;

    void remember() {
      if (!entry && location != '/') {
        sessionNotifier.pendingLocation = state.uri.toString();
      }
    }

    if (session == null) {
      remember();
      return location == AppRoutes.setup ? null : AppRoutes.setup;
    }
    // An incoming email sign-in link is confirmed on the sign-in screen, even
    // when a session is already signed in.
    if (magicLink != null && magicLink.handlingLink) {
      remember();
      return location == AppRoutes.signIn ? null : AppRoutes.signIn;
    }
    if (!sessionNotifier.signedIn) {
      remember();
      return location == AppRoutes.signIn ? null : AppRoutes.signIn;
    }
    if (!sessionNotifier.verified) {
      remember();
      return location == AppRoutes.verify ? null : AppRoutes.verify;
    }
    if (controller == null) {
      remember();
      return location == AppRoutes.setup ? null : AppRoutes.setup;
    }
    if (!controller.scopesLoaded) {
      // The collection list has not been answered yet. A deep link stays where
      // it is and renders its loading state; an entry screen waits on setup,
      // which is the screen that says access is being checked.
      if (location == AppRoutes.setup) return null;
      return entry || location == '/' ? AppRoutes.setup : null;
    }
    if (controller.scopes.isEmpty) {
      remember();
      return location == AppRoutes.setup ? null : AppRoutes.setup;
    }

    // A route that belongs to no collection is not a route with a missing
    // collection. Help opens over whatever the reviewer had open and closes
    // back to it.
    if (AppRoutes.isGlobalLocation(location)) return null;

    final String home = AppRoutes.queueOf(controller.defaultRouteKey!);
    if (entry || location == '/') {
      final String? pending = sessionNotifier.pendingLocation;
      sessionNotifier.pendingLocation = null;
      return pending ?? home;
    }

    final String? routeKey = AppRoutes.collectionKeyIn(state.uri);
    if (routeKey == null) return home;
    final String key = decodeCollectionKey(routeKey);
    final bool known = controller.scopes.any(
      (CollectionScope scope) => scope.key == key,
    );
    return known ? null : home;
  }

  return GoRouter(
    initialLocation: initialLocation,
    // Empty in the app. A test installs `TransitionDurationObserver` here,
    // because a page transition's length is no longer a literal a test may
    // assume: Flutter 3.38 moved the Android default to 450 ms
    // (motion and microinteractions, 6.1 and 6.3 A).
    observers: observers,
    refreshListenable: Listenable.merge(<Listenable?>[
      sessionNotifier,
      controller,
      magicLink,
    ]),
    redirect: redirect,
    routes: <RouteBase>[
      GoRoute(
        path: AppRoutes.signIn,
        builder: (BuildContext context, GoRouterState state) =>
            _EnvironmentFrame(
              environment: environment,
              child: SignInScreen(session: session!, magicLink: magicLink),
            ),
      ),
      GoRoute(
        path: AppRoutes.verify,
        builder: (BuildContext context, GoRouterState state) =>
            _EnvironmentFrame(
              environment: environment,
              child: EmailVerificationGate(
                session: session!,
                refreshVerification: sessionNotifier.refreshVerification,
                child: const _LeaveVerification(),
              ),
            ),
      ),
      GoRoute(
        path: AppRoutes.setup,
        builder: (BuildContext context, GoRouterState state) =>
            _EnvironmentFrame(
              environment: environment,
              child: SetupScreen(
                session: session,
                setupMessage: setupMessage,
                controller: controller,
              ),
            ),
      ),
      GoRoute(
        path: AppRoutes.help,
        pageBuilder: (BuildContext context, GoRouterState state) =>
            helpPage(context),
      ),
      if (!kReleaseMode)
        GoRoute(
          path: AppRoutes.gallery,
          builder: (BuildContext context, GoRouterState state) =>
              const UiGallery(),
        ),
      ShellRoute(
        builder: (BuildContext context, GoRouterState state, Widget child) {
          final String routeKey = AppRoutes.collectionKeyIn(state.uri) ?? '';
          final bool intake = state.uri.pathSegments.contains('intake');
          return CollectionWorkspace(
            routeKey: routeKey,
            destination: intake
                ? WorkspaceDestination.intake
                : WorkspaceDestination.queue,
            child: child,
          );
        },
        routes: <RouteBase>[
          GoRoute(
            path:
                '${AppRoutes.collectionPrefix}/'
                ':${AppRoutes.collectionParameter}/queue',
            builder: (BuildContext context, GoRouterState state) =>
                const QueueScreen(),
            routes: <RouteBase>[
              GoRoute(
                path: ':${AppRoutes.specimenParameter}',
                pageBuilder: (BuildContext context, GoRouterState state) {
                  final String id = Uri.decodeComponent(
                    state.pathParameters[AppRoutes.specimenParameter] ?? '',
                  );
                  final Widget screen = WorkbenchScreen(specimenId: id);
                  // At large and above the queue list is already beside this
                  // pane, so the detail cross-fades in place (motion catalog,
                  // row 17). Below that it is a pushed screen and keeps the
                  // platform transition (row 18).
                  if (!WindowClass.of(context).isAtLeast(WindowClass.large)) {
                    return MaterialPage<void>(
                      key: state.pageKey,
                      child: screen,
                    );
                  }
                  final MotionTokens motion = MotionTokens.of(context);
                  return CustomTransitionPage<void>(
                    key: state.pageKey,
                    transitionDuration: motion.standard,
                    reverseTransitionDuration: motion.quick,
                    child: screen,
                    transitionsBuilder:
                        (
                          BuildContext context,
                          Animation<double> animation,
                          Animation<double> secondary,
                          Widget child,
                        ) => FadeTransition(
                          opacity: CurvedAnimation(
                            parent: animation,
                            curve: MotionTokens.standardCurve,
                          ),
                          child: child,
                        ),
                  );
                },
              ),
            ],
          ),
          GoRoute(
            path:
                '${AppRoutes.collectionPrefix}/'
                ':${AppRoutes.collectionParameter}/intake',
            builder: (BuildContext context, GoRouterState state) =>
                const _IntakeRoute(),
            routes: <RouteBase>[
              GoRoute(
                path: 'sources',
                builder: (BuildContext context, GoRouterState state) =>
                    const _SourcesRoute(),
                routes: <RouteBase>[
                  GoRoute(
                    path: ':${AppRoutes.sourceParameter}',
                    builder: (BuildContext context, GoRouterState state) =>
                        _SourceRoute(
                          sourceId:
                              state.pathParameters[AppRoutes
                                  .sourceParameter] ??
                              '',
                        ),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    ],
  );
}

/// The registered sources for the open collection.
///
/// A repository that does not serve sources is a build without them rather
/// than a failure: the screen says so instead of offering a control that
/// cannot answer.
class _SourcesRoute extends StatelessWidget {
  const _SourcesRoute();

  @override
  Widget build(BuildContext context) {
    final WorkspaceController controller = WorkspaceScope.of(context);
    final CollectionScope? scope = controller.scope;
    if (scope == null) {
      return const Center(
        child: LoadingAnnouncement(thing: 'the collection', visible: true),
      );
    }
    final SourceRepository? repository = sourcesIn(controller.repository);
    if (repository == null) return const _NoSourceSupport();
    return SourcesScreen(
      key: ValueKey<String>(scope.key),
      repository: repository,
      scope: scope,
      onOpen: (RegisteredSource source) => GoRouter.of(
        context,
      ).go(AppRoutes.sourceOf(Uri.encodeComponent(scope.key), source.id)),
    );
  }
}

/// Browsing one registered source.
class _SourceRoute extends StatefulWidget {
  const _SourceRoute({required this.sourceId});

  final String sourceId;

  @override
  State<_SourceRoute> createState() => _SourceRouteState();
}

class _SourceRouteState extends State<_SourceRoute> {
  SourceBrowseController? _controller;
  RegisteredSource? _source;
  String? _key;

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  /// Builds the controller once per source, so a rebuild does not restart the
  /// listing under a reviewer who is part way through choosing.
  SourceBrowseController _controllerFor(
    SourceRepository repository,
    CollectionScope scope,
  ) {
    final String key = '${scope.key}/${widget.sourceId}';
    if (_key != key) {
      _controller?.dispose();
      _controller = SourceBrowseController(
        repository: repository,
        scope: scope,
        sourceId: widget.sourceId,
      );
      _key = key;
      _source = null;
    }
    return _controller!;
  }

  @override
  Widget build(BuildContext context) {
    final WorkspaceController controller = WorkspaceScope.of(context);
    final CollectionScope? scope = controller.scope;
    if (scope == null) {
      return const Center(
        child: LoadingAnnouncement(thing: 'the collection', visible: true),
      );
    }
    final SourceRepository? repository = sourcesIn(controller.repository);
    if (repository == null) return const _NoSourceSupport();
    final SourceBrowseController browse = _controllerFor(repository, scope);
    final RegisteredSource? source = _source;
    if (source != null) {
      return SourceBrowsePane(
        controller: browse,
        source: source,
        onOpenSpecimen: (String id) => GoRouter.of(
          context,
        ).go(AppRoutes.specimenOf(Uri.encodeComponent(scope.key), id)),
      );
    }
    return FutureBuilder<List<RegisteredSource>>(
      future: repository.sources(scope),
      builder:
          (
            BuildContext context,
            AsyncSnapshot<List<RegisteredSource>> snapshot,
          ) {
            final List<RegisteredSource>? sources = snapshot.data;
            if (sources == null) {
              return const Center(
                child: LoadingAnnouncement(thing: 'the source', visible: true),
              );
            }
            final RegisteredSource? found = sources
                .where((RegisteredSource s) => s.id == widget.sourceId)
                .firstOrNull;
            if (found == null) {
              return const EmptyState(
                icon: Symbols.inventory_2,
                title: 'Source not found',
                body: 'This source is not registered to the open collection.',
              );
            }
            _source = found;
            return SourceBrowsePane(
              controller: browse,
              source: found,
              onOpenSpecimen: (String id) => GoRouter.of(
                context,
              ).go(AppRoutes.specimenOf(Uri.encodeComponent(scope.key), id)),
            );
          },
    );
  }
}

/// What a build with no source support says.
class _NoSourceSupport extends StatelessWidget {
  const _NoSourceSupport();

  @override
  Widget build(BuildContext context) => const EmptyState(
    icon: Symbols.inventory_2,
    title: 'Sources not available',
    body: 'This build reads uploads only. Add photographs from Intake.',
  );
}

/// The environment band above an entry screen.
///
/// The collection shell draws its own band; these three screens sit outside
/// it, and the band is what replaced the caveat paragraph they used to carry
/// (screen blueprints, sections 1.3 and 2).
class _EnvironmentFrame extends StatelessWidget {
  const _EnvironmentFrame({required this.environment, required this.child});

  final String environment;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!EnvironmentBanner.showsFor(environment)) return child;
    return Material(
      color: Theme.of(context).colorScheme.surface,
      child: Column(
        children: <Widget>[
          SafeArea(
            bottom: false,
            child: EnvironmentBanner(environment: environment),
          ),
          Expanded(child: child),
        ],
      ),
    );
  }
}

/// The child the verification gate renders once the address is verified: it
/// leaves the verification location rather than drawing anything.
class _LeaveVerification extends StatefulWidget {
  const _LeaveVerification();

  @override
  State<_LeaveVerification> createState() => _LeaveVerificationState();
}

class _LeaveVerificationState extends State<_LeaveVerification> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) GoRouter.of(context).go(AppRoutes.setup);
    });
  }

  @override
  Widget build(BuildContext context) => const Scaffold(
    body: Center(
      child: LoadingAnnouncement(thing: 'your collection', visible: true),
    ),
  );
}

/// Intake, wired to the open collection.
class _IntakeRoute extends StatelessWidget {
  const _IntakeRoute();

  @override
  Widget build(BuildContext context) {
    final WorkspaceController controller = WorkspaceScope.of(context);
    final CollectionScope? scope = controller.scope;
    if (scope == null) {
      return const Center(
        child: LoadingAnnouncement(thing: 'the collection', visible: true),
      );
    }
    return IntakeScreen(
      key: ValueKey<String>(scope.key),
      repository: controller.repository,
      scope: scope,
      userId: controller.session.userId,
      onComplete: () => controller.refresh(quiet: true),
      // Hidden rather than disabled where the build serves no sources.
      onBrowseSources: sourcesIn(controller.repository) == null
          ? null
          : () => GoRouter.of(
              context,
            ).go(AppRoutes.sourcesOf(Uri.encodeComponent(scope.key))),
    );
  }
}
