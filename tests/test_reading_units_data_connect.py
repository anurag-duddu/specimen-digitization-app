"""Work package 1.1's Data Connect change against main (docs/execution/units/PLAN.md, WP 1.1).

Main's connector operations and schema types are pinned by name and by one digest of their exact
texts, as they stood at MAIN. Every one of them is byte-identical in this tree but
`TranscriptionVersion`, which gains one nullable field; exactly one operation is new; and the
data release's additive gate (scripts/ci/schema_gate.py) accepts the change.
"""

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ci"))
import schema_gate  # noqa: E402

MAIN = "e2faa1316785a9317e751c67b36175fa79d07382"  # pragma: allowlist secret (a commit id)
MAIN_OPERATIONS = (
    "AppendCandidateEvidence", "AppendCandidateEvidenceV2", "AppendCheckpoint",
    "AppendCheckpointV2", "AppendEvidenceItem", "AppendEvidenceItemV2", "AppendFieldCandidate",
    "AppendFieldCandidateV2", "AppendHarnessInputV1", "AppendLabelRegion", "AppendLabelRegionV2",
    "AppendModelObservation", "AppendModelObservationV2", "AppendPipelineRun",
    "AppendPipelineRunV2", "AppendProfileVersion", "AppendProfileVersionV2",
    "AppendReadingComparisonV1", "AppendRecordVersion", "AppendRecordVersionV2",
    "AppendResolvedField", "AppendResolvedFieldV2", "AppendReviewDecisionV1",
    "AppendReviewDecisionV2", "AppendSourceAsset", "AppendSourceAssetV2", "AppendToolCallV1",
    "AppendTranscriptionVersion", "AppendTranscriptionVersionV2", "AppendValidationFinding",
    "AppendValidationFindingV2", "CommitIntakeSubmission", "CompareResearchHarnessStateV1",
    "CostAllocationInputsV1", "CostAllocationStatusV1", "CostTotalsV1", "CreateDocument",
    "CreateDocumentV2", "CreateResearchHarnessStateV1", "CreateSpecimen", "CreateSpecimenV2",
    "CreateSpecimenV3", "FindSpecimenByChecksum", "FinishResearchDerivationV1",
    "FinishResearchRetryV1", "GetCanonicalResearchBindingV2",
    "GetCanonicalResearchMaterializationInputsV2", "GetDocument", "GetDocumentReceipt",
    "GetDocumentReceiptV2", "GetDocumentV2", "GetDocumentVersion", "GetDocumentVersionV2",
    "GetLatestRetainedRunSnapshot", "GetPrivateIntakeItems", "GetReceipt",
    "GetReprocessActionReceiptsV1", "GetResearchPublicationIntentV2",
    "GetResearchPublicationReceiptV2", "GetRetainedResearchPublicationLocatorsV2",
    "GetReviewSaveProofV1", "GetSnapshot", "GetSpecimen", "ListActiveIntakeJobs",
    "ListCollectionHierarchy", "ListDocumentPage", "ListDocumentPageV2", "ListDocuments",
    "ListDocumentsV2", "ListDueWork", "ListDueWorkV2", "ListPrivateIntakePage",
    "ListRunPaidCallsV1", "ListSnapshotHistory", "ListSpecimenPage", "ListSpecimens",
    "MarkResearchProgressAttemptV2", "MarkResearchPublicationAttemptV2", "Memberships",
    "ParkResearchRetryV1", "PublishCanonicalResearchProgressV2", "PublishCanonicalResearchV2",
    "ReadResearchHarnessStateV1", "Readiness", "RecordRunTraceV1",
    "RegisterCanonicalResearchBindingV2", "RetainResearchProgressIntentV2",
    "RetainResearchProgressPreparationV2", "RetainResearchPublicationIntentV2",
    "RetainResearchPublicationPreparationV2", "SaveDocument", "SaveDocumentV2", "SaveSpecimen",
    "SaveSpecimenV2", "SaveSpecimenV3", "ScheduleResearchDerivationV1", "ScheduleResearchRetryV1",
    "SearchSpecimens", "SetTenantBudgetCapV1", "TenantBudgetCapsV1", "UpsertCostAllocationsV1",
    "UpsertCostEntriesV1",
)
# The exact texts of MAIN's operations, in name order, joined by a blank line.
MAIN_OPERATIONS_SHA256 = "03fa0686b4ea163fab367417300628e65f9ae244e2a6839027e257e644e6676b"  # pragma: allowlist secret
MAIN_TYPES = (
    "ActiveIntakeJob", "AuditEvent", "AuxiliaryDocument", "AuxiliaryReceipt", "AuxiliaryVersion",
    "CandidateEvidence", "CanonicalResearchBindingV2", "CanonicalValueDependencyV2",
    "CanonicalValueEvidenceV2", "CanonicalValueLineageV2", "CapturedToolExecutionV2", "Checkpoint",
    "Collection", "CollectionMember", "CostEntry", "DocumentListing", "EvidenceItem",
    "FieldCandidate", "HarnessInput", "LabelRegion", "ModelObservation", "Organization",
    "OrganizationMember", "OutboxEvent", "PipelineRun", "ProfileVersion", "ProviderConnection",
    "ReadingComparison", "RecordVersion", "RequestReceipt", "ResearchHarnessState",
    "ResearchLedgerImportProofV1", "ResearchPublicationAttemptV2", "ResearchPublicationIntentV2",
    "ResearchPublicationPreparationV2", "ResearchPublicationReceiptV2", "ResolvedField",
    "ReviewDecision", "SourceAsset", "Specimen", "SpecimenListing", "SpecimenSearch",
    "SpecimenSnapshot", "TenantBudgetCap", "ToolCall", "ToolInputLineageV2", "TranscriptionVersion",
    "ValidationFinding",
)
# The exact texts of MAIN's types, in name order, joined by a blank line.
MAIN_TYPES_SHA256 = "0c7e9cee5211e1129d89de57d96fbaeeefd7081eeca60931ffd33fb22a214b96"  # pragma: allowlist secret
NEW_OPERATION = "AppendTranscriptionVersionV3"
NEW_FIELD = (
    "  # The label's reading units (DATA_CONTRACT.md 4.2); null on a row written without them.\n"
    "  readingUnits: Any\n"
)


