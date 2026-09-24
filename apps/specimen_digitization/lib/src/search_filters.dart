/// The queue filters (07 section 4).
///
/// A `UiSheet` on a compact window and a `UiDialog` everywhere else, through
/// `UiDialog.showAdaptive`. Fields are grouped, every label is a word from the
/// glossary rather than an API identifier, dates are typed as days and
/// converted to UTC instants here, and risk is a pair of bounds with an
/// explicit switch for records that have no measurement at all. The value this
/// sheet returns is unchanged: the same `Map<String, String>` with the same
/// keys the repository has always accepted.
library;

import 'dart:async';

// `widgets.dart` exports neither `SemanticsRole` nor the rest of
// `semantics.dart`, so the one role this form publishes is imported by name.
import 'package:flutter/semantics.dart' show SemanticsRole;
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'models.dart';
import 'reason_codes.dart';
import 'saved_filters.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

/// The wire keys this sheet can set, with the words a reviewer reads.
const Map<String, String> searchFields = <String, String>{
  'state': 'Run state',
  'stage': 'Processing step',
  'blocker': 'Blocker',
  'reason_code': 'Issue',
  'uploader_id': 'Uploaded by',
  'batch_id': 'Upload batch',
  'profile_id': 'Profile',
  'profile_version': 'Profile version',
  'asset_id': 'Image file',
  'active_run_id': 'Processing run',
  'created_from': 'Created on or after',
  'created_before': 'Created before',
  'risk_min': 'Lowest risk',
  'risk_max': 'Highest risk',
};

/// The reviewer-facing word for one filter key.
String searchFieldLabel(String key) => searchFields[key] ?? labelOf(key);

/// The run states the search API filters, in the order the picker offers
/// them (UI.md T3.3). `pending` joins once #85 adds it to the search API,
/// so the picker never offers a value the server refuses.
const List<String> runStateChoices = <String>[
  'running',
  'completed',
  'processing_blocked',
  'retry_scheduled',
  'paused',
  'cancelled',
];

/// A run state in the words the queue's rows use. `completed`, which no row
/// chip shows (UI.md T1.2), is "Completed", and a state this client does not
/// know keeps the server's word.
String runStateLabel(String state) {
  if (state == 'completed') return 'Completed';
  final SpecimenStatus status = SpecimenStatus.fromWire(state);
  return status == SpecimenStatus.unknown
      ? vocabularyLabel(state)
      : status.label;
}

/// A filter's value in words, as the picker and the active filter's chip
/// both show it (UI.md T3.3): a run state as the rows name it, a reason as
/// every screen reads it, and anything else as the vocabulary spells it,
/// which leaves an identifier, a date or a number as typed.
String searchValueLabel(String key, String value) => switch (key) {
  'state' => runStateLabel(value),
  'reason_code' => reasonLabel(value),
  _ => vocabularyLabel(value),
};

/// The title the sheet and the dialog both carry.
const String searchFiltersTitle = 'Filter the queue';

/// The keys whose values come from the collection configuration when it
/// publishes them, and from a typed value when it does not.
const Map<String, String> _configuredChoiceKeys = <String, String>{
  'stage': 'stages',
  'blocker': 'blockers',
  'reason_code': 'reason_codes',
  'uploader_id': 'uploaders',
};

/// The lowest and highest risk the server scores.
const int _riskFloor = 0;
const int _riskCeiling = 100;

/// What a picker's cleared option is worth. Not a value the API ever takes.
const String _anyValue = '';

/// The filter form.
///
/// The title and the two actions belong to the modal chrome
/// (`UiDialog.showAdaptive`), so this widget is the scrolling body and
/// nothing else. [SearchFilters.show] wires the three together; a test that
/// wants the body on its own pumps this.
class SearchFilters extends StatefulWidget {
  const SearchFilters({
    super.key,
    required this.initial,
    this.configuration = const <String, dynamic>{},
    this.savedFilters,
    this.dispositions,
    this.dispositionLabel = 'Status',
    this.disposition = '',
  });

