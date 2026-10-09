/// The rows a field with parts opens into: one row per part (field model v2;
/// wire contract in `docs/execution/FIELD_PARTS_WIRE.md` on pull request 288,
/// planned and not in force).
///
/// Each row names the part, shows its value, carries one basis chip and keeps
/// the label's own words beneath an interpreted value (UX writing 1.13; PRD
/// rule 4). A part a person is asked about says so in a neutral chip, opens by
/// default, and says why behind "Why". Every other part stays closed until a
/// reviewer opens it. The place is a tree, drawn indented by `parent`.
///
/// A person's decision on a part is not wired here: there is no new server
/// call. The "Correct this part" control opens the correction the field
/// already has, for the whole field.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../widgets/caveat_text.dart';
import 'evidence_picker.dart';
import 'field_parts.dart';
import 'value_basis.dart';
import 'value_basis_chip.dart';

/// The most levels a part is indented by. Deeper nodes keep the last indent, so
/// a deep tree still leaves a narrow window room to read the value.
const int _maxIndentLevels = 3;

/// The parts of one field, as rows.
class FieldPartRows extends StatelessWidget {
  const FieldPartRows({
    super.key,
    required this.specimenId,
    required this.fieldKey,
    required this.parts,
    required this.evidence,
    this.onCorrect,
    this.correctBlockedReason,
  });

  /// The record, so each row's key is unique across records.
  final String specimenId;

  /// The field the parts are carried on.
  final String fieldKey;

  /// The parts to draw. Nothing is drawn for none.
  final FieldParts parts;

  /// The record's evidence rows, so a part's "Why" can name what it cites.
  final List<Json> evidence;

  /// Opens the correction for the whole field. Null draws no control.
  final VoidCallback? onCorrect;

  /// Why correcting is unavailable, or null when it is available.
  final String? correctBlockedReason;

  /// The section's title (UX writing 4.2: a noun phrase that names what is
  /// inside).
  static const String heading = 'Parts of this value';

  /// The chip on a part a person is asked about. Neutral, because a part to
  /// check is a data question and not an error (UX writing 2.4).
  static const String checkChipLabel = 'Check this part';

  /// The chip on a part a person accepted or chose.
  static const String confirmedChipLabel = 'Reviewer confirmed';

  /// The chip on a part a person entered themselves. It has no basis.
  static const String editedChipLabel = 'Set by a reviewer';

  /// The control on a part a person is asked about.
  static const String correctLabel = 'Correct this part';

  /// What sits under that control, so it is not mistaken for a smaller action.
  static const String correctNote = 'Opens the whole field for correction.';

  /// The label of the line that names the label's own words.
  static const String writtenPrefix = 'As written: ';

  /// The count of parts a person is asked about, beside the heading.
  static String toCheck(int count) => '$count to check';

  @override
  Widget build(BuildContext context) {
    if (parts.isEmpty) return const SizedBox.shrink();
    final UiThemeData ui = context.ui;
    final Map<String, Json> rows = <String, Json>{
      for (final Json row in evidence)
        if (_evidenceId(row) case final String id) id: row,
    };
    final int flagged = parts.flagged.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Semantics(
          header: true,
          child: Wrap(
            spacing: ui.space.s2,
            runSpacing: ui.space.s1,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              Text(heading, style: ui.type.label),
              if (flagged > 0)
                Text(
                  toCheck(flagged),
                  style: ui.type.labelSmall.copyWith(
                    color: ui.color.status.needsReview.content,
                  ),
                ),
            ],
          ),
        ),
        SizedBox(height: ui.space.s1),
        for (final PartNode node in parts.tree)
          Padding(
            padding: EdgeInsetsDirectional.only(bottom: ui.space.s1),
            child: _PartRow(
              key: ValueKey<String>(
                'part-row:$specimenId:$fieldKey:${node.part.path.text}',
              ),
              node: node,
              evidenceRows: rows,
              onCorrect: onCorrect,
              correctBlockedReason: correctBlockedReason,
            ),
          ),
      ],
    );
  }
}

String? _evidenceId(Json row) {
  final Object? id = row['evidence_id'] ?? row['id'];
  return id is String && id.isNotEmpty ? id : null;
}

/// One part: a header that opens a body.
class _PartRow extends StatefulWidget {
  const _PartRow({
    super.key,
    required this.node,
    required this.evidenceRows,
    required this.onCorrect,
    required this.correctBlockedReason,
  });