def blocks(directory: Path, keywords: str) -> dict[str, str]:
    """Each definition's exact text, from its keyword at the start of a line to its closing `}`."""
    found: dict[str, str] = {}
    for path in sorted(directory.glob("*.gql")):
        lines = path.read_text().split("\n")
        at = 0
        while at < len(lines):
            match = re.match(rf"(?:{keywords}) ([_A-Za-z][_0-9A-Za-z]*)\b", lines[at])
            if not match:
                at += 1
                continue
            end = lines.index("}", at)
            assert match.group(1) not in found, match.group(1)
            found[match.group(1)] = "\n".join(lines[at:end + 1])
            at = end + 1
    return found


def operations() -> dict[str, str]:
    return blocks(ROOT / "dataconnect/connector", "query|mutation")


def types() -> dict[str, str]:
    return blocks(ROOT / "dataconnect/schema", "type|enum|input|scalar")


def joined(found: dict[str, str], names) -> str:
    return "\n\n".join(found[name] for name in sorted(names))


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def types_without_the_new_field() -> dict[str, str]:
    found = types()
    assert found["TranscriptionVersion"].count(NEW_FIELD) == 1
    return {**found, "TranscriptionVersion": found["TranscriptionVersion"].replace(NEW_FIELD, "")}


def test_the_blocks_are_every_definition_the_release_gate_parses():
    connector = schema_gate.read_tree(ROOT / "dataconnect/connector")
    schema = schema_gate.read_tree(ROOT / "dataconnect/schema")
    parsed = schema_gate.parse_connector(connector)
    assert set(operations()) == set(parsed)
    for name, text in operations().items():
        assert schema_gate.parse_connector({"one.gql": text}) == {name: parsed[name]}
    assert set(types()) == set(schema_gate.parse_schema(schema))


def test_every_connector_operation_on_main_is_byte_identical_and_exactly_one_is_new():
    found = operations()
    assert set(found) - set(MAIN_OPERATIONS) == {NEW_OPERATION}
    assert set(MAIN_OPERATIONS) <= set(found)
    assert sha256(joined(found, MAIN_OPERATIONS)) == MAIN_OPERATIONS_SHA256, (
        f"an operation of main {MAIN[:9]} changed: compare with git show {MAIN[:9]}:dataconnect/connector"
    )


def test_every_schema_type_on_main_is_byte_identical_but_transcription_versions_new_field():
    assert set(types()) == set(MAIN_TYPES)
    assert sha256(joined(types_without_the_new_field(), MAIN_TYPES)) == MAIN_TYPES_SHA256, (
        f"a type of main {MAIN[:9]} changed: compare with git show {MAIN[:9]}:dataconnect/schema"
    )


def test_the_new_operation_is_v2_with_the_units_and_the_same_checks():
    found = operations()
    expected = (
        found["AppendTranscriptionVersionV2"]
        .replace("AppendTranscriptionVersionV2(", NEW_OPERATION + "(", 1)
        .replace("$rationale: String, $actorUid", "$rationale: String, $readingUnits: Any!, $actorUid", 1)
        .replace("rationale: $rationale})", "rationale: $rationale, readingUnits: $readingUnits})", 1)
    )
    assert found[NEW_OPERATION] == expected
    assert found[NEW_OPERATION].count("readingUnits") == 3


def test_the_release_gate_reads_the_change_as_additive():
    live_schema = {"main.gql": joined(types_without_the_new_field(), MAIN_TYPES)}
    merged_schema = {"tree.gql": joined(types(), MAIN_TYPES)}
    live_connector = {"main.gql": joined(operations(), MAIN_OPERATIONS)}
    merged_connector = {"tree.gql": joined(operations(), operations())}
    assert schema_gate.check_additive(live_schema, merged_schema, live_connector, merged_connector) == []
    # The gate is not vacuous here: a required column, or V2 changed in place, is refused.
    required = {"tree.gql": merged_schema["tree.gql"].replace("readingUnits: Any\n", "readingUnits: Any!\n")}
    assert schema_gate.check_additive(live_schema, required, live_connector, merged_connector) == [
        "TranscriptionVersion.readingUnits: new field on an existing table must be nullable"
    ]
    v3 = operations()[NEW_OPERATION]
    in_place = {"tree.gql": live_connector["main.gql"].replace(
        operations()["AppendTranscriptionVersionV2"],
        v3.replace(NEW_OPERATION + "(", "AppendTranscriptionVersionV2(", 1),
    )}
    assert schema_gate.check_additive(live_schema, merged_schema, live_connector, in_place) == [
        "AppendTranscriptionVersionV2: operation changed"
    ]
