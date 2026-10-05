/// One sentence for every domain word this client puts on a screen
/// (screen blueprints, section 10; pass criterion 10.2).
///
/// The criterion asks for a definition reachable *from where the term
/// appears*, not only from a help sheet a reviewer has to go and find. This
/// file is the text; `widgets/term_text.dart` is the affordance that puts it
/// one tap from the word.
///
/// Every key is the exact string the interface draws, because a definition
/// keyed on a wire value cannot be looked up from a screen that never shows
/// one. The vocabulary table in `vocabulary.dart` decides the words; this
/// decides what they mean.
library;

/// The definition of one term, or null when the word is not a domain term.
///
/// Case insensitive, and tolerant of a trailing count or value, so "Risk 62
/// of 100" finds "Risk".
String? glossaryDefinition(String term) {
  final String key = term.trim().toLowerCase();
  final String? exact = glossary[key];
  if (exact != null) return exact;
  // A headline such as "Risk 62 of 100" is the term plus a measurement.
  final int space = key.indexOf(' ');
  if (space <= 0) return null;
  return glossary[key.substring(0, space)];
}

/// True when [term] has a definition to show.
bool isGlossaryTerm(String term) => glossaryDefinition(term) != null;

/// Every domain word, lower case, with one sentence each.
///
/// One sentence, because a definition a reviewer will not finish is a
/// definition a reviewer will not read (UX writing, section 8.2).
const Map<String, String> glossary = <String, String>{
  // Intake and sources.
  'source':
      'Storage an administrator registered for this collection, holding '
      'photographs it may add without uploading them again.',
  'sources':
      'Storage an administrator registered for this collection, holding '
      'photographs it may add without uploading them again.',
  // Queue dispositions and operational states.
  'cleared':
      'A reviewer affirmed this record, and it is recorded against the '
      'version they affirmed.',
  'needs review':
      'The server will not clear this record without a person, and the '
      'blockers list says what it is waiting for.',
  'deferred':
      'A reviewer shelved this record for later, without judging the '
      'specimen.',
  'processing':
      'Work is running on this record now, which is never a final queue.',
  'processing blocked':
      'Processing stopped before it finished, which is an operational fault '
      'rather than a finding about the specimen.',
  'retry scheduled':
      'Processing stopped and will try again on its own at the time shown, '
      'which is an operational fault rather than a finding about the '
      'specimen.',
  'paused':
      'Processing is paused on this record, which stops the run without '
      'saying anything about the specimen.',
  'cancelled':
      'Processing was cancelled on this record, which ends the run without '
      'saying anything about the specimen.',
  'state unknown':
      'The server reported a state this client has no treatment for, so it '
      'is shown rather than hidden.',

  // Field states.
  'supported': 'The evidence on this record supports this value.',
  'unknown': 'Nobody has established this value, and nothing claims one.',
  'unreadable': 'The pixels for this field could not be read.',
  'not present': 'The label does not carry this field at all.',
  'not applicable': 'This field does not apply to this specimen.',
  'ambiguous': 'More than one reading of this field is defensible.',
  'unresolved': 'Two readings conflict and no rule settles which is right.',
  'not recorded': 'Nothing was recorded here, which is a value, not a blank.',
  'not measured':
      'The measurement was not taken or not completed, so no number is '
      'shown in place of one.',
  'not calibrated':
      'The policy behind this score has not been calibrated, so the number '
      'orders the queue and proves nothing.',

  // The three layers of a field value.
  'as written':
      'The transcription of what the pixels say, verbatim, with nothing '
      'corrected.',
  'read as': 'What the transcription means, in prose, after interpretation.',
  'standardized':
      'The value after the collection standard was applied to the '
      'interpretation.',

  // Evidence and provenance.
  'risk':
      'A score out of one hundred that orders the queue, not a probability '
      'that the record is wrong.',
  'reading': 'One model transcription of one region of the photograph.',
  'provider': 'The service that ran the model which produced this reading.',
  'authority':
      'An external reference file a standardized value was matched against.',
  'label region':
      'A rectangle on the photograph that the label detection step found.',
  'region': 'A rectangle on the photograph that one reading was taken from.',
  'version':
      'The record revision a decision is recorded against, superseded by a '
      'later version rather than removed.',
  'run': 'One pass of the processing pipeline over this record.',
  'step': 'Where the current run had reached when it last reported.',
  'coverage': 'Whether every label region on the photograph has been read.',
  'blocks clearance':
      'A finding the server will not let the record be cleared with.',
  'worth checking':
      'A finding that does not block clearance but a reviewer should look '
      'at.',
  'already in collection':
      'The server matched this upload to a specimen the collection already '
      'holds.',
  'test data':
      'Fixtures produced for testing, not real processing and not approved '
      'museum records.',
};
