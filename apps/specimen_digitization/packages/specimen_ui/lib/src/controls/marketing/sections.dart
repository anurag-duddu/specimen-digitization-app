/// Marketing content families expressed with owned controls and semantic tokens.
library;

import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/surface.dart';
import '../../primitives/popover.dart';
import '../actions/button.dart';
import '../actions/icon_button.dart';
import '../actions/segmented.dart';
import '../data/pagination.dart';
import '../overlays/disclosure.dart';
import 'section.dart';

/// A group of navigation destinations, also used in multi-column footers.
@immutable
class UiMarketingLinkGroup {
  /// Creates a named destination group.
  const UiMarketingLinkGroup({
    required this.title,
    required this.links,
    this.content,
  });

  /// Visible group heading.
  final String title;

  /// Destinations in reading order.
  final List<UiMarketingAction> links;

  /// Optional mega-menu feature cards, sidebar or footer composition.
  final Widget? content;
}

/// Responsive public navigation with desktop links and a mobile menu.
class UiMarketingHeader extends StatefulWidget {
  /// Identity can be a brand mark, wordmark or home action.
  const UiMarketingHeader({
    super.key,
    required this.identity,
    this.links = const [],
    this.groups = const [],
    this.actions = const [],
    this.menuLabel = 'Menu',
  });

  /// Brand/home slot.
  final Widget identity;

  /// Top-level destinations.
  final List<UiMarketingAction> links;

  /// Expandable destination groups.
  final List<UiMarketingLinkGroup> groups;

  /// Login, account or principal commands.
  final List<UiMarketingAction> actions;

  /// Localizable compact menu label.
  final String menuLabel;
  @override
  State<UiMarketingHeader> createState() => _UiMarketingHeaderState();
}

class _UiMarketingHeaderState extends State<UiMarketingHeader> {
  bool _open = false;
  final _menuFocus = FocusNode();

  @override
  void dispose() {
    _menuFocus.dispose();
    super.dispose();
  }

  void _closeMenu() {
    setState(() => _open = false);
    _menuFocus.requestFocus();
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final ui = context.ui;
      final compact =
          constraints.maxWidth <
          ui.space.importWorkspaceMax *
              MediaQuery.textScalerOf(context).scale(16) /
              16;
      Widget destinations() => MarketingStack(
        children: [
          MarketingActions(actions: widget.links),
          for (final group in widget.groups)
            UiDisclosure(
              key: ValueKey(group.title),
              title: group.title,
              child: group.content ?? MarketingActions(actions: group.links),
            ),
          MarketingActions(actions: widget.actions),
        ],
      );
      return CallbackShortcuts(
        bindings: {
          if (compact && _open)
            const SingleActivator(LogicalKeyboardKey.escape): _closeMenu,
        },
        child: Semantics(
          container: true,
          explicitChildNodes: true,
          child: Surface(
            hairline: true,
            padding: EdgeInsets.all(ui.space.s4),
            child: MarketingStack(
              children: [
                if (compact)
                  Row(
                    children: [
                      Expanded(child: widget.identity),
                      Semantics(
                        expanded: _open,
                        child: UiButton(
                          label: widget.menuLabel,
                          focusNode: _menuFocus,
                          variant: UiButtonVariant.ghost,
                          onPressed: () => setState(() => _open = !_open),
                        ),
                      ),
                    ],
                  )
                else
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Flexible(child: widget.identity),
                      SizedBox(width: ui.space.s8),
                      Expanded(
                        flex: 3,
                        child: Wrap(
                          spacing: ui.space.s2,
                          runSpacing: ui.space.s2,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            for (final link in widget.links)
                              UiButton(
                                label: link.label,
                                variant: UiButtonVariant.ghost,
                                onPressed: link.onPressed,
                              ),
                            for (final group in widget.groups)
                              _MarketingMenuTrigger(
                                key: ValueKey(group.title),
                                group: group,
                              ),
                            MarketingActions(actions: widget.actions),
                          ],
                        ),
                      ),
                    ],
                  ),
                if (compact && _open) destinations(),
              ],
            ),
          ),
        ),
      );
    },
  );
}

/// Feature-card composition axes, independent of the enclosing section.
enum UiFeatureLayout {
  /// Icon and text in a row.
  horizontal,

  /// Icon above text.
  stacked,

  /// Centered icon and text.
  centered,

  /// Bordered card with icon above text.
  card,
}

/// A benefit or integration item with optional illustration and command.
class UiFeatureCard extends StatelessWidget {
  /// Creates a feature without fabricating a destination.
  const UiFeatureCard({
    super.key,
    required this.title,
    required this.description,
    this.icon,
    this.media,
    this.action,
    this.layout = UiFeatureLayout.stacked,
  });

  /// Feature heading.
  final String title;

  /// Supporting explanation.
  final String description;

  /// Phosphor icon slot.
  final IconSpec? icon;

  /// Host-provided product image or integration identity.
  final Widget? media;

  /// Optional explicit action.
  final UiMarketingAction? action;

  /// Feature anatomy.
  final UiFeatureLayout layout;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final centered = layout == UiFeatureLayout.centered;
    final text = MarketingStack(
      centered: centered,
      children: [
        Semantics(
          header: true,
          child: Text(
            title,
            textAlign: centered ? TextAlign.center : null,
            style: ui.type.title.copyWith(color: ui.color.ink),
          ),
        ),
        Text(
          description,
          textAlign: centered ? TextAlign.center : null,
          style: ui.type.body.copyWith(color: ui.color.inkSecondary),
        ),
        if (action != null)
          MarketingActions(actions: [action!], centered: centered),
      ],
    );
    final visual =
        media ??
        (icon == null
            ? null
            : UiIcon(
                icon!,
                size: UiIconSize.display,
                color: ui.brand.secondary.content,
              ));
    final content = layout == UiFeatureLayout.horizontal && visual != null
        ? Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              visual,
              SizedBox(width: ui.space.s4),
              Expanded(child: text),
            ],
          )
        : MarketingStack(
            centered: centered,
            children: [
              if (visual != null)
                Align(
                  alignment: centered
                      ? Alignment.center
                      : AlignmentDirectional.centerStart,
                  child: visual,
                ),
              text,
            ],
          );
    return layout == UiFeatureLayout.card
        ? Surface(
            hairline: true,
            radius: ui.shape.tile,
            padding: EdgeInsets.all(ui.space.s6),
            child: content,
          )
        : content;
  }
}

/// A feature collection; tabs can select a detail without reproducing screens.
class UiFeatureSection extends StatelessWidget {
  /// Builds a grid or an optionally controlled feature selector and media detail.
  const UiFeatureSection({
    super.key,
    required this.title,
    required this.features,
    this.description,
    this.media,
    this.selectedIndex,
    this.onSelected,
    this.layout = UiSectionLayout.start,
    this.columns = 3,
  });

