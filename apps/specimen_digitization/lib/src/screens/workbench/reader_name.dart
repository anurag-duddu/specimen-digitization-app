/// The names a reader and a label region go by on the record screen, in the
/// Readings segment and the Fields segment alike (UI.md T2.2 and T2.3).
library;

import '../../models.dart';
import '../../thread/thread.dart';

/// What a reader is called when no reading names it.
const String unnamedReader = 'A reader';

/// The name the reader of [observationId] goes by: the model its reading
/// names, from the workspace or else from the thread.
String readerName(
  Specimen specimen,
  SpecimenThread? thread,
  String? observationId,
) {
  if (observationId == null) return unnamedReader;
  for (final Json o in specimen.observations) {
    if (textOf(o['id'], textOf(o['observation_id'], '')) == observationId) {
      return textOf(o['model_id'], unnamedReader);
    }
  }
  final ThreadReading? reading = thread?.readingOf(observationId);
  return reading?.model ?? reading?.routeId ?? unnamedReader;
}

/// The label region the reading [observationId] was read from, from the
/// workspace or else from the thread; null when neither says.
String? regionOfReading(
  Specimen specimen,
  SpecimenThread? thread,
  String? observationId,
) {
  if (observationId == null) return null;
  for (final Json o in specimen.observations) {
    if (textOf(o['id'], textOf(o['observation_id'], '')) == observationId) {
      final String region = textOf(o['region_id'], '');
      if (region.isNotEmpty) return region;
      break;
    }
  }
  return thread?.regions
      .where(
        (ThreadRegion r) => r.readings.any(
          (ThreadReading reading) => reading.observationId == observationId,
        ),
      )
      .firstOrNull
      ?.regionId;
}

/// The name the label region [regionId] goes by, "Label K", by its place
/// among the record's regions as the Readings sections number them, or else
/// among the thread's; null for a region neither lists.
String? labelName(Specimen specimen, SpecimenThread? thread, String? regionId) {
  if (regionId == null) return null;
  final int listed = specimen.regions.indexWhere(
    (Json region) => region['region_id'] == regionId,
  );
  if (listed >= 0) return 'Label ${listed + 1}';
  final int threaded =
      thread?.regions.indexWhere((ThreadRegion r) => r.regionId == regionId) ??
      -1;
  return threaded >= 0 ? 'Label ${threaded + 1}' : null;
}