  final PartNode node;
  final Map<String, Json> evidenceRows;
  final VoidCallback? onCorrect;
  final String? correctBlockedReason;

  @override
  State<_PartRow> createState() => _PartRowState();
}

class _PartRowState extends State<_PartRow> {
  /// Only a part a person is asked about starts open.
  late bool _open = widget.node.part.needsReview;
  bool _whyOpen = false;

  FieldPart get _part => widget.node.part;

  Map<String, String> get _evidenceKinds => <String, String>{
    for (final MapEntry<String, Json> row in widget.evidenceRows.entries)
      row.key: textOf(row.value['kind'], ''),
  };

  _Why get _why => _Why.of(_part, widget.evidenceRows);

  String? get _sentence =>
      partReviewSentence(_part, evidenceKinds: _evidenceKinds);

  bool get _canCorrect => _part.needsReview && widget.onCorrect != null;

  /// A row with nothing behind it is not a control: a disclosure that opens
  /// onto nothing does nothing.
  bool get _hasBody => _sentence != null || !_why.isEmpty || _canCorrect;

  void _toggle() => setState(() => _open = !_open);

  /// The chip that says what a person has done or been asked to do.
  UiChip? get _statusChip {
    if (_part.needsReview) {
      return UiChip(
        label: FieldPartRows.checkChipLabel,
        icon: UiIcons.needsReview,
        semanticsLabel: FieldPartRows.checkChipLabel,
      );
    }
    final PartDecision? decision = _part.decision;
    if (decision == null) return null;
    return decision.action == PartDecisionAction.edit
        ? UiChip(
            label: FieldPartRows.editedChipLabel,
            icon: UiIcons.reviewer,
            semanticsLabel: FieldPartRows.editedChipLabel,
          )
        : UiChip(
            label: FieldPartRows.confirmedChipLabel,
            icon: UiIcons.check,
            semanticsLabel: FieldPartRows.confirmedChipLabel,
          );
  }

