import 'dart:async';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import '../harness/control_contract.dart';

void main() {
  Widget host(Widget child, {double width = 800}) => uiHarness(
    size: Size(width, 1000),
    disableAnimations: true,
    child: SingleChildScrollView(child: child),
  );

  testWidgets(
    'email capture validates, focuses, trims and prevents duplicate submissions',
    (tester) async {
      final pending = Completer<String?>();
      final submissions = <String>[];
      await tester.pumpWidget(
        host(
          UiEmailCapture(
            onSubmit: (email) {
              submissions.add(email);
              return pending.future;
            },
          ),
        ),
      );
      await tester.tap(find.text('Subscribe'));
      await tester.pump();
      expect(find.text('Enter a complete email address.'), findsOneWidget);
      expect(
        tester
            .widget<EditableText>(find.byType(EditableText))
            .focusNode
            .hasFocus,
        isTrue,
      );
      expect(submissions, isEmpty);
      await tester.enterText(find.byType(EditableText), ' sample@example.org ');
      await tester.tap(find.text('Subscribe'));
      await tester.pump();
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pump();
      expect(submissions, ['sample@example.org']);
      pending.complete('Please try later.');
      await tester.pumpAndSettle();
      expect(find.text('Please try later.'), findsOneWidget);
      expect(
        tester.widget<EditableText>(find.byType(EditableText)).controller.text,
        ' sample@example.org ',
      );
      expect(find.text('Thank you. Your request was received.'), findsNothing);
    },
  );

  testWidgets('email success is live and unavailable forms do not submit', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();

    await tester.pumpWidget(host(UiEmailCapture(onSubmit: (_) async => null)));
    await tester.enterText(find.byType(EditableText), 'sample@example.org');
    await tester.tap(find.text('Subscribe'));
    await tester.pumpAndSettle();
    expect(
      tester
          .getSemantics(find.text('Thank you. Your request was received.'))
          .getSemanticsData()
          .flagsCollection
          .isLiveRegion,
      isTrue,
    );
    await tester.pumpWidget(host(const UiEmailCapture(onSubmit: null)));
    expect(tester.widget<UiButton>(find.byType(UiButton)).onPressed, isNull);
    expect(tester.widget<UiField>(find.byType(UiField)).enabled, isFalse);
    semantics.dispose();
  });

  testWidgets('pending email completion is safe after unmount', (tester) async {
    final pending = Completer<String?>();
    await tester.pumpWidget(
      host(UiEmailCapture(onSubmit: (_) => pending.future)),
    );
    await tester.enterText(find.byType(EditableText), 'sample@example.org');
    await tester.tap(find.text('Subscribe'));
    await tester.pump();
    await tester.pumpWidget(const SizedBox());
    pending.complete(null);
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'contact form requires data and explicit consent before host submission',
    (tester) async {
      UiContactRequest? result;
      await tester.pumpWidget(
        host(
          UiContactForm(
            consentLabel: 'I agree',
            onSubmit: (value) async {
              result = value;
              return null;
            },
          ),
        ),
      );
      await tester.tap(find.text('Send message'));
      await tester.pump();
      expect(find.text('Enter your name.'), findsOneWidget);
      expect(result, isNull);
      await tester.enterText(find.byType(EditableText).at(0), ' Sample Name ');
      await tester.enterText(
        find.byType(EditableText).at(1),
        'sample@example.org',
      );
      await tester.enterText(
        find.byType(EditableText).at(2),
        ' Example message ',
      );
      await tester.tap(find.text('Send message'));
      await tester.pump();
      expect(result, isNull);
      expect(
        find.text('Accept the consent statement to continue.'),
        findsOneWidget,
      );
      await tester.tap(find.text('I agree'));
      await tester.pump();
      await tester.tap(find.text('Send message'));
      await tester.pumpAndSettle();
      expect(result!.name, 'Sample Name');
      expect(result!.message, 'Example message');
      expect(result!.consent, isTrue);
      expect(find.text('Your message was received.'), findsOneWidget);
    },
  );

  testWidgets('auth preserves password bytes and delegates actual policy', (
    tester,
  ) async {
    UiAuthSubmission? result;
    await tester.pumpWidget(
      host(
        UiAuthForm(
          mode: UiAuthMode.signUp,
          validatePassword: (value) =>
              value.length < 8 ? 'Use eight characters.' : null,
          onSubmit: (value) async {
            result = value;
            return null;
          },
        ),
      ),
    );
    await tester.enterText(find.byType(EditableText).at(0), 'Sample');
    await tester.enterText(
      find.byType(EditableText).at(1),
      'sample@example.org',
    );
    await tester.enterText(find.byType(EditableText).at(2), 'short');
    await tester.tap(find.text('Create account'));
    await tester.pump();
    expect(find.text('Use eight characters.'), findsOneWidget);
    expect(result, isNull);
    await tester.enterText(
      find.byType(EditableText).at(2),
      ' secret  password ',
    );
    await tester.tap(find.text('Show'));
    await tester.pump();
    expect(
      tester.widget<EditableText>(find.byType(EditableText).at(2)).obscureText,
      isFalse,
    );
    await tester.tap(find.text('Create account'));
    await tester.pumpAndSettle();
    expect(result!.password, ' secret  password ');
    expect(result!.mode, UiAuthMode.signUp);
  });

  testWidgets(
    'auth ignores a late result after switching stage and clears secrets',
    (tester) async {
      final pending = Completer<String?>();
      final stage = ValueNotifier(UiAuthMode.signIn);
      addTearDown(stage.dispose);
      await tester.pumpWidget(
        host(
          ValueListenableBuilder(
            valueListenable: stage,
            builder: (_, mode, _) =>
                UiAuthForm(mode: mode, onSubmit: (_) => pending.future),
          ),
        ),
      );
      await tester.enterText(
        find.byType(EditableText).at(0),
        'sample@example.org',
      );
      await tester.enterText(
        find.byType(EditableText).at(1),
        'private password',
      );
      await tester.tap(find.text('Sign in'));
      await tester.pump();
      stage.value = UiAuthMode.recovery;
      await tester.pump();
      pending.complete('Stale sign-in error');
      await tester.pumpAndSettle();
      expect(find.text('Stale sign-in error'), findsNothing);
      expect(find.text('Request completed.'), findsNothing);
      expect(find.text('Send recovery link'), findsOneWidget);
      stage.value = UiAuthMode.signIn;
      await tester.pump();
      expect(
        tester
            .widget<EditableText>(find.byType(EditableText).at(1))
            .controller
            .text,
        isEmpty,
      );
    },
  );

  testWidgets(
    'auth validation names and focuses the first invalid field at large text',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(320, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      var submissions = 0;
      await tester.pumpWidget(
        uiHarness(
          size: const Size(320, 1000),
          textScaler: const TextScaler.linear(2),
          textDirection: TextDirection.rtl,
          brightness: Brightness.dark,
          disableAnimations: true,
          child: SingleChildScrollView(
            child: UiAuthForm(
              mode: UiAuthMode.signUp,
              onSubmit: (_) async {
                submissions++;
                return null;
              },
            ),
          ),
        ),
      );
      await tester.ensureVisible(find.text('Create account'));
      await tester.tap(find.text('Create account'));
      await tester.pumpAndSettle();
      expect(find.text('Enter your name.'), findsOneWidget);
      expect(
        tester
            .widget<EditableText>(find.byType(EditableText).at(0))
            .focusNode
            .hasFocus,
        isTrue,
      );
      await tester.enterText(find.byType(EditableText).at(0), 'Sample Person');
      await tester.ensureVisible(find.text('Create account'));
      await tester.tap(find.text('Create account'));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<EditableText>(find.byType(EditableText).at(1))
            .focusNode
            .hasFocus,
        isTrue,
      );
      expect(submissions, 0);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'compact navigation exposes destinations with keyboard activation',
    (tester) async {
      var selected = false;
      await tester.pumpWidget(
        host(
          UiMarketingHeader(
            identity: const Text('Specimen'),
            links: [
              UiMarketingAction(
                'Collections',
                onPressed: () => selected = true,
              ),
            ],
          ),
          width: 320,
        ),
      );
      expect(find.text('Collections'), findsNothing);
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pump();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(find.text('Collections'), findsOneWidget);
      await tester.tap(find.text('Collections'));
      expect(selected, isTrue);
    },
  );

  testWidgets('billing changes host prices without inferring a discount', (
    tester,
  ) async {
    var period = UiBillingPeriod.monthly;
    await tester.pumpWidget(
      host(
        StatefulBuilder(
          builder: (_, setState) => UiPricingSection(
            title: 'Plans',
            period: period,
            onPeriodChanged: (value) => setState(() => period = value),
            plans: [
              UiPricingCard(
                title: 'Research',
                price: period == UiBillingPeriod.monthly ? r'$12' : r'$120',
                features: const [],
              ),
            ],
          ),
        ),
      ),
    );
    expect(find.text(r'$12'), findsOneWidget);
    await tester.tap(find.text('Annually'));
    await tester.pumpAndSettle();
    expect(period, UiBillingPeriod.annually);
    expect(find.text(r'$120'), findsOneWidget);
    expect(find.text(r'$12'), findsNothing);
  });

  testWidgets('compact menu Escape restores the actual trigger focus', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(320, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      host(
        UiMarketingHeader(
          identity: const Text('Specimen'),
          links: [UiMarketingAction('Collections', onPressed: () {})],
        ),
        width: 320,
      ),
    );
    await tester.tap(find.text('Menu'));
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pump();
    expect(find.text('Collections'), findsNothing);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(find.text('Collections'), findsOneWidget);
  });

  testWidgets(
    'article carousel keeps selection host controlled without autoplay',
    (tester) async {
      var active = 0;
      int? requested;
      late StateSetter update;
      await tester.pumpWidget(
        host(
          StatefulBuilder(
            builder: (_, setState) {
              update = setState;
              return UiBlogSection(
                title: 'Journal',
                layout: UiBlogLayout.carousel,
                selectedIndex: active,
                onSelected: (index) => requested = index,
                articles: const [
                  UiArticleCard(
                    title: 'First article',
                    description: 'First summary',
                  ),
                  UiArticleCard(
                    title: 'Second article',
                    description: 'Second summary',
                  ),
                ],
              );
            },
          ),
        ),
      );
      await tester.pump(const Duration(seconds: 30));
      expect(find.text('First article'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('Next page'));
      await tester.pump();
      expect(requested, 1);
      expect(find.text('First article'), findsOneWidget);
      update(() => active = requested!);
      await tester.pump();
      expect(find.text('Second article'), findsOneWidget);
      expect(find.text('First article'), findsNothing);
    },
  );

  testWidgets(
    'location selection changes address and media together; unknown ID is not substituted',
    (tester) async {
      var selected = 'north';
      late StateSetter update;
      await tester.pumpWidget(
        host(
          StatefulBuilder(
            builder: (_, setState) {
              update = setState;
              return UiContactLocations(
                title: 'Locations',
                selectedId: selected,
                onSelected: (id) => setState(() => selected = id),
                locations: const [
                  UiContactLocation(
                    id: 'north',
                    name: 'North',
                    address: 'North address',
                    media: Text('North map'),
                  ),
                  UiContactLocation(
                    id: 'south',
                    name: 'South',
                    address: 'South address',
                    media: Text('South map'),
                  ),
                ],
              );
            },
          ),
        ),
      );
      expect(find.text('North address'), findsOneWidget);
      expect(find.text('North map'), findsOneWidget);
      await tester.tap(find.text('South'));
      await tester.pump();
      expect(find.text('South address'), findsOneWidget);
      expect(find.text('South map'), findsOneWidget);
      expect(find.text('North address'), findsNothing);
      update(() => selected = 'removed');
      await tester.pump();
      expect(find.text('South map'), findsNothing);
      expect(
        find.text('Select a location to view its details.'),
        findsOneWidget,
      );
    },
  );

  test(
    'comparison rejects misaligned values instead of attributing to wrong plan',
    () {
      expect(
        () => UiPricingComparison(
          plans: const ['One', 'Two'],
          rows: const [
            UiPricingComparisonRow('Export', ['Included']),
          ],
        ),
        throwsArgumentError,
      );
    },
  );

  testWidgets('narrow pricing keeps feature and plan context for every value', (
    tester,
  ) async {
    await tester.pumpWidget(
      host(
        UiPricingComparison(
          plans: const ['One', 'Two'],
          rows: const [
            UiPricingComparisonRow('Export', ['CSV', 'API']),
          ],
        ),
        width: 320,
      ),
    );
    // The harness surface is 800 px unless the test viewport is also changed.
    await tester.binding.setSurfaceSize(const Size(320, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pump();
    expect(find.text('Export: CSV'), findsOneWidget);
    expect(find.text('Export: API'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'testimonial navigation respects boundaries and never autoplays',
    (tester) async {
      var selected = 0;
      await tester.pumpWidget(
        host(
          StatefulBuilder(
            builder: (_, setState) => UiTestimonialSection(
              title: 'Perspectives',
              selectedIndex: selected,
              onSelected: (value) => setState(() => selected = value),
              items: const [
                UiTestimonial(quote: 'First quote', author: 'First author'),
                UiTestimonial(quote: 'Second quote', author: 'Second author'),
              ],
            ),
          ),
        ),
      );
      // Select by the public accessible name rather than a paint icon.
      expect(
        tester
            .widget<UiIconButton>(
              find.byWidgetPredicate(
                (w) =>
                    w is UiIconButton &&
                    w.semanticsLabel == 'Previous testimonial',
              ),
            )
            .onPressed,
        isNull,
      );
      await tester.pump(const Duration(seconds: 30));
      expect(selected, 0);
      await tester.tap(find.bySemanticsLabel('Next testimonial'));
      await tester.pumpAndSettle();
      expect(selected, 1);
      expect(find.text('“Second quote”'), findsOneWidget);
      expect(
        tester
            .widget<UiIconButton>(
              find.byWidgetPredicate(
                (w) =>
                    w is UiIconButton && w.semanticsLabel == 'Next testimonial',
              ),
            )
            .onPressed,
        isNull,
      );
    },
  );

  testWidgets('FAQ preserves expanded item identity across reordering', (
    tester,
  ) async {
    final reverse = ValueNotifier(false);
    addTearDown(reverse.dispose);
    const items = [
      UiFaqItem(
        id: 'one',
        question: 'Question one',
        answer: Text('Answer one'),
      ),
      UiFaqItem(
        id: 'two',
        question: 'Question two',
        answer: Text('Answer two'),
      ),
    ];
    await tester.pumpWidget(
      host(
        ValueListenableBuilder(
          valueListenable: reverse,
          builder: (_, value, _) => UiFaqSection(
            title: 'Questions',
            items: value ? items.reversed.toList() : items,
          ),
        ),
      ),
    );
    await tester.tap(find.text('Question one'));
    await tester.pumpAndSettle();
    expect(find.text('Answer one'), findsOneWidget);
    expect(find.text('Answer two'), findsNothing);
    reverse.value = true;
    await tester.pump();
    expect(find.text('Answer one'), findsOneWidget);
    expect(find.text('Answer two'), findsNothing);
  });

  testWidgets(
    'rich navigation overlay dismisses with Escape and returns focus',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1440, 1000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        host(
          UiMarketingHeader(
            identity: const Text('Specimen'),
            groups: [
              UiMarketingLinkGroup(
                title: 'Resources',
                links: const [],
                content: UiMegaMenuContent(
                  columns: [
                    UiFeatureCard(
                      title: 'Guides',
                      description: 'Reference resources',
                      action: UiMarketingAction(
                        'Read guides',
                        onPressed: () {},
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          width: 1440,
        ),
      );
      await tester.tap(find.text('Resources'));
      await tester.pumpAndSettle();
      expect(find.text('Read guides'), findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
      expect(find.text('Read guides'), findsNothing);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(find.text('Read guides'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'media controls delegate seek playback captions and retry without autoplay',
    (tester) async {
      var playing = false;
      var captions = false;
      var retried = false;
      Duration? position;
      await tester.pumpWidget(
        host(
          StatefulBuilder(
            builder: (_, setState) => UiMediaPlayer(
              title: 'Example film',
              position: Duration.zero,
              duration: const Duration(minutes: 3),
              playing: playing,
              onPlayingChanged: (value) => setState(() => playing = value),
              onSeek: (value) => position = value,
              captions: captions,
              onCaptionsChanged: (value) => setState(() => captions = value),
              child: const Text('Player surface'),
            ),
          ),
        ),
      );
      await tester.pump(const Duration(seconds: 10));
      expect(playing, isFalse);
      await tester.tap(find.text('Play'));
      await tester.pump();
      expect(playing, isTrue);
      await tester.tap(find.text('Show captions'));
      await tester.pump();
      expect(captions, isTrue);
      tester.widget<UiSlider>(find.byType(UiSlider)).onChanged!(90000);
      expect(position, const Duration(seconds: 90));
      await tester.pumpWidget(
        host(
          UiMediaPlayer(
            title: 'Example film',
            position: Duration.zero,
            duration: Duration.zero,
            playing: false,
            error: 'Media unavailable',
            onRetry: () => retried = true,
            child: const Text('Poster'),
          ),
        ),
      );
      expect(find.byType(UiSlider), findsNothing);
      await tester.tap(find.text('Retry media'));
      expect(retried, isTrue);
    },
  );

  testWidgets(
    'extended contact captures explicit services and verbatim phone',
    (tester) async {
      UiContactRequest? result;
      await tester.binding.setSurfaceSize(const Size(1180, 1400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        host(
          UiContactForm(
            splitName: true,
            showPhone: true,
            services: const ['Research', 'Digitization'],
            onSubmit: (value) async {
              result = value;
              return null;
            },
          ),
        ),
      );
      final fields = find.byType(EditableText);
      await tester.enterText(fields.at(0), 'Sample');
      await tester.enterText(fields.at(1), 'Person');
      await tester.enterText(fields.at(2), 'sample@example.org');
      await tester.enterText(fields.at(3), '+1 (555) 010-0123 ext 4');
      await tester.enterText(fields.at(4), 'Example request');
      await tester.tap(find.text('Research'));
      await tester.tap(find.text('Send message'));
      await tester.pumpAndSettle();
      expect(result!.lastName, 'Person');
      expect(result!.phone, '+1 (555) 010-0123 ext 4');
      expect(result!.phoneCountryCode, isNull);
      expect(result!.services, ['Research']);
    },
  );

  test('credential visual accepts only last four digits', () {
    expect(
      () => UiPaymentCardMockup(
        label: 'Example',
        holder: 'Sample',
        lastFour: '1234567890123456',
      ),
      throwsArgumentError,
    );
  });
}
