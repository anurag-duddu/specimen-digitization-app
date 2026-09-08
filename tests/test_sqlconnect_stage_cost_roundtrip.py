"""Opt-in real connector stage-cost/launch-ledger round trip; metadata fixtures only.

Start scripts/data/serve-local.sh on isolated ports, then set
SPECIMEN_TEST_SQL_EMULATOR=true and SPECIMEN_SQL_EMULATOR_HOST=127.0.0.1:PORT.
No images, blob readers, model adapters or cloud authentication are constructed.
Requires the stage-map runtime implementation and its trusted-snapshot fix.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
from uuid import uuid4

import pytest
from pydantic import ValidationError

from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG
from specimen_digitization.application.domain import (
    Asset, ExecutionPolicy, Principal, Profile, Run, Scope, Specimen,
)
from specimen_digitization.application.production import (
    SqlConnectRepository, actor_uid, sql_emulator_host,
)
from specimen_digitization.application.storage import digest
from specimen_digitization.application.worker_launch import PilotAdmission, PilotLaunch
from specimen_digitization.application.workflow import OperationalBlock


pytestmark = pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires explicitly started isolated SQL Connect/PostgreSQL emulator",
)


@pytest.mark.parametrize("include_admission", [False, True], ids=["snapshot", "launch-ledger"])
def test_connector_preserves_stage_policy_and_launch_ledger_after_reconstruction(include_admission):
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
    context = actor_uid.set(principal.user_id)
    repositories = []

    def connect():
        repo = SqlConnectRepository(project="demo-specimen-data", emulator_host=sql_emulator_host())
        repositories.append(repo)
        return repo

    try:
        repo = connect()
        assert any(m["collection_id"] == scope.collection_id for m in repo.memberships(principal.user_id))
        costs = {
            "version": "stage-cost-reservations-v1",
            "cost_micros": {"segment": 17, "transcribe:handwriting-qwen": 59,
                            "transcribe:handwriting-muse": 89},
        }
        policy = ExecutionPolicy(stage_cost_reservations=costs, approved_cost_limit_micros=1000)
        # Ten synthetic binding declarations satisfy the launch shape. Only one
        # metadata specimen is persisted, never counted as actual cohort evidence.
        bindings = []
        for _ in range(10):
            ident = str(uuid4())
            checksum = hashlib.sha256(ident.encode()).hexdigest()
            bindings.append(dict(specimen_id=ident, asset_sha256=checksum, blob_ref=checksum + ":123"))
        binding = bindings[0]
        specimen = Specimen(
            id=binding["specimen_id"], scope=scope,
            asset=Asset(sha256=binding["asset_sha256"], blob_ref=binding["blob_ref"],
                        media_type="image/png", size_bytes=1, width=1, height=1,
                        filename="synthetic-metadata-only.png", uploader=principal.user_id),
            run=Run(profile=Profile(synthetic=False, execution=policy)),
        )
        launch = PilotLaunch(
            evidence_only=True, evidence_profile_sha256="b" * 64,
            source_manifest_sha256=hashlib.sha256(str(uuid4()).encode()).hexdigest(),
            authorization_reference="synthetic-local-connector-contract",
            scope=scope, specimens=bindings,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            total_cost_limit_micros=10000, per_specimen_cost_limit_micros=1000,
            per_specimen_call_limit=32, per_specimen_token_limit=160000,
            effect_timeout_seconds=120, stage_cost_reservations=costs,
            hf_secret_resource="/".join(
                ["projects", "specimen-digitization", "secrets", "synthetic-unused", "versions", "1"]
            ),
        )
        expected_policy = policy.model_dump(mode="json")
        policy_sha = digest(expected_policy)
        launch_sha = digest(launch.model_dump(mode="json"))
        created = repo.create(principal, specimen, "stage-map-create:" + specimen.id, digest(specimen.id))
        raw = repo.execute("GetSnapshot", dict(repo.variables(scope), id=specimen.id, revision=created.version))[
            "specimenSnapshot"
        ]
        raw_costs = raw["snapshot"]["run"]["profile"]["execution"]["stage_cost_reservations"]["cost_micros"]
        assert raw_costs == costs["cost_micros"]
        assert all(type(value) in (int, float) for value in raw_costs.values())
        print("Observed SQL Connect JSON cost types:", sorted({type(v).__name__ for v in raw_costs.values()}))

        fresh = connect()
        restored = fresh.get(scope, specimen.id)
        restored_policy = restored.run.profile.execution
        assert restored_policy.model_dump(mode="json") == expected_policy
        assert all(type(value) is int for value in restored_policy.stage_cost_reservations.cost_micros.values())
        assert digest(restored_policy.model_dump(mode="json")) == policy_sha
        restored.run.usage.reserved_cost_micros = 17
        saved = fresh.save(principal, restored, restored.version, "stage-map-save:" + specimen.id, digest("reserved17"))
        again = connect()
        for version in (created.version, saved.version):
            historic = again.version(scope, specimen.id, version)
            assert digest(historic.run.profile.execution.model_dump(mode="json")) == policy_sha
            assert all(type(v) is int for v in historic.run.profile.execution.stage_cost_reservations.cost_micros.values())
        assert again.get(scope, specimen.id).run.usage.reserved_cost_micros == 17
        # A cost map reconstructed from connector values still receives strict
        # external validation; trusted snapshot context must never leak outward.
        for malformed in (17.0, 17.5, True, "17"):
            changed = deepcopy(raw_costs)
            changed["segment"] = malformed
            bad = dict(costs, cost_micros=changed)
            with pytest.raises(ValidationError):
                ExecutionPolicy(stage_cost_reservations=bad)
            with pytest.raises(ValidationError):
                PilotLaunch.model_validate(dict(launch.model_dump(mode="json"), stage_cost_reservations=bad))

        if not include_admission:
            return
        item = again.get(scope, specimen.id)
        admission = PilotAdmission(again, launch)
        admission.admit(item)
        ledger = deepcopy(again.document(scope, "pilot_launch", admission.ledger_id))
        assert ledger["launch_sha256"] == launch_sha
        assert ledger["runs"][specimen.id]["policy_sha256"] == policy_sha
        restarted_repo = connect()
        restarted = PilotAdmission(restarted_repo, launch)
        restarted.admit(restarted_repo.get(scope, specimen.id))
        assert restarted.launch_digest == launch_sha
        assert restarted_repo.document(scope, "pilot_launch", restarted.ledger_id) == ledger

        changed = deepcopy(costs)
        changed["cost_micros"]["segment"] = 18
        revised = PilotLaunch.model_validate(dict(launch.model_dump(mode="json"), stage_cost_reservations=changed))
        item = again.get(scope, specimen.id)
        with pytest.raises(OperationalBlock, match="stage_cost_reservations_mismatch"):
            PilotAdmission(again, revised).admit(item)
        item.run.profile.execution = ExecutionPolicy.model_validate(
            dict(expected_policy, stage_cost_reservations=changed)
        )
        with pytest.raises(OperationalBlock, match="launch_changed_requires_reconciliation"):
            PilotAdmission(again, revised).admit(item)
        assert again.document(scope, "pilot_launch", restarted.ledger_id) == ledger
    finally:
        for repo in repositories:
            repo.session.close()
        actor_uid.reset(context)
