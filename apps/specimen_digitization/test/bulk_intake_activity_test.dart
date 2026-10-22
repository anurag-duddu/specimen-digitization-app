import 'dart:async';
import 'dart:io';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_repository.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_screen.dart';
import 'package:specimen_digitization/src/workspace.dart'
    show WorkspaceBranchScope;
import 'bulk_draft_recovery_test.dart' show OfflineIntake;
import 'bulk_intake_test.dart' show BulkFixtureRepository;
import 'bulk_source_recovery_test.dart'
    show InterruptedSourceRepository, sourcePhotos, sourceScope;
import 'golden/golden_harness.dart' show goldenPreviewBytes;
import 'widgets/harness.dart';

class PausedFile extends XFile {
  PausedFile(super.path);
  final started = Completer<void>(), release = Completer<void>();
  @override
  Future<int> length() async {
    if (!started.isCompleted) started.complete();
    await release.future;
    return super.length();
  }
}

class ProgressRepository extends BulkFixtureRepository {
  ProgressRepository({this.total = 500}) : super(1);
  final int total;
  bool terminal = false, failPreview = false;
  bool workerError = false;
  int? failedIndex;
  List<String> retried = [];
  Completer<Json>? heldSummary;
  int summaries = 0, pages = 0, reads = 0, maxReads = 0, draftReads = 0;
  final List<String> observed = [];
  Json summary(String id) => {
    'id': id,
    'total': total,
    'counts': {
      terminal ? 'sent' : 'checking': total - (failedIndex == null ? 0 : 1),
      if (failedIndex != null) 'needs_attention': 1,
    },
    if (workerError) 'worker_error': {'message': 'Retry the saved batch.'},
  };
  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    reads++;
    if (reads > maxReads) maxReads = reads;
    try {
      if (method == 'POST' && path.endsWith('/retry')) {
        retried = List<String>.from(body!['item_ids'] as List);
        return {};
      }
      if (path.startsWith('/submissions/') && !path.endsWith('/items')) {
        summaries++;
        final id = path.split('/').last;
        observed.add(id);
        final gate = heldSummary;
        heldSummary = null;
        return gate == null ? summary(id) : await gate.future;
      }
      if (path.startsWith('/submissions/') && path.endsWith('/items')) {
        pages++;
        final start = int.tryParse(query?['after'] ?? '0') ?? 0;
        final end = (start + 100).clamp(0, total);
        return {
          'items': [
            for (var i = start; i < end; i++)
              {
                'item_id': 'photo-$i',
                'filename': 'photo-$i.png',
                'state': i == failedIndex
                    ? 'needs_attention'
                    : terminal
                    ? 'sent'
                    : 'checking',
              },
          ],
          'next_cursor': end < total ? '$end' : null,
        };
      }
      if (path == '/drafts/draft') draftReads++;
      return await super.intakeRequest(
        scope,
        method,
        path,
        body: body,
        query: query,
        bytes: bytes,
        offset: offset,
      );
    } finally {
      reads--;
    }
  }

  @override
  Future<Uint8List> intakePreview(
    CollectionScope scope,
    String itemId, {
    bool full = false,
  }) async {
    previewCalls++;
    if (failPreview) throw StateError('Fixture preview unavailable');
    return goldenPreviewBytes;
  }
}

class HeldDraftRepository extends InterruptedSourceRepository {
  bool hold = false;
  final started = Completer<void>(), release = Completer<void>();
  @override
  Future<Json> intakeRequest(
    CollectionScope scope,
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    Uint8List? bytes,
    int? offset,
  }) async {
    final response = await super.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
      bytes: bytes,
      offset: offset,
    );
    if (hold && method == 'GET' && path == '/drafts/draft/items') {
      hold = false;
      started.complete();
      await release.future;
    }
    return response;
  }
}

