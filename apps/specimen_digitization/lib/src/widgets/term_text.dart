/// A domain term that carries its own definition (pass criterion 10.2).
///
/// The glossary on the help sheet was complete and two taps away, which is
/// not what the criterion asks for: it asks for a definition reachable from
/// where the term appears. A term drawn through [TermText] keeps a hairline
/// dotted underline in the `boundary` role, opens its one sentence in a small
/// sheet, and announces itself as "Country, term, double tap for definition".
///
/// It is a link, not a button, and deliberately so. WCAG 2.2 SC 2.5.8 exempts
/// an inline link from the target size rule for exactly this case: a word
/// inside a sentence cannot be given a 48 dp box without breaking the
/// sentence, and the definition is a convenience rather than a control the
/// review depends on. Everything the definition explains is also on the help
/// sheet, which is one tap from every screen and whose entry is a full
/// target.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../glossary.dart';

/// A term, underlined, that opens its definition.
///
/// Renders as plain text when the word is not in the glossary, so a caller
/// can pass a server string without checking first and no underline ever
/// promises a definition that does not exist.
class TermText extends StatelessWidget {
  const TermText(
    this.term, {
    super.key,
    this.displayText,
    this.trailing,
    this.style,
    this.spokenTerm,
    this.maxLines,
    this.overflow,
  });

  /// The glossary word this run of text is an instance of.
  final String term;

  /// What is drawn, when it is not the term itself.
  ///
  /// "Fixture provider" is an instance of the term "Provider" and "Label 1"
  /// an instance of "Region". Underlining the value rather than inserting the
  /// word keeps the string the product already shows, which pass criterion
  /// 2.4 depends on: two elements naming the same object have to use the same
  /// name everywhere.
  final String? displayText;

  /// Text appended after the term, outside the underline. A count, a value,
  /// an identifier: the part of the line that is not the term.
  final String? trailing;

  /// The text style for the whole line.
  final TextStyle? style;

  /// What a screen reader hears before ", term, double tap for definition".
  ///
  /// Defaults to the term plus [trailing], so "Version 17" is spoken whole
  /// and gaining a definition never costs a reader the value. A chip that
  /// already announces which vocabulary its word came from passes its own
  /// phrase here instead.
  final String? spokenTerm;

  final int? maxLines;
  final TextOverflow? overflow;

  /// The word that closes a definition sheet.
  static const String closeLabel = 'Close';

  /// The phrase every term announces, so one wording covers the product.
  static String semanticsFor(String spoken) =>
      '$spoken, term, double tap for definition';

  /// Opens one definition in a sheet over whatever is on screen.
  static Future<void> show(BuildContext context, String term) {
    final String? definition = glossaryDefinition(term);
    if (definition == null) return Future<void>.value();
    return UiSheet.show<void>(
      context: context,
      title: term,
      body: (BuildContext sheetContext) => Text(
        definition,
        style: sheetContext.ui.type.body.copyWith(
          color: sheetContext.ui.color.ink,
        ),
      ),
      secondaryAction: (BuildContext sheetContext) => UiButton(
        label: closeLabel,
        variant: UiButtonVariant.ghost,
        onPressed: () => Navigator.of(sheetContext).pop(),
      ),
      dismissLabel: closeLabel,
    );
  }

  /// The run of text this widget draws, before [trailing].
  String get _shown => displayText ?? term;

  @override
  Widget build(BuildContext context) {
    final String tail = trailing ?? '';
    if (!isGlossaryTerm(term)) {
      return Text(
        '$_shown$tail',
        style: style,
        maxLines: maxLines,
        overflow: overflow,
      );
    }
    final UiThemeData ui = context.ui;
    final TextStyle base = style ?? DefaultTextStyle.of(context).style;
    void open() => TermText.show(context, term);

    return Semantics(
      link: true,
      label: semanticsFor(spokenTerm ?? '$_shown$tail'),
      onTap: open,
      excludeSemantics: true,
      child: GestureDetector(
        onTap: open,
        behavior: HitTestBehavior.opaque,
        child: Text.rich(
          TextSpan(
            children: <InlineSpan>[
              TextSpan(
                text: _shown,
                style: base.copyWith(
                  decoration: TextDecoration.underline,
                  decorationStyle: TextDecorationStyle.dotted,
                  decorationColor: ui.color.boundary,
                ),
              ),
              if (tail.isNotEmpty) TextSpan(text: tail),
            ],
          ),
          style: base,
          maxLines: maxLines,
          overflow: overflow ?? TextOverflow.clip,
        ),
      ),
    );
  }
}

/// Wraps a whole component in the same definition affordance.
///
/// For a term that is drawn as something other than a run of text: a chip, a
/// meter, a card heading. The child keeps its own appearance and loses its
/// own semantics, because two nodes for one word is what a screen reader
/// reads as two things.
class TermAffordance extends StatelessWidget {
  const TermAffordance({
    super.key,
    required this.term,
    required this.spokenTerm,
    required this.child,
  });

  /// The glossary word this component is about.
  final String term;

  /// What a screen reader hears before ", term, double tap for definition".
  final String spokenTerm;

  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!isGlossaryTerm(term)) return child;
    void open() => TermText.show(context, term);
    return Semantics(
      link: true,
      label: TermText.semanticsFor(spokenTerm),
      onTap: open,
      excludeSemantics: true,
      child: GestureDetector(
        onTap: open,
        behavior: HitTestBehavior.opaque,
        child: child,
      ),
    );
  }
}
