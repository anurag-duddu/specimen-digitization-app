/// Shared page layouts, message templates and brand-owned presentation assets.
library;

import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../../primitives/brand_hero.dart';
import '../../primitives/field_core.dart';
import '../../primitives/surface.dart';
import '../actions/button.dart';
import '../inputs/slider.dart';
import 'section.dart';

/// Call-to-action section supporting simple, card, split and brand treatments.
class UiCallToActionSection extends StatelessWidget {
  /// All commands are explicit callbacks supplied by the host.
  const UiCallToActionSection({
    super.key,
    required this.title,
    required this.actions,
    this.description,
    this.media,
    this.layout = UiSectionLayout.centered,
    this.treatment = UiSectionTreatment.brand,
  });

  /// Call-to-action heading.
  final String title;

  /// Supporting copy.
  final String? description;

  /// Actual commands.
  final List<UiMarketingAction> actions;

  /// Optional image or product preview.
  final Widget? media;

  /// Heading/media composition.
  final UiSectionLayout layout;

  /// Surface treatment.
  final UiSectionTreatment treatment;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    description: description,
    actions: actions,
    media: media,
    layout: layout,
    treatment: treatment,
  );
}

/// Public header/hero section with optional email, search or tabs beneath copy.
class UiHeroSection extends StatelessWidget {
  /// The [lead] slot hosts actual controls rather than screenshot controls.
  const UiHeroSection({
    super.key,
    required this.title,
    this.announcement,
    this.eyebrow,
    this.description,
    this.actions = const [],
    this.media,
    this.lead,
    this.layout = UiSectionLayout.centered,
    this.treatment = UiSectionTreatment.brand,
  });

  /// Primary page heading.
  final String title;

  /// Optional announcement, badge or link before the heading.
  /// Supply a real owned control when the announcement is actionable.
  final Widget? announcement;

  /// Optional introductory label.
  final String? eyebrow;

  /// Supporting copy.
  final String? description;

  /// Hero commands.
  final List<UiMarketingAction> actions;

  /// Product screenshot, actual preview, or photograph.
  final Widget? media;

  /// Email capture, search, tabs or other actual controls.
  final Widget? lead;

  /// Composition for wide windows.
  final UiSectionLayout layout;

  /// Brand and surface treatment.
  final UiSectionTreatment treatment;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    leading: announcement,
    eyebrow: eyebrow,
    description: description,
    actions: actions,
    media: media,
    layout: layout,
    treatment: treatment,
    child: lead,
  );
}

/// Centered/card/split auth shell; stage and session state stay in the host.
class UiAuthLayout extends StatelessWidget {
  /// Forms are actual widgets, such as UiAuthForm or the application's auth flow.
  const UiAuthLayout({
    super.key,
    required this.title,
    required this.form,
    this.description,
    this.identity,
    this.media,
    this.footer,
    this.layout = UiSectionLayout.centered,
    this.framed = false,
    this.progress,
  });

  /// Optional actual stepper/progress control for multi-stage signup.
  final Widget? progress;

  /// Stage heading.
  final String title;

  /// Context or recovery instructions.
  final String? description;

  /// Actual form.
  final Widget form;

  /// Brand/home slot.
  final Widget? identity;

  /// Image, quotation or visual supporting the form.
  final Widget? media;

  /// Legal, support or navigation footer.
  final Widget? footer;

  /// Centered versus split composition.
  final UiSectionLayout layout;

  /// Card treatment around the form.
  final bool framed;
  @override
  Widget build(BuildContext context) => MarketingStack(
    children: [
      ?identity,
      ?progress,
      UiMarketingSection(
        title: title,
        description: description,
        layout: layout,
        media: media,
        treatment: framed ? UiSectionTreatment.card : UiSectionTreatment.plain,
        child: Align(
          alignment: layout == UiSectionLayout.centered
              ? Alignment.center
              : AlignmentDirectional.centerStart,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: context.ui.space.dialogMax),
            child: form,
          ),
        ),
      ),
      ?footer,
    ],
  );
}

