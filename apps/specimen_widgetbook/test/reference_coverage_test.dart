import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_widgetbook/catalog.dart';
import 'package:widgetbook/widgetbook.dart';

const _coverageDirectory = '../specimen_digitization/design/coverage';
const _auditFiles = <String>[
  'application-data.json',
  'foundations.json',
  'marketing-components.json',
  'navigation-feedback.json',
  'shared-components.json',
];

// These are file setup/navigation pages in the actual reference inventory.
// All other pages require implementation and a reachable component or story.
const _nonComponentPages = <String, String>{
  '1480:0': 'file_setup',
  '2210:441096': 'file_setup',
  '1624:431457': 'separator',
  '1624:431456': 'separator',
  '1624:431458': 'separator',
  '925:34508': 'section_label',
  '1030:33572': 'section_label',
  '1238:52': 'section_label',
  '1622:261458': 'section_label',
  '1622:261457': 'section_label',
  '1664:398801': 'section_label',
  '1215:104942': 'section_label',
};
const _parityLimit =
    'Page and story registration does not establish complete variant, '
    'interaction, visual, assistive technology or physical device parity.';

void main() {
  late Map<String, dynamic> reference;
  late Map<String, dynamic> coverage;
  late Map<String, Map<String, dynamic>> audits;
  late Map<String, dynamic> marketingInventory;
  late WidgetbookRoot root;
  late Set<String> declarations;

  setUp(() {
    reference = _read('reference-pages.json');
    coverage = _read('reference-coverage.json');
    audits = {for (final file in _auditFiles) file: _read(file)};
    marketingInventory = _read('marketing-reference-inventory.json');
    root = WidgetbookRoot(children: specimenCatalog);
    final declaration = RegExp(
      r'\b(?:class|enum|mixin|typedef)\s+([A-Za-z_$][\w$]*)',
    );
    declarations = {
      for (final source in Directory(
        '../specimen_digitization/packages/specimen_ui/lib',
      ).listSync(recursive: true).whereType<File>())
        if (source.path.endsWith('.dart'))
          for (final match in declaration.allMatches(source.readAsStringSync()))
            match.group(1)!,
    };
  });

  List<String> problems() => _validate(
    reference,
    coverage,
    audits,
    marketingInventory,
    root,
    declarations,
  );

  test(
    'all 95 reference pages reconcile to actual stories and family audits',
    () {
      expect(problems(), isEmpty, reason: problems().join('\n'));
    },
  );

  group('reference coverage fails closed', () {
    test(
      'a missing or duplicate reference page cannot disappear in totals',
      () {
        final pages = _rows(coverage['pages']);
        pages.removeLast();
        pages.add(Map<String, dynamic>.from(pages.first));
        coverage['pages'] = pages;
        expect(
          problems(),
          contains('Reference pages must appear exactly once.'),
        );
      },
    );

    test('a component page cannot be relabeled as a section heading', () {
      final page = _rows(
        coverage['pages'],
      ).firstWhere((page) => page['kind'] == 'component_or_example');
      page['kind'] = 'section_label';
      expect(problems(), contains('${page['pageId']}: incorrect page kind.'));
    });

    test('a source filename cannot substitute for a registered story', () {
      final audit = _rows(audits['application-data.json']!['rows']).first;
      audit['catalogPaths'] = [
        'apps/specimen_widgetbook/lib/catalog/data.dart',
      ];
      expect(
        problems().any(
          (problem) => problem.contains('unreachable catalog path'),
        ),
        isTrue,
      );
    });

    test('invented implementation names do not count as coverage', () {
      final audit = _rows(audits['application-data.json']!['rows']).first;
      audit['implementations'] = ['UiNonexistentReferenceControl'];
      expect(
        problems().any((problem) => problem.contains('unknown implementation')),
        isTrue,
      );
    });

    test('a page cannot omit a contributing family audit', () {
      final page = _rows(
        coverage['pages'],
      ).firstWhere((page) => page['kind'] == 'component_or_example');
      page['auditRefs'] = <String>[];
      expect(
        problems(),
        contains('${page['pageId']}: family audit links drifted.'),
      );
    });

    test('pending visual limits cannot become an approval claim', () {
      final page = _rows(
        coverage['pages'],
      ).firstWhere((page) => page['kind'] == 'component_or_example');
      page['visualParity'] = 'approved';
      page['pendingValidation'] = <String>[];
      expect(
        problems(),
        contains(
          '${page['pageId']}: structural coverage cannot approve parity.',
        ),
      );
      expect(
        problems(),
        contains('${page['pageId']}: pending validation drifted.'),
      );
    });

    test('raw reference variant families cannot lose their audit row', () {
      final rows = _rows(audits['marketing-components.json']!['rows']);
      rows.removeWhere((row) => row['family'] == 'header');
      audits['marketing-components.json']!['rows'] = rows;
      expect(
        problems(),
        contains(
          'Marketing reference family header must have exactly one audit.',
        ),
      );
    });

    test(
      'source variant counts remain reconciled with the family evidence',
      () {
        final family = _rows(marketingInventory['families']).first;
        family['variants'] = _rows(family['variants'])..removeLast();
        expect(
          problems(),
          contains('Marketing reference family header variant count drifted.'),
        );
      },
    );
  });
}

