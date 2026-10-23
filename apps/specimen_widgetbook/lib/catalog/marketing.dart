import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';

import '../story.dart';

const _guidance =
    'Original Specimen composition using the approved five-color brand and owned controls. All content is synthetic. Width, text scale, RTL and appearance are controlled by the Widgetbook environment. Actions update this preview only.';

/// Marketing and shared pages, including every reference family.
List<WidgetbookComponent> get marketingComponents => [
  _component('UiMarketingHeader', [
    'Public navigation and account actions',
    'Grouped navigation and compact menu',
  ]),
  _component('UiMegaMenuContent', ['Columns sidebar and feature footer']),
  _component('UiFeatureShowcase', ['Alternating image and text rows']),
  _component('UiEditorialFigure', [
    'Landscape figure and caption',
    'Square figure and caption',
  ]),
  _component('UiEditorialQuote', ['Leading quotation', 'Centered quotation']),
  _component('UiMediaPlayer', [
    'Controlled playback and captions',
    'Buffering and error recovery',
  ]),
  _component('UiMarketingPage', [
    'Landing',
    'Pricing',
    'Blog',
    'Article',
    'About',
    'Contact',
    'Team',
    'Careers',
    'Legal',
    'FAQ',
    'Authentication',
    'Not found',
  ]),
  _component('UiPressMentionsSection', [
    'Editorial mention cards',
    'Editorial mention list',
  ]),
  _component('UiMarketingSection', [
    for (final layout in UiSectionLayout.values) layout.name,
  ]),
  _component('UiSectionGrid', ['Responsive feature grid']),
  _component('UiHeroSection', [
    'Centered brand hero',
    'Split product preview',
    'Reverse media and search',
  ]),
  _component('UiFeatureCard', [
    for (final layout in UiFeatureLayout.values) layout.name,
  ]),
  _component('UiFeatureSection', [
    'Grid of benefits',
    'Controlled feature selector',
  ]),
  _component('UiPricingCard', ['Basic tier', 'Featured tier and dual actions']),
  _component('UiPricingSection', ['Billing toggle and tier cards']),
  _component('UiPricingComparison', ['Plan features and narrow labeled cards']),
  _component('UiCallToActionSection', [
    'Centered brand',
    'Split card',
    'Simple leading',
  ]),
  _component('UiMetricsSection', [
    'Centered measures',
    'Metric cards',
    'Leading measures and visual',
  ]),
  _component('UiEmailCapture', [
    'Validation pending success and retry',
    'Unavailable capture',
  ]),
  _component('UiNewsletterSection', [
    'Centered newsletter',
    'Split newsletter card',
  ]),
  _component('UiTestimonialSection', [
    'Controlled carousel',
    'Quote grid',
    'Split portrait quote',
  ]),
  _component('UiSocialProofSection', ['Identity strip', 'Partner cards']),
  _component('UiArticleCard', [
    for (final layout in UiArticleLayout.values) layout.name,
  ]),
  _component('UiBlogSection', [
    'Category filtering and load more',
    'Featured article and grid',
    'Sidebar filtering and newsletter',
    'Controlled article carousel',
  ]),
  _component('UiContentSection', ['Editorial content and section anchors']),
  _component('UiContactForm', [
    'Validation consent submission and retry',
    'Split name phone and service choices',
  ]),
  _component('UiContactSection', [
    'Form with contact methods',
    'Form and location visual',
  ]),
  _component('UiContactLocations', ['Controlled locations and map detail']),
  _component('UiTeamMemberCard', [
    'Leading biography',
    'Centered profile card',
    'Horizontal portrait and biography',
    'Portrait with readable content panel',
  ]),
  _component('UiTeamSection', ['Team directory and recruiting actions']),
  _component('UiCareerCard', ['Vacancy card', 'Simple vacancy row']),
  _component('UiCareersSection', ['Controlled department filter']),
  _component('UiFaqSection', [
    'Accordion questions',
    'Always-visible question columns',
  ]),
  _component('UiMarketingFooter', [
    'Minimal legal footer',
    'Grouped links and newsletter',
  ]),
  _component('UiAnnouncementBanner', [
    'Dismissible announcement',
    'Floating dual action',
    'Inline email capture',
  ]),
  _component('UiAuthLayout', ['Centered form card', 'Split quotation layout']),
  _component('UiAuthForm', [for (final mode in UiAuthMode.values) mode.name]),
  _component('UiErrorPage', [
    'Centered missing page',
    'Split unavailable page',
  ]),
  _component('UiEmailTemplate', [
    for (final kind in UiEmailTemplateKind.values) kind.name,
  ]),
  _component('UiDeviceMockup', [
    for (final frame in UiDeviceFrame.values) frame.name,
  ]),
  _component('UiBrandPattern', [
    for (final pattern in UiBrandPatternStyle.values) pattern.name,
  ]),
  _component('UiPaymentCardMockup', [
    'Branded masked credential',
    'Neutral masked credential',
  ]),
];