  /// What a screen reader hears for the header: one complete phrase, so the
  /// chips inside it are not read a second time.
  String get _semanticsLabel {
    final FieldPart part = _part;
    final String? where = widget.node.parent?.path.label;
    final ValueBasis? basis = part.basis;
    final UiChip? status = _statusChip;
    return <String>[
      '${part.path.label}${where == null ? '' : ', in $where'}',
      part.valueText,
      if (part.originalWording case final String words)
        '${FieldPartRows.writtenPrefix}$words',
      if (basis != null) basis.semanticsLabel,
      ?status?.semanticsLabel,
    ].join('. ');
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final int level = math.min(widget.node.depth, _maxIndentLevels);
    final Widget row = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _hasBody ? _pressableHeader(ui) : _staticHeader(ui),
        if (_hasBody) _body(ui),
      ],
    );
    return Padding(
      padding: EdgeInsetsDirectional.only(start: level * ui.space.s4),
      child: widget.node.depth == 0
          ? row
          // A rule at the start of a nested row ties it to the rows above it.
          : DecoratedBox(
              decoration: BoxDecoration(
                border: BorderDirectional(
                  start: BorderSide(
                    color: ui.color.hairline,
                    width: ui.shape.stroke.hairline,
                  ),
                ),
              ),
              child: row,
            ),
    );
  }

  /// The title with its chips, the value, and the label's own words.
  Widget _headerContent(UiThemeData ui, {required bool caret}) {
    final FieldPart part = _part;
    final ValueBasis? basis = part.basis;
    final UiChip? status = _statusChip;
    return Padding(
      padding: EdgeInsetsDirectional.symmetric(
        horizontal: ui.space.s2,
        vertical: ui.space.s2,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                // The title is a label and never wraps; the chips flow to the
                // next line when the title leaves them no room (11 section
                // 3.3).
                Wrap(
                  spacing: ui.space.s2,
                  runSpacing: ui.space.s1,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: <Widget>[
                    UiLabel(
                      part.path.label,
                      style: ui.type.label.copyWith(color: ui.color.ink),
                    ),
                    if (basis != null) valueBasisChip(basis),
                    ?status,
                  ],
                ),
                SizedBox(height: ui.space.s1),
                Text(
                  part.valueText,
                  style: ui.type.body.copyWith(color: ui.color.ink),
                ),
                if (part.originalWording case final String words)
                  Text(
                    '${FieldPartRows.writtenPrefix}$words',
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
              ],
            ),
          ),
          if (caret) ...<Widget>[
            SizedBox(width: ui.space.s3),
            Padding(
              padding: EdgeInsetsDirectional.only(top: ui.space.s1),
              child: AnimatedRotation(
                turns: _open ? UiDisclosureStyle.caretTurns : 0,
                duration: ui.motion.short,
                curve: MotionTokens.standardCurve,
                child: UiIcon(
                  UiIcons.expand,
                  size: UiIconSize.inline,
                  color: ui.color.inkSecondary,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _staticHeader(UiThemeData ui) => Semantics(
    container: true,
    excludeSemantics: true,
    label: _semanticsLabel,
    child: _headerContent(ui, caret: false),
  );

  /// The header publishes its own node so it carries `expanded`, which
  /// `Pressable` has no member for; the body keeps its own semantics.
  Widget _pressableHeader(UiThemeData ui) => Semantics(
    container: true,
    excludeSemantics: true,
    button: true,
    label: _semanticsLabel,
    expanded: _open,
    onTap: _toggle,
    child: Pressable(
      semanticsLabel: _semanticsLabel,
      onPressed: _toggle,
      radius: ui.shape.inner,
      excludeFromSemantics: true,
      builder: (BuildContext context, Set<WidgetState> states) =>
          _headerContent(ui, caret: true),
    ),
  );

  Widget _body(UiThemeData ui) {
    final String? sentence = _sentence;
    final Widget content = Padding(
      padding: EdgeInsetsDirectional.fromSTEB(
        ui.space.s2,
        0,
        ui.space.s2,
        ui.space.s2,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (sentence != null)
            Text(
              sentence,
              style: ui.type.bodySmall.copyWith(color: ui.color.ink),
            ),
          if (!_why.isEmpty) _whyBlock(ui),
          if (_canCorrect) ...<Widget>[
            SizedBox(height: ui.space.s2),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: UiButton(
                label: FieldPartRows.correctLabel,
                semanticsLabel:
                    '${FieldPartRows.correctLabel}: ${_part.path.label}',
                variant: UiButtonVariant.secondary,
                disabledReason: widget.correctBlockedReason,
                onPressed: widget.correctBlockedReason == null
                    ? widget.onCorrect
                    : null,
              ),
            ),
            Text(
              FieldPartRows.correctNote,
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          ],
        ],
      ),
    );
    // Under reduced motion the body appears at its full height, and
    // `AnimatedSize` is left out of the tree rather than given no duration.
    if (ui.motion.reduced) {
      return _open ? content : const SizedBox(width: double.infinity);
    }
    return AnimatedSize(
      alignment: AlignmentDirectional.topStart,
      duration: ui.motion.standard,
      curve: MotionTokens.standardCurve,
      child: _open ? content : const SizedBox(width: double.infinity),
    );
  }

  /// "Why": the writer's reason, then what the part cites, grouped.
  Widget _whyBlock(UiThemeData ui) {
    final Widget list = _whyOpen
        ? Padding(
            padding: EdgeInsetsDirectional.only(bottom: ui.space.s2),
            child: _why.build(ui),
          )
        : const SizedBox(width: double.infinity);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Align(
          alignment: AlignmentDirectional.centerStart,
          // One node, so a screen reader reads "Why, button, collapsed".
          child: MergeSemantics(
            child: Semantics(
              expanded: _whyOpen,
              child: UiButton(
                label: CaveatText.affordance,
                semanticsLabel: '${CaveatText.affordance}: ${_part.path.label}',
                variant: UiButtonVariant.ghost,
                trailing: _whyOpen ? UiIcons.collapse : UiIcons.expand,
                onPressed: () => setState(() => _whyOpen = !_whyOpen),
              ),
            ),
          ),
        ),
        if (ui.motion.reduced)
          list
        else
          AnimatedSize(
            alignment: AlignmentDirectional.topStart,
            duration: ui.motion.standard,
            curve: MotionTokens.standardCurve,
            child: list,
          ),
      ],
    );
  }
}

/// What a part rests on, ready to draw: the writer's reason, the rows it cites
/// by kind, the one reasoning line, and the parts it follows from.
class _Why {
  const _Why({
    this.reason,
    this.groups = const <(String, List<String>)>[],
    this.reasoning,
    this.followsFrom,
    this.someMissing = false,
  });

  final String? reason;
  final List<(String, List<String>)> groups;
  final String? reasoning;
  final String? followsFrom;
  final bool someMissing;

  /// The headings of the groups, in the order they are drawn.
  static const String readings = 'Readings';
  static const String lookups = 'Lookups';
  static const String rules = 'Rules and checks';
  static const String others = 'Other sources';
  static const String reasoningHeading = 'Reasoning';
  static const String missingNote = 'Some cited sources are not in this view.';

  bool get isEmpty =>
      reason == null &&
      groups.isEmpty &&
      reasoning == null &&
      followsFrom == null &&
      !someMissing;

  static _Why of(FieldPart part, Map<String, Json> rows) {
    final List<String> readings = <String>[];
    final List<String> lookups = <String>[];
    final List<String> rules = <String>[];
    final List<String> others = <String>[];
    String? reasoning;
    bool missing = false;
    for (final String id in part.evidenceIds) {
      final Json? row = rows[id];
      if (row == null) {
        missing = true;
        continue;
      }
      final PartRelation? relation = part.evidenceRelations[id];
      switch (textOf(row['kind'], '')) {
        case 'reasoning':
          // The one reasoning line the part rests on, in the writer's words.
          final String statement = textOf(row['excerpt'], '').trim();
          if (statement.isNotEmpty) reasoning ??= statement;
        case 'literal':
          readings.add(_line(evidenceDisplaySummary(row), relation, true));
        case 'authority' || 'lookup' || 'authority_selection':
          lookups.add(_line(_withSource(row), relation, false));
        case 'rule' || 'derived':
          rules.add(_line(_withSource(row), relation, false));
        default:
          others.add(_line(_withSource(row), relation, false));
      }
    }
    final String? follows = part.derivedFrom.isEmpty
        ? null
        : 'Follows from: ${part.derivedFrom.map((PartPath p) => p.label).join(', ')}';
    return _Why(
      reason: part.review?.reason,
      groups: <(String, List<String>)>[
        if (readings.isNotEmpty) (_Why.readings, readings),
        if (lookups.isNotEmpty) (_Why.lookups, lookups),
        if (rules.isNotEmpty) (_Why.rules, rules),
        if (others.isNotEmpty) (_Why.others, others),
      ],
      reasoning: reasoning,
      followsFrom: follows,
      someMissing: missing,
    );
  }

  /// A row's text, with the source it came from where the row names one.
  static String _withSource(Json row) {
    final String summary = evidenceDisplaySummary(row);
    final String? source = evidenceSourceLabel(row);
    if (source == null || summary == source) return summary;
    return '$source: $summary';
  }

  /// A row's text and how it bears on the part, where it does more than
  /// support it. The middle dot separates metadata from the text.
  static String _line(String text, PartRelation? relation, bool reading) {
    final String? how = switch (relation) {
      PartRelation.decides => 'decides',
      PartRelation.contradicts => reading ? 'differs' : 'disagrees',
      PartRelation.considered => 'no match',
      PartRelation.supports || null => null,
    };
    return how == null ? text : '$text · $how';
  }

  Widget build(UiThemeData ui) {
    final TextStyle heading = ui.type.labelSmall.copyWith(
      color: ui.color.inkSecondary,
    );
    final TextStyle line = ui.type.bodySmall.copyWith(color: ui.color.ink);
    final List<Widget> children = <Widget>[];
    void gap() {
      if (children.isNotEmpty) children.add(SizedBox(height: ui.space.s2));
    }

    if (reason != null) children.add(Text(reason!, style: line));
    for (final (String title, List<String> lines) in groups) {
      gap();
      children
        ..add(Text(title, style: heading))
        ..addAll(<Widget>[
          for (final String text in lines)
            Padding(
              padding: EdgeInsetsDirectional.only(top: ui.space.s1),
              child: Text(text, style: line),
            ),
        ]);
    }
    if (reasoning != null) {
      gap();
      children
        ..add(Text(reasoningHeading, style: heading))
        ..add(
          Padding(
            padding: EdgeInsetsDirectional.only(top: ui.space.s1),
            child: Text(reasoning!, style: line),
          ),
        );
    }
    if (followsFrom != null) {
      gap();
      children.add(Text(followsFrom!, style: line));
    }
    if (someMissing) {
      gap();
      children.add(Text(missingNote, style: heading));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: children,
    );
  }
}
