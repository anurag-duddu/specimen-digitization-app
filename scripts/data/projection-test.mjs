// Synthetic-only projection operations test (docs/execution/golive/DATA_CONTRACT.md).
// Never contacts a cloud endpoint.
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
const host = process.env.FIREBASE_DATACONNECT_EMULATOR_HOST || '127.0.0.1:9499';
assert.match(host, /^(127\.0\.0\.1|localhost):\d+$/);
const base = `http://${host}/v1/projects/demo-specimen-data/locations/us-east4/services/specimen-digitization-service`;
async function call(path, body) {
  const response = await fetch(base + path, {method:'POST', headers:{'Content-Type':'application/json', 'Authorization':'Bearer owner'}, body:JSON.stringify(body)});
  return response.json();
}
const raw = query => call(':executeGraphql', {query});
const op = (operationName, variables) => call('/connectors/specimen-server:impersonateMutation', {operationName, variables, extensions: {}});
const query = (operationName, variables) => call('/connectors/specimen-server:impersonateQuery', {operationName, variables, extensions: {}});
function ok(r) { assert.ok(!r.errors?.length && !r.code, JSON.stringify(r)); return r.data; }
function denied(r) { assert.ok(r.errors?.length || r.code, JSON.stringify(r)); return r; }
function conflict(r, constraint) {
  denied(r);
  assert.equal(r.errors?.[0]?.extensions?.code, 'ALREADY_EXISTS', JSON.stringify(r));
  assert.match(r.errors[0].message, new RegExp(constraint), JSON.stringify(r));
}
const hex = c => c.repeat(64);
// Data Connect returns UUID fields without dashes; compare both sides in that form.
const bare = value => JSON.parse(JSON.stringify(value).replace(/\b([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})\b/g, '$1$2$3$4$5'));
const same = (actual, expected) => assert.deepEqual(bare(actual), bare(expected));
// A pair of readings in its fixed order. Inside a @check a UUID variable is lowercase hex without
// dashes, and randomUUID's lowercase form sorts the same way.
const pair = (a, b) => { const [left, right] = [a, b].sort(); return {leftObservationId: left, rightObservationId: right}; };

const org = randomUUID(), coll = randomUUID(), otherColl = randomUUID(), open = randomUUID(), closed = randomUUID(), idle = randomUUID(), undated = randomUUID(), other = randomUUID();
const ties = [randomUUID(), randomUUID(), randomUUID()].sort();
const tie = '2026-01-03T00:00:00.123456Z';
// Sorts after every random id, so due-time order and id order disagree.
const early = 'ffffffff-ffff-4fff-bfff-' + randomUUID().slice(-12);
// Each specimen with a chain has its own source checksum, unique per collection; an original must match it.
const checksum = {[open]: hex('1'), [closed]: hex('2'), [other]: hex('3')};
const sc = `organizationId:"${org}",collectionId:"${coll}"`;
ok(await raw(`mutation @transaction {
 o: organization_insert(data:{id:"${org}",name:"Synthetic museum"})
 c1: collection_insert(data:{organizationId:"${org}",id:"${coll}",name:"Synthetic insects"})
 c2: collection_insert(data:{organizationId:"${org}",id:"${otherColl}",name:"Other synthetic collection"})
 m1: organizationMember_insert(data:{organizationId:"${org}",uid:"worker",active:true})
 m2: organizationMember_insert(data:{organizationId:"${org}",uid:"reviewer",active:true})
 m3: organizationMember_insert(data:{organizationId:"${org}",uid:"viewer",active:true})
 cm1: collectionMember_insert(data:{${sc},uid:"worker",active:true,role:"operator",canViewSensitive:false})
 cm2: collectionMember_insert(data:{${sc},uid:"reviewer",active:true,role:"reviewer",canViewSensitive:true})
 cm3: collectionMember_insert(data:{${sc},uid:"viewer",active:true,role:"viewer",canViewSensitive:true})
 cm4: collectionMember_insert(data:{organizationId:"${org}",collectionId:"${otherColl}",uid:"reviewer",active:true,role:"reviewer",canViewSensitive:true})
 s1: specimen_insert(data:{${sc},id:"${open}",revision:1,state:"running",sensitive:false,createdBy:"worker",workAvailableAt:"2026-01-02T00:00:00Z",sourceChecksum:"${checksum[open]}"})
 s2: specimen_insert(data:{${sc},id:"${closed}",revision:2,state:"running",sensitive:true,createdBy:"reviewer",workAvailableAt:"2026-01-01T00:00:00Z",sourceChecksum:"${checksum[closed]}"})
 s3: specimen_insert(data:{${sc},id:"${idle}",revision:1,state:"completed",sensitive:false,createdBy:"worker",workAvailableAt:"2026-01-01T00:00:00Z"})
 s4: specimen_insert(data:{${sc},id:"${early}",revision:1,state:"pending",sensitive:false,createdBy:"worker",workAvailableAt:"2026-01-01T00:00:00Z"})
 s5: specimen_insert(data:{${sc},id:"${undated}",revision:1,state:"running",sensitive:false,createdBy:"worker"})
 s6: specimen_insert(data:{${sc},id:"${other}",revision:1,state:"completed",sensitive:false,createdBy:"worker",sourceChecksum:"${checksum[other]}"})
 t0: specimen_insert(data:{${sc},id:"${ties[0]}",revision:1,state:"running",sensitive:false,createdBy:"worker",workAvailableAt:"${tie}"})
 t1: specimen_insert(data:{${sc},id:"${ties[1]}",revision:1,state:"running",sensitive:false,createdBy:"worker",workAvailableAt:"${tie}"})
 t2: specimen_insert(data:{${sc},id:"${ties[2]}",revision:1,state:"running",sensitive:false,createdBy:"worker",workAvailableAt:"${tie}"})
}`));
const scope = {organizationId: org, collectionId: coll};
const profileId = randomUUID();
ok(await op('AppendProfileVersionV2', {...scope, actorUid: 'worker', id: profileId, profileKey: 'zoology_insects_slides', version: '1.0.0', configObject: '{}', configSha256: hex('c'), approvedBy: null}));
denied(await op('AppendProfileVersionV2', {...scope, actorUid: 'viewer', id: randomUUID(), profileKey: 'k', version: '1', configObject: '{}', configSha256: hex('c'), approvedBy: null}));

