import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('application and catalog resolve the canonical shared UI source', () {
    final repository = Directory(Directory('../..').resolveSymbolicLinksSync());
    final shared = Directory.fromUri(
      repository.uri.resolve(
        'apps/specimen_digitization/packages/specimen_ui/',
      ),
    );
    final application = _requireSharedSource(
      File('../specimen_digitization/.dart_tool/package_config.json'),
      shared,
    );
    final catalog = _requireSharedSource(
      File('.dart_tool/package_config.json'),
      shared,
    );
    expect(application, catalog);
  });

  group('shared package resolution guard', () {
    late Directory temporary;
    late Directory shared;
    late File config;

    setUp(() {
      temporary = Directory(
        Directory.systemTemp
            .createTempSync('shared-ui-source-')
            .resolveSymbolicLinksSync(),
      );
      shared = Directory.fromUri(temporary.uri.resolve('shared/specimen_ui/'));
      Directory.fromUri(shared.uri.resolve('lib/')).createSync(recursive: true);
      config = File.fromUri(
        temporary.uri.resolve('catalog/.dart_tool/package_config.json'),
      );
      config.parent.createSync(recursive: true);
    });

    tearDown(() => temporary.deleteSync(recursive: true));

    void writeConfig({
      String rootUri = '../../shared/specimen_ui',
      String packageUri = 'lib/',
      int entries = 1,
    }) {
      config.writeAsStringSync(
        jsonEncode({
          'configVersion': 2,
          'packages': [
            for (var index = 0; index < entries; index++)
              {
                'name': 'specimen_ui',
                'rootUri': rootUri,
                'packageUri': packageUri,
              },
          ],
        }),
      );
    }

    test('relative roots resolve from the config file, not the process', () {
      writeConfig();
      final source = _requireSharedSource(config, shared);
      expect(source.root, shared.resolveSymbolicLinksSync());
      expect(
        source.library,
        Directory.fromUri(
          shared.uri.resolve('lib/'),
        ).resolveSymbolicLinksSync(),
      );
    });

    test('absolute file roots resolve to the same source', () {
      writeConfig(rootUri: shared.uri.toString());
      expect(
        _requireSharedSource(config, shared).root,
        shared.resolveSymbolicLinksSync(),
      );
    });

    test('a cached or copied package cannot replace the shared source', () {
      for (final substitute in [
        'pub-cache/specimen_ui',
        'copied/specimen_ui',
      ]) {
        final copy = Directory.fromUri(temporary.uri.resolve('$substitute/'));
        Directory.fromUri(copy.uri.resolve('lib/')).createSync(recursive: true);
        writeConfig(rootUri: copy.uri.toString());
        expect(() => _requireSharedSource(config, shared), throwsStateError);
      }
    });

    test(
      'a redirected library cannot hide behind the correct package root',
      () {
        Directory.fromUri(shared.uri.resolve('copied_lib/')).createSync();
        writeConfig(packageUri: 'copied_lib/');
        expect(() => _requireSharedSource(config, shared), throwsStateError);
      },
    );

    test('missing and duplicate package entries fail closed', () {
      for (final entries in [0, 2]) {
        writeConfig(entries: entries);
        expect(
          () => _requireSharedSource(config, shared),
          throwsFormatException,
        );
      }
    });

    test('an absent generated config reports the dependency setup step', () {
      expect(
        () => _requireSharedSource(config, shared),
        throwsA(
          isA<StateError>().having(
            (error) => error.message,
            'setup guidance',
            contains('flutter pub get --enforce-lockfile'),
          ),
        ),
      );
    });
  });
}

({String root, String library}) _requireSharedSource(
  File config,
  Directory expected,
) {
  if (!config.existsSync()) {
    throw StateError(
      'Missing ${config.path}. Run flutter pub get --enforce-lockfile in '
      'both apps/specimen_digitization and apps/specimen_widgetbook.',
    );
  }
  final document =
      jsonDecode(config.readAsStringSync()) as Map<String, dynamic>;
  if (document['configVersion'] != 2) {
    throw const FormatException('Expected package config version 2.');
  }
  final entries = (document['packages'] as List<dynamic>)
      .cast<Map<String, dynamic>>()
      .where((entry) => entry['name'] == 'specimen_ui')
      .toList();
  if (entries.length != 1) {
    throw const FormatException('Expected exactly one specimen_ui package.');
  }
  final entry = entries.single;
  final rootUri = config.absolute.uri.resolve(entry['rootUri'] as String);
  if (rootUri.scheme != 'file') {
    throw const FormatException(
      'The shared UI package must be a local source.',
    );
  }
  final root = Directory.fromUri(rootUri);
  final library = Directory.fromUri(
    root.uri.resolve(entry['packageUri'] as String? ?? ''),
  );
  final source = (
    root: root.resolveSymbolicLinksSync(),
    library: library.resolveSymbolicLinksSync(),
  );
  final canonicalExpected = Directory(expected.resolveSymbolicLinksSync());
  if (canonicalExpected.uri != expected.absolute.uri ||
      source.root != canonicalExpected.path ||
      Directory(source.library).uri != canonicalExpected.uri.resolve('lib/')) {
    throw StateError(
      '${config.path} must use ${expected.absolute.path}/lib; '
      'resolved package ${source.root}, library ${source.library}.',
    );
  }
  return source;
}
