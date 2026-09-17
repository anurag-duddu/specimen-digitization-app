/// One candidate returned by an external authority
/// (design system, 7.3 `AuthorityCandidateCard`; 10 section 5).
///
/// Teal, because an authority is an external reference file and not a
/// decision. Choosing a match is a reviewer's act, so the action says what it
/// does rather than saying "OK".
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'evidence_drawer.dart';
import 'reading_card.dart';

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

  /// Why the action is unavailable when the record does not permit it.
  static const String unavailableReason =
      'This match cannot be applied on this version';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Color accent = ui.color.status.authority.content;

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
            Row(
              children: <Widget>[
                UiIcon(
                  UiIcons.authority,
                  size: UiIconSize.inline,
                  color: accent,
                ),
                SizedBox(width: ui.space.s1),
                Expanded(
                  child: Text(
                    authorityName ?? 'Authority candidate',
                    style: ui.type.label.copyWith(color: accent),
                  ),
                ),
              ],
            ),
            SizedBox(height: ui.space.s2),
            Text(name, style: ui.type.title),
            SizedBox(height: ui.space.s1),
            Text(identifier, style: ui.type.mono.identifier),
            SizedBox(height: ui.space.s2),
            Text(relation, style: ui.type.body),
            SizedBox(height: ui.space.s1),
            Text(
              reason,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
            if (raw != null) ...<Widget>[
              SizedBox(height: ui.space.s2),
              EvidenceDrawer(payload: raw, section: name),
            ],
            SizedBox(height: ui.space.s2),
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: UiButton(
                label: useLabel,
                variant: UiButtonVariant.secondary,
                semanticsLabel: '$useLabel, $name',
                disabledReason: onUse == null ? unavailableReason : null,
                onPressed: onUse,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