WidgetbookComponent _component(
  String name,
  List<String> cases,
) => WidgetbookComponent(
  name: name,
  useCases: [
    for (var i = 0; i < cases.length; i++)
      story(
        cases[i],
        '$name. $_guidance${name == "UiEmailTemplate" ? " This is an accessible Flutter message preview. HTML export, email-client rendering and transmission belong to the host and are not demonstrated here." : ""}',
        (_) => _MarketingDemo(kind: name, variant: i),
      ),
  ],
);

class _MarketingDemo extends StatefulWidget {
  const _MarketingDemo({required this.kind, required this.variant});
  final String kind;
  final int variant;
  @override
  State<_MarketingDemo> createState() => _MarketingDemoState();
}

class _MarketingDemoState extends State<_MarketingDemo> {
  var _period = UiBillingPeriod.monthly;
  var _selected = 0;
  var _category = 'All';
  var _department = 'All teams';
  var _visible = true;
  var _fail = false;
  var _more = false;
  var _playing = false;
  var _captions = false;
  var _position = Duration.zero;
  var _volume = 0.7;
  var _mediaError = true;
  var _location = 'north';
  String _receipt = 'No action yet';
  final _sectionKey = GlobalKey();
  void _report(String value) => setState(() => _receipt = value);
  UiMarketingAction _action(String label, {bool primary = false}) =>
      UiMarketingAction(
        label,
        primary: primary,
        onPressed: () => _report('$label selected'),
      );
  Future<String?> _submit(Object value) async {
    await Future<void>.delayed(const Duration(milliseconds: 500));
    if (!mounted) return null;
    _report(
      _fail
          ? 'Synthetic request failed; retry is available'
          : 'Synthetic request accepted',
    );
    return _fail ? 'This synthetic request failed. Try again.' : null;
  }