// The whole chain of one run, in foreign-key order. Returns the variables of every write.
async function chain(specimenId, actorUid) {
  const v = {...scope, actorUid};
  const id = () => randomUUID();
  const w = {};
  w.original = {...v, id: id(), specimenId, kind: 'original', parentAssetId: null, bucket: 'demo-specimen-data.appspot.com', objectName: `application/sha256/${randomUUID()}`, generation: '1', sha256: checksum[specimenId], mimeType: 'image/png', byteSize: '4', width: 4000, height: 3000, acquisitionMethod: 'source_import', uploaderUid: actorUid};
  w.envelope = {...w.original, id: id(), kind: 'raw_response', parentAssetId: null, objectName: `application/sha256/${randomUUID()}`, sha256: hex('9'), mimeType: 'application/json', width: null, height: null, acquisitionMethod: 'model_response'};
  w.placeRecord = {...w.envelope, id: id(), kind: 'evidence_record', objectName: `application/sha256/${randomUUID()}`, sha256: hex('8'), acquisitionMethod: 'lookup'};
  w.run = {...v, id: id(), specimenId, profileVersionId: profileId, supersedesRunId: null, pinnedVersions: {segmentation: {model_revision: 'fixture', settings: {concept_prompt: 'label'}}}, inputSha256: hex('a'), traceId: null};
  w.region = {...v, id: id(), runId: w.run.id, domainRegionId: randomUUID(), sourceAssetId: w.original.id, cropAssetId: null, geometry: {bbox: [10, 20, 400, 180]}, ordinal: 0, regionType: 'label', segmentationVersion: 'fixture', supersedesRegionId: null};
  const reading = (route, text) => ({...v, id: id(), runId: w.run.id, regionId: w.region.id, rawAssetId: w.envelope.id, stepKey: `transcribe:${w.region.domainRegionId}:${route}`, provider: 'fixture', modelVersion: route, promptVersion: 'p1', inputSha256: hex('b'), parameters: {}, literalText: text, outcome: 'stop', independent: true, routeId: route, unreadableSpans: []});
  w.left = reading('handwriting-qwen', 'Chicago, Ill.');
  w.right = {...reading('handwriting-muse', 'Chicago, Il1.'), unreadableSpans: ['Il1.']};
  w.third = reading('handwriting-third', 'Chicago, Ill.');
  w.firstPassCall = {...reading('first-pass', 'Chicago, Ill.'), stepKey: `first_pass:${w.region.domainRegionId}`, independent: false};
  w.comparison = {...v, id: id(), runId: w.run.id, regionId: w.region.id, ...pair(w.left.id, w.right.id), algorithm: 'bounded-levenshtein-fraction-v1', ratio: 1 / 13, editDistance: 1, lengthBasis: 13, status: 'difference', reasons: []};
  w.transcription = {...v, id: id(), runId: w.run.id, literalText: w.left.literalText, spans: [], alternatives: [w.left.literalText, w.right.literalText], unresolved: false, regionId: w.region.id, decisionKind: 'first_pass', selectedObservationId: w.left.id, firstPassObservationId: w.firstPassCall.id, rationale: 'The crop shows a lowercase l.'};
  w.decided = {...v, id: id(), runId: w.run.id, transcriptionVersionId: w.transcription.id, observationId: w.left.id, role: 'decided_transcript', handedText: w.left.literalText, note: null};
  w.evidence = {...v, id: id(), runId: w.run.id, source: 'google-maps-geocoding', sourceVersion: 'v1', adapterVersion: 'a1', query: {address: 'Chicago, Ill.'}, outcome: 'success', locator: 'place/fixture-place', responseSha256: hex('e'), capturedAt: '2026-09-23T12:00:00Z', rawAssetId: w.placeRecord.id};
  w.toolCall = {...v, id: id(), runId: w.run.id, callKey: `lookup:geocode:decided_transcript:${w.region.domainRegionId}:-:0af70af70af70af7:1`, phase: 'lookup', tool: 'geocode', toolVersion: 't1', source: 'google-maps-geocoding', fieldKeys: ['country', 'province_state', 'county', 'city'], inputSource: 'decided_transcript', transcriptionVersionId: w.transcription.id, observationId: null, attempt: 1, arguments: {query: 'Chicago, Ill.'}, outcome: 'success', result: {candidates: [{place_id: 'fixture-place'}]}, evidenceId: w.evidence.id, startedAt: '2026-09-23T12:00:00Z', completedAt: '2026-09-23T12:00:01Z'};
  w.candidate = {...v, id: id(), runId: w.run.id, fieldKey: 'city', state: 'supported', literalValue: 'Chicago', parsedValue: null, normalizedValue: null, authorityId: 'fixture-place', derivation: 'literal', inputSource: 'decided_transcript', sourceTranscriptionId: w.transcription.id, sourceObservationId: null};
  w.link = {...v, id: id(), candidateId: w.candidate.id, evidenceId: w.evidence.id, relation: 'supports'};
  w.record = {...v, id: id(), runId: w.run.id, predecessorId: null, disposition: 'needs_human_review', policyVersion: 'insects-clearance-v1', reasonCodes: ['mandatory_unresolved:county'], summary: 'mandatory_unresolved:county'};
  w.resolved = {...v, id: id(), recordVersionId: w.record.id, candidateId: w.candidate.id, fieldKey: 'city', state: 'supported', fieldGroup: 'mandatory'};
  w.finding = {...v, id: id(), recordVersionId: w.record.id, runId: w.run.id, evidenceIds: null, ruleId: 'mandatory_unresolved', ruleVersion: 'insects-clearance-v1', severity: 'hard', outcome: 'fail', fieldKey: 'county', reasonCode: 'mandatory_unresolved:county'};
  w.checkpoint = {...v, id: id(), runId: w.run.id, stepKey: 'lookup', inputSha256: hex('f'), state: 'completed', attempt: 1, nextRetryAt: null, blockerCode: null, outputReferences: {}};
  return w;
}
const writes = [
  ['AppendSourceAssetV2', 'original'], ['AppendSourceAssetV2', 'envelope'], ['AppendSourceAssetV2', 'placeRecord'], ['AppendPipelineRunV2', 'run'],
  ['AppendLabelRegionV2', 'region'], ['AppendModelObservationV2', 'left'], ['AppendModelObservationV2', 'right'], ['AppendModelObservationV2', 'third'],
  ['AppendModelObservationV2', 'firstPassCall'], ['AppendReadingComparisonV1', 'comparison'],
  ['AppendTranscriptionVersionV2', 'transcription'], ['AppendHarnessInputV1', 'decided'],
  ['AppendEvidenceItemV2', 'evidence'], ['AppendToolCallV1', 'toolCall'], ['AppendFieldCandidateV2', 'candidate'],
  ['AppendCandidateEvidenceV2', 'link'], ['AppendRecordVersionV2', 'record'], ['AppendResolvedFieldV2', 'resolved'],
  ['AppendValidationFindingV2', 'finding'], ['AppendCheckpointV2', 'checkpoint'],
];
async function writeAll(w) { for (const [name, key] of writes) ok(await op(name, w[key])); }

