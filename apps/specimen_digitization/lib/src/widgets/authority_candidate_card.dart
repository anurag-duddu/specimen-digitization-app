/// One candidate returned by an external authority
/// (design system, 7.3 `AuthorityCandidateCard`).
///
/// Teal, because an authority is an external reference file and not a
/// decision. Choosing a match is a reviewer's act, so the action says what it
/// does rather than saying "OK".
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';
import 'evidence_drawer.dart';

/// A named candidate, why it was proposed, and one way to take it.
class AuthorityCandidateCard extends StatelessWidget {
  const AuthorityCandidateCard({
    super.key,
    required this.name,
    required this.identifier,
    required this.relation,
    required this.reason,
    this.authorityName,
    this.onUse,
    this.raw,
    this.selected = false,
  });

  /// The candidate's name, as the authority spells it.
  final String name;

  /// The authority's identifier for the candidate. Rendered monospace.
  final String identifier;

  /// How the candidate relates to the record's value, such as "Accepted name"
  /// or "Synonym".
  final String relation;

  /// One plain sentence saying why this candidate came back.
  final String reason;

  /// The authority the candidate came from.
  final String? authorityName;

  /// Takes this candidate. Disabled when null.
  final VoidCallback? onUse;

  /// The raw record the authority returned, shown behind the drawer.
  final Object? raw;

  /// True when this candidate is the one the reviewer picked.
  final bool selected;

  /// The one action label, fixed across the app.
  static const String useLabel = 'Use this match';

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Color accent = context.tokens.evidenceAuthorityContent;

    return Semantics(
      container: true,
      selected: selected,
      child: Card(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(context.shape.radiusSm),
          side: BorderSide(
            color: selected ? accent : theme.colorScheme.outlineVariant,
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
                    Symbols.menu_book,
                    size: context.sizes.iconInline,
                    color: accent,
                  ),
                  SizedBox(width: context.space.space1),
                  Expanded(
                    child: Text(
                      authorityName ?? 'Authority candidate',
                      style: theme.textTheme.labelMedium?.copyWith(
                        color: accent,
                      ),
                    ),
                  ),
                ],
              ),
              SizedBox(height: context.space.space2),
              Text(name, style: theme.textTheme.titleMedium),
              SizedBox(height: context.space.space1),
              Text(identifier, style: context.mono.identifier),
              SizedBox(height: context.space.space2),
              Text(relation, style: theme.textTheme.bodyMedium),
              SizedBox(height: context.space.space1),
              Text(
                reason,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              if (raw != null) ...<Widget>[
                SizedBox(height: context.space.space2),
                EvidenceDrawer(payload: raw),
              ],
              SizedBox(height: context.space.space2),
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: FilledButton.tonal(
                  onPressed: onUse,
                  child: const Text(useLabel),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
