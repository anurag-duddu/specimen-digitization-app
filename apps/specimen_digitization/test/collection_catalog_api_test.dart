import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';

ApiSpecimenRepository repository(Object? hierarchy) => ApiSpecimenRepository(
  baseUrl: Uri.parse('https://fixture.invalid'),
  token: () async => 'fixture',
  appCheckToken: () async => 'fixture',
  client: MockClient(
    (request) async => http.Response(
      jsonEncode(
        request.url.path == '/v1/session'
            ? {
                'user_id': 'fixture-user',
                'mode': 'production',
                'memberships': [
                  {
                    'organization_id': 'org',
                    'collection_id': 'insects',
                    'role': 'reviewer',
                  },
                ],
              }
            : {
                'items': [
                  {
                    'collection_id': 'insects',
                    'display_name': 'Insects',
                    'kind': 'museum',
                    'is_default': true,
                  },
                ],
                'hierarchy': ?hierarchy,
              },
      ),
      200,
    ),
  ),
);

void main() {
  test(
    'catalog metadata and default selection never grant its other collections',
    () async {
      final scopes = await repository([
        {'collection_id': 'zoology', 'display_name': 'Zoology'},
        {
          'collection_id': 'insects',
          'display_name': 'Insects',
          'parent_collection_id': 'zoology',
        },
        {
          'collection_id': 'birds',
          'display_name': 'Birds',
          'parent_collection_id': 'zoology',
          'selectable': true,
        },
        {
          'collection_id': 'test',
          'display_name': 'Test archive',
          'parent_collection_id': 'insects',
          'kind': 'testing',
        },
      ]).scopes();
      expect(scopes, hasLength(1));
      expect(scopes.single.collectionId, 'insects');
      expect(scopes.single.defaultSelection, isTrue);
      expect(scopes.single.catalogNodes, hasLength(4));
      expect(scopes.single.catalogNodes[1].parentCollectionId, 'zoology');
      expect(scopes.single.catalogNodes.last.testing, isTrue);
    },
  );
  test('older server without hierarchy retains granted scope', () async {
    final scopes = await repository(null).scopes();
    expect(scopes.single.catalogNodes, isEmpty);
  });
  for (final invalid in <String, Object>{
    'wrong shape': 'tree',
    'cycle': [
      {'collection_id': 'a', 'display_name': 'A', 'parent_collection_id': 'b'},
      {'collection_id': 'b', 'display_name': 'B', 'parent_collection_id': 'a'},
    ],
    'orphan': [
      {
        'collection_id': 'a',
        'display_name': 'A',
        'parent_collection_id': 'absent',
      },
    ],
    'duplicate': [
      {'collection_id': 'a', 'display_name': 'A'},
      {'collection_id': 'a', 'display_name': 'B'},
    ],
    'cross organization': [
      {'collection_id': 'a', 'display_name': 'A', 'organization_id': 'other'},
    ],
    'invalid kind': [
      {'collection_id': 'a', 'display_name': 'A', 'kind': 'grant'},
    ],
  }.entries) {
    test('malformed ${invalid.key} context fails closed', () async {
      await expectLater(
        repository(invalid.value).scopes(),
        throwsA(
          isA<ApiFailure>().having(
            (failure) => failure.code,
            'code',
            'invalid_collections',
          ),
        ),
      );
    });
  }
}