// The worker writes a non-sensitive specimen's whole run.
const work = await chain(open, 'worker');
await writeAll(work);
const thread = ok(await raw(`query {
 pipelineRun(key:{${sc},id:"${work.run.id}"}) { specimenId traceId }
 labelRegions(where:{runId:{eq:"${work.run.id}"}}) { domainRegionId sourceAssetId cropAssetId }
 modelObservations(where:{runId:{eq:"${work.run.id}"}}, orderBy:{stepKey:ASC}) { stepKey independent literalText routeId unreadableSpans }
 readingComparisons(where:{runId:{eq:"${work.run.id}"}}) { ratio editDistance lengthBasis leftObservationId rightObservationId }
 transcriptionVersions(where:{runId:{eq:"${work.run.id}"}}) { regionId decisionKind selectedObservationId firstPassObservationId }
 harnessInputs(where:{runId:{eq:"${work.run.id}"}}, orderBy:{role:ASC}) { role handedText observationId }
 toolCalls(where:{runId:{eq:"${work.run.id}"}}) { callKey source fieldKeys outcome inputSource evidenceId attempt }
 fieldCandidates(where:{runId:{eq:"${work.run.id}"}}) { inputSource sourceTranscriptionId }
 resolvedFields(where:{recordVersionId:{eq:"${work.record.id}"}}) { fieldKey fieldGroup }
 sourceAssets(where:{specimenId:{eq:"${open}"},kind:{eq:"raw_response"}}) { width height }
}`));
same(thread.pipelineRun.specimenId, open);
same(thread.labelRegions, [{domainRegionId: work.region.domainRegionId, sourceAssetId: work.original.id, cropAssetId: null}]);
same(thread.modelObservations.map(o => [o.independent, o.routeId, o.unreadableSpans]), [[false, 'first-pass', []], [true, 'handwriting-muse', ['Il1.']], [true, 'handwriting-qwen', []], [true, 'handwriting-third', []]]);
same([thread.readingComparisons[0].ratio, thread.readingComparisons[0].editDistance, thread.readingComparisons[0].lengthBasis], [1 / 13, 1, 13]);
same(thread.transcriptionVersions, [{regionId: work.region.id, decisionKind: 'first_pass', selectedObservationId: work.left.id, firstPassObservationId: work.firstPassCall.id}]);
same(thread.harnessInputs.map(h => [h.role, h.observationId]), [['decided_transcript', work.left.id]]);
same(thread.toolCalls, [{callKey: work.toolCall.callKey, source: 'google-maps-geocoding', fieldKeys: ['country', 'province_state', 'county', 'city'], outcome: 'success', inputSource: 'decided_transcript', evidenceId: work.evidence.id, attempt: 1}]);
same(thread.fieldCandidates, [{inputSource: 'decided_transcript', sourceTranscriptionId: work.transcription.id}]);
same(thread.resolvedFields, [{fieldKey: 'city', fieldGroup: 'mandatory'}]);
same(thread.sourceAssets, [{width: null, height: null}]);
console.log('PASS the worker writes a whole non-sensitive run, linked to its specimen, image and run');

