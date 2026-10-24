import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/specimen_application.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_widgetbook/catalog.dart';
import 'package:specimen_widgetbook/environment.dart';
import 'package:specimen_widgetbook/product/fixture_repository.dart';
import 'package:specimen_widgetbook/product/local_routes.dart';
import 'package:specimen_widgetbook/product/product_preview.dart';
import 'package:specimen_widgetbook/story.dart';
import 'package:widgetbook/widgetbook.dart';

Future<void> showProduct(
  WidgetTester tester,
  ProductPreviewCase example, {
  Size size = const Size(1440, 900),
  bool dark = false,
  bool rtl = false,
  double scale = 1,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      builder: (context, _) => MediaQuery(
        data: MediaQuery.of(
          context,
        ).copyWith(textScaler: TextScaler.linear(scale)),
        child: SpecimenEnvironmentScope(
          setting: SpecimenEnvironment(
            dark: dark,
            direction: rtl ? TextDirection.rtl : TextDirection.ltr,
            reduceMotion: true,
          ),
          child: ProductPreview(key: ValueKey(example), example: example),
        ),
      ),
    ),
  );
  await tester.runAsync(
    () async => Future<void>.delayed(const Duration(milliseconds: 30)),
  );
  await tester.pumpAndSettle();
}

Future<void> closeProduct(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump();
}

