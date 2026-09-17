/// One model reading of one region (design system, 7.3 `ReadingCard`;
/// 10 section 5).
///
/// Two readings are two readings. The card names which model produced this
/// one and which provider ran it, then shows the literal against the
/// reference reading. Agreement between two models is not evidence of
/// correctness, so nothing here reads as an endorsement.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'disclosure_target.dart';
import 'diff_text.dart';
import 'term_text.dart';

/// The surface the two evidence cards are drawn on (10 section 5).
///
/// `paper` at `shape.tile`, with a hairline at rest and the `emphasis` stroke
/// in the family's own colour when the reviewer has this one selected. The
/// package's `Surface` takes a hairline or a boundary and nothing wider, so
/// the selected edge is drawn here; the package API that would retire this is
/// recorded in the slot closeout.
class EvidenceSurface extends StatelessWidget {
  const EvidenceSurface({
    super.key,
    required this.child,
    required this.accent,
    this.selected = false,
  });

  /// The card's content, already padded by the caller's column.
  final Widget child;

  /// The colour of the selected edge: the evidence family's own content
  /// colour, so a picked reading and a picked authority match do not look
  /// like the same decision.
  final Color accent;

  /// True when the reviewer picked this card.
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    if (!selected) {
      return Surface(
        radius: ui.shape.tile,
        hairline: true,
        padding: EdgeInsetsDirectional.all(ui.space.s4),
        child: child,
      );
    }
    return DecoratedBox(
      decoration: ShapeDecoration(
        color: ui.color.paper,
        shape: Squircle.border(
          ui.shape.tile,
          side: BorderSide(color: accent, width: ui.shape.stroke.emphasis),
        ),
      ),
      child: Padding(
        padding: EdgeInsetsDirectional.all(ui.space.s4),
        child: child,
      ),
    );
  }
}

/// A model reading, its provenance, and what it differs from.
class ReadingCard extends StatelessWidget {
  const ReadingCard({
    super.key,
    required this.modelName,
    required this.provider,
    required this.literal,
    this.regionName,
    this.reference,
    this.executionDetails,
    this.footerActions,
    this.selected = false,
  });

  /// The disclosure the execution facts sit behind (blueprint 6.3).
  static const String executionTitle = 'Reported reading execution';

  /// The model that produced the reading.
  final String modelName;

  /// The provider that ran the model.
  final String provider;

  /// The transcription, verbatim.
  final String literal;

  /// Which region of the photograph the reading was taken from, as the region
  /// list names it. Null where the caller has already said so nearby.
  final String? regionName;

  /// The first reading for this region, if this is not it.
  final String? reference;

  /// Reported execution facts: latency, tokens, finish state. Optional
  /// because a historical revision may not carry them.
  final Widget? executionDetails;

  /// Actions for this reading, laid out at the foot of the card.
  final Widget? footerActions;

  /// True when the reviewer picked this reading as the supported one.
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Color accent = ui.color.status.model.content;
    final String? region = regionName;
    final Widget? execution = executionDetails;

    return Semantics(
      container: true,
      selected: selected,
      child: EvidenceSurface(
        accent: accent,
        selected: selected,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (region != null) ...<Widget>[
              // The region is the part of the photograph this reading was
              // taken from, which is the word a first-time reviewer asks
              // about first (pass criterion 10.2).
              TermText(
                'Region',
                displayText: region,
                style: ui.type.label.copyWith(color: ui.color.inkSecondary),
              ),
              SizedBox(height: ui.space.s1),
            ],
            // The model and the provider are a pair of arbitrary length
            // strings beside each other, so they wrap rather than compete
            // for one line. A `Row` here overflowed at a realistic pane
            // width, and the pane goes down to a 320 dp window.
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Padding(
                  padding: EdgeInsetsDirectional.only(top: ui.space.s1),
                  child: UiIcon(
                    UiIcons.modelReading,
                    size: UiIconSize.inline,
                    color: accent,
                  ),
                ),
                SizedBox(width: ui.space.s1),
                Expanded(
                  child: Wrap(
                    spacing: ui.space.s2,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: <Widget>[
                      Text(modelName, style: ui.type.title),
                      TermText(
                        'Provider',
                        displayText: provider,
                        style: ui.type.label.copyWith(
                          color: ui.color.inkSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            SizedBox(height: ui.space.s3),
            DiffText(text: literal, reference: reference),
            if (execution != null) ...<Widget>[
              SizedBox(height: ui.space.s3),
              UiDisclosure(
                style: fullTargetDisclosure(ui),
                title: executionTitle,
                semanticsLabel: '$executionTitle, $modelName',
                child: execution,
              ),
            ],
            if (footerActions != null) ...<Widget>[
              SizedBox(height: ui.space.s2),
              footerActions!,
            ],
          ],
        ),
      ),
    );
  }
}