// A replay hits the primary key; a second row for the same natural key hits its unique constraint.
conflict(await op('AppendToolCallV1', work.toolCall), 'tool_call_pkey');
conflict(await op('AppendToolCallV1', {...work.toolCall, id: randomUUID()}), 'tool_call_key');
conflict(await op('AppendHarnessInputV1', {...work.decided, id: randomUUID()}), 'harness_input_reader');
conflict(await op('AppendReadingComparisonV1', {...work.comparison, id: randomUUID()}), 'reading_comparison_pair');
console.log('PASS replays are primary-key conflicts and natural-key duplicates are refused');

// The trace id is recorded once, in the W3C format.
const trace = '0af7'.repeat(8);
const record = traceId => op('RecordRunTraceV1', {...scope, actorUid: 'worker', id: work.run.id, traceId});
denied(await record('0'.repeat(32)));
denied(await record(trace.toUpperCase()));
ok(await record(trace));
ok(await record(trace));
denied(await record('f'.repeat(32)));
denied(await op('RecordRunTraceV1', {...scope, actorUid: 'worker', id: randomUUID(), traceId: trace}));
assert.equal(ok(await raw(`query { pipelineRun(key:{${sc},id:"${work.run.id}"}) { traceId } }`)).pipelineRun.traceId, trace);
const traced = await chain(open, 'worker');
ok(await op('AppendSourceAssetV2', traced.original));
denied(await op('AppendPipelineRunV2', {...traced.run, traceId: 'not-a-trace'}));
ok(await op('AppendPipelineRunV2', {...traced.run, traceId: trace}));
const race = await chain(open, 'worker');
ok(await op('AppendSourceAssetV2', race.original));
ok(await op('AppendPipelineRunV2', race.run));
const contenders = ['1a2b'.repeat(8), '3c4d'.repeat(8)];
const raced = await Promise.all(contenders.map(traceId => op('RecordRunTraceV1', {...scope, actorUid: 'worker', id: race.run.id, traceId})));
assert.equal(raced.filter(r => !r.errors?.length && !r.code).length, 1, JSON.stringify(raced));
const winner = ok(await raw(`query { pipelineRun(key:{${sc},id:"${race.run.id}"}) { traceId } }`)).pipelineRun.traceId;
assert.ok(contenders.includes(winner));
console.log('PASS the trace id is recorded once, well formed, and of two concurrent ids exactly one wins');

// An approval claim needs a reviewer or above with sensitive access; the worker writes none.
const profile = {...scope, profileKey: 'zoology_insects_slides', version: '1.0.1', configObject: '{}', configSha256: hex('c')};
denied(await op('AppendProfileVersionV2', {...profile, actorUid: 'worker', id: randomUUID(), approvedBy: 'worker'}));
ok(await op('AppendProfileVersionV2', {...profile, actorUid: 'reviewer', id: randomUUID(), approvedBy: 'reviewer'}));
console.log('PASS only a sensitive-capable reviewer may claim a profile approval');

