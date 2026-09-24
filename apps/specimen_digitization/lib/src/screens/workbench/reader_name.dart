/// The name a reader goes by on the record screen, in the Readings segment
/// and the Fields segment alike (UI.md T2.2 and T2.3).
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