  /// Section heading.
  final String title;

  /// Supporting copy.
  final String? description;

  /// Feature descriptions in reading order.
  final List<UiFeatureCard> features;

  /// Optional active product preview.
  final Widget? media;

  /// Selected feature for a selectable presentation; null renders a static grid.
  final int? selectedIndex;

  /// Controlled selection callback. Null disables selection.
  final ValueChanged<int>? onSelected;

  /// Heading/media layout.
  final UiSectionLayout layout;

  /// Maximum grid columns.
  final int columns;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    description: description,
    layout: layout,
    media: media,
    child: selectedIndex == null
        ? UiSectionGrid(columns: columns, children: features)
        : MarketingStack(
            children: [
              Wrap(
                spacing: context.ui.space.s2,
                runSpacing: context.ui.space.s2,
                children: [
                  for (var i = 0; i < features.length; i++)
                    Semantics(
                      selected: selectedIndex == i,
                      child: UiButton(
                        label: features[i].title,
                        variant: selectedIndex == i
                            ? UiButtonVariant.primary
                            : UiButtonVariant.secondary,
                        onPressed: onSelected == null
                            ? null
                            : () => onSelected!(i),
                      ),
                    ),
                ],
              ),
              if (selectedIndex! >= 0 && selectedIndex! < features.length)
                features[selectedIndex!],
            ],
          ),
  );
}

/// A price feature value keeps absence distinct from a textual allowance.
@immutable
class UiPricingFeature {
  /// The row can be included, excluded, or a textual quota.
  const UiPricingFeature(this.label, {this.included = true, this.value});

  /// Feature or quota name.
  final String label;

  /// True when included. False is announced as not included.
  final bool included;

  /// Optional authoritative allowance; never calculated from marketing copy.
  final String? value;
}

/// A subscription tier card; billing calculations stay in the host.
class UiPricingCard extends StatelessWidget {
  /// Creates a tier with price, feature list and purchase/request actions.
  const UiPricingCard({
    super.key,
    required this.title,
    required this.price,
    required this.features,
    this.period,
    this.description,
    this.badge,
    this.featured = false,
    this.actions = const [],
    this.icon,
    this.centered = true,
    this.featureColumns = 1,
  });

  /// Centers plan identity and price while keeping feature labels readable.
  final bool centered;

  /// Maximum feature columns for wide dual-feature plan cards.
  final int featureColumns;

  /// Tier name.
  final String title;

  /// Already localized price, including any currency.
  final String price;

  /// Billing cadence or qualification, such as per month billed annually.
  final String? period;

  /// Supporting description.
  final String? description;

  /// Visible qualification or promotion.
  final String? badge;

  /// Emphasizes the border and title using the secondary brand role.
  final bool featured;

  /// Feature and quota values.
  final List<UiPricingFeature> features;

  /// Primary and secondary commands.
  final List<UiMarketingAction> actions;

  /// Optional leading tier glyph.
  final IconSpec? icon;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Surface(
      boundary: featured,
      hairline: !featured,
      radius: ui.shape.tile,
      padding: EdgeInsets.all(ui.space.s6),
      child: MarketingStack(
        children: [
          if (icon != null)
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiIcon(
                icon!,
                size: UiIconSize.display,
                color: ui.brand.secondary.content,
              ),
            ),
          if (badge != null)
            Text(
              badge!,
              style: ui.type.label.copyWith(color: ui.brand.secondary.content),
            ),
          Semantics(
            header: true,
            child: Text(
              title,
              textAlign: centered ? TextAlign.center : null,
              style: ui.type.title.copyWith(
                color: featured ? ui.brand.secondary.content : ui.color.ink,
              ),
            ),
          ),
          Text(
            price,
            textAlign: centered ? TextAlign.center : null,
            style: ui.type.headline.copyWith(color: ui.color.ink),
          ),
          if (period != null)
            Text(
              period!,
              textAlign: centered ? TextAlign.center : null,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          if (description != null) Text(description!),
          UiSectionGrid(
            columns: featureColumns,
            children: [
              for (final feature in features)
                Semantics(
                  label:
                      '${feature.label}: ${feature.value ?? (feature.included ? "Included" : "Not included")}',
                  excludeSemantics: true,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      UiIcon(
                        feature.included ? UiIcons.check : UiIcons.notPresent,
                        color: ui.color.inkSecondary,
                      ),
                      SizedBox(width: ui.space.s2),
                      Expanded(
                        child: Text(
                          feature.value == null
                              ? feature.label
                              : '${feature.label}: ${feature.value}',
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          MarketingActions(actions: actions, expanded: true),
        ],
      ),
    );
  }
}

/// Controlled billing period for pricing sections.
enum UiBillingPeriod {
  /// Monthly billing.
  monthly,

  /// Annual billing.
  annually,
}

/// Tier grid with a controlled billing switch and optional comparison content.
class UiPricingSection extends StatelessWidget {
  /// Host rebuilds [plans] with its authoritative prices on a period change.
  const UiPricingSection({
    super.key,
    required this.title,
    required this.plans,
    this.description,
    this.period = UiBillingPeriod.monthly,
    this.onPeriodChanged,
    this.comparison,
    this.showBillingToggle = true,
  });

  /// Section heading.
  final String title;

  /// Supporting price explanation.
  final String? description;

  /// Actual price cards for the selected period.
  final List<UiPricingCard> plans;

  /// Current billing mode.
  final UiBillingPeriod period;

  /// Reports a user change; null disables the switch.
  final ValueChanged<UiBillingPeriod>? onPeriodChanged;

  /// Whether the billing selector applies to these plans.
  final bool showBillingToggle;

  /// Detailed comparison, such as [UiPricingComparison].
  final Widget? comparison;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    description: description,
    layout: UiSectionLayout.centered,
    child: MarketingStack(
      children: [
        if (showBillingToggle)
          Align(
            alignment: Alignment.center,
            child: UiSegmented<UiBillingPeriod>(
              label: 'Billing period',
              segments: const [
                UiSegment(value: UiBillingPeriod.monthly, label: 'Monthly'),
                UiSegment(value: UiBillingPeriod.annually, label: 'Annually'),
              ],
              value: period,
              onChanged: onPeriodChanged,
            ),
          ),
        UiSectionGrid(children: plans),
        ?comparison,
      ],
    ),
  );
}

/// A comparison row keyed to the supplied plan labels.
@immutable
class UiPricingComparisonRow {
  /// Values must match the number and order of columns in the comparison.
  const UiPricingComparisonRow(this.feature, this.values);

  /// Compared capability.
  final String feature;

  /// Localized value per plan, including explicit not-included values.
  final List<String> values;
}

/// Pricing comparison that becomes fully labeled cards on narrow allocations.
class UiPricingComparison extends StatelessWidget {
  /// Every row must have exactly one value per plan.
  UiPricingComparison({super.key, required this.plans, required this.rows}) {
    if (plans.isEmpty || rows.any((row) => row.values.length != plans.length)) {
      throw ArgumentError(
        'Comparison requires plans and one value per plan for every row.',
      );
    }
  }

  /// Column labels.
  final List<String> plans;

  /// Feature rows.
  final List<UiPricingComparisonRow> rows;
  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final ui = context.ui;
      final compact =
          constraints.maxWidth <
          ui.space.readingMax * MediaQuery.textScalerOf(context).scale(16) / 16;
      if (compact) {
        return UiSectionGrid(
          children: [
            for (var i = 0; i < plans.length; i++)
              Surface(
                hairline: true,
                padding: EdgeInsets.all(ui.space.s4),
                child: MarketingStack(
                  children: [
                    Semantics(
                      header: true,
                      child: Text(plans[i], style: ui.type.title),
                    ),
                    for (final row in rows)
                      Text('${row.feature}: ${row.values[i]}'),
                  ],
                ),
              ),
          ],
        );
      }
      return Table(
        defaultVerticalAlignment: TableCellVerticalAlignment.middle,
        border: TableBorder(
          horizontalInside: BorderSide(color: ui.color.hairline),
        ),
        children: [
          TableRow(
            children: [
              for (final label in ['Feature', ...plans])
                Padding(
                  padding: EdgeInsets.all(ui.space.s4),
                  child: Semantics(
                    header: true,
                    child: Text(label, style: ui.type.label),
                  ),
                ),
            ],
          ),
          for (final row in rows)
            TableRow(
              children: [
                Padding(
                  padding: EdgeInsets.all(ui.space.s4),
                  child: Text(row.feature),
                ),
                for (var i = 0; i < plans.length; i++)
                  Padding(
                    padding: EdgeInsets.all(ui.space.s4),
                    child: Semantics(
                      label: '${plans[i]}, ${row.feature}: ${row.values[i]}',
                      excludeSemantics: true,
                      child: Text(row.values[i]),
                    ),
                  ),
              ],
            ),
        ],
      );
    },
  );
}

/// A metric whose formatted value and provenance remain host owned.
@immutable
class UiMarketingMetric {
  /// Creates an editorial metric, never an inferred measurement.
  const UiMarketingMetric({
    required this.value,
    required this.label,
    this.description,
    this.icon,
  });