// Closed vocabularies and image dimensions are enforced.
denied(await op('AppendHarnessInputV1', {...work.decided, id: randomUUID(), observationId: work.firstPassCall.id, role: 'decided'}));
denied(await op('AppendToolCallV1', {...work.toolCall, id: randomUUID(), callKey: 'x', inputSource: 'decided'}));
denied(await op('AppendToolCallV1', {...work.toolCall, id: randomUUID(), callKey: 'y', attempt: 0}));
denied(await op('AppendToolCallV1', {...work.toolCall, id: randomUUID(), callKey: 'z', outcome: 'unavailable'}));
denied(await op('AppendHarnessInputV1', {...work.decided, id: randomUUID(), observationId: work.firstPassCall.id, handedText: null}));
denied(await op('AppendTranscriptionVersionV2', {...work.transcription, id: randomUUID(), decisionKind: 'llm'}));
denied(await op('AppendFieldCandidateV2', {...work.candidate, id: randomUUID(), inputSource: 'raw'}));
denied(await op('AppendResolvedFieldV2', {...work.resolved, id: randomUUID(), fieldGroup: 'required'}));
denied(await op('AppendReadingComparisonV1', {...work.comparison, id: randomUUID(), ...pair(work.left.id, work.third.id), editDistance: -1}));
denied(await op('AppendReadingComparisonV1', {...work.comparison, id: randomUUID(), ...pair(work.left.id, work.third.id), lengthBasis: 0}));
denied(await op('AppendReadingComparisonV1', {...work.comparison, id: randomUUID(), leftObservationId: work.comparison.rightObservationId, rightObservationId: work.comparison.leftObservationId}));
denied(await op('AppendReadingComparisonV1', {...work.comparison, id: randomUUID(), ...pair(work.left.id, work.firstPassCall.id)}));
denied(await op('AppendToolCallV1', {...work.toolCall, id: randomUUID(), callKey: randomUUID(), phase: 'lookups'}));
denied(await op('AppendToolCallV1', {...work.toolCall, id: randomUUID(), callKey: randomUUID(), observationId: work.left.id}));
denied(await op('AppendCandidateEvidenceV2', {...work.link, id: randomUUID(), relation: 'agrees'}));
denied(await op('AppendValidationFindingV2', {...work.finding, id: randomUUID(), severity: 'fatal'}));
denied(await op('AppendValidationFindingV2', {...work.finding, id: randomUUID(), outcome: 'failed'}));
denied(await op('AppendValidationFindingV2', {...work.finding, id: randomUUID(), evidenceIds: [work.evidence.id, work.evidence.id]}));
ok(await op('AppendValidationFindingV2', {...work.finding, id: randomUUID(), severity: 'warning', ruleId: 'taxonomy_source_disagreement', fieldKey: 'taxon', reasonCode: 'taxonomy_source_disagreement'}));
// A decision other than a reviewer's is unresolved exactly when it selects no reading, and only a
// first-pass decision names a model call.
denied(await op('AppendTranscriptionVersionV2', {...work.transcription, id: randomUUID(), firstPassObservationId: null}));
denied(await op('AppendTranscriptionVersionV2', {...work.transcription, id: randomUUID(), selectedObservationId: null, unresolved: false}));
denied(await op('AppendTranscriptionVersionV2', {...work.transcription, id: randomUUID(), unresolved: true}));
denied(await op('AppendTranscriptionVersionV2', {...work.transcription, id: randomUUID(), decisionKind: 'identical_readings'}));
// A decided transcript is the decision's selected reading; raw readings are handed only without one.
denied(await op('AppendHarnessInputV1', {...work.decided, id: randomUUID(), observationId: work.right.id, handedText: work.right.literalText}));
denied(await op('AppendHarnessInputV1', {...work.decided, id: randomUUID(), observationId: work.right.id, role: 'raw_reading', handedText: work.right.literalText}));
denied(await op('AppendSourceAssetV2', {...work.original, id: randomUUID(), objectName: randomUUID(), kind: 'originals'}));
denied(await op('AppendSourceAssetV2', {...work.original, id: randomUUID(), objectName: randomUUID(), width: 0}));
denied(await op('AppendSourceAssetV2', {...work.original, id: randomUUID(), objectName: randomUUID(), width: null}));
denied(await op('AppendSourceAssetV2', {...work.original, id: randomUUID(), objectName: randomUUID(), sha256: hex('d')}));
denied(await op('AppendLabelRegionV2', {...work.region, id: randomUUID(), domainRegionId: null}));
denied(await op('AppendReadingComparisonV1', {...work.comparison, id: randomUUID(), rightObservationId: work.comparison.leftObservationId}));
denied(await op('AppendEvidenceItemV2', {...work.evidence, id: randomUUID(), outcome: 'found'}));
ok(await op('AppendFieldCandidateV2', {...work.candidate, id: randomUUID(), derivation: 'human', inputSource: null, sourceTranscriptionId: null}));
console.log('PASS closed vocabularies, decisions, handoff roles, the fixed pair order, image dimensions and the original checksum are enforced');

