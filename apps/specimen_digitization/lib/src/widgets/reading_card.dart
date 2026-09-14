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

/// A model reading, its provenance, and what it differs from.
class ReadingCard extends StatelessWidget {
  const ReadingCard({
    super.key,
    required this.modelName,
    required this.provider,
    required this.literal,
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
              Row(
                children: <Widget>[
                  Icon(
                    Symbols.memory,
                    size: context.sizes.iconInline,
                    color: accent,
                  ),
                  SizedBox(width: context.space.space1),
                  Expanded(
                    child: Text(
                      modelName,
                      style: theme.textTheme.titleSmall,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  SizedBox(width: context.space.space2),
                  Text(
                    provider,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
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
