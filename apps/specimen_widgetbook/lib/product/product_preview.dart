import 'dart:async';

import 'package:specimen_digitization/specimen_application.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'fixture_repository.dart';
import 'local_routes.dart';

/// The real app router, controllers and shell on an isolated example repository.
/// It inherits Widgetbook's tokens, density, text scale and direction.
class ProductPreview extends StatefulWidget {
  const ProductPreview({super.key, required this.example});
  final ProductPreviewCase example;
  @override
  State<ProductPreview> createState() => _ProductPreviewState();
}

class _ProductPreviewState extends State<ProductPreview> {
  int _revision = 0;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Padding(
        padding: EdgeInsets.symmetric(horizontal: context.ui.space.s3),
        child: Row(
          children: [
            Expanded(
              child: Text(
                'Synthetic preview · Changes are not saved or submitted.',
                style: context.ui.type.labelSmall.copyWith(
                  color: context.ui.color.inkSecondary,
                ),
              ),
            ),
            UiIconButton(
              icon: UiIcons.reload,
              semanticsLabel: 'Reset screen preview',
              onPressed: () => setState(() => _revision++),
            ),
          ],
        ),
      ),
      const UiHairline(),
      Expanded(
        child: ClipRect(
          child: _ProductApplication(
            key: ValueKey((widget.example, _revision)),
            example: widget.example,
          ),
        ),
      ),
    ],
  );
}

class _ProductApplication extends StatefulWidget {
  const _ProductApplication({super.key, required this.example});
  final ProductPreviewCase example;
  @override
  State<_ProductApplication> createState() => _ProductApplicationState();
}

class _ProductApplicationState extends State<_ProductApplication> {
  PreviewSession? _session;
  WorkspaceController? _workspace;
  AppSessionNotifier? _notifier;
  GoRouter? _router;
  PreviewRouteInformationProvider? _routes;
  Object? _failure;

  @override
  void initState() {
    super.initState();
    unawaited(_initialize());
  }

  Future<void> _initialize() async {
    try {
      final asset = await rootBundle.load('assets/synthetic-label.png');
      if (!mounted) return;
      // A new owner prevents draft preference state from leaking between
      // examples or reset runs. The visible fixture remains deterministic.
      final session = PreviewSession('widgetbook-${UniqueKey()}');
      final repository = PreviewRepository(
        example: widget.example,
        pixels: asset.buffer.asUint8List(
          asset.offsetInBytes,
          asset.lengthInBytes,
        ),
      );
      final workspace = WorkspaceController(
        repository: repository,
        session: session,
        pollInterval: const Duration(days: 1),
      );
      final notifier = AppSessionNotifier(session: session);
      final scopeKey = encodeCollectionKey(PreviewRepository.scope.key);
      final initial = switch (widget.example) {
        ProductPreviewCase.intakeEmpty ||
        ProductPreviewCase.intakeSaved => AppRoutes.intakeOf(scopeKey),
        ProductPreviewCase.workbench => AppRoutes.specimenOf(
          scopeKey,
          repository.record.id,
        ),
        _ => AppRoutes.queueOf(scopeKey),
      };
      final router = buildAppRouter(
        sessionNotifier: notifier,
        controller: workspace,
        synthetic: true,
        initialLocation: initial,
        overridePlatformDefaultLocation: true,
        bulkIntakeEnabled: true,
        intakePickFiles: () async => throw const ApiFailure(
          'File selection is disabled in this synthetic preview. Open the saved draft example to inspect a photo.',
        ),
        intakeCameraFactory: () async =>
            throw const CaptureCameraUnavailable(CaptureUnavailable.noCamera),
      );
      final routes = PreviewRouteInformationProvider(
        router.routeInformationProvider,
      );
      _session = session;
      _workspace = workspace;
      _notifier = notifier;
      _router = router;
      _routes = routes;
      workspace.start();
      setState(() {});
    } catch (error) {
      if (mounted) setState(() => _failure = error);
    }
  }

  @override
  void dispose() {
    _routes?.dispose();
    _router?.dispose();
    _workspace?.dispose();
    _notifier?.dispose();
    _session?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_failure != null) {
      return const UiEmptyState(
        icon: UiIcons.info,
        title: 'Preview could not load',
        body: 'Reset this example to load its bundled synthetic fixture.',
      );
    }
    final router = _router;
    final workspace = _workspace;
    if (router == null || workspace == null) {
      return const Center(
        child: UiProgress.ring(semanticsLabel: 'Loading screen preview'),
      );
    }
    return LayoutBuilder(
      builder: (context, constraints) => MediaQuery(
        data: MediaQuery.of(
          context,
        ).copyWith(size: Size(constraints.maxWidth, constraints.maxHeight)),
        child: WorkspaceScope(
          controller: workspace,
          child: UiModalNavigator(
            navigatorKey: router.configuration.navigatorKey,
            child: UiToastHost(
              child: Router(
                routerDelegate: router.routerDelegate,
                routeInformationParser: router.routeInformationParser,
                routeInformationProvider: _routes,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