  List<UiMarketingAction> get _actions => [
    _action('Explore collections', primary: true),
    _action('Contact the team'),
  ];
  List<UiFeatureCard> get _features => [
    for (final (title, description, icon) in [
      (
        'Capture',
        'Preserve specimen photographs and label detail.',
        UiIcons.camera,
      ),
      (
        'Understand',
        'Review provenance alongside every interpretation.',
        UiIcons.authority,
      ),
      (
        'Connect',
        'Explore the relationship between records and collections.',
        UiIcons.collection,
      ),
    ])
      UiFeatureCard(
        title: title,
        description: description,
        icon: icon,
        action: _action('Explore $title'),
        layout: UiFeatureLayout.card,
      ),
  ];
  List<UiPricingCard> get _plans => [
    UiPricingCard(
      title: 'Research',
      price: _period == UiBillingPeriod.monthly ? r'$12' : r'$120',
      period: _period == UiBillingPeriod.monthly ? 'per month' : 'per year',
      description: 'Synthetic plan for catalog demonstration.',
      features: const [
        UiPricingFeature('Personal workspace'),
        UiPricingFeature('Records', value: '1,000'),
        UiPricingFeature('Shared team', included: false),
      ],
      actions: [_action('Choose Research', primary: true)],
    ),
    UiPricingCard(
      title: 'Collections',
      price: _period == UiBillingPeriod.monthly ? r'$36' : r'$360',
      period: _period == UiBillingPeriod.monthly ? 'per month' : 'per year',
      badge: 'For collaborating teams',
      featured: true,
      features: const [
        UiPricingFeature('Shared workspace'),
        UiPricingFeature('Records', value: '10,000'),
        UiPricingFeature('Team review'),
      ],
      actions: [
        _action('Choose Collections', primary: true),
        _action('Ask about access'),
      ],
    ),
  ];
  UiPricingComparison get _comparison => UiPricingComparison(
    plans: const ['Research', 'Collections'],
    rows: const [
      UiPricingComparisonRow('Records', ['1,000', '10,000']),
      UiPricingComparisonRow('Shared review', ['Not included', 'Included']),
      UiPricingComparisonRow('Export', ['CSV', 'CSV and API']),
    ],
  );
  Widget _visual(String label) => Surface(
    hairline: true,
    padding: EdgeInsets.all(context.ui.space.s4),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const UiBrandPattern(height: 96),
        SizedBox(height: context.ui.space.s4),
        Text(label, textAlign: TextAlign.center, style: context.ui.type.label),
      ],
    ),
  );
  UiArticleCard _article(
    String title,
    String category, {
    UiArticleLayout layout = UiArticleLayout.card,
  }) => UiArticleCard(
    title: title,
    category: category,
    description:
        'A synthetic editorial example about preserving and understanding museum collections.',
    metadata: 'Sample author · 22 October 2026 · 4 min read',
    media: _visual('Synthetic editorial illustration'),
    onRead: () => _report('Opened $title'),
    layout: layout,
  );
  UiTeamMemberCard _person(
    String name, {
    bool centered = false,
    bool framed = false,
    UiTeamMemberLayout layout = UiTeamMemberLayout.stacked,
  }) => UiTeamMemberCard(
    name: name,
    role: 'Example collection specialist',
    biography:
        'Synthetic profile used only to demonstrate the directory layout.',
    portrait: _visual('Portrait slot'),
    actions: [_action('View $name profile')],
    centered: centered,
    framed: framed,
    layout: layout,
  );
  UiCareerCard _job(String title, {bool framed = true}) => UiCareerCard(
    title: title,
    description: 'Help teams preserve and share knowledge from collections.',
    metadata: const ['Chicago', 'Full-time', 'Example vacancy'],
    onApply: () => _report('Application flow for $title requested'),
    framed: framed,
  );
  List<UiTestimonial> get _quotes => [
    UiTestimonial(
      quote: 'The evidence stays connected to the record.',
      author: 'Sample researcher',
      role: 'Synthetic quotation',
      portrait: widget.variant == 2 ? _visual('Portrait slot') : null,
      rating: 5,
    ),
    const UiTestimonial(
      quote: 'Our team can review the source together.',
      author: 'Sample curator',
      role: 'Synthetic quotation',
    ),
  ];
  Widget _formControls(Widget child) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      UiCheckbox(
        label: 'Simulate a submission failure',
        value: _fail,
        onChanged: (value) => setState(() => _fail = value),
      ),
      SizedBox(height: context.ui.space.s4),
      child,
    ],
  );
  Widget _buildCase() {
    final v = widget.variant;
    switch (widget.kind) {
      case 'UiMegaMenuContent':
        return UiMegaMenuContent(
          columns: [
            UiFeatureCard(
              title: 'Explore',
              description: 'Browse collection resources.',
              icon: UiIcons.collection,
              action: _action('Browse collections'),
            ),
            UiFeatureCard(
              title: 'Learn',
              description: 'Read guides and examples.',
              icon: UiIcons.authority,
              action: _action('Open guides'),
            ),
          ],
          sidebar: UiFeatureCard(
            title: 'Community',
            description: 'Connect with collection teams.',
            action: _action('Community events'),
          ),
          footer: UiButton(
            label: 'View every resource',
            onPressed: () => _report('Resource index requested'),
          ),
        );
      case 'UiFeatureShowcase':
        return UiFeatureShowcase(
          items: [
            for (final feature in _features.take(2))
              UiFeatureShowcaseItem(
                title: feature.title,
                description: feature.description,
                media: _visual('Product visual for ${feature.title}'),
                actions: [_action('Explore ${feature.title}')],
              ),
          ],
        );
      case 'UiEditorialFigure':
        return UiEditorialFigure(
          alternative: 'Synthetic collection visual',
          caption: 'Example figure attribution and explanation.',
          aspectRatio: v == 0 ? 3 / 2 : 1,
          child: const UiBrandPattern(),
        );
      case 'UiEditorialQuote':
        return UiEditorialQuote(
          quote: 'A collection is a continuing record of discovery.',
          attribution: 'Synthetic quotation',
          centered: v == 1,
        );
      case 'UiMediaPlayer':
        return UiMediaPlayer(
          title: 'Example collection film',
          position: _position,
          duration: const Duration(minutes: 3),
          playing: _playing,
          onPlayingChanged: (value) => setState(() => _playing = value),
          onSeek: (value) => setState(() => _position = value),
          volume: _volume,
          onVolumeChanged: (value) => setState(() => _volume = value),
          captions: _captions,
          onCaptionsChanged: (value) => setState(() => _captions = value),
          onFullscreen: () => _report('Host full-screen requested'),
          buffering: v == 1 && !_mediaError,
          error: v == 1 && _mediaError ? 'Synthetic media unavailable.' : null,
          onRetry: () => setState(() => _mediaError = false),
          child: _visual(
            'Host media surface; no actual film plays in this synthetic story',
          ),
        );
      case 'UiMarketingPage':
        return _page(v);
      case 'UiPressMentionsSection':
        return UiPressMentionsSection(
          title: 'In the collection journal',
          cards: v == 0,
          mentions: [
            for (final source in [
              'Example Journal',
              'Example Review',
              'Example Bulletin',
            ])
              UiPressMention(
                publication: source,
                headline: 'Connecting collection knowledge',
                date: '22 October 2026',
                onRead: () => _report('Opened $source mention'),
              ),
          ],
        );
      case 'UiMarketingHeader':
        return UiMarketingHeader(
          identity: Text('Specimen', style: context.ui.type.title),
          links: [_action('Collections'), _action('About')],
          actions: [_action('Sign in', primary: true)],
          groups: v == 0
              ? []
              : [
                  UiMarketingLinkGroup(
                    title: 'Resources',
                    links: [_action('Guides'), _action('Community')],
                  ),
                ],
        );
      case 'UiMarketingSection':
        return UiMarketingSection(
          title: 'From specimens to knowledge.',
          description: 'A modern platform for museum collections.',
          eyebrow: 'Specimen Digitization',
          actions: _actions,
          media: _visual('Product visual slot'),
          layout: UiSectionLayout.values[v],
        );
      case 'UiSectionGrid':
        return UiSectionGrid(children: _features);
      case 'UiHeroSection':
        return UiHeroSection(
          title: 'From specimens to knowledge.',
          eyebrow: 'Specimen Digitization',
          description: 'Digitize, enrich, and explore your collections.',
          actions: _actions,
          layout: [
            UiSectionLayout.centered,
            UiSectionLayout.split,
            UiSectionLayout.splitReversed,
          ][v],
          media: UiDeviceMockup(child: _visual('Live product preview slot')),
          lead: v == 2
              ? UiSearchField(
                  label: 'Search collections',
                  clearLabel: 'Clear search',
                  onChanged: (value) => _report('Search: $value'),
                )
              : null,
        );
      case 'UiFeatureCard':
        return UiFeatureCard(
          title: 'Keep evidence connected',
          description:
              'Review original source details alongside structured information.',
          icon: UiIcons.authority,
          action: _action('Explore evidence'),
          layout: UiFeatureLayout.values[v],
        );
      case 'UiFeatureSection':
        return UiFeatureSection(
          title: 'A collection workflow that fits your team',
          features: _features,
          selectedIndex: v == 1 ? _selected : null,
          onSelected: (value) => setState(() => _selected = value),
          media: v == 1
              ? _visual('Preview for ${_features[_selected].title}')
              : null,
          layout: UiSectionLayout.split,
        );
      case 'UiPricingCard':
        return _plans[v];
      case 'UiPricingSection':
        return UiPricingSection(
          title: 'Example plans',
          description: 'Synthetic prices for component review only.',
          plans: _plans,
          period: _period,
          onPeriodChanged: (value) => setState(() => _period = value),
          comparison: _comparison,
        );
      case 'UiPricingComparison':
        return _comparison;
      case 'UiCallToActionSection':
        return UiCallToActionSection(
          title: 'Bring your collection into focus',
          description: 'Start with the evidence you already have.',
          actions: _actions,
          layout: [
            UiSectionLayout.centered,
            UiSectionLayout.split,
            UiSectionLayout.start,
          ][v],
          treatment: [
            UiSectionTreatment.brand,
            UiSectionTreatment.card,
            UiSectionTreatment.plain,
          ][v],
          media: v == 1 ? _visual('Collection image slot') : null,
        );
      case 'UiMetricsSection':
        return UiMetricsSection(
          title: 'Synthetic collection measures',
          cards: v == 1,
          centered: v != 2,
          media: v == 2 ? _visual('Measure context visual') : null,
          metrics: const [
            UiMarketingMetric(
              value: '12k',
              label: 'Example specimens',
              description: 'Illustrative values only',
            ),
            UiMarketingMetric(value: '8', label: 'Example collections'),
            UiMarketingMetric(value: '24', label: 'Example contributors'),
          ],
        );
      case 'UiEmailCapture':
        return _formControls(
          UiEmailCapture(
            onSubmit: v == 1 ? null : _submit,
            privacy: Text(
              'Synthetic capture. No email will be sent.',
              style: context.ui.type.bodySmall,
            ),
          ),
        );
      case 'UiNewsletterSection':
        return _formControls(
          UiNewsletterSection(
            title: 'Notes from the collection',
            description: 'Collection stories and product updates.',
            onSubmit: _submit,
            privacy: const Text(
              'This example does not subscribe or send email.',
            ),
            layout: v == 0 ? UiSectionLayout.centered : UiSectionLayout.split,
            treatment: v == 0
                ? UiSectionTreatment.plain
                : UiSectionTreatment.card,
            media: v == 1 ? _visual('Editorial visual slot') : null,
          ),
        );
      case 'UiTestimonialSection':
        return UiTestimonialSection(
          title: 'Collection perspectives',
          items: _quotes,
          selectedIndex: v == 1 ? null : _selected,
          onSelected: (value) => setState(() => _selected = value),
          layout: v == 2 ? UiSectionLayout.split : UiSectionLayout.centered,
        );
      case 'UiSocialProofSection':
        return UiSocialProofSection(
          title: 'Example partner identities',
          cards: v == 1,
          partners: [
            for (final name in [
              'Collection One',
              'Research Group',
              'Archive Network',
              'Learning Lab',
            ])
              UiPartnerIdentity(
                name: name,
                onPressed: () => _report('$name selected'),
              ),
          ],
        );
      case 'UiArticleCard':
        return _article(
          'Reading the record',
          'Research',
          layout: UiArticleLayout.values[v],
        );
      case 'UiBlogSection':
        return UiBlogSection(
          title: 'From the collection',
          layout: UiBlogLayout.values[v],
          selectedIndex: _selected,
          onSelected: (value) => setState(() => _selected = value),
          sidebar: v == 2
              ? UiEmailCapture(
                  onSubmit: _submit,
                  submitLabel: 'Follow the journal',
                )
              : null,
          categories: const ['All', 'Research', 'Practice'],
          selectedCategory: _category,
          onCategoryChanged: (value) => setState(() {
            _category = value;
            _selected = 0;
          }),
          articles: [
            if (_category != 'Practice')
              _article('Reading the record', 'Research'),
            if (_category != 'Research')
              _article('A shared review practice', 'Practice'),
            if (_more)
              _article(
                'Connecting collection histories',
                _category == 'All' ? 'Research' : _category,
              ),
          ],
          footer: UiButton(
            label: _more ? 'All examples loaded' : 'Load more articles',
            onPressed: _more ? null : () => setState(() => _more = true),
          ),
        );
      case 'UiContentSection':
        return UiContentSection(
          title: 'The story behind a specimen',
          description: 'A synthetic editorial layout.',
          media: _visual('Article figure'),
          caption: 'Synthetic figure caption.',
          contents: [
            UiMarketingAction(
              'Jump to Methods',
              onPressed: () {
                final target = _sectionKey.currentContext;
                if (target != null) Scrollable.ensureVisible(target);
              },
            ),
          ],
          body: UiSelectionArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'A record can carry a remarkable amount of context. Preserve each observation and distinguish it from interpretation.',
                  style: context.ui.type.bodyLarge,
                ),
                SizedBox(height: context.ui.space.s8),
                Semantics(
                  header: true,
                  child: Text(
                    'Methods',
                    key: _sectionKey,
                    style: context.ui.type.title,
                  ),
                ),
                const Text(
                  'Use source-linked descriptions and review uncertain claims. The displayed copy is sample content.',
                ),
              ],
            ),
          ),
          actions: [_action('Copy article link')],
        );
      case 'UiContactForm':
        return _formControls(
          UiContactForm(
            onSubmit: _submit,
            consentLabel: 'I agree to the example privacy statement.',
            splitName: v == 1,
            showPhone: v == 1,
            services: v == 1
                ? const ['Digitization', 'Research', 'Education', 'Other']
                : const [],
            phoneCountries: const [
              UiPhoneCountry(
                code: 'US',
                name: 'United States',
                dialingCode: '+1',
              ),
              UiPhoneCountry(
                code: 'GB',
                name: 'United Kingdom',
                dialingCode: '+44',
              ),
            ],
          ),
        );
      case 'UiContactSection':
        return _formControls(
          UiContactSection(
            title: 'Talk with the collection team',
            description: 'Tell us what you are working on.',
            methods: [
              _action('Email the team'),
              _action('View office details'),
            ],
            form: UiContactForm(
              onSubmit: _submit,
              consentLabel: 'I agree to the example privacy statement.',
            ),
            media: v == 1
                ? _visual('Location map slot; host provides accessible map')
                : null,
          ),
        );
      case 'UiTeamMemberCard':
        return _person(
          'Alex Example',
          centered: v == 1,
          framed: v == 1,
          layout: v == 2
              ? UiTeamMemberLayout.horizontal
              : v == 3
              ? UiTeamMemberLayout.portraitCard
              : UiTeamMemberLayout.stacked,
        );
      case 'UiContactLocations':
        return UiContactLocations(
          title: 'Example collection locations',
          selectedId: _location,
          onSelected: (value) => setState(() => _location = value),
          locations: [
            UiContactLocation(
              id: 'north',
              name: 'North collection',
              address: '100 Example Avenue, Sample City',
              description: 'Synthetic location. Visits by appointment.',
              media: _visual('North collection map slot'),
              actions: [_action('North collection directions')],
            ),
            UiContactLocation(
              id: 'south',
              name: 'South archive',
              address: '200 Example Street, Sample City',
              description: 'Synthetic location. Contact the archive to visit.',
              media: _visual('South archive map slot'),
              actions: [_action('South archive directions')],
            ),
          ],
        );
      case 'UiTeamSection':
        return UiTeamSection(
          title: 'People behind the collection',
          description: 'Synthetic profiles, not actual staff.',
          members: [
            _person('Alex Example'),
            _person('Sam Example'),
            _person('Jordan Example'),
          ],
          actions: [_action('View open roles')],
        );
      case 'UiCareerCard':
        return _job('Collection specialist', framed: v == 0);
      case 'UiCareersSection':
        return UiCareersSection(
          title: 'Build knowledge with us',
          description: 'Synthetic vacancies only.',
          departments: const ['All teams', 'Collections', 'Engineering'],
          selectedDepartment: _department,
          onDepartmentChanged: (value) => setState(() => _department = value),
          jobs: [
            if (_department != 'Engineering') _job('Collection specialist'),
            if (_department != 'Collections') _job('Product engineer'),
          ],
        );
      case 'UiFaqSection':
        return UiFaqSection(
          title: 'Frequently asked questions',
          accordion: v == 0,
          items: const [
            UiFaqItem(
              id: 'evidence',
              question: 'Where does the evidence live?',
              answer: Text(
                'Evidence remains linked to its source and collection.',
              ),
            ),
            UiFaqItem(
              id: 'export',
              question: 'Can records be exported?',
              answer: Text(
                'Export capabilities depend on the host application and your access.',
              ),
            ),
          ],
          footer: UiButton(
            label: 'Contact support',
            onPressed: () => _report('Support requested'),
          ),
        );
      case 'UiMarketingFooter':
        return UiMarketingFooter(
          identity: Text('Specimen', style: context.ui.type.title),
          legal: '© 2026 Example collection. Synthetic content.',
          groups: v == 0
              ? []
              : [
                  UiMarketingLinkGroup(
                    title: 'Product',
                    links: [_action('Collections'), _action('Pricing')],
                  ),
                  UiMarketingLinkGroup(
                    title: 'Resources',
                    links: [_action('Guides'), _action('Accessibility')],
                  ),
                ],
          newsletter: v == 1 ? UiEmailCapture(onSubmit: _submit) : null,
          actions: [_action('Privacy'), _action('Terms')],
        );
      case 'UiAnnouncementBanner':
        return _visible
            ? UiAnnouncementBanner(
                message: 'Explore the new collection workspace.',
                actions: v == 2
                    ? []
                    : [
                        _action('Learn more', primary: true),
                        if (v == 1) _action('Maybe later'),
                      ],
                onDismiss: () => setState(() => _visible = false),
                floating: v == 1,
                form: v == 2 ? UiEmailCapture(onSubmit: _submit) : null,
              )
            : UiButton(
                label: 'Restore announcement',
                onPressed: () => setState(() => _visible = true),
              );
      case 'UiAuthLayout':
        return UiAuthLayout(
          title: 'Welcome to Specimen',
          description: 'Synthetic authentication preview.',
          identity: Text('Specimen', style: context.ui.type.title),
          framed: v == 0,
          form: UiAuthForm(mode: UiAuthMode.emailLink, onSubmit: _submit),
          layout: v == 0 ? UiSectionLayout.centered : UiSectionLayout.split,
          media: v == 1 ? _visual('Collection quotation and image slot') : null,
          footer: const Text('No account, email or session is created.'),
        );
      case 'UiAuthForm':
        const policyHelp = 'Example policy: use at least 8 characters.';
        return _formControls(
          UiAuthForm(
            mode: UiAuthMode.values[v],
            onSubmit: _submit,
            passwordHelp: policyHelp,
            validatePassword: (value) =>
                value.length < 8 ? 'Use at least 8 characters.' : null,
            otherActions: [_action('Back to sign in'), _action('Get help')],
          ),
        );
      case 'UiErrorPage':
        return UiErrorPage(
          title: v == 0
              ? 'This page could not be found'
              : 'This collection is unavailable',
          description: 'Check the address or return to your collections.',
          code: v == 0 ? '404' : 'Unavailable',
          actions: _actions,
          layout: v == 0 ? UiSectionLayout.centered : UiSectionLayout.split,
          illustration: v == 1 ? _visual('Decorative recovery visual') : null,
        );
      case 'UiEmailTemplate':
        return UiEmailTemplate(
          subject: [
            'Welcome to Specimen',
            'Verify your email',
            'Recover your account',
            'You have an invitation',
            'Your example receipt',
            'This week in the collection',
            'Your export is ready',
          ][v],
          kind: UiEmailTemplateKind.values[v],
          preheader: 'Synthetic message preview. Nothing is delivered.',
          identity: Text('Specimen Digitization', style: context.ui.type.label),
          body: const Text(
            'Hello Sample Reader,\n\nThis message shows our reusable header, content, action and footer anatomy. Any actual token, destination and delivery belongs to the host.',
          ),
          actions: [_action('Open example destination', primary: true)],
          summary: v == 4
              ? _comparison
              : v == 5
              ? _article('Reading the record', 'Research')
              : null,
          footer: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Example sender address. Synthetic content.'),
              UiButton(
                label: 'Email preferences',
                variant: UiButtonVariant.ghost,
                onPressed: () => _report('Preferences requested'),
              ),
            ],
          ),
        );
      case 'UiDeviceMockup':
        return UiDeviceMockup(
          frame: UiDeviceFrame.values[v],
          child: _visual('Actual product content slot'),
        );
      case 'UiBrandPattern':
        return UiBrandPattern(style: UiBrandPatternStyle.values[v]);
      case 'UiPaymentCardMockup':
        return UiPaymentCardMockup(
          label: 'Example credential',
          holder: 'SAMPLE PERSON',
          lastFour: '0123',
          expiry: '12 / 28',
          branded: v == 0,
        );
      default:
        throw StateError('Unregistered marketing case ${widget.kind}');
    }
  }

  Widget _page(int variant) {
    final sections = <Widget>[];
    switch (variant) {
      case 0:
        sections.addAll([
          UiHeroSection(
            title: 'From specimens to knowledge.',
            description: 'A modern platform for museum collections.',
            actions: _actions,
            media: _visual('Collection visual'),
          ),
          UiFeatureSection(title: 'A connected workflow', features: _features),
          UiSocialProofSection(
            title: 'Designed for collection teams',
            partners: const [
              UiPartnerIdentity(name: 'Example Natural History Collection'),
              UiPartnerIdentity(name: 'Example Research Archive'),
              UiPartnerIdentity(name: 'Example Learning Collection'),
            ],
          ),
          UiTestimonialSection(
            title: 'Example collection perspectives',
            items: _quotes,
            selectedIndex: _selected,
            onSelected: (value) => setState(() => _selected = value),
          ),
          UiMetricsSection(
            title: 'Synthetic collection measures',
            metrics: const [
              UiMarketingMetric(value: '12', label: 'Example collections'),
              UiMarketingMetric(value: '400', label: 'Example records'),
              UiMarketingMetric(value: '8', label: 'Example contributors'),
            ],
          ),
          UiPricingSection(
            title: 'Synthetic plan comparison',
            plans: _plans,
            period: _period,
            onPeriodChanged: (value) => setState(() => _period = value),
          ),
          _pageFaq,
          UiBlogSection(
            title: 'From the journal',
            articles: [
              _article('Reading the record', 'Research'),
              _article('A shared practice', 'Practice'),
            ],
          ),
          _pagePress,
          UiNewsletterSection(
            title: 'Follow the collection journal',
            description: 'A synthetic subscription preview.',
            onSubmit: _submit,
          ),
          UiCallToActionSection(
            title: 'Start with your collection',
            actions: _actions,
          ),
        ]);
      case 1:
        sections.addAll([
          UiPricingSection(
            title: 'Example plans',
            description: 'Synthetic pricing only.',
            plans: _plans,
            period: _period,
            onPeriodChanged: (value) => setState(() => _period = value),
          ),
          _comparison,
          _pageFaq,
          UiFeatureSection(
            title: 'Included in the workflow',
            features: _features,
          ),
          UiCallToActionSection(
            title: 'Find the right collection workflow',
            actions: _actions,
          ),
        ]);
      case 2:
        sections.addAll([
          UiBlogSection(
            title: 'Collection journal',
            articles: [
              _article('Reading the record', 'Research'),
              _article('A shared practice', 'Practice'),
            ],
          ),
          UiNewsletterSection(title: 'Follow the journal', onSubmit: _submit),
        ]);
      case 3:
        sections.add(
          UiContentSection(
            title: 'The story behind a specimen',
            description: 'Synthetic long-form example.',
            media: _visual('Article image'),
            body: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Every record connects an observation to its source.',
                ),
                const UiEditorialQuote(
                  quote: 'Preserve context alongside interpretation.',
                  attribution: 'Synthetic quotation',
                ),
                Text('Methods', style: context.ui.type.title),
                const Text(
                  'Document uncertainty and keep original evidence accessible.',
                ),
              ],
            ),
            actions: [_action('Copy article link')],
          ),
        );
      case 4:
        sections.addAll([
          UiHeroSection(
            title: 'Built around the evidence',
            description:
                'Our purpose is to connect collections and understanding.',
            actions: _actions,
          ),
          UiFeatureShowcase(
            items: [
              UiFeatureShowcaseItem(
                title: 'A shared practice',
                description: 'Bring people and sources together.',
                media: _visual('Team visual'),
              ),
            ],
          ),
          UiTeamSection(
            title: 'The example team',
            members: [_person('Alex Example'), _person('Sam Example')],
          ),
          UiCareersSection(
            title: 'Help connect collections',
            jobs: [_job('Collection specialist'), _job('Product engineer')],
          ),
          _pagePress,
          UiContactSection(
            title: 'Start a conversation',
            form: UiContactForm(
              onSubmit: _submit,
              splitName: true,
              showPhone: true,
            ),
            media: _visual('Collection research visual'),
          ),
        ]);
      case 5:
        sections.addAll([
          UiContactSection(
            title: 'Talk to the team',
            form: UiContactForm(
              onSubmit: _submit,
              consentLabel: 'I agree to the example privacy statement.',
            ),
            methods: [_action('Email'), _action('Office details')],
            media: _visual('Location visual'),
          ),
          UiContactLocations(
            title: 'Example locations',
            selectedId: 'collection',
            locations: [
              UiContactLocation(
                id: 'collection',
                name: 'Example collection',
                address: '100 Example Avenue, Sample City',
                media: _visual('Accessible location map slot'),
                actions: [_action('Directions to example collection')],
              ),
            ],
          ),
        ]);
      case 6:
        sections.add(
          UiTeamSection(
            title: 'Our example team',
            description: 'Synthetic directory.',
            members: [_person('Alex Example'), _person('Sam Example')],
            actions: [_action('Open roles')],
          ),
        );
      case 7:
        sections.add(
          UiCareersSection(
            title: 'Work with collections',
            jobs: [_job('Collection specialist'), _job('Product engineer')],
          ),
        );
      case 8:
        sections.add(
          UiContentSection(
            title: 'Example privacy information',
            description: 'Demonstration content, not a legal policy.',
            body: UiSelectionArea(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Information you provide', style: context.ui.type.title),
                  const Text(
                    'The host supplies its reviewed policy in this content slot.',
                  ),
                  Text('Your choices', style: context.ui.type.title),
                  const Text(
                    'Links and contact details must point to actual policy actions.',
                  ),
                ],
              ),
            ),
            actions: [_action('Contact privacy team')],
          ),
        );
      case 9:
        sections.add(
          UiFaqSection(
            title: 'How can we help?',
            items: const [
              UiFaqItem(
                id: 'access',
                question: 'How does access work?',
                answer: Text(
                  'The host controls collection membership and permissions.',
                ),
              ),
            ],
            footer: UiCallToActionSection(
              title: 'Still have a question?',
              actions: [_action('Contact support')],
            ),
          ),
        );
      case 10:
        sections.add(
          UiAuthLayout(
            title: 'Welcome to Specimen',
            description: 'Synthetic email-first authentication preview.',
            form: UiAuthForm(mode: UiAuthMode.emailLink, onSubmit: _submit),
            media: _visual('Collection visual'),
            layout: UiSectionLayout.split,
          ),
        );
      case 11:
        sections.add(
          UiErrorPage(
            title: 'This page could not be found',
            description: 'Check the address or return to the collection.',
            actions: _actions,
          ),
        );
    }
    return UiMarketingPage(
      header: UiMarketingHeader(
        identity: Text('Specimen', style: context.ui.type.title),
        links: [_action('Collections'), _action('About')],
        actions: [_action('Sign in')],
      ),
      sections: sections,
      footer: UiMarketingFooter(
        identity: Text('Specimen Digitization', style: context.ui.type.label),
        legal:
            'Synthetic page composition. No production content or network actions.',
        actions: [_action('Privacy'), _action('Accessibility')],
      ),
    );
  }

  Widget get _pageFaq => UiFaqSection(
    title: 'Common questions',
    items: const [
      UiFaqItem(
        id: 'workflow',
        question: 'How do teams review records?',
        answer: Text(
          'Review source evidence and record each decision with its reason.',
        ),
      ),
      UiFaqItem(
        id: 'access',
        question: 'Who can access a collection?',
        answer: Text(
          'The host controls membership and permissions for each collection.',
        ),
      ),
    ],
  );

  Widget get _pagePress => UiPressMentionsSection(
    title: 'Example editorial mentions',
    mentions: [
      UiPressMention(
        publication: 'Example Science Journal',
        headline: 'Connecting records with their source evidence',
        date: '22 October 2026',
        onRead: () => _report('Example journal article requested'),
      ),
    ],
  );

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      _buildCase(),
      SizedBox(height: context.ui.space.s6),
      Semantics(liveRegion: true, child: Text(_receipt)),
    ],
  );
}