  /// Already formatted value.
  final String value;

  /// What is measured.
  final String label;

  /// Optional period or qualification.
  final String? description;

  /// Optional explanatory glyph.
  final IconSpec? icon;
}

/// A row/grid of prominent metrics with optional solid cards and media.
class UiMetricsSection extends StatelessWidget {
  /// Cards and centered/start alignment share one responsive metric model.
  const UiMetricsSection({
    super.key,
    required this.title,
    required this.metrics,
    this.cards = false,
    this.centered = true,
    this.media,
    this.eyebrow,
    this.description,
    this.layout,
  });

  /// Section heading.
  final String title;

  /// Measured values.
  final List<UiMarketingMetric> metrics;

  /// Encloses each metric in a bordered card.
  final bool cards;

  /// Centers metric typography.
  final bool centered;

  /// Optional supporting evidence or illustration.
  final Widget? media;

  /// Optional context above the metric section heading.
  final String? eyebrow;

  /// Explanation of the section's measurements.
  final String? description;

  /// Optional text/media composition; null retains [centered]'s arrangement.
  final UiSectionLayout? layout;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    eyebrow: eyebrow,
    description: description,
    layout:
        layout ?? (centered ? UiSectionLayout.centered : UiSectionLayout.start),
    media: media,
    child: UiSectionGrid(
      columns: 4,
      children: [
        for (final metric in metrics)
          Surface(
            hairline: cards,
            padding: EdgeInsets.all(context.ui.space.s4),
            child: MarketingStack(
              centered: centered,
              children: [
                if (metric.icon != null)
                  UiIcon(
                    metric.icon!,
                    color: context.ui.brand.secondary.content,
                  ),
                Text(
                  metric.value,
                  textAlign: centered ? TextAlign.center : null,
                  style: context.ui.type.headline.copyWith(
                    color: context.ui.brand.secondary.content,
                  ),
                ),
                Text(
                  metric.label,
                  textAlign: centered ? TextAlign.center : null,
                  style: context.ui.type.title,
                ),
                if (metric.description != null)
                  Text(
                    metric.description!,
                    textAlign: centered ? TextAlign.center : null,
                  ),
              ],
            ),
          ),
      ],
    ),
  );
}

/// Quote data with independently labeled attribution and optional portrait.
@immutable
class UiTestimonial {
  /// Only use actual quotations with permission in product pages.
  const UiTestimonial({
    required this.quote,
    required this.author,
    this.role,
    this.portrait,
    this.rating,
  });

  /// Quoted words.
  final String quote;

  /// Attribution.
  final String author;

  /// Optional role or organisation.
  final String? role;

  /// Host-provided portrait.
  final Widget? portrait;

  /// Optional rating from one through five.
  final int? rating;
}

/// Controlled testimonial carousel or a static multi-column collection.
class UiTestimonialSection extends StatelessWidget {
  /// A selected index enables a non-autoplay carousel with explicit controls.
  const UiTestimonialSection({
    super.key,
    required this.title,
    required this.items,
    this.selectedIndex,
    this.onSelected,
    this.layout = UiSectionLayout.centered,
    this.description,
    this.actions = const [],
  });

  /// Section heading.
  final String title;

  /// Quotes in reading order.
  final List<UiTestimonial> items;

  /// Active item, or null for a grid.
  final int? selectedIndex;

  /// Reports carousel selection. Null disables navigation.
  final ValueChanged<int>? onSelected;

  /// Quote and portrait relationship.
  final UiSectionLayout layout;

  /// Introductory copy before the quote collection.
  final String? description;

