import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:specimen_digitization/src/api_repository.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/reading_declarations.dart';
import 'package:specimen_digitization/src/workbench.dart';

void main() {
  final fixture =
      jsonDecode(
            File(
              'test/fixtures/backend-declarations-wire-examples.json',
            ).readAsStringSync(),
          )
          as Json;
  final mixed = fixture['cases']['mixed'] as Json;
  final workspace = mixed['workspace'] as Json;
  final scope = CollectionScope(
    organizationId: workspace['organization_id'],
    collectionId: workspace['collection_id'],
    name: 'Synthetic declarations',
  );
  test(
    'exact human declaration request retains CAS and immutable model evidence',
    () async {
      final human = mixed['human_decisions'][0] as Json;
      var changed = false;
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8018'),
        token: () async => 'test-only',
        client: MockClient((r) async {
          if (r.method == 'POST') {
            final body = jsonDecode(r.body) as Json;
            final expected = human['request'] as Json;
            for (final key in expected.keys) {
              expect(body[key], expected[key]);
            }
            expect(body['after'].keys.toSet(), {
              'language_candidates',
              'script_candidates',
              'language_relation',
            });
            expect(r.headers['Idempotency-Key'], 'declaration-key');
            changed = true;
            return http.Response(jsonEncode(human['response']), 200);
          }
          if (r.url.path.endsWith('/workspace')) {
            return http.Response(
              jsonEncode(changed ? human['response'] : workspace),
              200,
            );
          }
          if (r.url.path.contains('/assets/')) return http.Response('', 404);
          throw StateError('Unexpected request ${r.url}');
        }),
      );
      final before = await repo.specimen(scope, workspace['specimen_id']);
      final after = await repo.review(scope, before, {
        'kind': 'reading_metadata',
        'target_id': human['request']['target_id'],
        'reason': human['request']['reason'],
        ...human['request']['after'] as Json,
      }, 'declaration-key');
      expect(after.revision, before.revision + 1);
      expect(after.observations, before.observations);
      expect(after.data['run']['human_approved'], false);
      expect(after.data['run']['reading_declarations'], isNotEmpty);
    },
  );
  test(
    'declaration provenance uses current auth, pinned revision and observation identity',
    () async {
      final provenance = mixed['declaration_provenance'] as Json;
      var tamper = false;
      final repo = ApiSpecimenRepository(
        baseUrl: Uri.parse('http://localhost:8018'),
        token: () async => 'new-test-token',
        client: MockClient((r) async {
          expect(
            r.url.path.endsWith(
              '/observations/${provenance['observation_id']}/declarations',
            ),
            true,
          );
          expect(r.url.queryParameters, {
            'revision': '${workspace['revision']}',
          });
          expect(r.headers['Authorization'], 'Bearer new-test-token');
          return http.Response(
            jsonEncode({...provenance, if (tamper) 'revision': 999}),
            200,
          );
        }),
      );
      final record = Specimen(workspace);
      final request = ArtifactRequest(
        ArtifactKind.readingDeclarations,
        provenance['observation_id'],
      );
      expect(await repo.artifact(scope, record, request), provenance);
      tamper = true;
      await expectLater(
        repo.artifact(scope, record, request),
        throwsA(
          isA<ApiFailure>().having((e) => e.code, 'code', 'invalid_evidence'),
        ),
      );
    },
  );
  testWidgets(
    'label policy distinguishes mixed, conflicting and unknown without inferred confidence',
    (tester) async {
      for (final name in ['mixed', 'conflicting', 'unknown']) {
        final handling =
            fixture['cases'][name]['workspace']['run']['label_language_handling']
                as Json;
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SingleChildScrollView(
                child: LabelLanguagePolicy(handling: handling),
              ),
            ),
          ),
        );
        expect(
          find.text(
            'Multiple languages declared together: ${name == 'mixed' ? 'Yes' : 'No'}',
          ),
          findsOneWidget,
        );
        expect(
          find.text(
            'Conflicting candidate interpretations: ${name == 'conflicting' ? 'Yes' : 'No'}',
          ),
          findsOneWidget,
        );
        expect(
          find.text('Language confidence is not measured.'),
          findsOneWidget,
        );
        expect(
          find.textContaining('Policy language-handling-v1'),
          findsOneWidget,
        );
        if (name == 'unknown') {
          expect(
            find.text('Languages: Not declared · Scripts: Not declared'),
            findsOneWidget,
          );
        }
      }
    },
  );
  testWidgets(
    'human history keeps model declaration and supersession distinct',
    (tester) async {
      final provenance =
          mixed['human_decisions'][1]['declaration_provenance'] as Json;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: ReadingDeclarationView(provenance: provenance),
            ),
          ),
        ),
      );
      expect(find.text('Model languages: English, German'), findsOneWidget);
      expect(find.text('Superseded human declaration'), findsOneWidget);
      expect(find.text('Current human declaration'), findsOneWidget);
      expect(find.text('Languages: French · Scripts: Latin'), findsOneWidget);
      expect(find.text('Languages: Italian · Scripts: Latin'), findsOneWidget);
      expect(find.text('Record language and script declaration'), findsNothing);
    },
  );
  testWidgets(
    'declaration editing requires explicit server action and reviewer permission',
    (tester) async {
      final actions = jsonDecode(
        File(
          'test/fixtures/backend-declaration-actions-wire-examples.json',
        ).readAsStringSync(),
      )['responses']['workspace']['body_projection']['available_actions'];
      Future<void> show(List<dynamic> allowed, bool reviewer) async {
        final record = Specimen({
          ...workspace,
          'available_actions': allowed,
          'observations': [workspace['observations'][0]],
        });
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ReviewWorkbench(
                specimen: record,
                canReview: reviewer,
                onChange: (_) async {},
                onRetry: (_) async {},
                onRefresh: () {},
                loadArtifact: (_) async =>
                    mixed['declaration_provenance'] as Json,
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
      }

      await show([], true);
      await tester.ensureVisible(find.text('Read declaration provenance'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Read declaration provenance'));
      await tester.pumpAndSettle();
      expect(find.text('Record language and script declaration'), findsNothing);
      await show(List<dynamic>.from(actions), true);
      expect(
        find.text('Record language and script declaration'),
        findsOneWidget,
      );
      await show(List<dynamic>.from(actions), false);
      expect(find.text('Record language and script declaration'), findsNothing);
    },
  );
  testWidgets(
    'declaration form requires reason and explicit valid language relationship',
    (tester) async {
      Json? saved;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () async {
                  saved = await showDialog<Json>(
                    context: context,
                    builder: (_) => const ReadingDeclarationDialog(
                      observationId: 'observation-test',
                    ),
                  );
                },
                child: const Text('Open declaration'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open declaration'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save declaration'));
      await tester.pumpAndSettle();
      expect(find.text('A reason is required.'), findsOneWidget);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Language candidates'),
        'English',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Script candidates'),
        'Latin',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Reason for declaration'),
        'Visible two-language source',
      );
      await tester.ensureVisible(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Multiple languages on this label').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save declaration'));
      await tester.pumpAndSettle();
      expect(
        find.text('This relationship requires at least 2 distinct languages.'),
        findsOneWidget,
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Language candidates'),
        'English\nDeutsch',
      );
      await tester.tap(find.text('Save declaration'));
      await tester.pumpAndSettle();
      expect(saved, {
        'kind': 'reading_metadata',
        'target_id': 'observation-test',
        'reason': 'Visible two-language source',
        'language_candidates': ['English', 'Deutsch'],
        'script_candidates': ['Latin'],
        'language_relation': 'cooccurring',
      });
    },
  );
}
