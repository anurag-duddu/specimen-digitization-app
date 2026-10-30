import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

void main() {
  testWidgets('breadcrumb ancestors meet the interaction contract', (
    tester,
  ) async {
    await expectControlContract(
      tester,
      (_) => UiBreadcrumbs(
        items: [
          UiBreadcrumb(label: 'Collections', onSelected: () {}),
          const UiBreadcrumb(label: 'Current specimen'),
        ],
      ),
      semanticsLabel: 'Collections',
    );
  });

  testWidgets('current breadcrumb never activates a supplied callback', (
    tester,
  ) async {
    var ancestors = 0;
    var current = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiBreadcrumbs(
          items: [
            UiBreadcrumb(label: 'Collections', onSelected: () => ancestors++),
            UiBreadcrumb(
              label: 'Current specimen',
              onSelected: () => current++,
            ),
          ],
        ),
      ),
    );
    await tester.tap(find.text('Current specimen'));
    await tester.tap(find.text('Collections'));
    expect(current, 0);
    expect(ancestors, 1);
  });

  testWidgets('actionable steps meet the interaction contract', (tester) async {
    await expectControlContract(
      tester,
      (_) => UiSteps(
        steps: [
          UiStep(
            label: 'Review evidence',
            state: UiStepState.current,
            onSelected: () {},
          ),
        ],
      ),
      semanticsLabel: 'Step 1 of 1, Review evidence, Current step',
    );
  });

  testWidgets('steps remain controlled and expose state without colour', (
    tester,
  ) async {
    var requested = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiSteps(
          steps: [
            const UiStep(label: 'Add images', state: UiStepState.complete),
            UiStep(
              label: 'Review evidence',
              state: UiStepState.error,
              onSelected: () => requested++,
            ),
          ],
        ),
      ),
    );
    await tester.tap(find.text('Add images'));
    expect(requested, 0);
    await tester.tap(find.text('Review evidence'));
    expect(requested, 1);
    expect(find.text('2 / 2 · Needs correction'), findsOneWidget);
  });

  testWidgets('copy blocks duplicate requests and ignores stale completion', (
    tester,
  ) async {
    final pending = Completer<void>();
    final copied = <String>[];
    Future<void> copy(String value) {
      copied.add(value);
      return pending.future;
    }

    await tester.pumpWidget(
      uiHarness(
        child: UiCodeSnippet(label: 'Source', code: 'A', onCopy: copy),
      ),
    );
    await tester.tap(find.text('Copy code'));
    await tester.pump();
    await tester.tap(find.byType(UiButton));
    expect(copied, ['A']);
    await tester.pumpWidget(
      uiHarness(
        child: UiCodeSnippet(label: 'Source', code: 'B', onCopy: copy),
      ),
    );
    pending.complete();
    await tester.pump();
    expect(find.text('Copied'), findsNothing);
    await tester.tap(find.text('Copy code'));
    await tester.pump();
    expect(copied, ['A', 'B']);
    expect(find.text('Copied'), findsOneWidget);
  });

  testWidgets('clipboard failures remain recoverable', (tester) async {
    var attempts = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiCodeSnippet(
          label: 'Source',
          code: 'A',
          onCopy: (_) async {
            if (attempts++ == 0) throw PlatformException(code: 'unavailable');
          },
        ),
      ),
    );
    await tester.tap(find.text('Copy code'));
    await tester.pump();
    expect(find.text('Could not copy. Try again.'), findsOneWidget);
    await tester.tap(find.text('Copy code'));
    await tester.pump();
    expect(find.text('Copied'), findsOneWidget);
    expect(attempts, 2);
  });

  testWidgets('message retry exists only for failed delivery', (tester) async {
    var retries = 0;
    for (final state in UiMessageState.values) {
      await tester.pumpWidget(
        uiHarness(
          child: UiMessage(
            author: 'Alex',
            body: 'Original text',
            timeLabel: '10:42',
            state: state,
            onRetry: () => retries++,
          ),
        ),
      );
      expect(find.byType(UiSelectableText), findsOneWidget);
      if (state == UiMessageState.failed) {
        await tester.tap(find.text('Retry message'));
      } else {
        expect(find.text('Retry message'), findsNothing);
      }
    }
    expect(retries, 1);
  });

  testWidgets(
    'content and navigation fit narrow, large text, RTL and both modes',
    (tester) async {
      for (final width in [320.0, 768.0, 1440.0]) {
        tester.view.physicalSize = Size(width, 960);
        tester.view.devicePixelRatio = 1;
        for (final brightness in Brightness.values) {
          for (final direction in TextDirection.values) {
            await tester.pumpWidget(
              uiHarness(
                size: Size(width, 960),
                brightness: brightness,
                textScaler: const TextScaler.linear(2),
                textDirection: direction,
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      UiBreadcrumbs(
                        items: [
                          UiBreadcrumb(
                            label: 'Historical collections',
                            onSelected: () {},
                          ),
                          const UiBreadcrumb(
                            label: 'A detailed specimen catalogue title',
                          ),
                        ],
                      ),
                      const UiSteps(
                        steps: [
                          UiStep(
                            label: 'Add original source images',
                            state: UiStepState.complete,
                          ),
                          UiStep(
                            label: 'Review the evidence',
                            state: UiStepState.current,
                          ),
                        ],
                      ),
                      const UiActivityFeed(
                        entries: [
                          UiActivityEntry(
                            title: 'Corrected the catalogue number',
                            timeLabel: 'Today, 10:42',
                            actor: 'Alex Morgan',
                            description:
                                'Confirmed against the original label.',
                          ),
                        ],
                      ),
                      const UiMessage(
                        author: 'Alex Morgan',
                        body: 'The source text remains selectable.',
                        timeLabel: '10:42',
                      ),
                      const UiCodeSnippet(
                        label: 'Occurrence JSON',
                        code: '{"catalogNumber":"EXAMPLE-001"}',
                      ),
                    ],
                  ),
                ),
              ),
            );
            await tester.pump();
            expect(
              tester.takeException(),
              isNull,
              reason: '$width $brightness $direction',
            );
          }
        }
      }
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
    },
  );
}
