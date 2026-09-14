// The four built-in guideline matchers over the workbench, at each layout
// regime, and over the surfaces it opens (accessibility, section 4.1; design
// 06, section 4.3 makes `flutter test test/accessibility/` a merge gate).
//
// The suite is in its own file so the screen this step adds does not collide
// with the screens the other steps own. A guideline that a surface fails
// would be marked `skip:` with the finding it belongs to, never weakened; the
// list is empty, which is a result rather than an empty harness.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/workbench.dart';

import 'guidelines_test.dart' show countSemantics, guidelines;

/// A record carrying one of everything the workbench renders.
Specimen workbenchRecord() => Specimen({
  'specimen_id': 'a11y-001',
  'display_name': 'Synthetic accessibility record',
  'revision': 4,
  'disposition': 'needs_human_review',
  'available_actions': const <String>[
    'field',
    'transcription',
    'coverage',
    'approve',
    'regions',
  ],
  'assets': <Json>[
    <String, dynamic>{
      'width': 1000,
      'height': 520,
      'asset_id': 'asset-1',
      'sha256': 'a' * 64,
      'preview_bytes': File(
        'test/fixtures/synthetic-wide-label.png',
      ).readAsBytesSync(),
    },
  ],
  'regions': const <Json>[
    {
      'region_id': 'r1',
      'bbox': [100, 52, 400, 212],
    },
    {
      'region_id': 'r2',
      'bbox': [420, 52, 700, 212],
    },
  ],
  'observations': const <Json>[
    {
      'id': 'o1',
      'model_id': 'Reader A',
      'provider': 'synthetic',
      'region_id': 'r1',
      'literal_text': 'Chicago 1912',
    },
    {
      'id': 'o2',
      'model_id': 'Reader B',
      'provider': 'synthetic',
      'region_id': 'r1',
      'literal_text': 'Chicago 1917',
    },
  ],
  'fields': const <Json>[
    {
      'field_key': 'country',
      'display_name': 'Country',
      'required': true,
      'state': 'unknown',
      'literal_value': null,
    },
  ],
  'validation_findings': const <Json>[
    {
      'field_key': 'country',
      'message': 'A supported country is required',
      'severity': 'hard',
      'rule_id': 'country.required',
    },
  ],
  'audit_events': const <Json>[
    {
      'action': 'intake',
      'actor_id': 'fixture-user',
      'created_at': '2026-09-07T10:00:00Z',
    },
  ],
  'run': const <String, dynamic>{
    'stage': 'validate',
    'usage': {'steps': 16, 'actual_cost_micros': null},
    'attempts': {'segment': 1},
  },
});

Future<void> pumpWorkbench(WidgetTester tester, Size window) async {
  tester.view.physicalSize = window;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        body: ReviewWorkbench(
          specimen: workbenchRecord(),
          onChange: (_) async => false,
          onRetry: (_) async {},
          onRefresh: () {},
          onNext: () {},
          onPrevious: () {},
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  const Map<String, Size> windows = <String, Size>{
    'compact': Size(390, 844),
    'expanded': Size(1000, 800),
    'large': Size(1440, 1000),
  };

  windows.forEach((String name, Size window) {
    group('ReviewWorkbench at $name', () {
      testWidgets('renders an inspectable semantics tree', (tester) async {
        final handle = tester.ensureSemantics();
        await pumpWorkbench(tester, window);
        expect(
          countSemantics(tester, (node) => true),
          greaterThanOrEqualTo(12),
          reason: 'the workbench produced almost no semantics nodes',
        );
        handle.dispose();
      });

      guidelines.forEach((String label, AccessibilityGuideline guideline) {
        testWidgets('meets the $label guideline', (tester) async {
          final handle = tester.ensureSemantics();
          await pumpWorkbench(tester, window);
          await expectLater(tester, meetsGuideline(guideline));
          handle.dispose();
        });
      });
    });
  });

  group('the surfaces the workbench opens', () {
    testWidgets('the field editor meets every guideline', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpWorkbench(tester, windows['large']!);
      await tester.tap(find.text('Fields'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip(RegExp(r'^Edit as written')).first);
      await tester.pumpAndSettle();
      for (final AccessibilityGuideline guideline in guidelines.values) {
        await expectLater(tester, meetsGuideline(guideline));
      }
      handle.dispose();
    });

    testWidgets('the shortcut list meets every guideline', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpWorkbench(tester, windows['large']!);
      await tester.tap(find.byTooltip('Keyboard shortcuts'));
      await tester.pumpAndSettle();
      for (final AccessibilityGuideline guideline in guidelines.values) {
        await expectLater(tester, meetsGuideline(guideline));
      }
      handle.dispose();
    });
  });
}