  /// The filters already applied.
  final Map<String, String> initial;

  /// The collection document, which feeds the pickers where it names choices.
  final Json configuration;

  /// Where named filter sets are kept, or null when the host offers none
  /// (pass criterion 7.4).
  final SavedFilterStore? savedFilters;

  /// The disposition options this sheet also chooses, or null where the
  /// screen draws them itself.
  ///
  /// A phone has no room for six chips above the list and a pinned row it
  /// could put them in (13 sections 2.3 and 4.2), so the sheet is where the
  /// disposition is chosen there. A window with room keeps them one tap away
  /// and passes null.
  final Map<String, String>? dispositions;

  /// What the disposition filter is called. The caller's word, so the sheet
  /// and the chip that survives it cannot drift.
  final String dispositionLabel;

  /// The disposition already chosen, as a key of [dispositions].
  final String disposition;

  /// Opens the form and answers the filters the reviewer applied.
  ///
  /// Null when they backed out; an empty map when they cleared everything,
  /// which is a filter change rather than a dismissal.
  static Future<Map<String, String>?> show(
    BuildContext context, {
    required Map<String, String> initial,
    Json configuration = const <String, dynamic>{},
    SavedFilterStore? savedFilters,
    Map<String, String>? dispositions,
    String dispositionLabel = 'Status',
    String disposition = '',
    ValueChanged<String>? onDisposition,
  }) {
    final GlobalKey<SearchFiltersState> form = GlobalKey<SearchFiltersState>();
    return showProductModal<Map<String, String>>(
      context: context,
      title: searchFiltersTitle,
      body: (BuildContext modalContext) => SearchFilters(
        key: form,
        initial: initial,
        configuration: configuration,
        savedFilters: savedFilters,
        dispositions: dispositions,
        dispositionLabel: dispositionLabel,
        disposition: disposition,
      ),
      secondaryAction: (BuildContext modalContext) => UiButton(
        label: 'Clear all',
        variant: UiButtonVariant.ghost,
        onPressed: () {
          // Clearing clears everything the sheet holds, the disposition
          // included: a reviewer who cleared the filters and found the list
          // still hiding four of its six dispositions would be right to call
          // that a lie.
          onDisposition?.call('');
          Navigator.of(modalContext).pop(const <String, String>{});
        },
      ),
      primaryAction: (BuildContext modalContext) => UiButton(
        label: 'Apply',
        onPressed: () {
          final SearchFiltersState? state = form.currentState;
          final Map<String, String>? values = state?.submit();
          if (values == null) return;
          onDisposition?.call(state!.disposition);
          Navigator.of(modalContext).pop(values);
        },
      ),
    );
  }

  @override
  State<SearchFilters> createState() => SearchFiltersState();
}

/// The form's state, so the modal's Apply can ask it for the filters.
///
/// Public for the same reason `FormState` is: the control that commits the
/// form is drawn by the chrome around it, one layer up.
class SearchFiltersState extends State<SearchFilters> {
  late final Map<String, String> _values = Map<String, String>.from(
    widget.initial,
  );

  /// The disposition the reviewer has chosen in this sheet.
  ///
  /// Public for the same reason [submit] is: the control that commits the
  /// sheet is drawn by the chrome around it.
  String get disposition => _disposition;
  late String _disposition = widget.disposition;
  final Map<String, TextEditingController> _text =
      <String, TextEditingController>{};
  final Map<String, String> _errors = <String, String>{};

  late String _from = _dayOf(_values['created_from']);
  late String _before = _dayOf(_values['created_before']);
  late int _riskMin = _intOf(_values['risk_min'], _riskFloor);
  late int _riskMax = _intOf(_values['risk_max'], _riskCeiling);
  late bool _includeUnmeasured =
      !_values.containsKey('risk_min') && !_values.containsKey('risk_max');

  List<SavedFilterSet> _saved = const <SavedFilterSet>[];
  bool _savedLoaded = false;

  @override
  void initState() {
    super.initState();
    unawaited(_loadSaved());
  }

