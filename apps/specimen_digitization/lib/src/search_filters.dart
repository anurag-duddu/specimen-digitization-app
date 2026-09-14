/// The queue filters (screen blueprints, section 4).
///
/// A bottom sheet on a compact window and a 480 dp dialog everywhere else,
/// through `showAdaptiveForm`. Fields are grouped, every label is a word from
/// the glossary rather than an API identifier, dates are picked and converted
/// to UTC instants here, and risk is a range rather than two typed numbers.
/// The value this sheet returns is unchanged: the same `Map<String, String>`
/// with the same keys the repository has always accepted.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'models.dart';
import 'saved_filters.dart';
import 'theme/icons.dart';
import 'vocabulary.dart';
import 'widgets/widgets.dart';

/// The wire keys this sheet can set, with the words a reviewer reads.
const Map<String, String> searchFields = <String, String>{
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

/// The keys whose values come from the collection configuration when it
/// publishes them, and from a typed value when it does not.
const Map<String, String> _configuredChoiceKeys = <String, String>{
  'stage': 'stages',
  'blocker': 'blockers',
  'reason_code': 'reason_codes',
  'uploader_id': 'uploaders',
};

/// The lowest and highest risk the server scores.
const double _riskFloor = 0;
const double _riskCeiling = 100;

/// The filter form.
///
/// Rendered as the child of [showAdaptiveForm], so it sizes itself and does
/// not carry a dialog of its own.
class SearchFilters extends StatefulWidget {
  const SearchFilters({
    super.key,
    required this.initial,
    this.configuration = const <String, dynamic>{},
    this.savedFilters,
  });

  /// The filters already applied.
  final Map<String, String> initial;

  /// The collection document, which feeds the pickers where it names choices.
  final Json configuration;

  /// Where named filter sets are kept, or null when the host offers none
  /// (pass criterion 7.4).
  final SavedFilterStore? savedFilters;

  @override
  State<SearchFilters> createState() => _SearchFiltersState();
}

class _SearchFiltersState extends State<SearchFilters> {
  late final Map<String, String> _values = Map<String, String>.from(
    widget.initial,
  );
  final GlobalKey<FormState> _form = GlobalKey<FormState>();

  late DateTimeRange? _dates = _initialRange();
  late RangeValues _risk = _initialRisk();
  late bool _includeUnmeasured =
      !_values.containsKey('risk_min') && !_values.containsKey('risk_max');

  List<SavedFilterSet> _saved = const <SavedFilterSet>[];
  bool _savedLoaded = false;

  @override
  void initState() {
    super.initState();
    unawaited(_loadSaved());
  }

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

  /// The filter map the sheet would return right now.
  Map<String, String> _resolved() {
    _writeDates();
    _writeRisk();
    return Map<String, String>.from(_values)
      ..removeWhere((String key, String value) => value.isEmpty);
  }

  Future<void> _saveCurrent() async {
    final SavedFilterStore? store = widget.savedFilters;
    if (store == null) return;
    final Map<String, String> filters = _resolved();
    final String? name = await _askForName(context);
    if (name == null || !mounted) return;
    final List<SavedFilterSet> sets = await store.save(
      SavedFilterSet(name: name, filters: filters),
    );
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
      Navigator.pop(context, Map<String, String>.from(set.filters));

  DateTimeRange? _initialRange() {
    final DateTime? from = DateTime.tryParse(_values['created_from'] ?? '');
    final DateTime? before = DateTime.tryParse(_values['created_before'] ?? '');
    if (from == null || before == null) return null;
    // `created_before` is exclusive, so the last day a reviewer picked is the
    // day before it.
    return DateTimeRange(
      start: from.toLocal(),
      end: before.subtract(const Duration(days: 1)).toLocal(),
    );
  }

  RangeValues _initialRisk() {
    final double low = double.tryParse(_values['risk_min'] ?? '') ?? _riskFloor;
    final double high =
        double.tryParse(_values['risk_max'] ?? '') ?? _riskCeiling;
    return RangeValues(
      low.clamp(_riskFloor, _riskCeiling),
      high.clamp(low, _riskCeiling),
    );
  }

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

  Future<void> _pickDates() async {
    final DateTime now = DateTime.now();
    final DateTimeRange? picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - _yearsOfHistory),
      lastDate: now,
      initialDateRange: _dates,
      helpText: 'Created between',
      saveText: 'Use these dates',
    );
    if (picked == null) return;
    setState(() => _dates = picked);
  }

  /// How far back the date picker offers. Collections predate the client, so
  /// this is a picker range, not a claim about the data.
  static const int _yearsOfHistory = 20;

  /// Turns the picked local days into the UTC instants the API filters on.
  void _writeDates() {
    final DateTimeRange? range = _dates;
    if (range == null) {
      _values.remove('created_from');
      _values.remove('created_before');
      return;
    }
    final DateTime from = DateTime.utc(
      range.start.year,
      range.start.month,
      range.start.day,
    );
    final DateTime before = DateTime.utc(
      range.end.year,
      range.end.month,
      range.end.day,
    ).add(const Duration(days: 1));
    _values['created_from'] = from.toIso8601String();
    _values['created_before'] = before.toIso8601String();
  }

  void _writeRisk() {
    if (_includeUnmeasured) {
      _values.remove('risk_min');
      _values.remove('risk_max');
      return;
    }
    _values['risk_min'] = _risk.start.round().toString();
    _values['risk_max'] = _risk.end.round().toString();
  }

  String _dateSummary() {
    final DateTimeRange? range = _dates;
    if (range == null) return 'Any date';
    return '${absoluteDay(range.start)} to ${absoluteDay(range.end)}';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Form(
      key: _form,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Padding(
            padding: EdgeInsets.fromLTRB(
              context.space.space6,
              context.space.space4,
              context.space.space6,
              context.space.space0,
            ),
            child: Text('Filter the queue', style: theme.textTheme.titleLarge),
          ),
          // Loose, so the form still lays out where it is pumped into an
          // unbounded height. What stops the scrolling body from being drawn
          // over Apply is the dialog's own height bound in
          // `showAdaptiveForm`: without one the remaining space is infinite,
          // this child shrink-wraps its whole content, and the last control
          // in it lands on top of the action row (finding V-6).
          Flexible(
            child: SingleChildScrollView(
              padding: EdgeInsets.all(context.space.space6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  if (widget.savedFilters != null)
                    _SavedSets(
                      sets: _saved,
                      loaded: _savedLoaded,
                      onApply: _applySaved,
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
                      OutlinedButton.icon(
                        onPressed: _pickDates,
                        icon: const Icon(Symbols.date_range),
                        label: Text('Created: ${_dateSummary()}'),
                      ),
                      if (_dates != null)
                        Align(
                          alignment: AlignmentDirectional.centerStart,
                          child: TextButton(
                            onPressed: () => setState(() => _dates = null),
                            child: const Text('Any date'),
                          ),
                        ),
                    ],
                  ),
                  _Group(
                    title: 'Risk',
                    children: <Widget>[
                      SwitchListTile(
                        value: _includeUnmeasured,
                        onChanged: (bool value) =>
                            setState(() => _includeUnmeasured = value),
                        title: const Text('Include not measured'),
                        subtitle: const Text(
                          'Turn this off to narrow the queue to a risk range.',
                        ),
                        contentPadding: EdgeInsets.zero,
                      ),
                      Semantics(
                        label: 'Risk range, 0 to 100',
                        child: RangeSlider(
                          values: _risk,
                          min: _riskFloor,
                          max: _riskCeiling,
                          divisions: _riskCeiling.round(),
                          labels: RangeLabels(
                            _risk.start.round().toString(),
                            _risk.end.round().toString(),
                          ),
                          onChanged: _includeUnmeasured
                              ? null
                              : (RangeValues values) =>
                                    setState(() => _risk = values),
                        ),
                      ),
                      Text(
                        _includeUnmeasured
                            ? 'Every record, measured or not.'
                            : 'Risk ${_risk.start.round()} to '
                                  '${_risk.end.round()} of 100.',
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                  ),
                  _Group(
                    title: 'Identifiers',
                    children: <Widget>[
                      _field('asset_id'),
                      _field('active_run_id'),
                    ],
                  ),
                ],
              ),
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(
              context.space.space4,
              context.space.space0,
              context.space.space4,
              context.space.space4,
            ),
            child: OverflowBar(
              alignment: MainAxisAlignment.end,
              spacing: context.space.space2,
              children: <Widget>[
                TextButton(
                  onPressed: () =>
                      Navigator.pop(context, const <String, String>{}),
                  child: const Text('Clear all'),
                ),
                FilledButton(
                  onPressed: () {
                    if (!_form.currentState!.validate()) return;
                    Navigator.pop(context, _resolved());
                  },
                  child: const Text('Apply'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// A picker when the collection published the choices, a text field with the
  /// plain label when it did not (screen blueprints, section 4).
  Widget _field(String key) {
    final List<String> choices = _choices(key);
    if (choices.isNotEmpty) return _picker(key, choices);
    return Padding(
      padding: EdgeInsets.symmetric(vertical: context.space.space2),
      child: TextFormField(
        // The first text field takes focus on open, so a keyboard reviewer
        // starts in the form rather than silently on Cancel (accessibility,
        // section 4.2 step 5; finding V-10).
        autofocus: key == searchFields.keys.first,
        initialValue: _values[key],
        decoration: InputDecoration(labelText: searchFieldLabel(key)),
        onChanged: (String value) => _values[key] = value.trim(),
      ),
    );
  }

  Widget _picker(String key, List<String> choices) {
    if (choices.isEmpty) {
      return Padding(
        padding: EdgeInsets.symmetric(vertical: context.space.space2),
        child: TextFormField(
          initialValue: _values[key],
          decoration: InputDecoration(labelText: searchFieldLabel(key)),
          onChanged: (String value) => _values[key] = value.trim(),
        ),
      );
    }
    final String? current = choices.contains(_values[key])
        ? _values[key]
        : null;
    return Padding(
      padding: EdgeInsets.symmetric(vertical: context.space.space2),
      child: DropdownButtonFormField<String>(
        initialValue: current,
        isExpanded: true,
        decoration: InputDecoration(labelText: searchFieldLabel(key)),
        items: <DropdownMenuItem<String>>[
          const DropdownMenuItem<String>(child: Text('Any')),
          for (final String choice in choices)
            DropdownMenuItem<String>(
              value: choice,
              child: Text(vocabularyLabel(choice)),
            ),
        ],
        onChanged: (String? value) => _set(key, value),
      ),
    );
  }
}

/// The saved filter sets, at the top of the form (pass criterion 7.4).
///
/// Each set applies in one tap and deletes from its own chip. The sets live
/// on this device, which is said out loud rather than implied, because the
/// collection API has nowhere to keep one.
class _SavedSets extends StatelessWidget {
  const _SavedSets({
    required this.sets,
    required this.loaded,
    required this.onApply,
    required this.onDelete,
    required this.onSaveCurrent,
  });

  final List<SavedFilterSet> sets;
  final bool loaded;
  final ValueChanged<SavedFilterSet> onApply;
  final ValueChanged<String> onDelete;
  final VoidCallback onSaveCurrent;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text('Saved filter sets', style: theme.textTheme.titleSmall),
        SizedBox(height: context.space.space1),
        if (!loaded)
          const LoadingAnnouncement(thing: 'saved filter sets', visible: true)
        else if (sets.isEmpty)
          Text(
            'None saved on this device yet.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          )
        else
          Wrap(
            spacing: context.space.space2,
            runSpacing: context.space.space2,
            children: <Widget>[
              for (final SavedFilterSet set in sets)
                InputChip(
                  key: ValueKey<String>('saved-filter-${set.name}'),
                  label: Text('${set.name} (${set.count})'),
                  tooltip: 'Apply the ${set.name} filter set',
                  onPressed: () => onApply(set),
                  onDeleted: () => onDelete(set.name),
                  deleteIcon: const Icon(Symbols.close),
                  deleteButtonTooltipMessage:
                      'Delete the ${set.name} filter set',
                ),
            ],
          ),
        SizedBox(height: context.space.space2),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: OutlinedButton.icon(
            onPressed: onSaveCurrent,
            icon: const Icon(Symbols.bookmark_add),
            label: const Text('Save these filters'),
          ),
        ),
        Text(
          'Saved on this device only.',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}

/// Asks what to call the current filters. Returns null when nothing was named.
Future<String?> _askForName(BuildContext context) => showDialog<String>(
  context: context,
  builder: (BuildContext dialogContext) => const _NameFilterSet(),
);

/// The name prompt. A widget of its own, because the field's controller has to
/// outlive the route's exit animation and be disposed after it, which a
/// `whenComplete` on the future cannot do.
class _NameFilterSet extends StatefulWidget {
  const _NameFilterSet();

  @override
  State<_NameFilterSet> createState() => _NameFilterSetState();
}

class _NameFilterSetState extends State<_NameFilterSet> {
  final TextEditingController _name = TextEditingController();

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  void _accept() {
    final String value = _name.text.trim();
    Navigator.pop(context, value.isEmpty ? null : value);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Name these filters'),
    content: TextField(
      controller: _name,
      autofocus: true,
      decoration: const InputDecoration(
        labelText: 'Filter set name',
        helperText: 'Saved on this device. Reusing a name replaces that set.',
      ),
      onSubmitted: (String _) => _accept(),
    ),
    actions: <Widget>[
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: _accept,
        child: const Text('Save the filter set'),
      ),
    ],
  );
}

/// A titled group of fields.
class _Group extends StatelessWidget {
  const _Group({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(top: context.space.space4),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(title, style: Theme.of(context).textTheme.titleSmall),
        ...children,
      ],
    ),
  );
}

/// A day, spelled the way the queue spells a date.
String absoluteDay(DateTime moment) =>
    absoluteTime(moment).split(',').first.trim();