// Google keeps a place id only for a single match, points at an evidence record, and supports (G26).
denied(await op('AppendEvidenceItemV2', {...work.evidence, id: randomUUID(), locator: 'lookup/1'}));
denied(await op('AppendEvidenceItemV2', {...work.evidence, id: randomUUID(), locator: 'place/41.8781,-87.6298'}));
denied(await op('AppendEvidenceItemV2', {...work.evidence, id: randomUUID(), locator: 'place/Chicago, IL'}));
denied(await op('AppendEvidenceItemV2', {...work.evidence, id: randomUUID(), locator: null}));
denied(await op('AppendEvidenceItemV2', {...work.evidence, id: randomUUID(), outcome: 'ambiguous'}));
denied(await op('AppendEvidenceItemV2', {...work.evidence, id: randomUUID(), source: 'Google-Maps-Geocoding'}));
denied(await op('AppendEvidenceItemV2', {...work.evidence, id: randomUUID(), rawAssetId: work.envelope.id}));
const noMatch = {...work.evidence, id: randomUUID(), outcome: 'no_match', locator: null};
ok(await op('AppendEvidenceItemV2', noMatch));
denied(await op('AppendCandidateEvidenceV2', {...work.link, id: randomUUID(), evidenceId: noMatch.id}));
denied(await op('AppendCandidateEvidenceV2', {...work.link, id: randomUUID(), relation: 'decides'}));
const elsewhere = {...work.candidate, id: randomUUID(), authorityId: 'another-place'};
ok(await op('AppendFieldCandidateV2', elsewhere));
denied(await op('AppendCandidateEvidenceV2', {...work.link, id: randomUUID(), candidateId: elsewhere.id}));
ok(await op('AppendCandidateEvidenceV2', {...work.link, id: randomUUID(), relation: 'contradicts'}));
console.log('PASS Google evidence keeps a place id only for a single match, points at an evidence record, and never decides');

// Sensitive specimens: a sensitive-capable reviewer writes the run; the worker and a viewer cannot.
const kept = await chain(closed, 'reviewer');
await writeAll(kept);
// Each write is refused for the worker, then the same write succeeds for the reviewer.
const created = {};
for (const [name, key] of writes) {
  const variables = {...kept[key], id: randomUUID(), actorUid: 'worker'};
  if ('callKey' in variables) variables.callKey = randomUUID();
  if ('stepKey' in variables) variables.stepKey = randomUUID();
  if ('objectName' in variables) variables.objectName = randomUUID();
  if (name === 'AppendHarnessInputV1') variables.transcriptionVersionId = created.transcription;
  if (name === 'AppendReadingComparisonV1') Object.assign(variables, pair(kept.left.id, kept.third.id));
  denied(await op(name, variables));
  ok(await op(name, {...variables, actorUid: 'reviewer'}));
  created[key] = variables.id;
}
denied(await op('RecordRunTraceV1', {...scope, actorUid: 'worker', id: kept.run.id, traceId: trace}));
ok(await op('RecordRunTraceV1', {...scope, actorUid: 'reviewer', id: kept.run.id, traceId: trace}));
ok(await op('AppendReviewDecisionV1', {...scope, actorUid: 'reviewer', id: randomUUID(), specimenId: closed, baseRevision: 1, resultingRevision: 2, reason: 'Checked the label', correction: {kind: 'field', target_id: 'county', after: {literal: 'Cook'}}}));
denied(await op('AppendReviewDecisionV1', {...scope, actorUid: 'reviewer', id: randomUUID(), specimenId: closed, baseRevision: 2, resultingRevision: 3, reason: 'r', correction: {}}));
denied(await op('AppendReviewDecisionV1', {...scope, actorUid: 'worker', id: randomUUID(), specimenId: open, baseRevision: 0, resultingRevision: 1, reason: 'r', correction: {}}));
denied(await op('AppendModelObservationV2', {...work.left, id: randomUUID(), stepKey: randomUUID(), actorUid: 'viewer'}));
console.log('PASS sensitive runs need a sensitive-capable member; review decisions need a reviewer and stay within the specimen\'s revision');