  @override
  void dispose() {
    for (final TextEditingController controller in _text.values) {
      controller.dispose();
    }
    super.dispose();
  }

  /// One controller per typed field, so the reviewer's text survives a
  /// rebuild and is never cleared by a validation failure (02 section 4.10).
  TextEditingController _controllerFor(String key, String initial) =>
      _text.putIfAbsent(key, () => TextEditingController(text: initial));

  Future<void> _loadSaved() async {
    final SavedFilterStore? store = widget.savedFilters;
    if (store == null) {
      setState(() => _savedLoaded = true);
      return;
    }
    final List<SavedFilterSet> sets = await store.load();
    if (!mounted) return;
    setState(() {
      _saved = sets;
      _savedLoaded = true;
    });
  }

  /// The filters the form holds right now, or null when something on screen
  /// does not read as a value.
  ///
  /// Validation runs on submit rather than on every keystroke, which is what
  /// 02 section 4.10 asks for, and the message states the rule positively.
  Map<String, String>? submit() {
    final Map<String, String> errors = <String, String>{};
    final DateTime? from = _parseDay(_from);
    final DateTime? before = _parseDay(_before);
    if (_from.isNotEmpty && from == null) {
      errors['created_from'] = _dateRule;
    }
    if (_before.isNotEmpty && before == null) {
      errors['created_before'] = _dateRule;
    }
    if (!_includeUnmeasured && _riskMin > _riskMax) {
      errors['risk_max'] = 'Enter a highest risk at or above the lowest.';
    }
    if (errors.isNotEmpty) {
      setState(() {
        _errors
          ..clear()
          ..addAll(errors);
      });
      return null;
    }
    setState(_errors.clear);
    _writeDates(from, before);
    _writeRisk();
    return Map<String, String>.from(_values)
      ..removeWhere((String key, String value) => value.isEmpty);
  }

  /// The rule a date field states, positively (02 section 4.10).
  static const String _dateRule = 'Enter a date like 2026-09-13.';

  /// The rule a risk bound states.
  static const String _riskRule = 'Enter a number from 0 to 100.';

  Future<void> _saveCurrent() async {
    final SavedFilterStore? store = widget.savedFilters;
    if (store == null) return;
    final Map<String, String>? filters = submit();
    if (filters == null) return;
    final String? name = await _askForName(context);
    if (name == null || !mounted) return;
    final List<SavedFilterSet> sets = await store.save(
      SavedFilterSet(name: name, filters: filters),
    );
    if (!mounted) return;
    setState(() => _saved = sets);
  }

  Future<void> _renameSaved(SavedFilterSet set) async {
    final SavedFilterStore? store = widget.savedFilters;
    if (store == null) return;
    final String? name = await _askForName(context, initial: set.name);
    if (name == null || name == set.name || !mounted) return;
    await store.save(SavedFilterSet(name: name, filters: set.filters));
    final List<SavedFilterSet> sets = await store.remove(set.name);
    if (!mounted) return;
    setState(() => _saved = sets);
  }

  Future<void> _deleteSaved(String name) async {
    final SavedFilterStore? store = widget.savedFilters;
    if (store == null) return;
    final List<SavedFilterSet> sets = await store.remove(name);
    if (!mounted) return;
    setState(() => _saved = sets);
  }

  /// Applies a saved set and closes the sheet, which is the one action pass
  /// criterion 7.4 asks for.
  void _applySaved(SavedFilterSet set) =>
      Navigator.of(context).pop(Map<String, String>.from(set.filters));

  /// The day part of a stored instant, as the reviewer types it.
  static String _dayOf(String? raw) {
    if (raw == null || raw.isEmpty) return '';
    final DateTime? parsed = DateTime.tryParse(raw);
    if (parsed == null) return '';
    final DateTime day = parsed.toUtc();
    return '${day.year.toString().padLeft(4, '0')}-'
        '${day.month.toString().padLeft(2, '0')}-'
        '${day.day.toString().padLeft(2, '0')}';
  }

