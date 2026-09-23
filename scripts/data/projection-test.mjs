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

const org = randomUUID(), coll = randomUUID(), otherColl = randomUUID(), open = randomUUID(), closed = randomUUID(), idle = randomUUID(), undated = randomUUID();
// Sorts after every random id, so due-time order and id order disagree.
const early = 'ffffffff-ffff-4fff-bfff-' + randomUUID().slice(-12);
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
 s1: specimen_insert(data:{${sc},id:"${open}",revision:1,state:"running",sensitive:false,createdBy:"worker",workAvailableAt:"2026-01-02T00:00:00Z"})
 s2: specimen_insert(data:{${sc},id:"${closed}",revision:1,state:"running",sensitive:true,createdBy:"reviewer",workAvailableAt:"2026-01-01T00:00:00Z"})
 s3: specimen_insert(data:{${sc},id:"${idle}",revision:1,state:"completed",sensitive:false,createdBy:"worker",workAvailableAt:"2026-01-01T00:00:00Z"})
 s4: specimen_insert(data:{${sc},id:"${early}",revision:1,state:"pending",sensitive:false,createdBy:"worker",workAvailableAt:"2026-01-01T00:00:00Z"})
 s5: specimen_insert(data:{${sc},id:"${undated}",revision:1,state:"running",sensitive:false,createdBy:"worker"})
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
  w.original = {...v, id: id(), specimenId, kind: 'original', parentAssetId: null, bucket: 'demo-specimen-data.appspot.com', objectName: `application/sha256/${randomUUID()}`, generation: '1', sha256: hex('a'), mimeType: 'image/png', byteSize: '4', width: 4000, height: 3000, acquisitionMethod: 'source_import', uploaderUid: actorUid};
  w.envelope = {...w.original, id: id(), kind: 'raw_response', parentAssetId: null, objectName: `application/sha256/${randomUUID()}`, mimeType: 'application/json', width: null, height: null, acquisitionMethod: 'model_response'};
  w.run = {...v, id: id(), specimenId, profileVersionId: profileId, supersedesRunId: null, pinnedVersions: {segmentation: {model_revision: 'fixture', settings: {concept_prompt: 'label'}}}, inputSha256: hex('a'), traceId: null};
  w.region = {...v, id: id(), runId: w.run.id, sourceAssetId: w.original.id, cropAssetId: null, geometry: {bbox: [10, 20, 400, 180]}, ordinal: 0, regionType: 'label', segmentationVersion: 'fixture', supersedesRegionId: null};
  const reading = (route, text) => ({...v, id: id(), runId: w.run.id, regionId: w.region.id, rawAssetId: w.envelope.id, stepKey: `transcribe:${w.region.id}:${route}`, provider: 'fixture', modelVersion: route, promptVersion: 'p1', inputSha256: hex('b'), parameters: {}, literalText: text, outcome: 'stop', independent: true, routeId: route, unreadableSpans: []});
  w.left = reading('handwriting-qwen', 'Chicago, Ill.');
  w.right = {...reading('handwriting-muse', 'Chicago, Il1.'), unreadableSpans: ['Il1.']};
  w.firstPassCall = {...reading('first-pass', 'Chicago, Ill.'), stepKey: `first_pass:${w.region.id}`, independent: false};
  w.comparison = {...v, id: id(), runId: w.run.id, regionId: w.region.id, leftObservationId: w.left.id, rightObservationId: w.right.id, algorithm: 'bounded-levenshtein-fraction-v1', ratio: 1 / 13, editDistance: 1, lengthBasis: 13, status: 'difference', reasons: []};
  w.transcription = {...v, id: id(), runId: w.run.id, literalText: w.left.literalText, spans: [], alternatives: [w.left.literalText, w.right.literalText], unresolved: false, regionId: w.region.id, decisionKind: 'first_pass', selectedObservationId: w.left.id, firstPassObservationId: w.firstPassCall.id, rationale: 'The crop shows a lowercase l.'};
  w.decided = {...v, id: id(), runId: w.run.id, transcriptionVersionId: w.transcription.id, observationId: w.left.id, role: 'decided_transcript', handedText: w.left.literalText, note: null};
  w.fallback = {...w.decided, id: id(), observationId: w.right.id, role: 'raw_reading', handedText: w.right.literalText};
  w.evidence = {...v, id: id(), runId: w.run.id, source: 'google_geocoding', sourceVersion: 'v1', adapterVersion: 'a1', query: {address: 'Chicago, Ill.'}, outcome: 'success', locator: 'place/1', responseSha256: hex('e'), capturedAt: '2026-09-23T12:00:00Z', rawAssetId: w.envelope.id};
  w.toolCall = {...v, id: id(), runId: w.run.id, callKey: 'lookup:geocode:decided_transcript:-:0af70af70af70af7:1', phase: 'lookup', tool: 'geocode', toolVersion: 't1', source: 'google-maps-geocoding', fieldKeys: ['country', 'province_state', 'county', 'city'], inputSource: 'decided_transcript', transcriptionVersionId: w.transcription.id, observationId: null, attempt: 1, arguments: {query: 'Chicago, Ill.'}, outcome: 'success', result: {candidates: [{place_id: 'fixture-place', name: 'Chicago'}]}, evidenceId: w.evidence.id, startedAt: '2026-09-23T12:00:00Z', completedAt: '2026-09-23T12:00:01Z'};
  w.candidate = {...v, id: id(), runId: w.run.id, fieldKey: 'city', state: 'supported', literalValue: 'Chicago', parsedValue: 'Chicago', normalizedValue: 'Chicago', authorityId: null, derivation: 'lookup', inputSource: 'decided_transcript', sourceTranscriptionId: w.transcription.id, sourceObservationId: null};
  w.link = {...v, id: id(), candidateId: w.candidate.id, evidenceId: w.evidence.id, relation: 'supports'};
  w.record = {...v, id: id(), runId: w.run.id, predecessorId: null, disposition: 'needs_human_review', policyVersion: 'insects-clearance-v1', reasonCodes: ['mandatory_unresolved:county'], summary: 'mandatory_unresolved:county'};
  w.resolved = {...v, id: id(), recordVersionId: w.record.id, candidateId: w.candidate.id, fieldKey: 'city', state: 'supported', fieldGroup: 'mandatory'};
  w.finding = {...v, id: id(), recordVersionId: w.record.id, ruleId: 'mandatory_unresolved', ruleVersion: 'insects-clearance-v1', severity: 'hard', outcome: 'fail', fieldKey: 'county', reasonCode: 'mandatory_unresolved:county'};
  w.checkpoint = {...v, id: id(), runId: w.run.id, stepKey: 'lookup', inputSha256: hex('f'), state: 'completed', attempt: 1, nextRetryAt: null, blockerCode: null, outputReferences: {}};
  return w;
}
const writes = [
  ['AppendSourceAssetV2', 'original'], ['AppendSourceAssetV2', 'envelope'], ['AppendPipelineRunV2', 'run'],
  ['AppendLabelRegionV2', 'region'], ['AppendModelObservationV2', 'left'], ['AppendModelObservationV2', 'right'],
  ['AppendModelObservationV2', 'firstPassCall'], ['AppendReadingComparisonV1', 'comparison'],
  ['AppendTranscriptionVersionV2', 'transcription'], ['AppendHarnessInputV1', 'decided'], ['AppendHarnessInputV1', 'fallback'],
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
 labelRegions(where:{runId:{eq:"${work.run.id}"}}) { sourceAssetId cropAssetId }
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
same(thread.labelRegions, [{sourceAssetId: work.original.id, cropAssetId: null}]);
same(thread.modelObservations.map(o => [o.independent, o.routeId, o.unreadableSpans]), [[false, 'first-pass', []], [true, 'handwriting-muse', ['Il1.']], [true, 'handwriting-qwen', []]]);
same([thread.readingComparisons[0].ratio, thread.readingComparisons[0].editDistance, thread.readingComparisons[0].lengthBasis], [1 / 13, 1, 13]);
same(thread.transcriptionVersions, [{regionId: work.region.id, decisionKind: 'first_pass', selectedObservationId: work.left.id, firstPassObservationId: work.firstPassCall.id}]);
same(thread.harnessInputs.map(h => [h.role, h.observationId]), [['decided_transcript', work.left.id], ['raw_reading', work.right.id]]);
same(thread.toolCalls, [{callKey: 'lookup:geocode:decided_transcript:-:0af70af70af70af7:1', source: 'google-maps-geocoding', fieldKeys: ['country', 'province_state', 'county', 'city'], outcome: 'success', inputSource: 'decided_transcript', evidenceId: work.evidence.id, attempt: 1}]);
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
console.log('PASS the trace id is recorded once and well formed');

// Closed vocabularies and image dimensions are enforced.
denied(await op('AppendHarnessInputV1', {...work.decided, id: randomUUID(), observationId: work.firstPassCall.id, role: 'decided'}));
denied(await op('AppendToolCallV1', {...work.toolCall, id: randomUUID(), callKey: 'x', inputSource: 'decided'}));
denied(await op('AppendToolCallV1', {...work.toolCall, id: randomUUID(), callKey: 'y', attempt: 0}));
denied(await op('AppendToolCallV1', {...work.toolCall, id: randomUUID(), callKey: 'z', outcome: 'unavailable'}));
denied(await op('AppendHarnessInputV1', {...work.decided, id: randomUUID(), observationId: work.firstPassCall.id, handedText: null}));
denied(await op('AppendTranscriptionVersionV2', {...work.transcription, id: randomUUID(), decisionKind: 'llm'}));
denied(await op('AppendFieldCandidateV2', {...work.candidate, id: randomUUID(), inputSource: 'raw'}));
denied(await op('AppendResolvedFieldV2', {...work.resolved, id: randomUUID(), fieldGroup: 'required'}));
denied(await op('AppendReadingComparisonV1', {...work.comparison, id: randomUUID(), leftObservationId: work.firstPassCall.id, editDistance: -1}));
denied(await op('AppendReadingComparisonV1', {...work.comparison, id: randomUUID(), leftObservationId: work.firstPassCall.id, lengthBasis: 0}));
denied(await op('AppendReadingComparisonV1', {...work.comparison, id: randomUUID(), rightObservationId: work.left.id}));
denied(await op('AppendSourceAssetV2', {...work.original, id: randomUUID(), objectName: randomUUID(), width: null}));
ok(await op('AppendFieldCandidateV2', {...work.candidate, id: randomUUID(), derivation: 'human', inputSource: null, sourceTranscriptionId: null}));
console.log('PASS closed vocabularies and image dimensions are enforced');

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
  if (name === 'AppendReadingComparisonV1') variables.leftObservationId = kept.firstPassCall.id;
  denied(await op(name, variables));
  ok(await op(name, {...variables, actorUid: 'reviewer'}));
  created[key] = variables.id;
}
denied(await op('RecordRunTraceV1', {...scope, actorUid: 'worker', id: kept.run.id, traceId: trace}));
ok(await op('RecordRunTraceV1', {...scope, actorUid: 'reviewer', id: kept.run.id, traceId: trace}));
ok(await op('AppendReviewDecisionV1', {...scope, actorUid: 'reviewer', id: randomUUID(), specimenId: closed, baseRevision: 1, resultingRevision: 2, reason: 'Checked the label', correction: {kind: 'field', target_id: 'county', after: {literal: 'Cook'}}}));
denied(await op('AppendReviewDecisionV1', {...scope, actorUid: 'worker', id: randomUUID(), specimenId: open, baseRevision: 1, resultingRevision: 2, reason: 'r', correction: {}}));
denied(await op('AppendModelObservationV2', {...work.left, id: randomUUID(), stepKey: randomUUID(), actorUid: 'viewer'}));
console.log('PASS sensitive runs need a sensitive-capable member; review decisions need a reviewer');

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
same(ids(await due('worker', false)), [early, open]);
same(ids(await due('reviewer', true)), [closed, early, open]);
same(ids(await due('reviewer', false)), [early, open]);
const first = ok(await due('worker', false, start, 1)).items;
same(first.map(item => item.id), [early]);
const next = {afterAt: first[0].workAvailableAt, afterId: first[0].id};
same(ids(await due('worker', false, next, 1)), [open]);
same(ids(await due('worker', false, {afterAt: '2026-01-02T00:00:00Z', afterId: open}, 1)), []);
denied(await due('worker', true));
denied(await due('viewer', false));
denied(await due('worker', false, {...start, afterId: 'not-a-cursor'}));
console.log('PASS due work lists the oldest due time first, pages by due time and id, hides sensitive rows from the worker, and skips finished and undated runs');
