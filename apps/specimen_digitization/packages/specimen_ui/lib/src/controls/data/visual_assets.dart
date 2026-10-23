/// Small visual slots using Specimen tokens and Phosphor glyphs.
library;

import 'package:flutter/widgets.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../overlays/banner.dart';

/// Featured-glyph geometry for headers, cards and empty states.
enum UiFeaturedIconShape {
  /// Quiet circular surface.
  circle,

  /// Quiet rounded square surface.
  square,

  /// Circular boundary without an opaque fill.
  outlinedCircle,

  /// Rounded square boundary without an opaque fill.
  outlinedSquare,
}

/// A decorative featured icon with optional accessible meaning.
class UiFeaturedIcon extends StatelessWidget {
  /// A Phosphor icon in an owned surface. Leave [semanticsLabel] null beside text.
  const UiFeaturedIcon({
    super.key,
    required this.icon,
    this.shape = UiFeaturedIconShape.circle,
    this.size = 48,
    this.tone = UiBannerTone.info,
    this.semanticsLabel,
  }) : assert(size >= 24);

  /// Registry glyph.
  final IconSpec icon;

  /// Surface geometry.
  final UiFeaturedIconShape shape;

  /// Overall decorative extent; interactive hosts retain their own hit target.
  final double size;

  /// Functional tone; neutral by default.
  final UiBannerTone tone;

  /// Meaning when shown without a nearby text label.
  final String? semanticsLabel;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final style = UiBannerStyle.resolve(ui, tone);
    final outlined =
        shape == UiFeaturedIconShape.outlinedCircle ||
        shape == UiFeaturedIconShape.outlinedSquare;
    final circular =
        shape == UiFeaturedIconShape.circle ||
        shape == UiFeaturedIconShape.outlinedCircle;
    final visual = Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: outlined ? null : style.fill,
        border: outlined
            ? Border.all(
                color: ui.color.boundary,
                width: ui.shape.stroke.hairline,
              )
            : null,
        borderRadius: BorderRadius.circular(
          circular ? size / 2 : ui.shape.tile,
        ),
      ),
      child: UiIcon(icon, color: outlined ? ui.color.ink : style.foreground),
    );
    return semanticsLabel == null
        ? ExcludeSemantics(child: visual)
        : Semantics(
            label: semanticsLabel,
            image: true,
            child: ExcludeSemantics(child: visual),
          );
  }
}

/// File-format mark with visible extension and optional thumbnail.
class UiFileTypeIcon extends StatelessWidget {
  /// Accepts real source metadata, without guessing a file's contents.
  const UiFileTypeIcon({
    super.key,
    required this.extension,
    this.preview,
    this.semanticsLabel,
  });

  /// Short extension, such as PDF, JPG, CSV, ZIP or JSON.
  final String extension;

  /// Optional host-owned thumbnail. A failed load is the host's responsibility.
  final Widget? preview;

  /// Accessible alternative; defaults to the extension.
  final String? semanticsLabel;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Semantics(
      image: true,
      label: semanticsLabel ?? '$extension file',
      child: ExcludeSemantics(
        child: Container(
          constraints: BoxConstraints(minWidth: ui.space.fileMarkMin),
          padding: EdgeInsets.all(ui.space.s2),
          decoration: BoxDecoration(
            color: ui.color.paper,
            border: Border.all(color: ui.color.hairline),
            borderRadius: BorderRadius.circular(ui.shape.inner),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (preview != null)
                SizedBox(
                  width: ui.space.identityPreview,
                  height: ui.space.identityPreview,
                  child: ClipRect(child: preview!),
                )
              else
                const UiIcon(UiIcons.fileType),
              SizedBox(height: ui.space.s1),
              Text(
                extension.toUpperCase(),
                style: ui.type.labelSmall.copyWith(color: ui.color.ink),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A payment-provider identity slot with accessible name and optional real logo.
///
/// A neutral named mark is used when the host has no licensed provider asset.
/// This visual does not validate, collect or transmit payment details.
class UiPaymentMark extends StatelessWidget {
  /// Draws the provider's name and optional authentic host-owned logo.
  const UiPaymentMark({super.key, required this.name, this.logo});

  /// Provider name, retained in the accessible label even when a logo is supplied.
  final String name;

  /// Optional provider artwork supplied by the host.
  final Widget? logo;
  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return Semantics(
      image: true,
      label: name,
      child: ExcludeSemantics(
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: ui.space.s3,
            vertical: ui.space.s2,
          ),
          decoration: BoxDecoration(
            color: ui.color.paper,
            border: Border.all(color: ui.color.hairline),
            borderRadius: BorderRadius.circular(ui.shape.inner),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (logo != null)
                ConstrainedBox(
                  constraints: BoxConstraints(
                    maxWidth: ui.space.identityLeadingMax,
                    maxHeight: ui.space.identityPreview,
                  ),
                  child: logo!,
                )
              else
                const UiIcon(UiIcons.payment),
              SizedBox(width: ui.space.s2),
              Flexible(
                child: Text(
                  name,
                  style: ui.type.labelSmall.copyWith(color: ui.color.ink),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