  static int _intOf(String? raw, int fallback) =>
      int.tryParse(raw ?? '')?.clamp(_riskFloor, _riskCeiling) ?? fallback;

  /// A typed day, or null when it is not one.
  static DateTime? _parseDay(String raw) {
    if (raw.isEmpty) return null;
    final RegExpMatch? match = _dayPattern.firstMatch(raw.trim());
    if (match == null) return null;
    final DateTime day = DateTime.utc(
      int.parse(match.group(1)!),
      int.parse(match.group(2)!),
      int.parse(match.group(3)!),
    );
    // A month or a day the calendar does not have rolls over rather than
    // failing, so the round trip is what says whether it was a real date.
    if (day.month != int.parse(match.group(2)!)) return null;
    if (day.day != int.parse(match.group(3)!)) return null;
    return day;
  }

  static final RegExp _dayPattern = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$');

  List<String> _choices(String key) {
    final String? source = _configuredChoiceKeys[key];
    if (source == null) return const <String>[];
    final Object? published = widget.configuration[source];
    if (published is! List) return const <String>[];
    return published
        .map(
          (Object? value) => value is Map ? textOf(value['id'], '') : '$value',
        )
        .where((String value) => value.isNotEmpty)
        // A reason the search cannot find yet is not offered (UI.md T3.2).
        .where(
          (String value) =>
              key != 'reason_code' || !suffixedReasonCodes.contains(value),
        )
        .toList();
  }

  List<String> get _profileIds => objects(widget.configuration['profiles'])
      .map((Json profile) => textOf(profile['id'], ''))
      .where((String id) => id.isNotEmpty)
      .toSet()
      .toList();

  List<String> get _profileVersions => objects(widget.configuration['profiles'])
      .where(
        (Json profile) =>
            _values['profile_id'] == null ||
            _values['profile_id']!.isEmpty ||
            textOf(profile['id'], '') == _values['profile_id'],
      )
      .map((Json profile) => textOf(profile['version'], ''))
      .where((String version) => version.isNotEmpty)
      .toSet()
      .toList();

  void _set(String key, String? value) {
    setState(() {
      if (value == null || value.isEmpty) {
        _values.remove(key);
      } else {
        _values[key] = value;
      }
    });
  }

  /// Turns the typed days into the UTC instants the API filters on.
  ///
  /// `created_before` is exclusive on the wire and the field says so, so the
  /// day the reviewer types is the first day the filter leaves out.
  void _writeDates(DateTime? from, DateTime? before) {
    if (from == null) {
      _values.remove('created_from');
    } else {
      _values['created_from'] = from.toIso8601String();
    }
    if (before == null) {
      _values.remove('created_before');
    } else {
      _values['created_before'] = before.toIso8601String();
    }
  }