  /// Customer-story, contact or other host-owned section commands.
  final List<UiMarketingAction> actions;
  Widget _quote(BuildContext context, UiTestimonial item) => UiMarketingSection(
    title: '“${item.quote}”',
    description: '${item.author}${item.role == null ? "" : " · ${item.role}"}',
    layout: layout,
    media: item.portrait,
    treatment: UiSectionTreatment.card,
    child: item.rating == null
        ? null
        : Text('${item.rating!.clamp(1, 5)} out of 5 stars'),
  );
  @override
  Widget build(BuildContext context) {
    final active = selectedIndex == null || items.isEmpty
        ? null
        : selectedIndex!.clamp(0, items.length - 1);
    return UiMarketingSection(
      title: title,
      description: description,
      actions: actions,
      child: active == null
          ? UiSectionGrid(
              columns: 2,
              children: [for (final item in items) _quote(context, item)],
            )
          : MarketingStack(
              children: [
                Semantics(
                  liveRegion: true,
                  child: _quote(context, items[active]),
                ),
                Wrap(
                  spacing: context.ui.space.s2,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    UiIconButton(
                      icon: UiIcons.previous,
                      semanticsLabel: 'Previous testimonial',
                      onPressed: onSelected == null || active == 0
                          ? null
                          : () => onSelected!(active - 1),
                    ),
                    Text('${active + 1} of ${items.length}'),
                    UiIconButton(
                      icon: UiIcons.next,
                      semanticsLabel: 'Next testimonial',
                      onPressed:
                          onSelected == null || active == items.length - 1
                          ? null
                          : () => onSelected!(active + 1),
                    ),
                  ],
                ),
              ],
            ),
    );
  }
}

/// Social-proof identity with a readable name even when its visual is a logo.
@immutable
class UiPartnerIdentity {
  /// Uses authorized host-provided artwork; never copies reference logos.
  const UiPartnerIdentity({required this.name, this.visual, this.onPressed});

  /// Organisation name.
  final String name;

  /// Optional logo/image; textual identity is the default.
  final Widget? visual;

  /// Optional destination, represented by a separate named action.
  final VoidCallback? onPressed;
}

/// A wrapping, accessible partner/collection identity strip or card grid.
class UiSocialProofSection extends StatelessWidget {
  /// Creates a social proof collection.
  const UiSocialProofSection({
    super.key,
    required this.title,
    required this.partners,
    this.cards = false,
  });

  /// Section heading.
  final String title;

  /// Authorized identities.
  final List<UiPartnerIdentity> partners;

  /// Frames each identity in a card.
  final bool cards;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    layout: UiSectionLayout.centered,
    child: UiSectionGrid(
      columns: 4,
      children: [
        for (final partner in partners)
          Surface(
            hairline: cards,
            padding: EdgeInsets.all(context.ui.space.s4),
            child: MarketingStack(
              centered: true,
              children: [
                if (partner.visual != null)
                  Semantics(
                    label: partner.name,
                    image: true,
                    excludeSemantics: true,
                    child: partner.visual!,
                  )
                else
                  Text(
                    partner.name,
                    textAlign: TextAlign.center,
                    style: context.ui.type.title,
                  ),
                if (partner.onPressed != null)
                  UiButton(
                    label: 'Visit ${partner.name}',
                    variant: UiButtonVariant.ghost,
                    onPressed: partner.onPressed,
                  ),
              ],
            ),
          ),
      ],
    ),
  );
}

/// Article presentation axes; imagery is always a host-provided slot.
enum UiArticleLayout {
  /// Image above headline.
  vertical,

  /// Image beside headline, stacking on compact allocations.
  horizontal,

  /// A bordered vertical card.
  card,
}

/// Editorial card with category, author, date, reading time and an actual link.
class UiArticleCard extends StatelessWidget {
  /// No synthetic article or inaccessible image is inserted by the library.
  const UiArticleCard({
    super.key,
    required this.title,
    required this.description,
    this.category,
    this.metadata,
    this.author,
    this.media,
    this.onRead,
    this.layout = UiArticleLayout.vertical,
  });

  /// Headline.
  final String title;

  /// Summary.
  final String description;

  /// Topic/category.
  final String? category;

  /// Author, publication date and reading-time string.
  final String? metadata;

  /// Structured author identity, such as an avatar with name and publication date.
  final Widget? author;

  /// Photograph or illustration with host-supplied semantics.
  final Widget? media;

  /// Opens the article; null disables the visible action.
  final VoidCallback? onRead;

  /// Card composition.
  final UiArticleLayout layout;
  @override
  Widget build(BuildContext context) {
    final attribution = author == null && metadata == null
        ? null
        : MarketingStack(
            children: [
              ?author,
              if (metadata != null)
                Text(metadata!, style: context.ui.type.bodySmall),
            ],
          );
    final heading = UiMarketingSection(
      title: title,
      eyebrow: category,
      description: description,
      actions: [UiMarketingAction('Read $title', onPressed: onRead)],
      child: attribution,
    );
    if (layout == UiArticleLayout.horizontal) {
      return UiMarketingSection(
        title: title,
        eyebrow: category,
        description: description,
        media: media,
        layout: UiSectionLayout.splitReversed,
        actions: [UiMarketingAction('Read $title', onPressed: onRead)],
        child: attribution,
      );
    }
    final content = MarketingStack(children: [?media, heading]);
    return layout == UiArticleLayout.card
        ? Surface(
            hairline: true,
            radius: context.ui.shape.tile,
            padding: EdgeInsets.all(context.ui.space.s6),
            child: content,
          )
        : content;
  }
}

/// Editorial collection composition, independent of each article's card style.
enum UiBlogLayout {
  /// Equal-width cards in a responsive grid.
  grid,

  /// One leading article followed by the remaining article grid.
  featured,

  /// Filters and supporting content beside results, stacking on narrow screens.
  sidebar,

  /// One controlled article at a time with explicit paging and no autoplay.
  carousel,
}

/// Editorial collection with controlled category navigation and pagination slot.
class UiBlogSection extends StatelessWidget {
  /// The host supplies the filtered articles and owns querying/pagination.
  const UiBlogSection({
    super.key,
    required this.title,
    required this.articles,
    this.categories = const [],
    this.selectedCategory,
    this.onCategoryChanged,
    this.footer,
    this.layout = UiBlogLayout.grid,
    this.sidebar,
    this.selectedIndex = 0,
    this.onSelected,
    this.toolbar,
    this.eyebrow,
    this.description,
    this.featured,
  });

  /// Grid, featured, sidebar or carousel composition.
  final UiBlogLayout layout;

  /// Optional search, newsletter or supporting navigation beside the results.
  final Widget? sidebar;

  /// Caller-owned sort, search or display controls above the article results.
  final Widget? toolbar;

  /// Context above the collection heading.
  final String? eyebrow;

  /// Introductory copy before the featured article and results.
  final String? description;

  /// Independent leading article, including when results use a sidebar.
  /// The host excludes this article from [articles] to avoid duplicate results.
  final UiArticleCard? featured;

  /// Zero-based active article for [UiBlogLayout.carousel].
  final int selectedIndex;

  /// Host-controlled carousel selection; null disables its page commands.
  final ValueChanged<int>? onSelected;

  /// Section heading.
  final String title;

  /// Current article results.
  final List<UiArticleCard> articles;

  /// Available filter labels.
  final List<String> categories;

  /// Active category.
  final String? selectedCategory;

  /// Reports a category selection.
  final ValueChanged<String>? onCategoryChanged;