// Every parent a row names belongs to the row's own run, or to its specimen for assets.
const b = await chain(other, 'worker');
await writeAll(b);
const rid = () => randomUUID();
// A second region of the same run, with a reading of its own.
const second = {...work.region, id: rid(), domainRegionId: rid(), ordinal: 1};
ok(await op('AppendLabelRegionV2', second));
const secondReading = {...work.left, id: rid(), stepKey: rid(), regionId: second.id};
ok(await op('AppendModelObservationV2', secondReading));
const crossings = [
  ['AppendSourceAssetV2', {...work.envelope, id: rid(), objectName: rid(), parentAssetId: b.original.id}],
  ['AppendPipelineRunV2', {...work.run, id: rid(), supersedesRunId: b.run.id}],
  ['AppendLabelRegionV2', {...work.region, id: rid(), sourceAssetId: b.original.id}],
  ['AppendLabelRegionV2', {...work.region, id: rid(), cropAssetId: kept.original.id}],
  ['AppendLabelRegionV2', {...work.region, id: rid(), supersedesRegionId: b.region.id}],
  ['AppendModelObservationV2', {...work.left, id: rid(), stepKey: rid(), regionId: b.region.id}],
  ['AppendModelObservationV2', {...work.left, id: rid(), stepKey: rid(), rawAssetId: kept.envelope.id}],
  ['AppendReadingComparisonV1', {...work.comparison, id: rid(), regionId: b.region.id}],
  ['AppendReadingComparisonV1', {...work.comparison, id: rid(), ...pair(work.left.id, b.third.id)}],
  ['AppendReadingComparisonV1', {...work.comparison, id: rid(), ...pair(work.left.id, secondReading.id)}],
  ['AppendTranscriptionVersionV2', {...work.transcription, id: rid(), regionId: b.region.id}],
  ['AppendTranscriptionVersionV2', {...work.transcription, id: rid(), selectedObservationId: b.left.id}],
  ['AppendTranscriptionVersionV2', {...work.transcription, id: rid(), firstPassObservationId: b.firstPassCall.id}],
  ['AppendTranscriptionVersionV2', {...work.transcription, id: rid(), selectedObservationId: secondReading.id}],
  ['AppendHarnessInputV1', {...work.decided, id: rid(), transcriptionVersionId: b.transcription.id}],
  ['AppendHarnessInputV1', {...work.decided, id: rid(), observationId: b.left.id}],
  ['AppendHarnessInputV1', {...work.decided, id: rid(), observationId: secondReading.id}],
  ['AppendEvidenceItemV2', {...work.evidence, id: rid(), rawAssetId: kept.placeRecord.id}],
  ['AppendToolCallV1', {...work.toolCall, id: rid(), callKey: rid(), transcriptionVersionId: b.transcription.id}],
  ['AppendToolCallV1', {...work.toolCall, id: rid(), callKey: rid(), evidenceId: b.evidence.id}],
  ['AppendToolCallV1', {...work.toolCall, id: rid(), callKey: rid(), inputSource: 'raw_reading', transcriptionVersionId: null, observationId: b.left.id}],
  ['AppendFieldCandidateV2', {...work.candidate, id: rid(), sourceTranscriptionId: b.transcription.id}],
  ['AppendFieldCandidateV2', {...work.candidate, id: rid(), inputSource: 'raw_reading', sourceTranscriptionId: null, sourceObservationId: b.left.id}],
  ['AppendCandidateEvidenceV2', {...work.link, id: rid(), evidenceId: b.evidence.id}],
  ['AppendRecordVersionV2', {...work.record, id: rid(), predecessorId: b.record.id}],
  ['AppendResolvedFieldV2', {...work.resolved, id: rid(), candidateId: b.candidate.id}],
  ['AppendResolvedFieldV2', {...work.resolved, id: rid(), fieldKey: 'county'}],
  ['AppendValidationFindingV2', {...work.finding, id: rid(), runId: b.run.id}],
  ['AppendValidationFindingV2', {...work.finding, id: rid(), evidenceIds: [b.evidence.id]}],
];
for (const [name, variables] of crossings) denied(await op(name, variables));
ok(await op('AppendRecordVersionV2', {...work.record, id: rid(), predecessorId: work.record.id}));
ok(await op('AppendToolCallV1', {...work.toolCall, id: rid(), callKey: rid(), inputSource: 'raw_reading', transcriptionVersionId: null, observationId: work.right.id}));
console.log('PASS parents of another run or specimen, sensitive ones included, and readings of another region are refused');

// SourceAsset's object uniqueness becomes per specimen in two applies (DATA_CONTRACT.md 3.3). This is
// step 1: the per-specimen constraint is declared beside specimen_unique_1, which still refuses a second
// specimen's row for one stored object until T2a drops it.
const stored = {objectName: `application/sha256/${rid()}`, generation: '7'};
ok(await op('AppendSourceAssetV2', {...work.envelope, id: rid(), ...stored}));
conflict(await op('AppendSourceAssetV2', {...b.envelope, id: rid(), ...stored}), 'specimen_unique_1');
if (process.env.PSQL_BIN) {
  const {execFileSync} = await import('node:child_process');
  assert.match(process.env.SPECIMEN_TEST_PG_PORT, /^\d+$/);
  const sql = "SELECT indexname || ' ' || regexp_replace(indexdef, '^.* USING btree ', '') FROM pg_indexes WHERE tablename = 'source_asset' AND indexdef LIKE 'CREATE UNIQUE%' AND indexname <> 'source_asset_pkey' ORDER BY 1";
  const unique = execFileSync(process.env.PSQL_BIN, ['-h', '127.0.0.1', '-p', process.env.SPECIMEN_TEST_PG_PORT, '-d', 'specimen-digitization-database', '-qAt', '-v', 'ON_ERROR_STOP=1', '-c', sql], {encoding: 'utf8'}).trim().split('\n');
  assert.deepEqual(unique, ['source_asset_specimen_object (organization_id, collection_id, specimen_id, bucket, object_name, generation)', 'specimen_unique_1 (bucket, object_name, generation)']);
}
console.log('PASS step 1 of per-specimen object uniqueness: both constraints exist, and specimen_unique_1 still governs');