  void _writeRisk() {
    if (_includeUnmeasured) {
      _values.remove('risk_min');
      _values.remove('risk_max');
      return;
    }
    _values['risk_min'] = '$_riskMin';
    _values['risk_max'] = '$_riskMax';
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Semantics(
      // The body is a form, and says so: the chrome around it carries the
      // title and the two actions, so this is the only node that can.
      container: true,
      role: SemanticsRole.form,
      // Its groups and its fields are its own nodes, said here rather than
      // taken from a viewport. A container node absorbs every compatible
      // descendant below it, so while this body scrolled itself the
      // scrollable inside the node was the only thing keeping "Status",
      // "Provenance" and "Dates" out of the form's own label; a body that
      // lets its frame scroll it has no such boundary and would have
      // announced the six headings as one phrase.
      explicitChildNodes: true,
      // A column, not a scroller. Both modal frames bound this body to what
      // their chrome leaves and scroll it themselves, so a body that scrolled
      // as well would be a second scrollable inside the first, with an
      // unbounded height and a cap this file had to keep in step with a drag
      // handle, a title and an action row it does not own.
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (widget.dispositions != null) ...<Widget>[
            _Group(
              title: widget.dispositionLabel,
              children: <Widget>[
                UiSelect<String>(
                  label: widget.dispositionLabel,
                  placeholder: widget.dispositions![''] ?? 'All',
                  value: _disposition,
                  options: <UiSelectOption<String>>[
                    for (final MapEntry<String, String> entry
                        in widget.dispositions!.entries)
                      UiSelectOption<String>(
                        value: entry.key,
                        label: entry.value,
                      ),
                  ],
                  onChanged: (String value) =>
                      setState(() => _disposition = value),
                ),
              ],
            ),
            SizedBox(height: ui.space.s4),
          ],
          if (widget.savedFilters != null)
            _SavedSets(
              sets: _saved,
              loaded: _savedLoaded,
              onApply: _applySaved,
              onRename: (SavedFilterSet set) => unawaited(_renameSaved(set)),
              onDelete: _deleteSaved,
              onSaveCurrent: () => unawaited(_saveCurrent()),
            ),
          const CaveatText(
            label: 'All filters must match.',
            why:
                'A risk range excludes records with no measured risk. '
                'Risk never determines clearance.',
          ),
          _Group(
            title: 'Status',
            children: <Widget>[
              _picker('state', runStateChoices),
              for (final String key in <String>[
                'stage',
                'blocker',
                'reason_code',
              ])
                _field(key),
            ],
          ),
          _Group(
            title: 'Provenance',
            children: <Widget>[
              _field('uploader_id'),
              _field('batch_id'),
              _picker('profile_id', _profileIds),
              _picker('profile_version', _profileVersions),
            ],
          ),
          _Group(
            title: 'Dates',
            children: <Widget>[
              _dayField('created_from', 'The first day the filter keeps.'),
              _dayField(
                'created_before',
                'The first day the filter leaves out.',
              ),
              if (_from.isNotEmpty || _before.isNotEmpty)
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: UiButton(
                    label: 'Any date',
                    variant: UiButtonVariant.ghost,
                    onPressed: () => setState(() {
                      _from = '';
                      _before = '';
                      _controllerFor('created_from', '').clear();
                      _controllerFor('created_before', '').clear();
                      _errors
                        ..remove('created_from')
                        ..remove('created_before');
                    }),
                  ),
                ),
            ],
          ),
          _Group(
            title: 'Risk',
            children: <Widget>[
              Padding(
                padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s2),
                child: UiSwitch(
                  label: 'Include not measured',
                  value: _includeUnmeasured,
                  onChanged: (bool value) =>
                      setState(() => _includeUnmeasured = value),
                ),
              ),
              Text(
                'Turn this off to narrow the queue to a risk range.',
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
              _riskField('risk_min', _riskMin, (int value) => _riskMin = value),
              _riskField('risk_max', _riskMax, (int value) => _riskMax = value),
            ],
          ),
          _Group(
            title: 'Identifiers',
            children: <Widget>[_field('asset_id'), _field('active_run_id')],
          ),
        ],
      ),
    );
  }

  /// A picker when the collection published the choices, a text field with the
  /// plain label when it did not (07 section 4).
  Widget _field(String key) {
    final List<String> choices = _choices(key);
    if (choices.isNotEmpty) return _picker(key, choices);
    return _textField(key);
  }

  Widget _textField(String key) => Padding(
    padding: EdgeInsetsDirectional.symmetric(vertical: context.ui.space.s2),
    child: UiField(
      label: searchFieldLabel(key),
      controller: _controllerFor(key, _values[key] ?? ''),
      // The first field takes focus on open, so a keyboard reviewer starts in
      // the form rather than silently on the dismissal control
      // (06 section 4.2 step 5; finding V-10).
      autofocus: key == searchFields.keys.first,
      onChanged: (String value) => _values[key] = value.trim(),
    ),
  );

  Widget _picker(String key, List<String> choices) {
    if (choices.isEmpty) return _textField(key);
    final String current = choices.contains(_values[key])
        ? _values[key]!
        : _anyValue;
    return Padding(
      padding: EdgeInsetsDirectional.symmetric(vertical: context.ui.space.s2),
      child: UiSelect<String>(
        label: searchFieldLabel(key),
        placeholder: 'Any',
        value: current,
        options: <UiSelectOption<String>>[
          const UiSelectOption<String>(value: _anyValue, label: 'Any'),
          for (final String choice in choices)
            UiSelectOption<String>(
              value: choice,
              label: searchValueLabel(key, choice),
            ),
        ],
        onChanged: (String value) =>
            _set(key, value == _anyValue ? null : value),
      ),
    );
  }

  /// One day, typed.
  ///
  /// The design system has no date control yet and `showDateRangePicker` is a
  /// Material component this file may not reach for, so the two instants are
  /// typed as days and converted here, exactly as they were converted before.
  //
  // TODO(specimen_ui): a UiDateField, so a reviewer picks a day rather than
  // spelling one. Not a slot's to build until it has an entry in 10 section 4,
  // which 10 section 10 asks for before a new component exists.
  Widget _dayField(String key, String help) => Padding(
    padding: EdgeInsetsDirectional.symmetric(vertical: context.ui.space.s2),
    child: UiField(
      label: searchFieldLabel(key),
      controller: _controllerFor(key, key == 'created_from' ? _from : _before),
      hintText: '2026-09-13',
      helpText: help,
      errorText: _errors[key],
      keyboardType: TextInputType.datetime,
      onChanged: (String value) {
        final String trimmed = value.trim();
        if (key == 'created_from') {
          _from = trimmed;
        } else {
          _before = trimmed;
        }
      },
    ),
  );

  /// One end of the risk range, typed, and held at 0 to 100.
  Widget _riskField(String key, int value, void Function(int) write) => Padding(
    padding: EdgeInsetsDirectional.symmetric(vertical: context.ui.space.s2),
    child: UiField(
      label: searchFieldLabel(key),
      controller: _controllerFor(key, '$value'),
      enabled: !_includeUnmeasured,
      disabledReason: 'Turn off Include not measured to use a risk range.',
      helpText: _riskRule,
      errorText: _errors[key],
      keyboardType: TextInputType.number,
      onChanged: (String raw) {
        final int? parsed = int.tryParse(raw.trim());
        setState(() {
          if (parsed == null || parsed < _riskFloor || parsed > _riskCeiling) {
            _errors[key] = _riskRule;
          } else {
            _errors.remove(key);
            write(parsed);
          }
        });
      },
    ),
  );
}