/// Recoverable page-level error with accessible heading and explicit actions.
class UiErrorPage extends StatelessWidget {
  /// Supports 404, unavailable and permission errors without inventing navigation.
  const UiErrorPage({
    super.key,
    required this.title,
    required this.description,
    required this.actions,
    this.code = '404',
    this.illustration,
    this.recovery,
    this.layout = UiSectionLayout.centered,
  });

  /// Human-readable error heading.
  final String title;

  /// Explains recovery options.
  final String description;

  /// Status code or contextual label.
  final String code;

  /// Recovery/navigation commands.
  final List<UiMarketingAction> actions;

  /// Host-provided visual, not required for understanding the error.
  final Widget? illustration;

  /// Search, recovery form or contextual links owned by the host.
  /// The supplied control keeps its own state, labels and callbacks.
  final Widget? recovery;

  /// Text/illustration arrangement.
  final UiSectionLayout layout;
  @override
  Widget build(BuildContext context) => UiMarketingSection(
    title: title,
    eyebrow: code,
    description: description,
    actions: actions,
    media: illustration,
    layout: layout,
    child: recovery,
  );
}

/// Visual email/message template kind. Content remains explicit and localized.
enum UiEmailTemplateKind {
  /// Greeting and introduction.
  welcome,

  /// Verify or authenticate a recipient.
  verification,

  /// Recover an account.
  recovery,

  /// Invitation to a workspace or collection.
  invitation,

  /// Receipt or invoice with host-provided line items.
  receipt,

  /// Editorial digest.
  digest,

  /// Product notification.
  notification,
}

/// Accessible message composition preview, not an email transport or HTML export.
///
/// The host renders compatible HTML separately when actual email delivery is
/// needed. Do not claim Flutter rendering proves Outlook/Gmail compatibility.
class UiEmailTemplate extends StatelessWidget {
  /// Named header/body/footer slots cover message anatomy without hidden copy.
  const UiEmailTemplate({
    super.key,
    required this.subject,
    required this.body,
    required this.footer,
    this.kind = UiEmailTemplateKind.notification,
    this.identity,
    this.preheader,
    this.actions = const [],
    this.summary,
    this.centered = false,
  });

  /// Visible subject/title.
  final String subject;

  /// Optional inbox preview text, visible in the catalog preview.
  final String? preheader;

  /// Template classification.
  final UiEmailTemplateKind kind;

  /// Brand/message header.
  final Widget? identity;

  /// Main formatted content.
  final Widget body;

  /// Optional receipt, item summary or editorial cards.
  final Widget? summary;

  /// Actual host preview actions.
  /// They follow the body and optional summary, before the footer.
  final List<UiMarketingAction> actions;

  /// Legal, unsubscribe and sender information supplied by the host.
  final Widget footer;

  /// Centers heading/header/action content.
  final bool centered;
  @override
  Widget build(BuildContext context) => Center(
    child: ConstrainedBox(
      constraints: BoxConstraints(maxWidth: context.ui.space.readingMax),
      child: Surface(
        hairline: true,
        padding: EdgeInsets.all(context.ui.space.s6),
        child: MarketingStack(
          children: [
            if (preheader != null)
              Text(preheader!, style: context.ui.type.bodySmall),
            ?identity,
            UiMarketingSection(
              title: subject,
              layout: centered
                  ? UiSectionLayout.centered
                  : UiSectionLayout.start,
              child: UiSelectionArea(child: body),
            ),
            ?summary,
            if (actions.isNotEmpty)
              MarketingActions(actions: actions, centered: centered),
            footer,
          ],
        ),
      ),
    ),
  );
}

/// Device-frame composition, independent of a manufacturer's logo or artwork.
enum UiDeviceFrame {
  /// Tall rounded phone frame.
  phone,

  /// Tablet frame.
  tablet,

  /// Browser window with optional address title.
  browser,
}