  /// Pagination, load-more, or no-results content supplied by the host.
  final Widget? footer;
  @override
  Widget build(BuildContext context) {
    final filters = MarketingStack(
      children: [
        if (categories.isNotEmpty)
          Wrap(
            spacing: context.ui.space.s2,
            runSpacing: context.ui.space.s2,
            children: [
              for (final category in categories)
                Semantics(
                  selected: selectedCategory == category,
                  child: UiButton(
                    label: category,
                    variant: selectedCategory == category
                        ? UiButtonVariant.primary
                        : UiButtonVariant.secondary,
                    onPressed: onCategoryChanged == null
                        ? null
                        : () => onCategoryChanged!(category),
                  ),
                ),
            ],
          ),
        ?sidebar,
      ],
    );
    final active = articles.isEmpty
        ? 0
        : selectedIndex.clamp(0, articles.length - 1);
    final results = MarketingStack(
      children: [
        if (layout == UiBlogLayout.featured &&
            featured == null &&
            articles.isNotEmpty) ...[
          articles.first,
          UiSectionGrid(children: articles.skip(1).toList()),
        ] else if (layout == UiBlogLayout.carousel && articles.isNotEmpty) ...[
          Semantics(liveRegion: true, child: articles[active]),
          UiPagination(
            page: active + 1,
            pageCount: articles.length,
            onChanged: onSelected == null
                ? null
                : (page) => onSelected!(page - 1),
            semanticsLabel: 'Article carousel',
          ),
        ] else
          UiSectionGrid(children: articles),
        ?footer,
      ],
    );
    return UiMarketingSection(
      title: title,
      eyebrow: eyebrow,
      description: description,
      child: MarketingStack(
        children: [
          ?featured,
          ?toolbar,
          LayoutBuilder(
            builder: (context, constraints) {
              final wide =
                  constraints.maxWidth >=
                  context.ui.space.importWorkspaceMax *
                      MediaQuery.textScalerOf(context).scale(16) /
                      16;
              if (layout == UiBlogLayout.sidebar && wide) {
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: filters),
                    SizedBox(width: context.ui.space.s8),
                    Expanded(flex: 3, child: results),
                  ],
                );
              }
              return MarketingStack(children: [filters, results]);
            },
          ),
        ],
      ),
    );
  }
}

/// Long-form editorial content with a real table-of-contents action rail.
class UiContentSection extends StatelessWidget {
  /// Body supports owned headings, lists, quotations, code and native selection.
  const UiContentSection({
    super.key,
    required this.title,
    required this.body,
    this.description,
    this.media,
    this.caption,
    this.contents = const [],
    this.actions = const [],
    this.category,
    this.byline,
  });

  /// Article heading.
  final String title;

  /// Introductory summary.
  final String? description;

  /// Article category or publication context above the title.
  final String? category;

  /// Structured author, portrait and publication details before the main figure.
  final Widget? byline;

  /// Host-supplied structured content.
  final Widget body;

  /// Optional article figure.
  final Widget? media;

  /// Figure caption.
  final String? caption;

  /// Actions to real section anchors, supplied by the host.
  final List<UiMarketingAction> contents;

  /// Sharing/copy commands.
  final List<UiMarketingAction> actions;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    eyebrow: category,
    description: description,
    child: MarketingStack(
      children: [
        ?byline,
        ?media,
        if (caption != null) Text(caption!, style: context.ui.type.bodySmall),
        LayoutBuilder(
          builder: (context, constraints) {
            final wide =
                constraints.maxWidth >=
                context.ui.space.importWorkspaceMax *
                    MediaQuery.textScalerOf(context).scale(16) /
                    16;
            if (!wide || contents.isEmpty) {
              return MarketingStack(
                children: [
                  if (contents.isNotEmpty)
                    UiDisclosure(
                      title: 'On this page',
                      child: MarketingActions(actions: contents),
                    ),
                  body,
                ],
              );
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: MarketingActions(actions: contents)),
                SizedBox(width: context.ui.space.s8),
                Expanded(flex: 3, child: body),
              ],
            );
          },
        ),
        MarketingActions(actions: actions),
      ],
    ),
  );
}

/// Portrait and biography arrangement for a team member.
enum UiTeamMemberLayout {
  /// Portrait above biography.
  stacked,

  /// Portrait beside biography when the allocation allows it.
  horizontal,

  /// Full-width portrait over a solid, readable biography panel.
  portraitCard,
}

/// Host-provided location identity and accessible map/photograph.
@immutable
class UiContactLocation {
  /// Keeps location data and destinations explicit.
  const UiContactLocation({
    required this.id,
    required this.name,
    required this.address,
    this.description,
    this.media,
    this.actions = const [],
  });

  /// Stable identity used for controlled selection.
  final String id;

  /// Public location name.
  final String name;

  /// Display-ready street/postal address.
  final String address;

  /// Optional opening hours or contact context.
  final String? description;

  /// Actual map or photograph with its own accessible interaction contract.
  final Widget? media;

  /// Directions, email or phone actions supplied by the host.
  final List<UiMarketingAction> actions;
}

/// Controlled contact locations with matching address, actions and map content.
class UiContactLocations extends StatelessWidget {
  /// A missing selected ID shows no detail instead of attributing the wrong map.
  const UiContactLocations({
    super.key,
    required this.title,
    required this.locations,
    required this.selectedId,
    this.onSelected,
    this.layout = UiSectionLayout.split,
  });

  /// Section heading.
  final String title;

  /// Available locations, in reading order.
  final List<UiContactLocation> locations;

  /// Authoritative selected location ID.
  final String? selectedId;

  /// Selection request; null disables the location selectors.
  final ValueChanged<String>? onSelected;

  /// Address and map composition.
  final UiSectionLayout layout;

  @override
  Widget build(BuildContext context) {
    final selected = locations
        .where((location) => location.id == selectedId)
        .firstOrNull;
    return UiMarketingSection(
      title: title,
      child: MarketingStack(
        children: [
          Wrap(
            spacing: context.ui.space.s2,
            runSpacing: context.ui.space.s2,
            children: [
              for (final location in locations)
                Semantics(
                  selected: location.id == selectedId,
                  child: UiButton(
                    label: location.name,
                    variant: location.id == selectedId
                        ? UiButtonVariant.primary
                        : UiButtonVariant.secondary,
                    onPressed: onSelected == null
                        ? null
                        : () => onSelected!(location.id),
                  ),
                ),
            ],
          ),
          if (selected != null)
            UiMarketingSection(
              key: ValueKey(selected.id),
              title: selected.name,
              description: selected.description,
              media: selected.media,
              actions: selected.actions,
              layout: layout,
              child: Text(selected.address),
            )
          else
            const Text('Select a location to view its details.'),
        ],
      ),
    );
  }
}

