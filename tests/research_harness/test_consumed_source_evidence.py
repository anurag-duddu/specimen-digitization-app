"""Pure native source-association controls; no transaction or provider authority."""
import copy
from dataclasses import replace

import pytest

from test_native_canonical_contract import basis
from test_canonical_projection_v2 import projection_case
from specimen_digitization.application.projection import derived_id
from specimen_digitization.research_harness.canonical_projection_v2 import (
    CONTRACT, _consumed_source_value,
)
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import digest
from specimen_digitization.research_harness.publication import _native_checkpoint


def consumed_case(b):
    case = projection_case(b, "G44")
    proof = case.context.consumed_sources[0]
    native, original = _native_checkpoint(case.context.job, proof.checkpoint, case.context.scope)
    value = case.prior.run.fields[proof.canonical_field_key]
    scope = {"organizationId": case.context.scope.organization_id,
        "collectionId": case.context.scope.collection_id}
    line = {**scope, "id": derived_id(CONTRACT,"lineage",str(proof.canonical_candidate_id),
        str(proof.canonical_record_version_id)), "contractVersion": CONTRACT,
        "runId":str(proof.canonical_run_id), "specimenId":case.context.scope.specimen_id,
        "originalScope":original.scope.model_dump(mode="json"),
        "candidateId":str(proof.canonical_candidate_id), "recordVersionId":str(proof.canonical_record_version_id),
        "researchFieldKey":str(original.field_key), "nativeCheckpointId":native["id"],
        "nativeCheckpointDigest":digest(native), "typedCheckpointDigest":digest(original),
        "resolutionDigest":digest(original.resolution), "evidenceIds":value.evidence_ids,
        "evidenceRelations":value.evidence_relations}
    rows=tuple({**scope,"id":derived_id(CONTRACT,"evidence",line["id"],str(mapped)),
        "lineageId":line["id"],"evidenceId":str(mapped),"researchEvidenceId":key,
        "associationKind":"original_value_evidence","originalRelation":value.evidence_relations.get(str(mapped))}
        for key,mapped in case.context.evidence_id_mapping.items())
    proof=proof.model_copy(update={"source_lineage":line,"source_evidence_rows":rows,
        "source_publication_lineage_digest":digest(line)})
    # The consumer's own lookup has an independent evidence map. Source proof
    # must carry its actual mapping rather than inherit target lookup IDs.
    context=replace(case.context,evidence_id_mapping={})
    return case,proof,context,native,original,value


def test_consumed_field_uses_its_own_exact_native_evidence_associations(basis):
    _,proof,context,native,original,value=consumed_case(basis)
    assert _consumed_source_value(context,proof,native,original) == value


@pytest.mark.parametrize("defect", ["wrong_checkpoint","wrong_candidate","wrong_scope",
    "crossed_lineage","wrong_original","missing_row","duplicate_row","wrong_relation","row_relation","wrong_kind","wrong_record","wrong_lineage_id"])
def test_crossed_or_incomplete_source_evidence_never_becomes_dependency_authority(basis, defect):
    _,proof,context,native,original,_=consumed_case(basis)
    line=copy.deepcopy(proof.source_lineage);rows=list(copy.deepcopy(proof.source_evidence_rows))
    if defect=="wrong_checkpoint":line["nativeCheckpointId"]="0"*64
    elif defect=="wrong_candidate":line["candidateId"]="00000000-0000-0000-0000-000000000001"
    elif defect=="wrong_scope":rows[0]["collectionId"]="other"
    elif defect=="crossed_lineage":rows[0]["lineageId"]="00000000-0000-0000-0000-000000000001"
    elif defect=="wrong_original":rows[0]["researchEvidenceId"]="wrong"
    elif defect=="missing_row":rows.pop()
    elif defect=="duplicate_row":rows.append(rows[0])
    elif defect=="wrong_relation":line["evidenceRelations"]={}
    elif defect=="row_relation":rows[0]["originalRelation"]="contradicts"
    elif defect=="wrong_kind":rows[0]["associationKind"]="original_derivation_record"
    elif defect=="wrong_record":line["recordVersionId"]="not-a-native-uuid"
    elif defect=="wrong_lineage_id":line["id"]="00000000-0000-0000-0000-000000000001"
    proof=proof.model_copy(update={"source_lineage":line,"source_evidence_rows":tuple(rows),
        "source_publication_lineage_digest":digest(line)})
    with pytest.raises(PublicationUnavailable,match="consumed_source_evidence_unproved"):
        _consumed_source_value(context,proof,native,original)


def test_immutable_source_publication_record_survives_later_carried_projection(basis):
    from uuid import uuid4
    _,proof,context,native,original,value=consumed_case(basis)
    proof=proof.model_copy(update={"canonical_record_version_id":uuid4()})
    assert _consumed_source_value(context,proof,native,original) == value