/// The saved filter sets, at the top of the form (pass criterion 7.4).
///
/// Each set applies in one press, and its own menu renames or deletes it. The
/// sets live on this device, which is said out loud rather than implied,
/// because the collection API has nowhere to keep one.
class _SavedSets extends StatelessWidget {
  const _SavedSets({
    required this.sets,
    required this.loaded,
    required this.onApply,
    required this.onRename,
    required this.onDelete,
    required this.onSaveCurrent,
  });

  final List<SavedFilterSet> sets;
  final bool loaded;
  final ValueChanged<SavedFilterSet> onApply;
  final ValueChanged<SavedFilterSet> onRename;
  final ValueChanged<String> onDelete;
  final VoidCallback onSaveCurrent;

  /// How a set's filter count is worded, so one and several agree.
  static String countLabel(int count) =>
      count == 1 ? '1 filter' : '$count filters';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: Text(
            'Saved filter sets',
            style: ui.type.title.copyWith(color: ui.color.ink),
          ),
        ),
        SizedBox(height: ui.space.s1),
        if (!loaded)
          const LoadingAnnouncement(thing: 'saved filter sets', visible: true)
        else if (sets.isEmpty)
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: Text(
              'None saved on this device yet.',
              style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
            ),
          )
        else
          for (final SavedFilterSet set in sets)
            Row(
              key: ValueKey<String>('saved-filter-${set.name}'),
              children: <Widget>[
                Expanded(
                  child: UiListRow(
                    title: set.name,
                    subtitle: countLabel(set.count),
                    semanticsLabel:
                        'Apply the ${set.name} filter set, '
                        '${countLabel(set.count)}',
                    onPressed: () => onApply(set),
                  ),
                ),
                // The menu sits beside the row rather than in its trailing
                // slot: a row is one merged semantics node and one press
                // target, so a second control inside it would be unnamed to a
                // screen reader and would also apply the set when pressed.
                UiMenuTrigger(
                  icon: UiIcons.more,
                  semanticsLabel: 'Manage the ${set.name} filter set',
                  items: <UiMenuItem>[
                    UiMenuItem(
                      label: 'Rename',
                      icon: UiIcons.edit,
                      onSelected: () => onRename(set),
                    ),
                    UiMenuItem(
                      label: 'Delete',
                      icon: UiIcons.remove,
                      destructive: true,
                      onSelected: () => onDelete(set.name),
                    ),
                  ],
                ),
              ],
            ),
        SizedBox(height: ui.space.s2),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: UiButton(
            label: 'Save these filters',
            variant: UiButtonVariant.secondary,
            leading: UiIcons.saveFilter,
            onPressed: onSaveCurrent,
          ),
        ),
        SizedBox(height: ui.space.s1),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: Text(
            'Saved on this device only.',
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ),
      ],
    );
  }
}

