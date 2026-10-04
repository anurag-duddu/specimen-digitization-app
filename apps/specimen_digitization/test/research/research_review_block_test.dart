import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/research_review_block.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'research_fixture.dart';
import 'review_test_support.dart';

const _several =
    'Several possibilities remain. The research could not choose between them.';

Finder get _block => find.byType(ResearchReviewBlock);

Future<void> _show(
  WidgetTester tester,
  Map<String, dynamic> json,
  String key, {
  double width = 640,
  double scale = 1,
  bool dark = false,
  bool reducedMotion = true,
}) async {
  // A card for the same field keeps its disclosure state, so a test that shows
  // one twice starts each from nothing: the second tap would close it.
  await tester.pumpWidget(const SizedBox.shrink());
  await pumpCard(
    tester,
    unresolvedCard(json, key),
    width: width,
    scale: scale,
    dark: dark,
    reducedMotion: reducedMotion,
  );
  await openCard(tester);
}

void main() {
  group('the three cases in the owner\'s words', () {
    testWidgets(
      'several possibilities: each with its unit, distance, source and identifier',
      (tester) async {
        await _show(tester, unresolvedJson(), 'country');
        expect(find.text('Why it is unresolved'), findsOneWidget);
        expect(find.text(_several), findsOneWidget);
        expect(find.text('Possibilities found'), findsOneWidget);
        expect(find.text('MOUNT APO'), findsNWidgets(3));
        expect(
          find.text('CENTRAL MINDANAO · 46 km from the estimated location'),
          findsOneWidget,
        );
        expect(
          find.text('COTABATO · 46 km from the estimated location'),
          findsOneWidget,
        );
        expect(find.text('geolocate:a863d52e6ff08fe2'), findsOneWidget);
        expect(find.text('geolocate:3e5a153ca95eedd5'), findsOneWidget);
        expect(
          find.text('GEOLocate · Searched for “Mount Apo”'),
          findsNWidgets(3),
        );
        expect(find.text('Sources checked'), findsOneWidget);
        expect(find.text('GEOLocate · Several matches'), findsOneWidget);
        expect(
          find.text(
            "GEOLocate is ambiguous for 'Philippines': agreeing matches lie up to 92 km apart",
          ),
          findsOneWidget,
        );
        // The question and the research layers the card already showed stay.
        expect(
          find.text(
            'Three places called Mount Apo lie up to 92 km apart. Which one does the label mean?',
          ),
          findsOneWidget,
        );
        expect(find.text('What the research found'), findsOneWidget);
      },
    );

    testWidgets(
      'public sources could not settle it: what was searched, no invented possibilities',
      (tester) async {
        await _show(tester, unresolvedJson(), 'province_state');
        expect(
          find.text('Public sources could not settle this field.'),
          findsOneWidget,
        );
        expect(find.text('Possibilities found'), findsNothing);
        expect(find.text('GEOLocate · No match'), findsOneWidget);
        expect(
          find.text(
            "GEOLocate returned 9 match(es); none is 'Mount McKinley' within 40 km of the interpreted placement",
          ),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'the label lacks it: said only when the research marked it not present',
      (tester) async {
        await _show(tester, unresolvedJson(), 'habitat');
        expect(find.text('This field is not on the label.'), findsOneWidget);
        expect(find.text('The label names no habitat.'), findsOneWidget);
        expect(find.text('Possibilities found'), findsNothing);
        expect(find.text('Sources checked'), findsNothing);
      },
    );

    testWidgets(
      'waiting for a rule or a source says what is known and no more',
      (tester) async {
        await _show(tester, unresolvedJson(), 'collection_method');
        expect(
          find.text('No approved rule settles this field yet.'),
          findsOneWidget,
        );
        expect(
          find.textContaining('no approved rule chooses between them'),
          findsOneWidget,
        );
        expect(find.text('This field is not on the label.'), findsNothing);

        final json = unresolvedJson();
        final habitat = fixtureField(json, 'habitat');
        habitat['value']['state'] = 'unresolved';
        habitat['checkpoint']['resolution']['value']['state'] = 'unresolved';
        await _show(tester, json, 'habitat');
        expect(
          find.text('No source has settled this field yet.'),
          findsOneWidget,
        );
        expect(find.text('This field is not on the label.'), findsNothing);
      },
    );

    testWidgets('readings or sources that disagree are named as such', (
      tester,
    ) async {
      final json = unresolvedJson();
      reviewOf(json, 'country')['question_reason'] = 'evidence_conflict';
      fixtureField(
        json,
        'country',
      )['checkpoint']['resolution']['question']['reason'] = 'evidence_conflict';
      await _show(tester, json, 'country');
      expect(
        find.text(
          'The readings or sources disagree. The research could not choose between them.',
        ),
        findsOneWidget,
      );
      expect(find.text(_several), findsNothing);
    });
  });

  group('honest absence and bounds', () {
    testWidgets(
      'several possibilities with no named candidate say so in words',
      (tester) async {
        final json = unresolvedJson();
        reviewOf(json, 'country')['candidates'] = <Object>[];
        await _show(tester, json, 'country');
        expect(find.text('Possibilities found'), findsOneWidget);
        expect(
          find.text('No possibilities were recorded for this field.'),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'lists say what they leave out, in the singular and the plural',
      (tester) async {
        final json = unresolvedJson();
        reviewOf(json, 'country')['candidates_not_shown'] = 4;
        reviewOf(json, 'country')['evidence_not_shown'] = 1;
        await _show(tester, json, 'country');
        expect(
          find.text('4 more possibilities are not shown.'),
          findsOneWidget,
        );
        expect(
          find.text('1 source reference is not shown here.'),
          findsOneWidget,
        );

        reviewOf(json, 'country')['candidates_not_shown'] = 1;
        reviewOf(json, 'country')['evidence_not_shown'] = 2;
        await _show(tester, json, 'country');
        expect(find.text('1 more possibility is not shown.'), findsOneWidget);
        expect(
          find.text('2 source references are not shown here.'),
          findsOneWidget,
        );
      },
    );

    testWidgets('a reason that is a code is written as a sentence or left out', (
      tester,
    ) async {
      final json = unresolvedJson();
      reviewOf(json, 'collection_method')['reason'] =
          'missing_policy:verbatim_dts_definition_examples';
      await _show(tester, json, 'collection_method');
      expect(
        find.text(
          'The definition and examples for this field have not been supplied.',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('missing_policy'), findsNothing);

      reviewOf(json, 'collection_method')['reason'] = 'some_internal_code';
      await _show(tester, json, 'collection_method');
      expect(find.text('What the research found'), findsNothing);
      expect(find.textContaining('some_internal_code'), findsNothing);
    });

    testWidgets(
      'a source note loses the typed status it leads with, and a bare status says nothing',
      (tester) async {
        final json = unresolvedJson();
        final evidence =
            (reviewOf(json, 'country')['evidence'] as List).first
                as Map<String, dynamic>;
        evidence['note'] = 'ambiguous';
        await _show(tester, json, 'country');
        expect(find.text('ambiguous'), findsNothing);
        expect(find.textContaining('ambiguous:'), findsNothing);
      },
    );

    testWidgets('a field that does not wait for a person shows no review', (
      tester,
    ) async {
      await pumpCard(tester, cardFor(fixtureThread(), 'taxon'));
      await openCard(tester);
      expect(find.text('Research interrupted'), findsWidgets);
      expect(_block, findsNothing);
      expect(find.text('Why it is unresolved'), findsNothing);
    });

    testWidgets(
      'a field from a server that sent no review shows the card as before',
      (tester) async {
        final json = unresolvedJson();
        fixtureField(json, 'country')['review'] = null;
        await _show(tester, json, 'country');
        expect(_block, findsNothing);
        expect(
          find.text(
            'Three places called Mount Apo lie up to 92 km apart. Which one does the label mean?',
          ),
          findsOneWidget,
        );
      },
    );
  });

  group('case selection', () {
    final table = <(String, ResearchReviewCase)>[
      ('country', ResearchReviewCase.severalPossibilities),
      ('province_state', ResearchReviewCase.sourcesCouldNotSettle),
      ('habitat', ResearchReviewCase.labelLacksValue),
      ('collection_method', ResearchReviewCase.noRule),
    ];
    for (final (key, expected) in table) {
      test('$key is $expected', () {
        expect(researchReviewCase(unresolvedThread().field(key)!), expected);
      });
    }

    test('every headline fits its budget and passes the writing checks', () {
      final banned = RegExp(
        r"\b(invalid|illegal|oops|please|simply|just|easily|sorry|we|our)\b",
        caseSensitive: false,
      );
      for (final item in ResearchReviewCase.values) {
        final text = item.headline;
        expect(text.length, lessThanOrEqualTo(120), reason: text);
        expect(text.contains('—') || text.contains('–'), isFalse);
        expect(banned.hasMatch(text), isFalse, reason: text);
        for (final sentence in text.split('. ')) {
          expect(sentence.split(' ').length, lessThanOrEqualTo(25));
        }
        expect(text.endsWith('.'), isTrue);
      }
    });
  });

  group('layout follows the width, never the platform', () {
    // The block is narrower than the window by the card's own padding, and
    // it is the block's width that decides: two columns from 600 (medium).
    for (final (width, columns) in [
      (320.0, 1),
      (360.0, 1),
      (600.0, 1),
      (640.0, 2),
      (1000.0, 2),
    ]) {
      testWidgets('possibilities sit in $columns column(s) at $width wide', (
        tester,
      ) async {
        await _show(tester, unresolvedJson(), 'country', width: width);
        expect(
          tester.getSize(_block).width >= ResearchReviewBlock.twoColumnMinWidth,
          columns == 2,
        );
        final first = find.byKey(const ValueKey('review-candidate-1'));
        final second = find.byKey(const ValueKey('review-candidate-2'));
        expect(first, findsOneWidget);
        expect(
          tester.getTopLeft(first).dy == tester.getTopLeft(second).dy,
          columns == 2,
        );
        expect(
          tester.getTopLeft(first).dx == tester.getTopLeft(second).dx,
          columns == 1,
        );
        expect(tester.getSize(_block).width, lessThanOrEqualTo(width));
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets(
      'the card keeps one column on a phone even when the platform is a desktop',
      (tester) async {
        debugDefaultTargetPlatformOverride = TargetPlatform.macOS;
        try {
          await _show(tester, unresolvedJson(), 'country', width: 360);
          expect(
            tester
                .getTopLeft(find.byKey(const ValueKey('review-candidate-1')))
                .dx,
            tester
                .getTopLeft(find.byKey(const ValueKey('review-candidate-2')))
                .dx,
          );
        } finally {
          debugDefaultTargetPlatformOverride = null;
        }
      },
    );
  });

  group('long and overflowing text', () {
    Map<String, dynamic> crowded() {
      final json = unresolvedJson();
      final review = reviewOf(json, 'country');
      final label = 'ST ${'X' * 237}';
      final first =
          (review['candidates'] as List).first as Map<String, dynamic>;
      review['candidates'] = [
        for (var i = 0; i < 8; i++)
          {
            ...first,
            'label': label,
            'details': [for (var d = 0; d < 4; d++) 'U' * 80],
            'authority_id': 'geolocate:${'f' * 220}',
            'rank': i + 1,
          },
      ];
      review['reason'] = 'because ' * 74;
      review['candidates_not_shown'] = 3;
      (review['evidence'] as List).first['note'] = 'why ' * 60;
      (review['evidence'] as List).first['searched_text'] = 'S' * 240;
      return json;
    }

    for (final width in [320.0, 360.0, 640.0, 1000.0]) {
      for (final scale in [1.0, 2.0]) {
        testWidgets(
          'eight 240-character possibilities at $width wide and ${scale}x text',
          (tester) async {
            await _show(
              tester,
              crowded(),
              'country',
              width: width,
              scale: scale,
            );
            expect(
              find.byKey(const ValueKey('review-candidate-8')),
              findsOneWidget,
            );
            expect(tester.takeException(), isNull);
            expect(tester.getSize(_block).width, lessThanOrEqualTo(width));
          },
        );
      }
    }

    testWidgets('an empty label and empty lists draw nothing broken', (
      tester,
    ) async {
      final json = unresolvedJson();
      final review = reviewOf(json, 'habitat');
      review['reason'] = null;
      await _show(tester, json, 'habitat');
      expect(find.text('This field is not on the label.'), findsOneWidget);
      expect(find.text('What the research found'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });

  group('accessibility', () {
    testWidgets('one live region carries the headline and a rebuild keeps it', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await _show(tester, unresolvedJson(), 'country');
      int liveRegions() {
        var count = 0;
        void visit(SemanticsNode node) {
          if (node.getSemanticsData().flagsCollection.isLiveRegion) {
            count++;
            expect(node.label, contains(_several));
          }
          node.visitChildren((child) {
            visit(child);
            return true;
          });
        }

        visit(tester.getSemantics(find.byType(MaterialApp)));
        return count;
      }

      expect(liveRegions(), 1);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      expect(liveRegions(), 1);
      handle.dispose();
    });

    testWidgets('each possibility is announced with its place in the list', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await _show(tester, unresolvedJson(), 'country');
      // Each possibility is one node that reads its position, then its words.
      for (var i = 1; i <= 3; i++) {
        expect(
          find.bySemanticsLabel(RegExp('^Possibility $i of 3\\n')),
          findsOneWidget,
        );
      }
      expect(
        find.bySemanticsLabel(
          RegExp(
            r'^Possibility 1 of 3[\s\S]*Identifier geolocate:a863d52e6ff08fe2',
          ),
        ),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(RegExp(r'^Field: Several possibilities remain')),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets(
      'the block adds no control: nothing to focus and no action it cannot offer',
      (tester) async {
        await _show(tester, unresolvedJson(), 'country');
        expect(
          find.descendant(of: _block, matching: find.byType(Pressable)),
          findsNothing,
        );
        expect(
          find.descendant(of: _block, matching: find.byType(UiButton)),
          findsNothing,
        );
        expect(find.text('Use this match'), findsNothing);
      },
    );

    for (final dark in [false, true]) {
      testWidgets(
        'meets the tap target, label and contrast guidelines (${dark ? 'dark' : 'light'})',
        (tester) async {
          final handle = tester.ensureSemantics();
          await _show(tester, unresolvedJson(), 'country', dark: dark);
          await expectGuidelines(tester);
          handle.dispose();
        },
      );
    }
  });

  group('motion', () {
    for (final reduced in [true, false]) {
      testWidgets('the block never animates (reduced motion: $reduced)', (
        tester,
      ) async {
        await _show(
          tester,
          unresolvedJson(),
          'country',
          reducedMotion: reduced,
        );
        for (final animated in [
          find.byType(AnimatedSize),
          find.byType(AnimatedOpacity),
          find.byType(AnimatedContainer),
          find.byType(AnimatedSwitcher),
        ]) {
          expect(find.descendant(of: _block, matching: animated), findsNothing);
        }
        // Nothing is left running once the card has opened.
        await tester.pumpAndSettle(const Duration(milliseconds: 50));
        expect(tester.takeException(), isNull);
      });
    }
  });
}
