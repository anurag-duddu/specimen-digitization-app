import 'package:flutter/material.dart';

const searchFields = {
  'asset_id': 'Asset ID',
  'active_run_id': 'Run ID',
  'batch_id': 'Batch ID',
  'uploader_id': 'Uploader ID',
  'stage': 'Processing stage',
  'profile_id': 'Profile ID',
  'profile_version': 'Profile version',
  'reason_code': 'Issue code',
  'blocker': 'Blocker',
  'created_from': 'Created from (inclusive UTC)',
  'created_before': 'Created before (exclusive UTC)',
  'risk_min': 'Minimum risk (0–100)',
  'risk_max': 'Maximum risk (0–100)',
};

class SearchFilters extends StatefulWidget {
  const SearchFilters({super.key, required this.initial});
  final Map<String, String> initial;
  @override
  State<SearchFilters> createState() => _SearchFiltersState();
}

class _SearchFiltersState extends State<SearchFilters> {
  late final _values = Map<String, String>.from(widget.initial);
  final _form = GlobalKey<FormState>();
  String? _validate(String key, String? raw) {
    final value = raw?.trim() ?? '';
    if (value.isEmpty) return null;
    if (key.startsWith('risk_')) {
      final risk = double.tryParse(value);
      if (risk == null || !risk.isFinite || risk < 0 || risk > 100) {
        return 'Enter a number from 0 to 100.';
      }
      if (key == 'risk_max' &&
          risk < (double.tryParse(_values['risk_min'] ?? '') ?? 0)) {
        return 'Maximum must be at least the minimum.';
      }
    }
    if (key.startsWith('created_')) {
      final date = DateTime.tryParse(value);
      if (date == null || !date.isUtc) {
        return 'Use UTC, for example 2026-09-08T00:00:00Z.';
      }
      final from = DateTime.tryParse(_values['created_from'] ?? '');
      if (key == 'created_before' && from != null && !date.isAfter(from)) {
        return 'End must be after the start.';
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Filter collection queue'),
    content: SizedBox(
      width: 520,
      child: Form(
        key: _form,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'All filters must match. Risk filters exclude unmeasured records; risk does not establish clearance.',
              ),
              for (final entry in searchFields.entries)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: TextFormField(
                    initialValue: _values[entry.key],
                    decoration: InputDecoration(labelText: entry.value),
                    onChanged: (value) => _values[entry.key] = value.trim(),
                    validator: (value) => _validate(entry.key, value),
                  ),
                ),
            ],
          ),
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      TextButton(
        onPressed: () => Navigator.pop(context, <String, String>{}),
        child: const Text('Clear filters'),
      ),
      FilledButton(
        onPressed: () {
          if (_form.currentState!.validate()) {
            Navigator.pop(
              context,
              Map<String, String>.from(_values)
                ..removeWhere((k, v) => v.isEmpty),
            );
          }
        },
        child: const Text('Apply filters'),
      ),
    ],
  );
}