Map<String, dynamic> _read(String filename) =>
    jsonDecode(File('$_coverageDirectory/$filename').readAsStringSync())
        as Map<String, dynamic>;

List<Map<String, dynamic>> _rows(dynamic value) =>
    (value as List<dynamic>).cast<Map<String, dynamic>>();

List<String> _strings(dynamic value) => (value as List<dynamic>).cast<String>();

bool _sameStrings(Iterable<String> first, Iterable<String> second) {
  final left = first.toList()..sort();
  final right = second.toList()..sort();
  return jsonEncode(left) == jsonEncode(right);
}

List<String> _validate(
  Map<String, dynamic> reference,
  Map<String, dynamic> coverage,
  Map<String, Map<String, dynamic>> audits,
  Map<String, dynamic> marketingInventory,
  WidgetbookRoot root,
  Set<String> declarations,
) {
  final problems = <String>[];
  final referencePages = _rows(reference['pages']);
  final referenceNames = {
    for (final page in referencePages)
      page['id'] as String: page['name'] as String,
  };
  final pages = _rows(coverage['pages']);
  if (referencePages.length != 95 || referenceNames.length != 95) {
    problems.add('The source must contain 95 unique reference pages.');
  }
  if (coverage['referenceFileId'] != reference['referenceFileId'] ||
      coverage['sourceInventory'] != 'reference-pages.json' ||
      coverage['variantInventory'] != 'marketing-reference-inventory.json' ||
      coverage['schemaVersion'] != 1) {
    problems.add('Coverage must identify the exact reference inventory.');
  }
  if (coverage['coverageLevel'] != 'page_and_story_registration' ||
      coverage['parityStatus'] != 'not_approved') {
    problems.add('Structural coverage cannot claim visual or device approval.');
  }
  if (!_sameStrings(_strings(coverage['auditFiles']), _auditFiles)) {
    problems.add('All family audit files must participate.');
  }
  if (!_sameStrings(
    pages.map((page) => page['pageId'] as String),
    referenceNames.keys,
  )) {
    problems.add('Reference pages must appear exactly once.');
  }
  final auditsByPage = <String, Map<String, Map<String, dynamic>>>{};
  for (final entry in audits.entries) {
    final auditRows = _rows(entry.value['rows'] ?? entry.value['families']);
    final seenFamilies = <String>{};
    for (final row in auditRows) {
      final family = row['family'] as String;
      final pageId = row['pageId'] as String;
      final key = '${entry.key}#$family';
      if (!seenFamilies.add(family)) {
        problems.add('$key: duplicate audit family.');
      }
      if (!referenceNames.containsKey(pageId) ||
          _nonComponentPages.containsKey(pageId)) {
        problems.add(
          '$key: audit does not identify a component reference page.',
        );
      }
      (auditsByPage[pageId] ??= {})[key] = row;
      final implementations = _strings(row['implementations']);
      if (implementations.isEmpty) {
        problems.add('$key: no implementation named.');
      }
      for (final implementation in implementations) {
        if (!declarations.contains(implementation)) {
          problems.add('$key: unknown implementation $implementation.');
        }
      }
      final paths = _strings(row['catalogPaths']);
      if (paths.isEmpty || paths.toSet().length != paths.length) {
        problems.add('$key: catalog paths must be nonempty and unique.');
      }
      for (final path in paths) {
        final node = root.find((node) => node.path == path);
        final reachable =
            node is WidgetbookUseCase ||
            (node is WidgetbookComponent &&
                node.leaves.whereType<WidgetbookUseCase>().isNotEmpty);
        if (!reachable) problems.add('$key: unreachable catalog path $path.');
      }
    }
  }
  for (final page in pages) {
    final id = page['pageId'] as String;
    final kind = _nonComponentPages[id] ?? 'component_or_example';
    if (page['pageName'] != referenceNames[id]) {
      problems.add('$id: reference page name drifted.');
    }
    if (page['kind'] != kind) problems.add('$id: incorrect page kind.');
    if (kind != 'component_or_example') {
      if (page['structuralStatus'] != 'not_applicable' ||
          page['visualParity'] != 'not_applicable' ||
          _strings(page['catalogPaths']).isNotEmpty ||
          _strings(page['auditRefs']).isNotEmpty ||
          (page['reason'] as String).trim().isEmpty) {
        problems.add(
          '$id: file setup and navigation require explicit disposition.',
        );
      }
      continue;
    }
    final pageAudits = auditsByPage[id] ?? {};
    if (pageAudits.isEmpty || page['structuralStatus'] != 'mapped') {
      problems.add('$id: component reference page is not structurally mapped.');
    }
    if (!_sameStrings(_strings(page['auditRefs']), pageAudits.keys)) {
      problems.add('$id: family audit links drifted.');
    }
    final paths = {
      for (final audit in pageAudits.values) ..._strings(audit['catalogPaths']),
    };
    if (!_sameStrings(_strings(page['catalogPaths']), paths)) {
      problems.add('$id: registered story mapping drifted.');
    }
    final limits = {
      _parityLimit,
      for (final audit in pageAudits.values) ...[
        ..._strings(audit['remainingGaps'] ?? <String>[]),
        ..._strings(audit['pendingValidation'] ?? <String>[]),
      ],
    };
    if (!_sameStrings(_strings(page['pendingValidation']), limits)) {
      problems.add('$id: pending validation drifted.');
    }
    if (page['visualParity'] != 'not_approved') {
      problems.add('$id: structural coverage cannot approve parity.');
    }
  }
  final marketingRows = _rows(audits['marketing-components.json']!['rows']);
  final marketingFamilies = _rows(marketingInventory['families']);
  final seenReferenceFamilies = <String>{};
  for (final family in marketingFamilies) {
    final name = family['family'] as String;
    if (!seenReferenceFamilies.add(name)) {
      problems.add('Marketing raw reference family $name is duplicated.');
    }
    if (marketingRows.where((row) => row['family'] == name).length != 1) {
      problems.add(
        'Marketing reference family $name must have exactly one audit.',
      );
    }
    final variants = _rows(family['variants']);
    final ids = variants.map((variant) => variant['id']).toSet();
    if (variants.isEmpty || ids.length != variants.length) {
      problems.add(
        'Marketing reference family $name needs unique source variants.',
      );
    }
    final matchingAudits = marketingRows.where((row) => row['family'] == name);
    if (matchingAudits.length == 1 &&
        (matchingAudits.single['referenceEvidence']
                as Map<String, dynamic>)['metadataVariants'] !=
            variants.length) {
      problems.add('Marketing reference family $name variant count drifted.');
    }
  }
  return problems;
}
