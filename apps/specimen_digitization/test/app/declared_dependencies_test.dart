// The dependency gate (`declared_dependencies`).
//
// A package in `dependencies:` is in the bundle whether or not a line of the
// product ever calls it. `firebase_storage` and `firebase_data_connect` were
// declared for a design the client never took: photographs go up through the
// scoped API's `PUT /uploads/{id}/content` and every record is read and
// written through the same API, so neither package was ever imported. They
// were weight in `main.dart.js`, a plugin registered on every platform, and
// an attack surface for a capability the product does not have.
//
// The rule this holds is narrow and absolute: every package the application
// declares is imported by a file under `lib/`. It is the same shape as
// `google_fonts is gone from the dependency graph` in the font gate, except
// that it names nothing, so it covers the next unused package too.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Declared packages that no file under `lib/` can import, with the reason.
///
/// Empty, and it is meant to stay empty. An entry here is a claim that a
/// package earns its place in the bundle without appearing in the source,
/// which is true of almost nothing. `dev_dependencies` are not in scope: they
/// are tools, they are not in the bundle, and `flutter_launcher_icons` and
/// `flutter_native_splash` are run by hand rather than imported.
const Map<String, String> allowedWithoutImport = <String, String>{};

/// The `dependencies:` block, as package names.
///
/// Read out of the file rather than restated, so a package added without an
/// import reaches this gate without anybody editing it.
Set<String> declaredDependencies(String pubspec) {
  final List<String> lines = pubspec.split('\n');
  final Set<String> names = <String>{};
  bool inside = false;
  for (final String line in lines) {
    if (line.startsWith('dependencies:')) {
      inside = true;
      continue;
    }
    // Any other top level key ends the block: `dev_dependencies:`,
    // `dependency_overrides:`, `flutter:`.
    if (inside && line.isNotEmpty && !line.startsWith(' ')) break;
    if (!inside) continue;
    final RegExpMatch? match = RegExp(
      r'^  ([a-z_][a-z0-9_]*):',
    ).firstMatch(line);
    if (match != null) names.add(match.group(1)!);
  }
  return names;
}

void main() {
  test('the dependencies block is read, not assumed', () {
    final Set<String> declared = declaredDependencies(
      File('pubspec.yaml').readAsStringSync(),
    );
    // A parser that silently returned nothing would make every assertion
    // below pass over an empty set.
    expect(declared, contains('flutter'));
    expect(declared, contains('firebase_core'));
    expect(declared, contains('specimen_ui'));
    expect(declared.length, greaterThan(5));
    // The blocks below `dependencies:` are not part of it.
    expect(declared, isNot(contains('flutter_test')));
    expect(declared, isNot(contains('flutter_lints')));
    expect(declared, isNot(contains('firebase_core_web')));
  });

  test('every declared package is imported by a file under lib/', () {
    final Set<String> declared = declaredDependencies(
      File('pubspec.yaml').readAsStringSync(),
    );
    final StringBuffer source = StringBuffer();
    for (final FileSystemEntity entity in Directory(
      'lib',
    ).listSync(recursive: true)) {
      if (entity is File && entity.path.endsWith('.dart')) {
        source.writeln(entity.readAsStringSync());
      }
    }
    final String text = source.toString();

    final List<String> unused = <String>[];
    for (final String name in declared) {
      if (allowedWithoutImport.containsKey(name)) continue;
      if (!text.contains('package:$name/')) unused.add(name);
    }
    unused.sort();
    expect(
      unused,
      isEmpty,
      reason:
          'these packages are in the bundle and in no import: '
          '${unused.join(', ')}. Remove them from pubspec.yaml, or add an '
          'entry to allowedWithoutImport saying what earns the weight.',
    );
  });

  test('the two the client never used are out of the dependency graph', () {
    // Named rather than left to the rule above, because the lockfile is where
    // a removal that forgot `flutter pub get` would still be visible, and
    // because a transitive path back to either of them is a change worth
    // seeing rather than an accident.
    final Set<String> declared = declaredDependencies(
      File('pubspec.yaml').readAsStringSync(),
    );
    final String lock = File('pubspec.lock').readAsStringSync();
    for (final String name in <String>[
      'firebase_storage',
      'firebase_data_connect',
    ]) {
      // Asked of the parsed block, not of the file: the comment that says why
      // they are gone names them both, and a containment test over the whole
      // file would be answered by the explanation.
      expect(
        declared,
        isNot(contains(name)),
        reason: '$name is declared again',
      );
      expect(
        lock,
        isNot(contains('$name:')),
        reason: '$name is resolvable again, so it is back in the bundle',
      );
    }
  });

  test('the firebase_core_web override still has something to override', () {
    // The override is pinned for this toolchain (Flutter 3.38.5, Dart
    // 3.10.4). It is only meaningful while a declared package still pulls
    // firebase_core_web in, which after the removal is firebase_core,
    // firebase_auth and firebase_app_check by way of their web
    // implementations.
    final String pubspec = File('pubspec.yaml').readAsStringSync();
    expect(pubspec, contains('firebase_core_web: 3.10.0'));
    final Set<String> declared = declaredDependencies(pubspec);
    expect(
      declared.intersection(<String>{
        'firebase_core',
        'firebase_auth',
        'firebase_app_check',
      }),
      isNotEmpty,
      reason:
          'nothing needs firebase_core_web any more, so the override in '
          'pubspec.yaml is pinning a package that is not in the graph',
    );
    expect(
      File('pubspec.lock').readAsStringSync(),
      contains('firebase_core_web'),
    );
  });
}