/// A responsive, brand-neutral presentation frame for actual visual content.
///
/// This is presentation only; native input behavior must be verified in the
/// real Flutter target. A frame cannot establish native compatibility.
class UiDeviceMockup extends StatelessWidget {
  /// The content keeps its own sizing and semantics; it is never scaled to hide overflow.
  const UiDeviceMockup({
    super.key,
    required this.child,
    this.frame = UiDeviceFrame.browser,
    this.title,
  });

  /// Product screenshot or live preview.
  final Widget child;

  /// Frame style.
  final UiDeviceFrame frame;

  /// Optional browser/window title.
  final String? title;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: switch (frame) {
            UiDeviceFrame.phone => ui.space.paneDetailMin,
            UiDeviceFrame.tablet => ui.space.importWorkspaceMax,
            UiDeviceFrame.browser => double.infinity,
          },
        ),
        child: Surface(
          boundary: true,
          radius: frame == UiDeviceFrame.browser
              ? ui.shape.tile
              : ui.shape.tile * 2,
          clip: true,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (frame == UiDeviceFrame.browser || title != null)
                Padding(
                  padding: EdgeInsets.all(ui.space.s4),
                  child: Text(
                    title ?? 'Application preview',
                    style: ui.type.bodySmall,
                  ),
                ),
              Padding(
                padding: EdgeInsets.all(
                  frame == UiDeviceFrame.browser ? ui.space.s2 : ui.space.s4,
                ),
                child: child,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Brand-owned decorative patterns, excluding reference artwork and extra hues.
enum UiBrandPatternStyle {
  /// A regular dot field.
  dots,

  /// Horizontal and vertical lines.
  grid,

  /// Parallel diagonal lines.
  lines,

  /// Concentric line circles.
  circles,

  /// Concentric line squares.
  squares,

  /// Alternating grid cells.
  checks,

  /// A plain brand gradient.
  gradient,
}

/// Purely decorative background with no text/image content slot.
class UiBrandPattern extends StatelessWidget {
  /// Heights are explicit; all colors come from brand/semantic tokens.
  const UiBrandPattern({
    super.key,
    this.style = UiBrandPatternStyle.gradient,
    this.height = 160,
  });

  /// Pattern geometry.
  final UiBrandPatternStyle style;

  /// Region height.
  final double height;
  @override
  Widget build(BuildContext context) {
    if (style == UiBrandPatternStyle.gradient) {
      return UiBrandAccent(height: height);
    }
    final ui = context.ui;
    return ExcludeSemantics(
      child: SizedBox(
        height: height,
        width: double.infinity,
        child: CustomPaint(
          painter: _PatternPainter(
            style,
            ui.color.hairline,
            ui.color.paper,
            ui.space.s6,
          ),
        ),
      ),
    );
  }
}

class _PatternPainter extends CustomPainter {
  const _PatternPainter(this.style, this.line, this.background, this.step);
  final UiBrandPatternStyle style;
  final Color line, background;
  final double step;
  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = background);
    final paint = Paint()
      ..color = line
      ..strokeWidth = 1;
    canvas.save();
    canvas.clipRect(Offset.zero & size);
    switch (style) {
      case UiBrandPatternStyle.dots:
        for (double x = step / 2; x < size.width; x += step) {
          for (double y = step / 2; y < size.height; y += step) {
            canvas.drawCircle(Offset(x, y), 1.5, paint);
          }
        }
      case UiBrandPatternStyle.grid:
        for (double x = 0; x < size.width; x += step) {
          canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
        }
        for (double y = 0; y < size.height; y += step) {
          canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
        }
      case UiBrandPatternStyle.lines:
        for (double x = -size.height; x < size.width; x += step) {
          canvas.drawLine(
            Offset(x, 0),
            Offset(x + size.height, size.height),
            paint,
          );
        }
      case UiBrandPatternStyle.circles:
        final outline = Paint()
          ..color = line
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1;
        for (double radius = step; radius < size.longestSide; radius += step) {
          canvas.drawCircle(size.center(Offset.zero), radius, outline);
        }
      case UiBrandPatternStyle.squares:
        final outline = Paint()
          ..color = line
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1;
        for (double radius = step; radius < size.longestSide; radius += step) {
          canvas.drawRect(
            Rect.fromCenter(
              center: size.center(Offset.zero),
              width: radius * 2,
              height: radius * 2,
            ),
            outline,
          );
        }
      case UiBrandPatternStyle.checks:
        for (int x = 0; x * step < size.width; x++) {
          for (int y = 0; y * step < size.height; y++) {
            if ((x + y).isEven) {
              canvas.drawRect(
                Rect.fromLTWH(x * step, y * step, step, step),
                paint,
              );
            }
          }
        }
      case UiBrandPatternStyle.gradient:
        break;
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _PatternPainter oldDelegate) =>
      oldDelegate.style != style ||
      oldDelegate.line != line ||
      oldDelegate.background != background ||
      oldDelegate.step != step;
}

/// Decorative masked card/credential mockup, never a payment input control.
class UiPaymentCardMockup extends StatelessWidget {
  /// Only masked digits are accepted to avoid putting complete card data in previews.
  UiPaymentCardMockup({
    super.key,
    required this.label,
    required this.holder,
    required this.lastFour,
    this.expiry,
    this.branded = true,
  }) {
    if (!RegExp(r'^\d{4}$').hasMatch(lastFour)) {
      throw ArgumentError.value(
        lastFour,
        'lastFour',
        'Exactly four digits are required.',
      );
    }
  }

  /// Card or organisation label, no copied network logo.
  final String label;

  /// Display name, synthetic in stories.
  final String holder;

  /// Last four digits only.
  final String lastFour;

  /// Optional displayed expiration value.
  final String? expiry;

  /// Adds a separate brand strip.
  final bool branded;
  @override
  Widget build(BuildContext context) => Surface(
    hairline: true,
    radius: context.ui.shape.tile,
    clip: true,
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (branded) UiBrandAccent(height: context.ui.space.s8),
        Padding(
          padding: EdgeInsets.all(context.ui.space.s6),
          child: MarketingStack(
            children: [
              Text(label, style: context.ui.type.label),
              Semantics(
                label: 'Card ending $lastFour',
                excludeSemantics: true,
                child: Text(
                  '•••• •••• •••• $lastFour',
                  style: context.ui.type.title,
                ),
              ),
              Text(holder),
              if (expiry != null)
                Text(expiry!, style: context.ui.type.bodySmall),
            ],
          ),
        ),
      ],
    ),
  );
}

