import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

void main() {
  testWidgets(
    'metrics preserve context and adapt a split visual below at narrow widths',
    (tester) async {
      for (final width in [760.0, 280.0]) {
        await tester.pumpWidget(
          uiHarness(
            child: SingleChildScrollView(
              child: SizedBox(
                width: width,
                child: const UiMetricsSection(
                  title: 'Collection measures',
                  eyebrow: 'Reported activity',
                  description: 'Approved records in this collection.',
                  layout: UiSectionLayout.split,
                  metrics: [UiMarketingMetric(value: '120', label: 'Records')],
                  media: Text('Collection context'),
                ),
              ),
            ),
          ),
        );
        expect(find.text('Reported activity'), findsOneWidget);
        expect(
          find.text('Approved records in this collection.'),
          findsOneWidget,
        );
        final metric = tester.getRect(find.text('Records'));
        final visual = tester.getRect(find.text('Collection context'));
        if (width > 700) {
          expect(visual.left, greaterThan(metric.right));
        } else {
          expect(visual.top, greaterThan(metric.bottom));
        }
        expect(tester.takeException(), isNull);
      }
    },
  );

  testWidgets(
    'testimonial introduction and action remain outside controlled quotes',
    (tester) async {
      var activated = false;
      await tester.pumpWidget(
        uiHarness(
          child: SingleChildScrollView(
            child: UiTestimonialSection(
              title: 'Collection perspectives',
              description: 'Read what contributors have shared.',
              actions: [
                UiMarketingAction(
                  'Read their stories',
                  onPressed: () => activated = true,
                ),
              ],
              items: const [
                UiTestimonial(
                  quote: 'Sources remain connected.',
                  author: 'Sample curator',
                ),
              ],
            ),
          ),
        ),
      );
      expect(find.text('Read what contributors have shared.'), findsOneWidget);
      await tester.tap(find.text('Read their stories'));
      expect(activated, isTrue);
      expect(find.textContaining('Sources remain connected.'), findsOneWidget);
    },
  );

  testWidgets(
    'featured article coexists with sidebar and structured attribution',
    (tester) async {
      var read = '';
      await tester.pumpWidget(
        uiHarness(
          child: SingleChildScrollView(
            child: UiBlogSection(
              title: 'Journal',
              eyebrow: 'Collection news',
              description: 'Observations from our contributors.',
              layout: UiBlogLayout.sidebar,
              sidebar: const Text('Topic filters'),
              featured: UiArticleCard(
                title: 'Featured observations',
                description: 'A featured story.',
                author: const UiAvatarLabel(
                  name: 'Featured author',
                  supporting: '23 October 2026',
                ),
                onRead: () => read = 'featured',
              ),
              articles: [
                UiArticleCard(
                  title: 'Further observations',
                  description: 'Another story.',
                  author: const UiAvatarLabel(name: 'Second author'),
                  onRead: () => read = 'second',
                ),
              ],
            ),
          ),
        ),
      );
      expect(find.text('Collection news'), findsOneWidget);
      expect(find.text('Featured author'), findsOneWidget);
      expect(find.text('23 October 2026'), findsOneWidget);
      expect(find.text('Topic filters'), findsOneWidget);
      expect(find.text('Further observations'), findsOneWidget);
      expect(
        tester.getTopLeft(find.text('Featured observations')).dy,
        lessThan(tester.getTopLeft(find.text('Topic filters')).dy),
      );
      await tester.tap(find.text('Read Featured observations'));
      expect(read, 'featured');
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('content category and byline precede the figure and body', (
    tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const UiContentSection(
          title: 'Reading a record',
          category: 'Research',
          description: 'An introductory summary.',
          byline: UiAvatarLabel(
            name: 'Sample author',
            supporting: '23 October 2026',
          ),
          media: Text('Owned figure'),
          body: Text('Article body'),
        ),
      ),
    );
    final labels = [
      'Research',
      'Reading a record',
      'An introductory summary.',
      'Sample author',
      'Owned figure',
      'Article body',
    ];
    for (int i = 1; i < labels.length; i++) {
      expect(
        tester.getTopLeft(find.text(labels[i])).dy,
        greaterThan(tester.getTopLeft(find.text(labels[i - 1])).dy),
      );
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('career groups follow introductory media and host filtering', (
    tester,
  ) async {
    var onlyEngineering = false;
    var applied = false;
    await tester.pumpWidget(
      uiHarness(
        child: SingleChildScrollView(
          child: StatefulBuilder(
            builder: (_, setState) => UiCareersSection(
              title: 'Join the collection team',
              media: const Text('Team photograph'),
              departments: const ['All', 'Engineering'],
              selectedDepartment: onlyEngineering ? 'Engineering' : 'All',
              onDepartmentChanged: (value) =>
                  setState(() => onlyEngineering = value == 'Engineering'),
              groups: [
                if (!onlyEngineering)
                  const UiCareerGroup(
                    title: 'Collections roles',
                    jobs: [
                      UiCareerCard(
                        title: 'Curator',
                        description: 'Review collection records.',
                        metadata: ['Chicago', 'Full time'],
                      ),
                    ],
                  ),
                UiCareerGroup(
                  title: 'Engineering roles',
                  jobs: [
                    UiCareerCard(
                      title: 'Engineer',
                      description: 'Build collection tools.',
                      metadata: const ['Remote', 'Full time'],
                      onApply: () => applied = true,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
    expect(
      tester.getTopLeft(find.text('Team photograph')).dy,
      lessThan(tester.getTopLeft(find.text('Collections roles')).dy),
    );
    await tester.tap(find.text('Engineering'));
    await tester.pump();
    expect(find.text('Collections roles'), findsNothing);
    expect(find.text('Engineering roles'), findsOneWidget);
    await tester.ensureVisible(find.text('Apply for Engineer'));
    await tester.tap(find.text('Apply for Engineer'));
    expect(applied, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'banner separates icon title and supporting message at large text',
    (tester) async {
      var dismissed = false;
      await tester.pumpWidget(
        uiHarness(
          textScaler: const TextScaler.linear(4),
          textDirection: TextDirection.rtl,
          child: SingleChildScrollView(
            child: SizedBox(
              width: 280,
              child: UiAnnouncementBanner(
                title: 'Collection news',
                message: 'Receive updates from the collection.',
                icon: UiIcons.collection,
                onDismiss: () => dismissed = true,
              ),
            ),
          ),
        ),
      );
      expect(find.text('Collection news'), findsOneWidget);
      expect(find.text('Receive updates from the collection.'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('Dismiss announcement'));
      expect(dismissed, isTrue);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'footer closing action precedes navigation and legal information',
    (tester) async {
      var joined = false;
      await tester.pumpWidget(
        uiHarness(
          child: UiMarketingFooter(
            identity: const Text('Specimen'),
            legal: 'Example legal information',
            callToAction: UiMarketingSection(
              title: 'Explore the collection',
              actions: [
                UiMarketingAction(
                  'Get started',
                  onPressed: () => joined = true,
                ),
              ],
            ),
          ),
        ),
      );
      expect(
        tester.getTopLeft(find.text('Explore the collection')).dy,
        lessThan(tester.getTopLeft(find.text('Specimen')).dy),
      );
      await tester.tap(find.text('Get started'));
      expect(joined, isTrue);
      expect(find.text('Example legal information'), findsOneWidget);
    },
  );

  testWidgets('feature icon and benefits remain complete at large RTL text', (
    tester,
  ) async {
    const benefits = [
      'Keep original observations connected to each specimen.',
      'Review contributions before accepting a shared record.',
      'Export the collection with its complete source history.',
    ];
    for (final scale in [1.0, 2.0, 4.0]) {
      await tester.pumpWidget(
        uiHarness(
          textScaler: TextScaler.linear(scale),
          textDirection: TextDirection.rtl,
          child: const SingleChildScrollView(
            child: SizedBox(
              width: 280,
              child: UiFeatureShowcase(
                items: [
                  UiFeatureShowcaseItem(
                    title: 'Shared review',
                    description: 'Review knowledge together.',
                    icon: UiIcons.collection,
                    benefits: benefits,
                    media: Text('Owned product preview'),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      expect(
        find.byWidgetPredicate(
          (widget) => widget is UiIcon && widget.spec == UiIcons.collection,
        ),
        findsOneWidget,
      );
      for (final benefit in benefits) {
        expect(find.text(benefit), findsOneWidget);
      }
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('FAQ search filters supplied results and preserves support', (
    tester,
  ) async {
    var query = '';
    var support = 0;
    await tester.pumpWidget(
      uiHarness(
        child: SingleChildScrollView(
          child: StatefulBuilder(
            builder: (_, setState) => UiFaqSection(
              title: 'Collection questions',
              search: UiField(
                label: 'Search questions',
                onChanged: (value) => setState(() => query = value),
              ),
              items: [
                if ('alpha'.contains(query))
                  const UiFaqItem(
                    id: 'alpha',
                    question: 'Alpha collection',
                    answer: Text('Alpha details'),
                  ),
                if ('beta'.contains(query))
                  const UiFaqItem(
                    id: 'beta',
                    question: 'Beta collection',
                    answer: Text('Beta details'),
                  ),
              ],
              emptyState: const Text('No matching questions'),
              footer: UiButton(
                label: 'Contact support',
                onPressed: () => support++,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Beta collection'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(EditableText), 'beta');
    await tester.pumpAndSettle();
    expect(find.text('Alpha collection'), findsNothing);
    expect(find.text('Beta details').hitTestable(), findsOneWidget);
    await tester.enterText(find.byType(EditableText), 'missing');
    await tester.pumpAndSettle();
    expect(find.text('No matching questions'), findsOneWidget);
    await tester.tap(find.text('Contact support'));
    expect(support, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'blog sort toolbar controls result order without replacing cards',
    (tester) async {
      var newestFirst = false;
      var read = '';
      await tester.pumpWidget(
        uiHarness(
          child: SingleChildScrollView(
            child: SizedBox(
              width: 280,
              child: StatefulBuilder(
                builder: (_, setState) => UiBlogSection(
                  title: 'Collection journal',
                  toolbar: UiButton(
                    label: newestFirst ? 'Oldest first' : 'Most recent',
                    onPressed: () => setState(() => newestFirst = !newestFirst),
                  ),
                  articles: [
                    for (final title
                        in newestFirst
                            ? ['New observations', 'Early observations']
                            : ['Early observations', 'New observations'])
                      UiArticleCard(
                        title: title,
                        description: 'A collection update.',
                        onRead: () => read = title,
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
      expect(
        tester.getTopLeft(find.text('Early observations')).dy,
        lessThan(tester.getTopLeft(find.text('New observations')).dy),
      );
      await tester.tap(find.text('Most recent'));
      await tester.pump();
      expect(
        tester.getTopLeft(find.text('New observations')).dy,
        lessThan(tester.getTopLeft(find.text('Early observations')).dy),
      );
      await tester.tap(find.text('Read New observations'));
      expect(read, 'New observations');
      expect(tester.takeException(), isNull);
    },
  );
}