// The writes the pipeline makes are accepted.
const again = {...work.run, id: rid(), supersedesRunId: work.run.id, traceId: null};
ok(await op('AppendPipelineRunV2', again));
ok(await op('AppendLabelRegionV2', {...work.region, id: rid(), runId: again.id}));
ok(await op('AppendLabelRegionV2', {...work.region, id: rid(), domainRegionId: rid(), supersedesRegionId: work.region.id}));
const crop = {...work.original, id: rid(), kind: 'crop', parentAssetId: work.original.id, objectName: `application/sha256/${rid()}`, sha256: hex('d'), width: 390, height: 160, acquisitionMethod: 'segmentation_crop'};
ok(await op('AppendSourceAssetV2', crop));
ok(await op('AppendLabelRegionV2', {...work.region, id: rid(), domainRegionId: rid(), cropAssetId: crop.id}));
const noPick = {...work.transcription, id: rid(), selectedObservationId: null, unresolved: true, rationale: 'The readers disagree on a material character.'};
ok(await op('AppendTranscriptionVersionV2', noPick));
for (const reading of [work.left, work.right]) ok(await op('AppendHarnessInputV1', {...work.decided, id: rid(), transcriptionVersionId: noPick.id, observationId: reading.id, role: 'raw_reading', handedText: reading.literalText}));
denied(await op('AppendHarnessInputV1', {...work.decided, id: rid(), transcriptionVersionId: noPick.id, observationId: work.third.id, handedText: work.third.literalText}));
ok(await op('AppendFieldCandidateV2', {...work.candidate, id: rid(), literalValue: 'Chicago, Il1.', authorityId: null, inputSource: 'raw_reading', sourceTranscriptionId: null, sourceObservationId: work.right.id}));
ok(await op('AppendTranscriptionVersionV2', {...work.transcription, id: rid(), decisionKind: 'identical_readings', firstPassObservationId: null, rationale: null}));
ok(await op('AppendTranscriptionVersionV2', {...work.transcription, id: rid(), decisionKind: 'identical_readings', firstPassObservationId: null, selectedObservationId: null, unresolved: true, rationale: null}));
const human = {...work.transcription, id: rid(), decisionKind: 'human', firstPassObservationId: null, selectedObservationId: null, unresolved: false, rationale: 'Read under the microscope.'};
denied(await op('AppendTranscriptionVersionV2', human));
ok(await op('AppendTranscriptionVersionV2', {...human, actorUid: 'reviewer'}));
ok(await op('AppendTranscriptionVersionV2', {...human, id: rid(), actorUid: 'reviewer', selectedObservationId: work.left.id, unresolved: true}));
ok(await op('AppendValidationFindingV2', {...work.finding, id: rid(), severity: 'warning', ruleId: 'spelling_disagreement', fieldKey: 'city', reasonCode: 'spelling_disagreement', evidenceIds: [work.evidence.id, noMatch.id]}));
ok(await op('AppendReviewDecisionV1', {...scope, actorUid: 'reviewer', id: rid(), specimenId: open, baseRevision: 0, resultingRevision: 1, reason: 'Checked the label', correction: {}}));
console.log('PASS the pipeline\'s writes are accepted: a region id reused by a superseding run, a superseding region, a crop, a no-pick decision and its raw-reading handoffs, a per-reader candidate, identical and reviewer decisions, a finding with its evidence');

// Rows cannot reference a specimen, run or asset of another collection.
const foreign = {...work.region, id: randomUUID(), collectionId: otherColl, actorUid: 'reviewer'};
denied(await op('AppendLabelRegionV2', foreign));
denied(await op('AppendSourceAssetV2', {...work.original, id: randomUUID(), objectName: randomUUID(), collectionId: otherColl, actorUid: 'reviewer'}));
console.log('PASS composite keys refuse cross-collection references');

// The lane's worker lists due work without sensitive-record access, oldest due time first (ListDueWorkV2).
const cutoff = new Date().toISOString();
const start = {afterAt: '1970-01-01T00:00:00Z', afterId: ''};
const due = (actorUid, includeSensitive, cursor = start, limit = 100) => query('ListDueWorkV2', {...scope, actorUid, cutoff, ...cursor, limit, includeSensitive});
const ids = r => ok(r).items.map(item => item.id);
same(ids(await due('worker', false)), [early, open, ...ties]);
same(ids(await due('reviewer', true)), [closed, early, open, ...ties]);
same(ids(await due('reviewer', false)), [early, open, ...ties]);
const first = ok(await due('worker', false, start, 1)).items;
same(first.map(item => item.id), [early]);
const next = {afterAt: first[0].workAvailableAt, afterId: first[0].id};
same(ids(await due('worker', false, next, 1)), [open]);
same(ids(await due('worker', false, {afterAt: '2026-01-02T00:00:00Z', afterId: open}, 1)), [ties[0]]);
// One row per page across the tie: the returned stamp carries its microseconds back.
const paged = [];
for (let cursor = start; ;) {
  assert.ok(paged.length <= 10, 'the cursor does not advance');
  const page = ok(await due('worker', false, cursor, 1)).items;
  if (!page.length) break;
  paged.push(page[0].id);
  cursor = {afterAt: page[0].workAvailableAt, afterId: page[0].id};
}
same(paged, [early, open, ...ties]);
denied(await due('worker', true));
denied(await due('viewer', false));
denied(await due('worker', false, {...start, afterId: 'not-a-cursor'}));
console.log('PASS due work lists the oldest due time first, pages by due time and id, hides sensitive rows from the worker, and skips finished and undated runs');
