// The stand-in gate.
//
// Wave 1 built the five control families in parallel, so a family that needed
// a sibling's control before it existed built a private one and marked it
// `TODO(fe/<family>)`. Every one of those is now the real control. This gate
// is what keeps the next parallel wave from leaving one behind: a stand-in
// that outlives its wave is a second implementation of a control, which is
// the one thing a design system exists to prevent (10 section 0, property 6).

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The marker a cross-family stand-in carries.
final RegExp _standIn = RegExp(r'TODO\(fe/');

/// Every Dart file under `lib/`, by path relative to the package root.
List<File> _libraryFiles() {
  final Directory root = Directory('lib');
  expect(
    root.existsSync(),
    isTrue,
    reason: 'run this test from the package root',
  );
  return <File>[
    for (final FileSystemEntity entity in root.listSync(recursive: true))
      if (entity is File && entity.path.endsWith('.dart')) entity,
  ]..sort((File a, File b) => a.path.compareTo(b.path));
}

void main() {
  test('the gate is looking at the package it thinks it is', () {
    expect(_libraryFiles(), isNotEmpty);
  });

  test('no cross-family stand-in is left under lib', () {
    final List<String> found = <String>[];
    for (final File file in _libraryFiles()) {
      final List<String> lines = file.readAsLinesSync();
      for (int i = 0; i < lines.length; i++) {
        if (_standIn.hasMatch(lines[i])) {
          found.add('${file.path}:${i + 1}: ${lines[i].trim()}');
        }
      }
    }
    expect(
      found,
      isEmpty,
      reason:
          'a control that stands in for another family\'s control is a second '
          'implementation of it. Swap it for the real one and delete the '
          'stand-in, or, if the sibling has not merged yet, say so in the '
          'slot\'s closeout rather than shipping both.\n${found.join('\n')}',
    );
  });
}
