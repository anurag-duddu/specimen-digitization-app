import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

void main() {
  testWidgets(
    'remember-session stays controlled and is captured for submission',
    (tester) async {
      final preference = ValueNotifier<bool?>(false);
      addTearDown(preference.dispose);
      final requests = <bool>[];
      final submissions = <UiAuthSubmission>[];
      final pending = Completer<String?>();
      await tester.pumpWidget(
        uiHarness(
          child: SingleChildScrollView(
            child: ValueListenableBuilder(
              valueListenable: preference,
              builder: (_, value, _) => UiAuthForm(
                mode: UiAuthMode.signIn,
                email: 'researcher@example.org',
                rememberSession: value,
                onRememberSessionChanged: requests.add,
                onSubmit: (submission) {
                  submissions.add(submission);
                  return pending.future;
                },
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Remember me'));
      await tester.pump();
      expect(requests, [true]);
      expect(tester.widget<UiCheckbox>(find.byType(UiCheckbox)).value, isFalse);
      preference.value = true;
      await tester.pump();
      await tester.enterText(
        find.byType(EditableText).at(1),
        ' synthetic secret ',
      );
      await tester.tap(find.text('Sign in'));
      await tester.pump();
      expect(submissions.single.rememberSession, isTrue);
      expect(submissions.single.password, ' synthetic secret ');
      await tester.tap(find.text('Remember me'));
      await tester.pump();
      expect(requests, [true]);
      preference.value = false;
      await tester.pump();
      pending.complete('The synthetic request was declined.');
      await tester.pumpAndSettle();
      expect(submissions.single.rememberSession, isTrue);
      expect(tester.widget<UiCheckbox>(find.byType(UiCheckbox)).value, isFalse);
      expect(find.text('The synthetic request was declined.'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'unoffered and non-sign-in preferences are absent from payloads',
    (tester) async {
      final submissions = <UiAuthSubmission>[];
      for (final mode in [UiAuthMode.signIn, UiAuthMode.recovery]) {
        await tester.pumpWidget(
          uiHarness(
            child: SingleChildScrollView(
              child: UiAuthForm(
                key: ValueKey(mode),
                mode: mode,
                email: 'researcher@example.org',
                rememberSession: mode == UiAuthMode.signIn ? null : true,
                onSubmit: (value) async {
                  submissions.add(value);
                  return null;
                },
              ),
            ),
          ),
        );
        expect(find.byType(UiCheckbox), findsNothing);
        if (mode == UiAuthMode.signIn) {
          await tester.enterText(
            find.byType(EditableText).at(1),
            'synthetic secret',
          );
        }
        await tester.tap(
          find.text(
            mode == UiAuthMode.signIn ? 'Sign in' : 'Send recovery link',
          ),
        );
        await tester.pumpAndSettle();
        expect(submissions.last.rememberSession, isNull);
      }
      expect(submissions.length, 2);
    },
  );

  testWidgets('read-only and unavailable preferences cannot request a change', (
    tester,
  ) async {
    final requests = <bool>[];
    for (final enabled in [false, true]) {
      await tester.pumpWidget(
        uiHarness(
          child: SingleChildScrollView(
            child: UiAuthForm(
              mode: UiAuthMode.signIn,
              enabled: enabled,
              rememberSession: true,
              rememberSessionLabel: 'Keep this session on this device',
              onRememberSessionChanged: enabled ? null : requests.add,
              onSubmit: (_) async => null,
            ),
          ),
        ),
      );
      await tester.tap(find.text('Keep this session on this device'));
      await tester.pump();
      expect(requests, isEmpty);
      expect(tester.widget<UiCheckbox>(find.byType(UiCheckbox)).value, isTrue);
    }
  });

  testWidgets(
    'hero announcement precedes heading and retains its action at large RTL text',
    (tester) async {
      tester.view.physicalSize = const Size(320, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      var opened = 0;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 900),
          textDirection: TextDirection.rtl,
          textScaler: const TextScaler.linear(2),
          brightness: Brightness.dark,
          child: SingleChildScrollView(
            child: UiHeroSection(
              title: 'From specimens to knowledge',
              announcement: UiButton(
                label: 'New collection tools',
                onPressed: () => opened++,
              ),
              description: 'Explore original evidence with your research team.',
            ),
          ),
        ),
      );
      expect(
        tester.getBottomLeft(find.text('New collection tools')).dy,
        lessThan(
          tester.getTopLeft(find.text('From specimens to knowledge')).dy,
        ),
      );
      await tester.tap(find.text('New collection tools'));
      expect(opened, 1);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'error recovery slot keeps editable search and navigation usable',
    (tester) async {
      tester.view.physicalSize = const Size(320, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      var query = '', home = 0;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 900),
          textDirection: TextDirection.rtl,
          textScaler: const TextScaler.linear(2),
          child: SingleChildScrollView(
            child: UiErrorPage(
              title: 'Record not found',
              description: 'Search another collection record or return home.',
              actions: [
                UiMarketingAction('Return home', onPressed: () => home++),
              ],
              recovery: UiField(
                label: 'Find a record',
                onChanged: (value) => query = value,
              ),
            ),
          ),
        ),
      );
      await tester.ensureVisible(find.byType(EditableText));
      await tester.enterText(find.byType(EditableText), 'EXAMPLE-001');
      expect(query, 'EXAMPLE-001');
      await tester.ensureVisible(find.text('Return home'));
      await tester.tap(find.text('Return home'));
      expect(home, 1);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('email action follows message and summary before the footer', (
    tester,
  ) async {
    var started = 0;
    await tester.pumpWidget(
      uiHarness(
        child: SingleChildScrollView(
          child: UiEmailTemplate(
            kind: UiEmailTemplateKind.welcome,
            subject: 'Welcome to your collection',
            body: const Text('Your records and original evidence are ready.'),
            summary: const Text('Three collection folders'),
            actions: [
              UiMarketingAction('Get started', onPressed: () => started++),
            ],
            footer: const Text('Museum collection team'),
          ),
        ),
      ),
    );
    final body = tester.getRect(
      find.text('Your records and original evidence are ready.'),
    );
    final summary = tester.getRect(find.text('Three collection folders'));
    final action = tester.getRect(find.text('Get started'));
    final footer = tester.getRect(find.text('Museum collection team'));
    expect(body.bottom, lessThan(summary.top));
    expect(summary.bottom, lessThan(action.top));
    expect(action.bottom, lessThan(footer.top));
    await tester.tap(find.text('Get started'));
    expect(started, 1);
    expect(tester.takeException(), isNull);
  });
}