/// A person profile with optional portrait and contact/social actions.
class UiTeamMemberCard extends StatelessWidget {
  /// Names and biographies must represent authorized published information.
  const UiTeamMemberCard({
    super.key,
    required this.name,
    required this.role,
    this.biography,
    this.portrait,
    this.actions = const [],
    this.centered = false,
    this.framed = false,
    this.layout = UiTeamMemberLayout.stacked,
  });

  /// Portrait/biography relationship. Text always retains a solid background.
  final UiTeamMemberLayout layout;

  /// Public name.
  final String name;

  /// Position or contribution.
  final String role;

  /// Optional biography.
  final String? biography;

  /// Host-provided portrait.
  final Widget? portrait;

  /// Explicit public-profile/contact actions.
  final List<UiMarketingAction> actions;

  /// Centers text and portrait.
  final bool centered;

  /// Bordered card treatment.
  final bool framed;
  @override
  Widget build(BuildContext context) {
    final biographyPanel = MarketingStack(
      centered: centered,
      children: [
        Text(
          name,
          textAlign: centered ? TextAlign.center : null,
          style: context.ui.type.title,
        ),
        Text(
          role,
          textAlign: centered ? TextAlign.center : null,
          style: context.ui.type.label.copyWith(
            color: context.ui.brand.secondary.content,
          ),
        ),
        if (biography != null)
          Text(biography!, textAlign: centered ? TextAlign.center : null),
        MarketingActions(actions: actions, centered: centered),
      ],
    );
    if (layout == UiTeamMemberLayout.portraitCard) {
      return Surface(
        hairline: true,
        radius: context.ui.shape.tile,
        clip: true,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ?portrait,
            Padding(
              padding: EdgeInsets.all(context.ui.space.s6),
              child: biographyPanel,
            ),
          ],
        ),
      );
    }
    return Surface(
      hairline: framed,
      padding: EdgeInsets.all(context.ui.space.s4),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final scale = MediaQuery.textScalerOf(context).scale(16) / 16;
          if (layout == UiTeamMemberLayout.horizontal &&
              portrait != null &&
              constraints.maxWidth >= context.ui.space.readingMax * scale) {
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: portrait!),
                SizedBox(width: context.ui.space.s6),
                Expanded(flex: 2, child: biographyPanel),
              ],
            );
          }
          return MarketingStack(children: [?portrait, biographyPanel]);
        },
      ),
    );
  }
}

/// Responsive team directory with optional recruiting commands.
class UiTeamSection extends StatelessWidget {
  /// Creates a team section in a caller-selected number of columns.
  const UiTeamSection({
    super.key,
    required this.title,
    required this.members,
    this.description,
    this.actions = const [],
    this.columns = 3,
  });

  /// Heading.
  final String title;

  /// Introductory copy.
  final String? description;

  /// Published profiles.
  final List<UiTeamMemberCard> members;

  /// Recruiting or directory commands.
  final List<UiMarketingAction> actions;

  /// Maximum columns.
  final int columns;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    description: description,
    actions: actions,
    child: UiSectionGrid(columns: columns, children: members),
  );
}

/// A vacancy with meaningful metadata and a real application command.
class UiCareerCard extends StatelessWidget {
  /// Creates a vacancy row or framed card.
  const UiCareerCard({
    super.key,
    required this.title,
    required this.description,
    required this.metadata,
    this.onApply,
    this.framed = true,
  });

  /// Vacancy title.
  final String title;

  /// Role summary.
  final String description;

  /// Location, schedule and compensation where available.
  final List<String> metadata;

  /// Opens the host's application flow.
  final VoidCallback? onApply;

  /// Bordered card versus unframed row.
  final bool framed;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    description: description,
    treatment: framed ? UiSectionTreatment.card : UiSectionTreatment.plain,
    actions: [UiMarketingAction('Apply for $title', onPressed: onApply)],
    child: Wrap(
      spacing: context.ui.space.s4,
      runSpacing: context.ui.space.s2,
      children: [
        for (final value in metadata)
          Text(value, style: context.ui.type.bodySmall),
      ],
    ),
  );
}

/// A department heading and its current vacancies.
@immutable
class UiCareerGroup {
  /// The host supplies actual department membership and filtered vacancies.
  const UiCareerGroup({required this.title, required this.jobs});

  /// Department name, exposed as a section heading.
  final String title;

  /// Vacancies in this department, in reading order.
  final List<UiCareerCard> jobs;
}

/// Careers collection grouped by department, with a controlled filter.
class UiCareersSection extends StatelessWidget {
  /// Host owns the filtered vacancy set and application destinations.
  const UiCareersSection({
    super.key,
    required this.title,
    this.jobs = const [],
    this.description,
    this.departments = const [],
    this.selectedDepartment,
    this.onDepartmentChanged,
    this.media,
    this.groups = const [],
  });

  /// Section heading.
  final String title;

  /// Careers introduction.
  final String? description;

  /// Current vacancies.
  final List<UiCareerCard> jobs;

  /// Optional introductory photograph or culture/benefits content.
  final Widget? media;

  /// Department headings with host-owned vacancy membership.
  final List<UiCareerGroup> groups;

  /// Department choices.
  final List<String> departments;

  /// Active department.
  final String? selectedDepartment;

  /// Selection callback.
  final ValueChanged<String>? onDepartmentChanged;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    description: description,
    child: MarketingStack(
      children: [
        ?media,
        Wrap(
          spacing: context.ui.space.s2,
          runSpacing: context.ui.space.s2,
          children: [
            for (final department in departments)
              Semantics(
                selected: department == selectedDepartment,
                child: UiButton(
                  label: department,
                  variant: department == selectedDepartment
                      ? UiButtonVariant.primary
                      : UiButtonVariant.secondary,
                  onPressed: onDepartmentChanged == null
                      ? null
                      : () => onDepartmentChanged!(department),
                ),
              ),
          ],
        ),
        ...jobs,
        for (final group in groups)
          MarketingStack(
            children: [
              Semantics(
                header: true,
                child: Text(group.title, style: context.ui.type.title),
              ),
              ...group.jobs,
            ],
          ),
      ],
    ),
  );
}

/// Frequently asked question content.
@immutable
class UiFaqItem {
  /// Stable [id] preserves expansion when items are filtered or reordered.
  const UiFaqItem({
    required this.id,
    required this.question,
    required this.answer,
  });

  /// Stable identity.
  final String id;

  /// Question/header.
  final String question;

  /// Answer, links or formatted content.
  final Widget answer;
}

/// Accessible accordions or always-visible question columns.
class UiFaqSection extends StatelessWidget {
  /// Creates an accordion or static grid, including a support footer slot.
  const UiFaqSection({
    super.key,
    required this.title,
    required this.items,
    this.accordion = true,
    this.footer,
    this.description,
    this.search,
    this.emptyState,
  });

