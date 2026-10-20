import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/intake/bulk_intake_controller.dart';

import 'bulk_intake_test.dart' show BulkFixtureRepository;

const scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'collection',
  name: 'Collection',
);

class LostSubmitAck extends BulkFixtureRepository {
  LostSubmitAck() : super(1);
  bool loseAck = true;

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
    final result = await super.intakeRequest(
      scope,
      method,
      path,
      body: body,
      query: query,
      bytes: bytes,
      offset: offset,
    );
    if (path.endsWith('/submit') && loseAck) {
      loseAck = false;
      throw const ApiFailure('Connection interrupted.', code: 'network');
    }
    return result;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));

  for (final changedField in ['photo_sensitive', 'included', 'removed']) {
    test(
      'submit requires review after another tab changes $changedField',
      () async {
        final repo = BulkFixtureRepository(1);
        repo.photos.single['photo_sensitive'] = true;
        final controller = BulkIntakeController(
          repository: repo,
          scope: scope,
          userId: 'owner',
        );
        addTearDown(controller.dispose);
        await controller.initialize();
        repo.photos.single[changedField] = changedField == 'removed';
        repo.revision++;

        expect(await controller.submit(), isNull);
        expect(repo.submitted, isFalse);
        expect(controller.error, contains('Review the updated photos'));
        expect(controller.draft!.revision, repo.revision);
        if (changedField == 'photo_sensitive') {
          expect(controller.visible.single.sensitive, isFalse);
          expect(await controller.submit(), isNotNull);
        }
      },
    );
  }

  test(
    'new unseen photos do not change the reviewed submit selection',
    () async {
      final repo = BulkFixtureRepository(1);
      final controller = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      addTearDown(controller.dispose);
      await controller.initialize();
      repo.photos.add({...repo.photos.single, 'id': 'new-photo'});
      repo.revision++;

      expect(await controller.submit(), isNotNull);
      expect(repo.submittedIds, ['photo-0']);
    },
  );

  test(
    'lost submit acknowledgement can reconcile the same frozen selection',
    () async {
      final repo = LostSubmitAck();
      final controller = BulkIntakeController(
        repository: repo,
        scope: scope,
        userId: 'owner',
      );
      addTearDown(controller.dispose);
      await controller.initialize();

      expect(await controller.submit(), isNull);
      expect(repo.submitted, isTrue);
      expect(await controller.submit(), isNotNull);
      expect(repo.submittedIds, ['photo-0']);
    },
  );
}
