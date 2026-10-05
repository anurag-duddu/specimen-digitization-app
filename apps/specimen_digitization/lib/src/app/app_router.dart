/// The router (screen blueprints, section 1.1; responsive, section 6).
///
/// Every screen is a location, so the browser's address bar, the browser's
/// back button, a bookmark and an app link all name the same thing. Redirects
/// carry a window with no session to sign in, a session with an unverified
/// address to verification, and a session with no collection to the setup
/// screen, keeping the location it was trying to reach.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/cupertino.dart' show CupertinoRouteTransitionMixin;
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

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
import '../widgets/widgets.dart';
import '../workspace.dart';
import 'help_screen.dart';
import 'routes.dart';
import 'shell.dart';
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
    // Flutter 3.38 web history decodes an encoded slash in the scope key.
    // Restore its route spelling before the ordinary session/access checks.
    final restored = AppRoutes.restoreWebHistory(state.uri);
    if (restored != null) return restored.toString();
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
    if (AppRoutes.isGlobalLocation(location)) {
      sessionNotifier.pendingLocation = null;
      return null;
    }

    final String home = AppRoutes.queueOf(controller.defaultRouteKey!);
    if (entry || location == '/') {
      final String? pending = sessionNotifier.pendingLocation;
      // Scope loading can start overlapping redirects from the entry screen.
      // Keep the incoming link until navigation leaves that authorized target.
      return pending ?? home;
    }

    final String? routeKey = AppRoutes.collectionKeyIn(state.uri);
    if (routeKey == null) return home;
    final String key = decodeCollectionKey(routeKey);
    final bool known = controller.scopes.any(
      (CollectionScope scope) => scope.key == key,
    );
    if (known && state.uri.toString() != sessionNotifier.pendingLocation) {
      sessionNotifier.pendingLocation = null;
    }
    return known ? null : home;
  }

  RoutingConfig routes() {
    final queueRoute = GoRoute(
      path:
          '${AppRoutes.collectionPrefix}/'
          ':${AppRoutes.collectionParameter}/queue',
      pageBuilder: (context, state) =>
          _WorkspacePage<void>(key: state.pageKey, child: const QueueScreen()),
      routes: <RouteBase>[
        GoRoute(
          path: ':${AppRoutes.specimenParameter}',
          onExit: (context, state) =>
              controller?.mayLeaveReview() ?? Future<bool>.value(true),
          pageBuilder: (BuildContext context, GoRouterState state) {
            final String id = Uri.decodeComponent(
              state.pathParameters[AppRoutes.specimenParameter] ?? '',
            );
            final Widget screen = WorkbenchScreen(
              specimenId: id,
              collectionKey: decodeCollectionKey(
                AppRoutes.collectionKeyIn(state.uri) ?? '',
              ),
            );
            // Phone iOS uses the SDK's interactive route transition;
            // other layouts keep the quiet in-place transition.
            final MotionTokens motion = context.ui.motion;
            return _WorkspacePage<void>(
              key: state.pageKey,
              transitionDuration: defaultTargetPlatform == TargetPlatform.iOS
                  ? motion.navigationGlide
                  : motion.quick,
              reverseTransitionDuration:
                  defaultTargetPlatform == TargetPlatform.iOS
                  ? motion.navigationGlide
                  : motion.quick,
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
    );
    final intakeRoute = GoRoute(
      path:
          '${AppRoutes.collectionPrefix}/'
          ':${AppRoutes.collectionParameter}/intake',
      pageBuilder: (context, state) =>
          _WorkspacePage<void>(key: state.pageKey, child: const _IntakeRoute()),
      routes: <RouteBase>[
        GoRoute(
          path: 'sources',
          pageBuilder: (BuildContext context, GoRouterState state) =>
              _WorkspacePage<void>(
                key: state.pageKey,
                child: const _SourcesRoute(),
              ),
          routes: <RouteBase>[
            GoRoute(
              path: ':${AppRoutes.sourceParameter}',
              pageBuilder: (BuildContext context, GoRouterState state) =>
                  _WorkspacePage<void>(
                    key: state.pageKey,
                    child: _SourceRoute(
                      sourceId:
                          state.pathParameters[AppRoutes.sourceParameter] ?? '',
                    ),
                  ),
            ),
          ],
        ),
      ],
    );
    Widget frame(
      BuildContext context,
      GoRouterState state,
      Widget child, {
      StatefulNavigationShell? navigationShell,
    }) {
      return CollectionWorkspace(
        key: ValueKey((session?.userId, controller?.defaultRouteKey)),
        routeKey: AppRoutes.collectionKeyIn(state.uri) ?? '',
        destination: state.uri.pathSegments.contains('intake')
            ? WorkspaceDestination.intake
            : WorkspaceDestination.queue,
        navigationShell: navigationShell,
        // This temporary shell can overlap its authorized replacement during
        // route reconfiguration. It may show loading, but cannot own a record.
        child: navigationShell == null
            ? WorkspaceBranchScope(
                active: false,
                collectionKey: '',
                child: child,
              )
            : child,
      );
    }

    final routeKey = controller?.defaultRouteKey;
    final RouteBase collection = routeKey == null
        ? ShellRoute(
            builder: (context, state, child) => frame(context, state, child),
            routes: [queueRoute, intakeRoute],
          )
        : StatefulShellRoute(
            builder: (context, state, navigationShell) => frame(
              context,
              state,
              navigationShell,
              navigationShell: navigationShell,
            ),
            navigatorContainerBuilder: (context, navigationShell, children) =>
                WorkspaceBranchStack(
                  activeIndex: navigationShell.currentIndex,
                  collectionKey: decodeCollectionKey(routeKey),
                  children: children,
                ),
            branches: [
              StatefulShellBranch(
                preload: true,
                initialLocation: AppRoutes.queueOf(routeKey),
                routes: [queueRoute],
              ),
              StatefulShellBranch(
                initialLocation: AppRoutes.intakeOf(routeKey),
                routes: [intakeRoute],
              ),
            ],
          );
    return RoutingConfig(
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
        collection,
      ],
    );
  }

  final config = _WorkspaceRoutingConfig(
    build: routes,
    session: sessionNotifier,
    controller: controller,
  );
  return _WorkspaceRouter(
    config: config,
    initialLocation: initialLocation,
    observers: observers,
    refreshListenable: Listenable.merge([
      sessionNotifier,
      controller,
      magicLink,
    ]),
  );
}

/// Retained branch state belongs to one authorized account and collection.
/// Rebuild only on that ownership boundary, never on ordinary record updates.
class _WorkspaceRoutingConfig extends ValueNotifier<RoutingConfig> {
  _WorkspaceRoutingConfig({
    required this.build,
    required this.session,
    required this.controller,
  }) : super(build()) {
    _identity = _owner;
    session.addListener(_refresh);
    controller?.addListener(_refresh);
  }
  final RoutingConfig Function() build;
  final AppSessionNotifier session;
  final WorkspaceController? controller;
  late Object _identity;
  Object get _owner => (
    session.session?.userId,
    session.signedIn,
    session.verified,
    controller?.defaultRouteKey,
  );
  void _refresh() {
    final owner = _owner;
    if (owner == _identity) return;
    _identity = owner;
    value = build();
  }

  @override
  void dispose() {
    session.removeListener(_refresh);
    controller?.removeListener(_refresh);
    super.dispose();
  }
}

class _WorkspaceRouter extends GoRouter {
  _WorkspaceRouter({
    required _WorkspaceRoutingConfig config,
    required String initialLocation,
    required List<NavigatorObserver> observers,
    required Listenable refreshListenable,
  }) : _ownedConfig = config,
       super.routingConfig(
         routingConfig: config,
         initialLocation: initialLocation,
         observers: observers,
         refreshListenable: refreshListenable,
       );
  final _WorkspaceRoutingConfig _ownedConfig;
  @override
  void dispose() {
    super.dispose();
    _ownedConfig.dispose();
  }
}

/// A routed content pane is part of the workspace's keyboard traversal.
/// Its edges hand focus to the persistent sidebar; modal dialogs keep their
/// own closed traversal loop.
class _WorkspacePage<T> extends CustomTransitionPage<T> {
  const _WorkspacePage({
    required super.child,
    super.key,
    super.transitionDuration = Duration.zero,
    super.reverseTransitionDuration = Duration.zero,
    super.transitionsBuilder = _noTransition,
  });

  static Widget _noTransition(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) => child;

  @override
  Route<T> createRoute(BuildContext context) => _WorkspacePageRoute<T>(this);
}

class _WorkspacePageRoute<T> extends PageRoute<T> {
  _WorkspacePageRoute(_WorkspacePage<T> page)
    : super(
        settings: page,
        traversalEdgeBehavior: TraversalEdgeBehavior.parentScope,
      );
  _WorkspacePage<T> get _page => settings as _WorkspacePage<T>;
  @override
  bool get maintainState => true;
  @override
  Color? get barrierColor => null;
  @override
  String? get barrierLabel => null;
  @override
  Duration get transitionDuration => _page.transitionDuration;
  @override
  Duration get reverseTransitionDuration => _page.reverseTransitionDuration;
  @override
  Widget buildPage(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
  ) => Semantics(
    scopesRoute: true,
    explicitChildNodes: true,
    // Keep the presentation ancestry stable across phone/tablet changes.
    // Replacing this wrapper would dispose the live review and its drafts.
    child: ColoredBox(
      color: AppSidebarScope.maybeOf(context)?.mobileNavigation == true
          ? context.ui.color.ground
          : context.ui.color.ground.withValues(alpha: 0),
      child: _page.child,
    ),
  );
  @override
  Widget buildTransitions(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    if (defaultTargetPlatform == TargetPlatform.iOS &&
        AppSidebarScope.maybeOf(context)?.mobileNavigation == true) {
      return CupertinoRouteTransitionMixin.buildPageTransitions<T>(
        this,
        context,
        animation,
        secondaryAnimation,
        child,
      );
    }
    return _page.transitionsBuilder(
      context,
      animation,
      secondaryAnimation,
      child,
    );
  }
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
      // The way back to the other way photographs arrive (finding V2-4).
      onUpload: () => GoRouter.of(
        context,
      ).go(AppRoutes.intakeOf(Uri.encodeComponent(scope.key))),
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
  Future<List<RegisteredSource>>? _sources;
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
      _sources = repository.sources(scope);
      _key = key;
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
    return FutureBuilder<List<RegisteredSource>>(
      key: ValueKey<String?>(_key),
      future: _sources,
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
              return EmptyState(
                icon: UiIcons.queue.defaultGlyph,
                title: 'Source not found',
                body: 'This source is not registered to the open collection.',
              );
            }
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
  Widget build(BuildContext context) => EmptyState(
    icon: UiIcons.queue.defaultGlyph,
    title: 'Sources not available',
    body: 'This build reads uploads only. Add photographs from Intake.',
  );
}

/// The environment band above an entry screen (13 sections 2.3 and 4.6).
///
/// The collection shell draws its own band; these three screens sit outside
/// it, and the band is what replaced the caveat paragraph they used to carry
/// (screen blueprints, sections 1.3 and 2).
///
/// It takes the strip form on a phone, as the shell's band does, and marks
/// itself as the band it is, so a screen outside the shell spends its pinned
/// height where the budget can see it rather than where nothing counts it.
class _EnvironmentFrame extends StatelessWidget {
  const _EnvironmentFrame({required this.environment, required this.child});

  final String environment;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    // `showsBand` rather than `showsFor`: a production deployment serving a
    // bounded pilot carries a band of its own, and an entry screen is where a
    // reviewer first learns which build they signed in to.
    if (!EnvironmentBanner.showsBand(environment)) return child;
    return ColoredBox(
      color: context.ui.color.ground,
      child: Column(
        children: <Widget>[
          PinnedChrome(
            region: UiPinnedRegion.band,
            child: SafeArea(
              bottom: false,
              child: UiBandForm(
                form: WindowClass.of(context).isCompact
                    ? UiBannerForm.strip
                    : UiBannerForm.full,
                child: EnvironmentBanner(environment: environment),
              ),
            ),
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
  Widget build(BuildContext context) => const UiScaffold(
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
