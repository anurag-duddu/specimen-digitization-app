import 'dart:convert';

import '../../models.dart';

/// A stable identity comes from supplied producer metadata, never label order.
/// Route identity distinguishes two actual readers using the same model.
String? readerIdentity(Json observation) {
  String value(String key) => textOf(observation[key], '').trim();
  if (value('model_id').isEmpty &&
      value('provider_model_id').isEmpty &&
      value('route_id').isEmpty) {
    return null;
  }
  return jsonEncode(<String>[
    value('route_id'),
    value('provider'),
    value('model_id'),
    value('provider_model_id'),
  ]);
}

/// Preserves both recorded model identifiers when the upstream name differs.
/// Neither a configured alias nor a version is inferred from another reading.
String readerModelName(Json observation) {
  final upstream = textOf(observation['provider_model_id'], '').trim();
  final model = textOf(observation['model_id'], '').trim();
  if (model.isEmpty) return upstream.isEmpty ? 'Model not recorded' : upstream;
  return upstream.isEmpty || upstream == model ? model : '$model · $upstream';
}

/// Names stay tied to their producer across labels and observation order.
/// Provider and route qualify a model only when they distinguish readers.
Map<String, String> readerNames(Iterable<Json> observations) {
  final readers = <String, Json>{};
  for (final observation in observations) {
    final identity = readerIdentity(observation);
    if (identity != null) readers.putIfAbsent(identity, () => observation);
  }
  final identities = readers.keys.toList()..sort();
  final names = <String, String>{
    for (final identity in identities)
      identity: readerModelName(readers[identity]!),
  };
  for (final qualifier in ['provider', 'route_id']) {
    final groups = <String, List<String>>{};
    for (final identity in identities) {
      groups.putIfAbsent(names[identity]!, () => []).add(identity);
    }
    for (final group in groups.values.where((group) => group.length > 1)) {
      String value(String identity) =>
          textOf(readers[identity]![qualifier], '').trim();
      if (group.map(value).toSet().length < 2) continue;
      for (final identity in group) {
        final detail = value(identity);
        if (detail.isNotEmpty) names[identity] = '${names[identity]} · $detail';
      }
    }
  }
  return names;
}

/// A verified model-family mark, independent of its hosting provider.
enum ReaderBrand {
  qwen3Vl('assets/reader-brands/qwen3-vl.png', 72),
  muse('assets/reader-brands/muse.png', 24);

  const ReaderBrand(this.asset, this.width);
  final String asset;
  final double width;
}

ReaderBrand? readerBrand(Json observation) {
  final brands = <ReaderBrand>{};
  for (final key in ['model_id', 'provider_model_id']) {
    final model = textOf(
      observation[key],
      '',
    ).trim().split('/').last.toLowerCase();
    if (model == 'qwen3-vl' || model.startsWith('qwen3-vl-')) {
      brands.add(ReaderBrand.qwen3Vl);
    }
    if (model == 'muse-glimmer' || model.startsWith('muse-glimmer-')) {
      brands.add(ReaderBrand.muse);
    }
  }
  return brands.length == 1 ? brands.single : null;
}