/// Asks what to call a filter set. Returns null when nothing was named.
Future<String?> _askForName(BuildContext context, {String initial = ''}) {
  final GlobalKey<_NameFilterSetState> form = GlobalKey<_NameFilterSetState>();
  return showProductModal<String>(
    context: context,
    title: initial.isEmpty ? 'Name these filters' : 'Rename this filter set',
    body: (BuildContext modalContext) =>
        _NameFilterSet(key: form, initial: initial),
    secondaryAction: (BuildContext modalContext) => UiButton(
      label: 'Cancel',
      variant: UiButtonVariant.ghost,
      onPressed: () => Navigator.of(modalContext).pop(),
    ),
    primaryAction: (BuildContext modalContext) => UiButton(
      label: 'Save the filter set',
      onPressed: () {
        final String? name = form.currentState?.name;
        if (name != null) Navigator.of(modalContext).pop(name);
      },
    ),
  );
}

/// The name prompt's field.
///
/// A widget of its own, because the controller has to outlive the route's
/// exit animation and be disposed after it, which a `whenComplete` on the
/// future cannot do.
class _NameFilterSet extends StatefulWidget {
  const _NameFilterSet({super.key, required this.initial});

  final String initial;

  @override
  State<_NameFilterSet> createState() => _NameFilterSetState();
}

class _NameFilterSetState extends State<_NameFilterSet> {
  late final TextEditingController _name = TextEditingController(
    text: widget.initial,
  );

  /// What the reviewer typed, or null when they typed nothing.
  String? get name {
    final String value = _name.text.trim();
    return value.isEmpty ? null : value;
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  void _accept() {
    final String? value = name;
    if (value != null) Navigator.of(context).pop(value);
  }

  @override
  Widget build(BuildContext context) => UiField(
    label: 'Filter set name',
    controller: _name,
    autofocus: true,
    helpText: 'Saved on this device. Reusing a name replaces that set.',
    onSubmitted: (String _) => _accept(),
  );
}

/// A titled group of fields.
class _Group extends StatelessWidget {
  const _Group({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Padding(
      padding: EdgeInsetsDirectional.only(top: ui.space.s4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          // Aligned rather than stretched. A heading is not a full-width
          // object, and a `Text` stretched across the sheet reports its paint
          // bounds as the whole row, which is what `textContrastGuideline`
          // samples: the mode of the dark pixels in a mostly-empty row is an
          // anti-aliased edge shade rather than the ink the glyph is set in.
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: Text(
              title,
              style: ui.type.title.copyWith(color: ui.color.ink),
            ),
          ),
          ...children,
        ],
      ),
    );
  }
}

/// A day, spelled the way the queue spells a date.
String absoluteDay(DateTime moment) =>
    absoluteTime(moment).split(',').first.trim();
