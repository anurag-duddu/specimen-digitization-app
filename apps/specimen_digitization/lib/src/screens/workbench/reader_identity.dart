import 'dart:convert';

import '../../models.dart';

/// A stable identity comes from supplied producer metadata, never label order.
/// Route identity distinguishes two actual readers using the same model.
String? readerIdentity(Json observation) {
  String value(String key) => textOf(observation[key], '').trim();
  if (value('model_id').isEmpty && value('route_id').isEmpty) return null;
  return jsonEncode(<String>[
    value('route_id'),
    value('provider'),
    value('model_id'),
    value('provider_model_id'),
  ]);
}

/// Numbers are determined once from all supplied readers on this specimen.
/// Duplicate observations from one reader keep that reader's number.
Map<String, String> readerNames(Iterable<Json> observations) {
  final List<String> identities =
      observations.map(readerIdentity).whereType<String>().toSet().toList()
        ..sort();
  return <String, String>{
    for (final (int index, String identity) in identities.indexed)
      identity: 'VLM ${index + 1}',
  };
}