  /// Section heading.
  final String title;

  /// Introductory copy.
  final String? description;

  /// Host-owned search/filter control. The host supplies the matching [items].
  final Widget? search;

  /// Optional no-results content shown when the supplied item list is empty.
  final Widget? emptyState;

  /// Questions and stable identities.
  final List<UiFaqItem> items;

  /// Uses owned keyboard/screen-reader disclosures when true.
  final bool accordion;

  /// Optional support call-to-action.
  final Widget? footer;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    description: description,
    child: MarketingStack(
      children: [
        ?search,
        if (items.isEmpty) ?emptyState,
        if (accordion)
          for (final item in items)
            UiDisclosure(
              key: ValueKey(item.id),
              title: item.question,
              child: item.answer,
            )
        else
          UiSectionGrid(
            columns: 2,
            children: [
              for (final item in items)
                MarketingStack(
                  children: [
                    Semantics(
                      header: true,
                      child: Text(item.question, style: context.ui.type.title),
                    ),
                    item.answer,
                  ],
                ),
            ],
          ),
        ?footer,
      ],
    ),
  );
}

/// Multi-column footer with identity, newsletter, legal and social action slots.
class UiMarketingFooter extends StatelessWidget {
  /// The minimal form uses identity and legal text; groups expand it.
  const UiMarketingFooter({
    super.key,
    required this.identity,
    required this.legal,
    this.groups = const [],
    this.newsletter,
    this.actions = const [],
    this.callToAction,
  });

  /// Brand identity.
  final Widget identity;

  /// Copyright, ownership or legal copy.
  final String legal;

  /// Grouped destinations.
  final List<UiMarketingLinkGroup> groups;

  /// Optional actual email capture form.
  final Widget? newsletter;

  /// Legal/social/app-download destinations.
  final List<UiMarketingAction> actions;

  /// Optional closing section before identity and grouped destinations.
  final Widget? callToAction;
  @override
  Widget build(BuildContext context) => Surface(
    hairline: true,
    padding: EdgeInsets.all(context.ui.space.s6),
    child: MarketingStack(
      children: [
        ?callToAction,
        identity,
        ?newsletter,
        UiSectionGrid(
          columns: 4,
          children: [
            for (final group in groups)
              MarketingStack(
                children: [
                  Semantics(
                    header: true,
                    child: Text(group.title, style: context.ui.type.label),
                  ),
                  for (final link in group.links)
                    Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: UiButton(
                        label: link.label,
                        onPressed: link.onPressed,
                        variant: UiButtonVariant.ghost,
                      ),
                    ),
                ],
              ),
          ],
        ),
        Text(
          legal,
          style: context.ui.type.bodySmall.copyWith(
            color: context.ui.color.inkSecondary,
          ),
        ),
        MarketingActions(actions: actions),
      ],
    ),
  );
}

/// Announcements support slim text, actions, and inline forms without clipping.
class UiAnnouncementBanner extends StatelessWidget {
  /// Visibility is caller-owned; dismissal never silently persists a preference.
  const UiAnnouncementBanner({
    super.key,
    required this.message,
    this.actions = const [],
    this.onDismiss,
    this.form,
    this.floating = false,
    this.dismissLabel = 'Dismiss announcement',
    this.title,
    this.icon,
  });

  /// Announcement text.
  final String message;

  /// Optional heading, independently styled above the supporting [message].
  final String? title;

  /// Optional Phosphor icon accompanying the heading and message.
  final IconSpec? icon;

  /// Principal/secondary commands.
  final List<UiMarketingAction> actions;

  /// Optional dismissal callback.
  final VoidCallback? onDismiss;

  /// Optional text field/capture form.
  final Widget? form;

  /// Rounded floating rather than edge-to-edge presentation.
  final bool floating;

  /// Localizable accessible dismiss name.
  final String dismissLabel;
  @override
  Widget build(BuildContext context) => Surface(
    boundary: true,
    radius: floating ? context.ui.shape.tile : context.ui.shape.none,
    padding: EdgeInsets.all(context.ui.space.s4),
    child: MarketingStack(
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (icon != null) ...[
              UiIcon(icon!, color: context.ui.brand.secondary.content),
              SizedBox(width: context.ui.space.s3),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (title != null) ...[
                    Text(title!, style: context.ui.type.label),
                    SizedBox(height: context.ui.space.s1),
                  ],
                  Text(message, style: context.ui.type.body),
                ],
              ),
            ),
            if (onDismiss != null)
              UiIconButton(
                icon: UiIcons.close,
                semanticsLabel: dismissLabel,
                onPressed: onDismiss,
              ),
          ],
        ),
        if (actions.isNotEmpty) MarketingActions(actions: actions),
        ?form,
      ],
    ),
  );
}

/// Rich navigation panel with link columns, featured cards, sidebar and footer.
class UiMegaMenuContent extends StatelessWidget {
  /// Each slot can contain real actions, articles, features or video controls.
  const UiMegaMenuContent({
    super.key,
    required this.columns,
    this.featured,
    this.sidebar,
    this.footer,
  });

  /// Main column content in reading order.
  final List<Widget> columns;

  /// Optional featured card or media before the columns.
  final Widget? featured;

  /// Secondary resource column, stacked below on narrow allocations.
  final Widget? sidebar;

  /// Resource links or promotional footer.
  final Widget? footer;
  @override
  Widget build(BuildContext context) => MarketingStack(
    children: [
      ?featured,
      UiSectionGrid(
        columns: sidebar == null
            ? columns.length.clamp(1, 4)
            : (columns.length + 1).clamp(1, 4),
        children: [...columns, ?sidebar],
      ),
      ?footer,
    ],
  );
}

class _MarketingMenuTrigger extends StatefulWidget {
  const _MarketingMenuTrigger({super.key, required this.group});
  final UiMarketingLinkGroup group;
  @override
  State<_MarketingMenuTrigger> createState() => _MarketingMenuTriggerState();
}

class _MarketingMenuTriggerState extends State<_MarketingMenuTrigger> {
  final _controller = PopoverController();
  final _focus = FocusNode();

  void _toggle() {
    if (!_controller.isOpen) {
      // A pointer does not necessarily move focus. The overlay must begin in
      // this trigger's focus lineage so Escape also works for pointer opens.
      _focus.requestFocus();
      FocusManager.instance.applyFocusChangesIfNeeded();
    }
    _controller.toggle();
  }

  @override
  void initState() {
    super.initState();
    _controller.addListener(_restoreFocus);
  }