Finder button(String label) => find.byWidgetPredicate(
  (widget) => widget is UiButton && widget.label == label,
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  test('all six cases are registered as product screens', () {
    final root = WidgetbookRoot(children: specimenCatalog);
    final cases = root.leaves.whereType<WidgetbookUseCase>().where(
      (item) => item.path.startsWith('product-screens/'),
    );
    expect(cases, hasLength(6));
  });
  testWidgets(
    'Queue previews render production screens and recover from failure',
    (tester) async {
      await showProduct(tester, ProductPreviewCase.queueLoaded);
      expect(find.byType(QueueScreen), findsOneWidget);
      expect(find.byType(StoryFrame), findsNothing);
      expect(find.text('#synthetic-label'), findsOneWidget);
      await closeProduct(tester);
      await showProduct(tester, ProductPreviewCase.queueEmpty);
      expect(find.byType(QueueScreen), findsOneWidget);
      expect(find.text('#synthetic-label'), findsNothing);
      expect(tester.takeException(), isNull);
      await closeProduct(tester);
      await showProduct(tester, ProductPreviewCase.queueError);
      expect(
        find.text(
          'Synthetic queue failure. Retry to load the example. '
          'No records have been loaded yet.',
        ),
        findsOneWidget,
      );
      await WorkspaceScope.read(
        tester.element(find.byType(QueueScreen)),
      ).refresh();
      await tester.pumpAndSettle();
      expect(find.text('#synthetic-label'), findsOneWidget);
      expect(find.textContaining('Synthetic queue failure'), findsNothing);
      expect(tester.takeException(), isNull);
      await closeProduct(tester);
    },
  );
  testWidgets(
    'asset completion before the next frame preserves the initial route',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1440, 900);
      addTearDown(tester.view.reset);
      final pixels = ByteData.sublistView(
        File('assets/synthetic-label.png').readAsBytesSync(),
      );
      for (final example in [
        ProductPreviewCase.intakeSaved,
        ProductPreviewCase.workbench,
      ]) {
        final asset = Completer<ByteData?>();
        tester.binding.defaultBinaryMessenger.setMockMessageHandler(
          'flutter/assets',
          (message) {
            expect(
              utf8.decode(
                message!.buffer.asUint8List(
                  message.offsetInBytes,
                  message.lengthInBytes,
                ),
              ),
              'assets/synthetic-label.png',
            );
            return asset.future;
          },
        );
        addTearDown(
          () => tester.binding.defaultBinaryMessenger.setMockMessageHandler(
            'flutter/assets',
            null,
          ),
        );
        await tester.pumpWidget(
          MaterialApp(
            builder: (context, _) => SpecimenEnvironmentScope(
              setting: const SpecimenEnvironment(reduceMotion: true),
              child: ProductPreview(key: ValueKey(example), example: example),
            ),
          ),
        );
        expect(find.byType(BulkIntakeScreen), findsNothing);
        expect(find.byType(WorkbenchScreen), findsNothing);
        // Match a browser asset callback between frames: drain all immediately
        // answered repository futures before the newly scheduled frame mounts
        // the inner Router. Reconfiguring an unmounted router loses its target.
        asset.complete(pixels);
        await tester.idle();
        await tester.pumpAndSettle();
        if (example == ProductPreviewCase.intakeSaved) {
          expect(find.byType(BulkIntakeScreen), findsOneWidget);
          expect(find.text('synthetic-label.png'), findsWidgets);
          expect(button('Retry saving'), findsNothing);
        } else {
          expect(find.byType(WorkbenchScreen), findsOneWidget);
          expect(find.byType(ReviewWorkbench), findsOneWidget);
        }
        expect(find.byType(QueueScreen), findsNothing);
        expect(tester.takeException(), isNull);
        await closeProduct(tester);
      }
    },
  );
  testWidgets('empty and saved Intake initialize without a save failure', (
    tester,
  ) async {
    for (final example in [
      ProductPreviewCase.intakeEmpty,
      ProductPreviewCase.intakeSaved,
    ]) {
      await showProduct(tester, example);
      expect(find.byType(BulkIntakeScreen), findsOneWidget);
      expect(button('Retry saving'), findsNothing);
      expect(find.textContaining('Could not save this change'), findsNothing);
      expect(find.text(PreviewRepository.writeMessage), findsNothing);
      if (example == ProductPreviewCase.intakeEmpty) {
        expect(button('Choose files'), findsOneWidget);
        expect(find.text('synthetic-label.png'), findsNothing);
      } else {
        expect(find.text('synthetic-label.png'), findsWidgets);
        expect(button('Submit 1 photo'), findsOneWidget);
      }
      expect(tester.takeException(), isNull);
      await closeProduct(tester);
    }
  });
  test(
    'preview repository still rejects draft writes and submissions',
    () async {
      final repository = PreviewRepository(
        example: ProductPreviewCase.intakeEmpty,
        pixels: Uint8List(0),
      );
      for (final path in ['/drafts', '/drafts/preview-draft/submit']) {
        await expectLater(
          repository.intakeRequest(PreviewRepository.scope, 'POST', path),
          throwsA(
            isA<ApiFailure>().having(
              (error) => error.message,
              'message',
              PreviewRepository.writeMessage,
            ),
          ),
        );
      }
    },
  );
  testWidgets('production navigation preserves the catalog platform URL', (
    tester,
  ) async {
    tester.platformDispatcher.defaultRouteNameTestValue =
        '/?path=product-screens/queue/loaded';
    addTearDown(tester.platformDispatcher.clearDefaultRouteNameTestValue);
    final reports = <MethodCall>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.navigation,
      (call) async {
        reports.add(call);
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.navigation,
        null,
      ),
    );
    await showProduct(tester, ProductPreviewCase.queueLoaded);
    final router = GoRouter.of(tester.element(find.byType(QueueScreen)));
    final scopeKey = encodeCollectionKey(PreviewRepository.scope.key);
    router.go(AppRoutes.specimenOf(scopeKey, 'preview-specimen-001'));
    await tester.pumpAndSettle();
    expect(find.byType(WorkbenchScreen), findsOneWidget);
    expect(find.byType(ReviewWorkbench), findsOneWidget);
    router.go(AppRoutes.queueOf(scopeKey));
    await tester.pumpAndSettle();
    expect(find.byType(QueueScreen), findsOneWidget);
    router.go(AppRoutes.intakeOf(scopeKey));
    await tester.pumpAndSettle();
    expect(find.byType(BulkIntakeScreen), findsOneWidget);
    expect(button('Choose files'), findsOneWidget);
    expect(button('Retry saving'), findsNothing);
    expect(find.textContaining('Could not save this change'), findsNothing);
    router.go(AppRoutes.queueOf(scopeKey));
    await tester.pumpAndSettle();
    expect(find.byType(QueueScreen), findsOneWidget);
    expect(
      reports.where((call) => call.method == 'routeInformationUpdated'),
      isEmpty,
    );
    expect(tester.takeException(), isNull);
    await closeProduct(tester);
  });
  testWidgets(
    'local provider retains parsed locations on refresh and ignores browser events',
    (tester) async {
      final router = GoRouter(
        initialLocation: '/one',
        overridePlatformDefaultLocation: true,
        routes: [
          GoRoute(path: '/one', builder: (_, _) => const SizedBox()),
          GoRoute(path: '/two', builder: (_, _) => const SizedBox()),
        ],
      );
      final provider = PreviewRouteInformationProvider(
        router.routeInformationProvider,
      );
      var notifications = 0;
      provider.addListener(() => notifications++);
      provider.routerReportsNewRouteInformation(
        RouteInformation(uri: Uri.parse('/two'), state: {'parsed': true}),
      );
      router.routeInformationProvider.notifyListeners();
      expect(provider.value.uri.path, '/two');
      final completer = Completer<void>();
      tester.binding.defaultBinaryMessenger.handlePlatformMessage(
        'flutter/navigation',
        const JSONMethodCodec().encodeMethodCall(
          const MethodCall('pushRouteInformation', {
            'location': '/catalog-external',
            'state': null,
          }),
        ),
        (_) => completer.complete(),
      );
      await completer.future;
      expect(provider.value.uri.path, '/two');
      router.go('/one');
      expect(provider.value.uri.path, '/one');
      expect(notifications, greaterThanOrEqualTo(2));
      provider.dispose();
      router.dispose();
    },
  );
  testWidgets(
    'Intake uses production batch screens and contained themed dialogs',
    (tester) async {
      await showProduct(
        tester,
        ProductPreviewCase.intakeSaved,
        dark: true,
        rtl: true,
        scale: 2,
      );
      expect(find.byType(BulkIntakeScreen), findsOneWidget);
      expect(find.text('synthetic-label.png'), findsWidgets);
      final screen = tester.element(find.byType(BulkIntakeScreen));
      expect(Directionality.of(screen), TextDirection.rtl);
      expect(MediaQuery.textScalerOf(screen).scale(16), 32);
      expect(screen.ui.color.ground, UiThemeData.dark().color.ground);
      final add = button('Add photos');
      await tester.ensureVisible(add);
      await tester.tap(add);
      await tester.pumpAndSettle();
      expect(button('Take photos'), findsOneWidget);
      final modal = tester.element(button('Take photos'));
      expect(Directionality.of(modal), TextDirection.rtl);
      expect(MediaQuery.textScalerOf(modal).scale(16), 32);
      expect(
        tester
            .getRect(find.byType(ProductPreview))
            .contains(tester.getRect(button('Take photos')).center),
        isTrue,
      );
      await tester.tap(button('Choose files'));
      await tester.pumpAndSettle();
      expect(find.textContaining('File selection is disabled'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await closeProduct(tester);
    },
  );
  testWidgets('retake fallback stays on the injected preview file picker', (
    tester,
  ) async {
    for (final size in [const Size(1440, 900), const Size(390, 844)]) {
      await showProduct(tester, ProductPreviewCase.intakeSaved, size: size);
      final photo = find.byWidgetPredicate(
        (widget) =>
            widget is Pressable &&
            widget.semanticsLabel == 'Review synthetic-label.png. Saved',
      );
      await tester.ensureVisible(photo);
      await tester.tap(photo);
      await tester.pumpAndSettle();
      await tester.ensureVisible(button('Retake photo'));
      await tester.tap(button('Retake photo'));
      await tester.pumpAndSettle();
      expect(find.textContaining('No camera found'), findsOneWidget);
      await tester.ensureVisible(button('Choose files'));
      await tester.tap(button('Choose files'));
      await tester.pumpAndSettle();
      final intake = tester.widget<BulkIntakeScreen>(
        find.byType(BulkIntakeScreen, skipOffstage: false),
      );
      expect(intake.pickFiles, isNotNull);
      final close = find.byWidgetPredicate(
        (widget) =>
            widget is UiIconButton &&
            widget.semanticsLabel == 'Close photo review',
      );
      await tester.ensureVisible(close);
      await tester.tap(close);
      await tester.pumpAndSettle();
      // The rejected injected picker displays this message; a platform picker
      // would instead invoke a plugin channel or show a native dialog.
      expect(find.textContaining('File selection is disabled'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await closeProduct(tester);
    }
  });

  testWidgets('screen previews adapt to narrow enlarged-text viewports', (
    tester,
  ) async {
    for (final example in [
      ProductPreviewCase.intakeEmpty,
      ProductPreviewCase.intakeSaved,
      ProductPreviewCase.workbench,
    ]) {
      await showProduct(
        tester,
        example,
        size: const Size(320, 720),
        scale: 2,
        rtl: true,
      );
      expect(find.byType(StoryFrame), findsNothing);
      expect(tester.takeException(), isNull, reason: example.name);
      await closeProduct(tester);
    }
  });
}