BulkIntakeController controllerFor(BulkIntakeRepository repository) =>
    BulkIntakeController(
        repository: repository,
        scope: sourceScope,
        userId: 'owner',
      )
      ..loading = false
      ..capabilities = {'bulk_source_admission': true};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));
  group('incremental private preparation', () {
    late Directory directory;
    const channel = MethodChannel('plugins.flutter.io/path_provider');
    setUp(() async {
      directory = await Directory.systemTemp.createTemp('intake-polish-');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (_) async => directory.path);
    });
    tearDown(() async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null);
      await directory.delete(recursive: true);
    });
    test(
      'first retained photo and progress publish before the next file is ready',
      () async {
        final first = File('${directory.path}/first.png')
          ..writeAsBytesSync([1, 2, 3]);
        final second = File('${directory.path}/second.png')
          ..writeAsBytesSync([4, 5, 6]);
        final delayed = PausedFile(second.path);
        final controller = controllerFor(OfflineIntake());
        addTearDown(controller.dispose);
        final operation = controller.addFiles([XFile(first.path), delayed]);
        await delayed.started.future;
        expect(controller.visible.single.name, 'first.png');
        expect(controller.preparingFiles, isTrue);
        expect(controller.preparationCompleted, 1);
        expect(controller.preparationTotal, 2);
        expect(await controller.submit(), isNull);
        delayed.release.complete();
        await operation;
        expect(controller.visible.length, 2);
        expect(controller.preparingFiles, isFalse);
        expect(controller.preparationCompleted, 2);
      },
    );
    test(
      'source admission and switching batches wait for queued preparation',
      () async {
        final original = File('${directory.path}/first.png')
          ..writeAsBytesSync([1, 2, 3]);
        final delayed = PausedFile(original.path);
        final repository = InterruptedSourceRepository()..interrupt = false;
        final controller = controllerFor(repository);
        addTearDown(controller.dispose);
        final preparing = controller.addFiles([delayed]);
        await delayed.started.future;
        final adding = controller.addSource(sourcePhotos(1));
        final switching = controller.newDraft();
        await Future<void>.delayed(Duration.zero);
        expect(repository.bulkRequests, isEmpty);
        delayed.release.complete();
        await preparing;
        await adding;
        expect(repository.photos.length, 1);
        await switching;
        expect(controller.visible, isEmpty);
        expect(repository.maxActiveWrites, 1);
        expect(controller.savedDrafts, isNotEmpty);
      },
    );
  });
  testWidgets(
    'terminal progress stops for60seconds and pages only on explicit demand',
    (tester) async {
      final repository = ProgressRepository()..terminal = true;
      final controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await pumpComponent(
        tester,
        BulkIntakeProgress(
          controller: controller,
          submissionId: 'one',
          onAdd: () {},
          onViewSpecimens: () {},
        ),
      );
      expect(controller.progressFor('one')!.items.length, 100);
      expect(repository.pages, 1);
      expect(
        find.text('500 of 500 finished · 500 sent to pipeline'),
        findsOneWidget,
      );
      final before = repository.summaries;
      await tester.pump(const Duration(seconds: 60));
      expect(repository.summaries, before);
      expect(repository.pages, 1);
      await controller.loadMoreProgress('one');
      await tester.pump();
      expect(controller.progressFor('one')!.items.length, 200);
      expect(repository.pages, 3);
      expect(controller.progressFor('one')!.hasMore, isTrue);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
  testWidgets(
    'overlapping progress requests coalesce and a hidden old reply cannot publish',
    (tester) async {
      final repository = ProgressRepository();
      final gate = Completer<Json>();
      repository.heldSummary = gate;
      final controller = controllerFor(repository);
      addTearDown(controller.dispose);
      final first = controller.observeSubmission('one');
      for (var i = 0; i < 10; i++) {
        unawaited(controller.poll(force: true));
      }
      await tester.pump(const Duration(seconds: 60));
      expect(repository.summaries, 1);
      expect(repository.maxReads, 1);
      controller.setViewActive(false);
      gate.complete(repository.summary('one'));
      await first;
      expect(controller.progressFor('one'), isNull);
      await tester.pump(const Duration(seconds: 60));
      expect(repository.summaries, 1);
      repository.terminal = true;
      controller.setViewActive(true);
      await tester.pump();
      await tester.pump();
      expect(repository.summaries, 2);
      expect(controller.progressFor('one')!.batch.active, isFalse);
      expect(repository.maxReads, 1);
    },
  );
  testWidgets('switching the observed submission fences the old response', (
    tester,
  ) async {
    final repository = ProgressRepository()..terminal = true;
    final gate = Completer<Json>();
    repository.heldSummary = gate;
    final controller = controllerFor(repository);
    addTearDown(controller.dispose);
    final first = controller.observeSubmission('old');
    final next = controller.observeSubmission('new');
    gate.complete(repository.summary('old'));
    await first;
    await next;
    expect(controller.progressFor('old'), isNull);
    expect(controller.progressFor('new')!.batch.id, 'new');
    expect(repository.observed, ['old', 'new']);
    expect(repository.maxReads, 1);
  });
  test(
    'a draft read started before admission cannot erase acknowledged photos',
    () async {
      final repository = HeldDraftRepository()..interrupt = false;
      final controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.addSource(sourcePhotos(1));
      repository.hold = true;
      final oldRead = controller.refreshDraft();
      await repository.started.future;
      await controller.addSource(sourcePhotos(1, start: 10));
      expect(controller.visible.length, 2);
      repository.release.complete();
      await oldRead;
      expect(controller.visible.length, 2);
    },
  );
  for (final failedOnly in [false, true]) {
    testWidgets(
      'explicit retry covers ${failedOnly ? 'a failed photo beyond' : 'the entire batch beyond'} the first100 rows',
      (tester) async {
        final repository = ProgressRepository()
          ..workerError = !failedOnly
          ..failedIndex = failedOnly ? 499 : null;
        final controller = controllerFor(repository);
        addTearDown(controller.dispose);
        await pumpComponent(
          tester,
          BulkIntakeProgress(
            controller: controller,
            submissionId: 'one',
            onAdd: () {},
            onViewSpecimens: () {},
          ),
        );
        expect(repository.pages, 1);
        final button = find.text(
          failedOnly ? 'Retry failed photos' : 'Retry batch',
        );
        await tester.ensureVisible(button);
        await tester.tap(button);
        await tester.pumpAndSettle();
        expect(
          repository.retried,
          failedOnly ? ['photo-499'] : List.generate(500, (i) => 'photo-$i'),
        );
        expect(controller.progressFor('one')!.items.length, 100);
        expect(repository.maxReads, 1);
        await tester.pumpWidget(const SizedBox.shrink());
      },
    );
  }
  testWidgets(
    'explicit repair refuses an invalidated read instead of using cached first-page results',
    (tester) async {
      final repository = ProgressRepository()..failedIndex = 499;
      final controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await controller.observeSubmission('one');
      expect(controller.progressFor('one')!.items.length, 100);
      final old = Completer<Json>(), replacement = Completer<Json>();
      repository.heldSummary = old;
      final repair = controller.progressItemsForAction('one');
      await tester.pump();
      await controller.call(
        'POST',
        '/submissions/one/retry',
        body: {'item_ids': <String>[]},
      );
      repository.heldSummary = replacement;
      old.complete(repository.summary('one'));
      await expectLater(repair, throwsA(isA<ApiFailure>()));
      expect(repository.retried, isEmpty);
      replacement.complete(repository.summary('one'));
      await tester.pump();
      await tester.pump();
      controller.setViewActive(false);
    },
  );
  testWidgets(
    'retained branch, covering modal and app background stop reads and resume once',
    (tester) async {
      final repository = ProgressRepository();
      repository.photos.single['state'] = 'checking';
      final controller = controllerFor(repository);
      await controller.initialize();
      addTearDown(controller.dispose);
      Future<void> render(bool active) => pumpComponent(
        tester,
        WorkspaceBranchScope(
          active: active,
          collectionKey: sourceScope.key,
          child: BulkIntakeScreen(
            key: const ValueKey('intake'),
            repository: repository,
            scope: sourceScope,
            userId: 'owner',
            controller: controller,
            onViewSpecimens: () {},
          ),
        ),
      );
      await render(true);
      await render(false);
      final hidden = repository.draftReads;
      await tester.pump(const Duration(seconds: 60));
      expect(repository.draftReads, hidden);
      await render(true);
      expect(repository.draftReads, hidden + 1);
      await tester.tap(find.text('Your batches'));
      await tester.pumpAndSettle();
      final covered = repository.draftReads;
      await tester.pump(const Duration(seconds: 60));
      expect(repository.draftReads, covered);
      Navigator.of(tester.element(find.text('Your batches').last)).pop();
      await tester.pumpAndSettle();
      expect(repository.draftReads, covered + 1);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      final background = repository.draftReads;
      await tester.pump(const Duration(seconds: 60));
      expect(repository.draftReads, background);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      await tester.pump();
      expect(repository.draftReads, background + 1);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
  testWidgets(
    'failed preview stays bounded until explicit retry replaces the failed future',
    (tester) async {
      final repository = ProgressRepository()..failPreview = true;
      final controller = controllerFor(repository);
      addTearDown(controller.dispose);
      const item = IntakeDraftItem({
        'id': 'photo',
        'state': 'ready',
        'revision': 1,
      });
      await pumpComponent(
        tester,
        MediaQuery(
          data: MediaQueryData(textScaler: TextScaler.linear(2)),
          child: SizedBox(
            width: 84,
            height: 84,
            child: BulkPhotoPreview(controller: controller, item: item),
          ),
        ),
      );
      expect(
        find.byWidgetPredicate(
          (widget) =>
              widget is UiIconButton &&
              widget.semanticsLabel == 'Retry preview for Photo',
        ),
        findsOneWidget,
      );
      expect(repository.previewCalls, 1);
      await tester.pump();
      expect(repository.previewCalls, 1);
      repository.failPreview = false;
      await tester.tap(
        find.byWidgetPredicate(
          (widget) =>
              widget is UiIconButton &&
              widget.semanticsLabel == 'Retry preview for Photo',
        ),
      );
      await tester.pumpAndSettle();
      expect(repository.previewCalls, 2);
      expect(
        find.byWidgetPredicate(
          (widget) =>
              widget is UiIconButton &&
              widget.semanticsLabel == 'Retry preview for Photo',
        ),
        findsNothing,
      );
      expect(find.byType(Image), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
  testWidgets(
    'unsaved remote content keeps its placeholder until a preview exists',
    (tester) async {
      final repository = ProgressRepository();
      final controller = controllerFor(repository);
      addTearDown(controller.dispose);
      await pumpComponent(
        tester,
        BulkPhotoPreview(
          controller: controller,
          item: const IntakeDraftItem({
            'id': 'waiting-photo',
            'state': 'waiting',
          }),
        ),
      );
      expect(find.byType(UiIconButton), findsNothing);
      expect(repository.previewCalls, 0);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