  void _restoreFocus() {
    if (_controller.isOpen) return;
    // Pointer activation need not focus a button. Restore this actual trigger
    // after the popover has removed its focus scope, even for pointer opens.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && !_controller.isOpen) _focus.requestFocus();
    });
  }

  @override
  void dispose() {
    _controller.removeListener(_restoreFocus);
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Popover(
    controller: _controller,
    surface: PopoverSurface.paper,
    semanticsLabel: widget.group.title,
    overlayBuilder: (context) => SizedBox(
      width: context.ui.space.importWorkspaceMax,
      child: SingleChildScrollView(
        padding: EdgeInsets.all(context.ui.space.s6),
        child:
            widget.group.content ??
            MarketingActions(actions: widget.group.links),
      ),
    ),
    child: ListenableBuilder(
      listenable: _controller,
      builder: (context, _) => Semantics(
        expanded: _controller.isOpen,
        child: UiButton(
          label: widget.group.title,
          leading: UiIcons.expand,
          focusNode: _focus,
          variant: UiButtonVariant.ghost,
          onPressed: _toggle,
        ),
      ),
    ),
  );
}

/// A feature and its actual supporting media for alternating feature rows.
@immutable
class UiFeatureShowcaseItem {
  /// Creates a media/text pair.
  const UiFeatureShowcaseItem({
    required this.title,
    required this.description,
    required this.media,
    this.actions = const [],
    this.icon,
    this.benefits = const [],
  });

  /// Feature heading.
  final String title;

  /// Feature explanation.
  final String description;

  /// Product image, application preview or illustration.
  final Widget media;

  /// Commands relevant to this feature.
  final List<UiMarketingAction> actions;

  /// Optional Phosphor heading icon.
  final IconSpec? icon;

  /// Explicit supporting benefits, displayed as a readable checked list.
  final List<String> benefits;
}

/// Alternating text/media feature rows, stacking in reading order on mobile.
class UiFeatureShowcase extends StatelessWidget {
  /// Reverses every second row when [alternating] is enabled.
  const UiFeatureShowcase({
    super.key,
    required this.items,
    this.alternating = true,
  });

  /// Paired features.
  final List<UiFeatureShowcaseItem> items;

  /// Alternates media placement at wide widths.
  final bool alternating;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    mainAxisSize: MainAxisSize.min,
    children: [
      for (var i = 0; i < items.length; i++) ...[
        if (i > 0) SizedBox(height: context.ui.space.s16),
        UiMarketingSection(
          title: items[i].title,
          leading: items[i].icon == null
              ? null
              : UiIcon(
                  items[i].icon!,
                  size: UiIconSize.display,
                  color: context.ui.brand.secondary.content,
                ),
          description: items[i].description,
          media: items[i].media,
          actions: items[i].actions,
          layout: alternating && i.isOdd
              ? UiSectionLayout.splitReversed
              : UiSectionLayout.split,
          child: items[i].benefits.isEmpty
              ? null
              : MarketingStack(
                  children: [
                    for (final benefit in items[i].benefits)
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const UiIcon(UiIcons.check),
                          SizedBox(width: context.ui.space.s2),
                          Expanded(child: Text(benefit)),
                        ],
                      ),
                  ],
                ),
        ),
      ],
    ],
  );
}

/// Editorial figure with explicit image alternative and a visible caption.
class UiEditorialFigure extends StatelessWidget {
  /// Aspect ratio is optional so native sized content can grow naturally.
  const UiEditorialFigure({
    super.key,
    required this.child,
    required this.alternative,
    this.caption,
    this.aspectRatio,
  });

  /// Actual host-provided media.
  final Widget child;

  /// Accessible image description.
  final String alternative;

  /// Visible figure explanation or attribution.
  final String? caption;

  /// Optional display crop/fit allocation, such as 3/2 or 1.
  final double? aspectRatio;
  @override
  Widget build(BuildContext context) => MarketingStack(
    children: [
      Semantics(
        image: true,
        label: alternative,
        excludeSemantics: true,
        child: aspectRatio == null
            ? child
            : AspectRatio(aspectRatio: aspectRatio!, child: child),
      ),
      if (caption != null)
        Text(
          caption!,
          style: context.ui.type.bodySmall.copyWith(
            color: context.ui.color.inkSecondary,
          ),
        ),
    ],
  );
}

/// Quotation block with independent attribution and optional centered layout.
class UiEditorialQuote extends StatelessWidget {
  /// Text remains selectable when the host wraps the article in UiSelectionArea.
  const UiEditorialQuote({
    super.key,
    required this.quote,
    this.attribution,
    this.centered = false,
  });

  /// Verbatim quotation, supplied by the host with permission.
  final String quote;

  /// Author/source.
  final String? attribution;

  /// Centered versus leading quote rule.
  final bool centered;
  @override
  Widget build(BuildContext context) => Container(
    decoration: centered
        ? null
        : BoxDecoration(
            border: BorderDirectional(
              start: BorderSide(
                color: context.ui.brand.secondary.content,
                width: context.ui.shape.stroke.bar,
              ),
            ),
          ),
    padding: EdgeInsets.all(context.ui.space.s6),
    child: MarketingStack(
      centered: centered,
      children: [
        Text(
          '“$quote”',
          textAlign: centered ? TextAlign.center : TextAlign.start,
          style: context.ui.type.titleLarge,
        ),
        if (attribution != null)
          Text(
            attribution!,
            textAlign: centered ? TextAlign.center : null,
            style: context.ui.type.bodySmall,
          ),
      ],
    ),
  );
}

/// A published mention with explicit source, date and destination.
@immutable
class UiPressMention {
  /// The host supplies authorized identity artwork and actual article actions.
  const UiPressMention({
    required this.publication,
    required this.headline,
    required this.date,
    this.logo,
    this.onRead,
  });

  /// Publication/source name.
  final String publication;

  /// Article headline.
  final String headline;

  /// Localized publication date.
  final String date;

  /// Optional authorized publication identity.
  final Widget? logo;

  /// Opens the actual mention.
  final VoidCallback? onRead;
}

/// Press/editorial mentions as cards or a list, preserving source attribution.
class UiPressMentionsSection extends StatelessWidget {
  /// Published entries must be real; catalog entries are explicitly synthetic.
  const UiPressMentionsSection({
    super.key,
    required this.title,
    required this.mentions,
    this.cards = true,
  });

  /// Section heading.
  final String title;

  /// Mention entries.
  final List<UiPressMention> mentions;

  /// Card grid versus stacked editorial rows.
  final bool cards;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    child: UiSectionGrid(
      columns: cards ? 3 : 1,
      children: [
        for (final mention in mentions)
          UiArticleCard(
            title: mention.headline,
            description: mention.publication,
            metadata: mention.date,
            media: mention.logo == null
                ? null
                : Semantics(
                    label: mention.publication,
                    image: true,
                    excludeSemantics: true,
                    child: mention.logo!,
                  ),
            onRead: mention.onRead,
            layout: cards ? UiArticleLayout.card : UiArticleLayout.horizontal,
          ),
      ],
    ),
  );
}