/// Responsive page composition shared by landing, editorial and utility pages.
///
/// The host owns scrolling, routing, link destinations and data. Header/footer
/// occupy full width while each section gets a constrained content measure.
class UiMarketingPage extends StatelessWidget {
  /// Creates an actual composition from reusable section widgets.
  const UiMarketingPage({
    super.key,
    required this.sections,
    this.header,
    this.footer,
    this.maxContentWidth = 1216,
  });

  /// Ordered page sections, not flattened screenshots.
  final List<Widget> sections;

  /// Full-width primary navigation or identity.
  final Widget? header;

  /// Full-width footer.
  final Widget? footer;

  /// Maximum inner content width; narrow layouts keep token-based gutters.
  final double maxContentWidth;
  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      ?header,
      for (final section in sections)
        Padding(
          padding: EdgeInsets.symmetric(
            vertical: context.ui.space.s8,
            horizontal: context.ui.space.s4,
          ),
          child: Center(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: maxContentWidth),
              child: section,
            ),
          ),
        ),
      ?footer,
    ],
  );
}

/// Host-controlled media player chrome; playback uses the platform's player.
///
/// The content slot may be an actual player surface or a synthetic preview.
/// Controls never claim to decode, play or buffer media independently.
class UiMediaPlayer extends StatelessWidget {
  /// Values and callbacks come from the actual media controller.
  const UiMediaPlayer({
    super.key,
    required this.title,
    required this.child,
    required this.position,
    required this.duration,
    required this.playing,
    this.onPlayingChanged,
    this.onSeek,
    this.volume = 1,
    this.onVolumeChanged,
    this.captions = false,
    this.onCaptionsChanged,
    this.onFullscreen,
    this.buffering = false,
    this.error,
    this.onRetry,
  });

