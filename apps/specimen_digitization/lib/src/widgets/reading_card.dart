/// One model reading of one region (design system, 7.3 `ReadingCard`).
///
/// Two readings are two readings. The card names which model produced this
/// one and which provider ran it, then shows the literal against the
/// reference reading. Agreement between two models is not evidence of
/// correctness, so nothing here reads as an endorsement.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';
import 'diff_text.dart';
import 'term_text.dart';

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
    final ThemeData theme = Theme.of(context);
    final Color accent = context.tokens.evidenceModelContent;
    final String? region = regionName;

    return Semantics(
      container: true,
      selected: selected,
      child: Card(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(context.shape.radiusSm),
          side: BorderSide(
            color: selected
                ? theme.colorScheme.primary
                : theme.colorScheme.outlineVariant,
            width: selected
                ? context.shape.strokeEmphasis
                : context.shape.strokeHairline,
          ),
        ),
        child: Padding(
          padding: EdgeInsets.all(context.space.space4),
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
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                SizedBox(height: context.space.space1),
              ],
              // The model and the provider are a pair of arbitrary length
              // strings beside each other, so they wrap rather than compete
              // for one line. A `Row` here overflowed at a realistic pane
              // width, and the pane goes down to a 320dp window.
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Padding(
                    padding: EdgeInsets.only(top: context.space.space1),
                    child: Icon(
                      Symbols.memory,
                      size: context.sizes.iconInline,
                      color: accent,
                    ),
                  ),
                  SizedBox(width: context.space.space1),
                  Expanded(
                    child: Wrap(
                      spacing: context.space.space2,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: <Widget>[
                        Text(modelName, style: theme.textTheme.titleSmall),
                        TermText(
                          'Provider',
                          displayText: provider,
                          style: theme.textTheme.labelMedium?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              SizedBox(height: context.space.space3),
              DiffText(text: literal, reference: reference),
              if (executionDetails != null) ...<Widget>[
                SizedBox(height: context.space.space3),
                executionDetails!,
              ],
              if (footerActions != null) ...<Widget>[
                SizedBox(height: context.space.space2),
                footerActions!,
              ],
            ],
          ),
        ),
      ),
    );
  }
}