  /// Accessible media name.
  final String title;

  /// Actual playback surface, poster or application preview.
  final Widget child;

  /// Current position, clamped for display.
  final Duration position;

  /// Known duration. Zero disables seeking without inventing a duration.
  final Duration duration;

  /// Current playback state.
  final bool playing;

  /// Requests playback/pause.
  final ValueChanged<bool>? onPlayingChanged;

  /// Requests a new position.
  final ValueChanged<Duration>? onSeek;

  /// Current volume, clamped to zero through one for display.
  final double volume;

  /// Requests a volume change. Null hides optional volume control.
  final ValueChanged<double>? onVolumeChanged;

  /// Current caption visibility.
  final bool captions;

  /// Caption toggle, present only when available.
  final ValueChanged<bool>? onCaptionsChanged;

  /// Host enters full screen with the actual player.
  final VoidCallback? onFullscreen;

  /// Host reports buffering; controls remain sized and named.
  final bool buffering;

  /// Host error message.
  final String? error;

  /// Retries the actual media load.
  final VoidCallback? onRetry;
  String _time(Duration value) =>
      '${value.inMinutes}:${(value.inSeconds % 60).toString().padLeft(2, '0')}';
  @override
  Widget build(BuildContext context) => Surface(
    hairline: true,
    radius: context.ui.shape.tile,
    child: MarketingStack(
      children: [
        Semantics(label: title, child: child),
        Padding(
          padding: EdgeInsets.all(context.ui.space.s4),
          child: MarketingStack(
            children: [
              if (error != null)
                Semantics(liveRegion: true, child: Text(error!)),
              if (buffering)
                Semantics(liveRegion: true, child: const Text('Buffering')),
              if (duration > Duration.zero)
                UiSlider(
                  label: 'Playback position',
                  value: position.inMilliseconds.toDouble().clamp(
                    0,
                    duration.inMilliseconds.toDouble(),
                  ),
                  max: duration.inMilliseconds.toDouble(),
                  valueLabel: (value) =>
                      '${_time(Duration(milliseconds: value.round()))} of ${_time(duration)}',
                  onChanged: error != null || onSeek == null
                      ? null
                      : (value) =>
                            onSeek!(Duration(milliseconds: value.round())),
                ),
              Wrap(
                spacing: context.ui.space.s2,
                runSpacing: context.ui.space.s2,
                children: [
                  UiButton(
                    label: playing ? 'Pause' : 'Play',
                    onPressed: error != null || onPlayingChanged == null
                        ? null
                        : () => onPlayingChanged!(!playing),
                  ),
                  if (onCaptionsChanged != null)
                    UiButton(
                      label: captions ? 'Hide captions' : 'Show captions',
                      variant: UiButtonVariant.secondary,
                      onPressed: () => onCaptionsChanged!(!captions),
                    ),
                  if (onFullscreen != null)
                    UiButton(
                      label: 'Full screen',
                      variant: UiButtonVariant.secondary,
                      onPressed: onFullscreen,
                    ),
                  if (error != null && onRetry != null)
                    UiButton(
                      label: 'Retry media',
                      variant: UiButtonVariant.secondary,
                      onPressed: onRetry,
                    ),
                ],
              ),
              if (onVolumeChanged != null)
                UiSlider(
                  label: 'Volume',
                  value: volume.clamp(0, 1),
                  valueLabel: (value) => '${(value * 100).round()} percent',
                  onChanged: onVolumeChanged,
                ),
            ],
          ),
        ),
      ],
    ),
  );
}
