"""Actual declaration provenance, human supersession and label policy through HTTP."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_application import HEADERS, PREFIX, TOKEN, intake

from specimen_digitization.application.api import create_app, SYNTHETIC_TEXT
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters
from specimen_digitization.application.reading_declarations import (
    DeclarationCandidates,
    LanguageHandling,
    label_handling,
    language_key,
    model_evidence,
)
from specimen_digitization.transcription import LiteralTranscription


# What each route declares, by mode: the first route, then the second. The
# "vocabulary" pair is the observed 2026-09-14 dual read, where both routes
# agreed the label was English and named that language differently.
DECLARED_LANGUAGES = {
    "mixed": (["English", "German"], ["English", "German"]),
    "conflicting": (["English"], ["German"]),
    "vocabulary": (["en"], ["English"]),
}


class DeclaredAdapters(SyntheticAdapters):
    def __init__(self, blobs, mode):
        super().__init__(blobs, SYNTHETIC_TEXT)
        self.mode = mode

    def transcribe(self, specimen, region, route):
        observation = super().transcribe(specimen, region, route)
        if self.mode == "unknown":
            candidates = {}
        else:
            first, second = DECLARED_LANGUAGES[self.mode]
            candidates = {
                "language_candidates": first
                if route == specimen.run.profile.routes[0]
                else second,
                "script_candidates": ["Latin"],
                "language_relation": "cooccurring"
                if self.mode == "mixed"
                else "unspecified",
            }
        output = LiteralTranscription(
            verbatim_text=observation.literal_text,
            lines=observation.literal_text.split("\n"),
            **candidates,
        )
        observation.declaration_evidence = model_evidence(
            self.blobs,
            output,
            observation.raw_ref,
            observation.raw_sha256,
            observation.model_id,
            observation.prompt_version,
        )
        return observation


def app_at(root, mode="mixed"):
    blobs = LocalBlobs(root / "blobs")
    return create_app(
        mode="synthetic",
        repository=SQLiteRepository(root / "state.db"),
        blobs=blobs,
        adapters=DeclaredAdapters(blobs, mode),
        token=TOKEN,
    )


@pytest.mark.parametrize(
    "mode,mixed,conflicting",
    [("mixed", True, False), ("conflicting", False, True), ("unknown", False, False)],
)
def test_actual_declarations_keep_mixed_and_conflicting_distinct(
    tmp_path, mode, mixed, conflicting
):
    with TestClient(app_at(tmp_path, mode)) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        assert "reading_metadata" in work["available_actions"]
        label = work["run"]["label_language_handling"]["labels"][0]
        assert label["mixed_declared"] == mixed
        assert label["conflicting_candidates"] == conflicting
        assert label["policy_version"] == "language-handling-v1" and label["unmeasured"]
        assert label["review_required"] == (mixed or conflicting)
        obs = work["observations"][0]
        metadata = http.get(
            path + "/observations/" + obs["id"] + "/metadata", headers=HEADERS
        ).json()
        assert all(
            item["method"] == "model_declared" and item["reported_confidence"] is None
            for item in metadata["declarations"]
        )
        assert metadata["language_state"] == (
            "unknown"
            if mode == "unknown"
            else "multiple_candidates"
            if mode == "mixed"
            else "declared"
        )
        assert ("language_unknown_unmeasured" in label["reasons"]) == (
            mode == "unknown"
        )


def test_human_supersession_replay_restart_and_immutable_observation(tmp_path):
    app = app_at(tmp_path)
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        obs = work["observations"][0]
        raw_path = path + "/observations/" + obs["id"] + "/raw"
        raw = http.get(raw_path, headers=HEADERS).content
        for index, languages in enumerate((["French"], ["Italian"])):
            body = {
                "kind": "reading_metadata",
                "target_id": obs["id"],
                "after": {
                    "language_candidates": languages,
                    "script_candidates": ["Latin"],
                },
                "reason": "Synthetic reviewer declaration",
                "expected_revision": work["revision"],
                "base_record_version_id": work["record_version_id"],
            }
            headers = {**HEADERS, "Idempotency-Key": "metadata-" + str(index)}
            response = http.post(path + "/decisions", headers=headers, json=body)
            assert response.status_code == 200, response.text[:500]
            updated = response.json()
            replay = http.post(path + "/decisions", headers=headers, json=body)
            assert replay.status_code == 200 and replay.json() == updated
            assert updated["observations"] == work["observations"]
            assert updated["run"]["phase_results"] == work["run"]["phase_results"]
            assert (
                updated["run"]["authority_receipts"]
                == work["run"]["authority_receipts"]
            )
            assert not updated["run"]["human_approved"]
            stale = http.post(
                path + "/decisions",
                headers={**HEADERS, "Idempotency-Key": "stale-" + str(index)},
                json=body,
            )
            assert stale.status_code == 409
            work = updated
        evidence = http.get(
            path + "/observations/" + obs["id"] + "/declarations", headers=HEADERS
        ).json()
        assert evidence["model"]["raw_sha256"] == obs["raw_sha256"]
        history = evidence["human_history"]
        assert len(history) == 2 and history[1]["supersedes"] == history[0]["id"]
        assert history[1]["actor"] == "synthetic-reviewer" and history[1]["created_at"]
        metadata = http.get(
            path + "/observations/" + obs["id"] + "/metadata", headers=HEADERS
        ).json()
        assert {
            d["value"]
            for d in metadata["declarations"]
            if d["method"] == "human_recorded" and d["kind"] == "language"
        } == {"Italian"}
        assert http.get(raw_path, headers=HEADERS).content == raw
        invalid = {
            **body,
            "expected_revision": work["revision"],
            "base_record_version_id": work["record_version_id"],
            "target_id": "previous-run-observation",
        }
        assert (
            http.post(path + "/decisions", headers=HEADERS, json=invalid).status_code
            == 422
        )
    with TestClient(app_at(tmp_path)) as http:
        restored = http.get(path + "/workspace", headers=HEADERS).json()
        assert (
            restored["run"]["reading_declarations"]
            == work["run"]["reading_declarations"]
        )
        assert http.get(raw_path, headers=HEADERS).content == raw


@pytest.mark.parametrize(
    "value",
    [
        {"language_candidates": ["x"] * 9},
        {"language_candidates": ["x" * 101]},
        {"language_candidates": ["English"], "language_relation": "cooccurring"},
        {"producer": "spoofed"},
        {"language_candidates": ["English", "English"]},
    ],
)
def test_declaration_bounds_and_server_provenance(value):
    with pytest.raises(ValueError):
        DeclarationCandidates.model_validate(value)


def test_resegmentation_rejects_old_reading_target_and_preserves_history(tmp_path):
    with TestClient(app_at(tmp_path)) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        original = http.get(path + "/workspace", headers=HEADERS).json()
        obs = original["observations"][0]
        region = {key: value for key, value in original["run"]["regions"][0].items()}
        response = http.post(
            path + "/regions",
            headers=HEADERS,
            json={
                "regions": [region],
                "reason": "Synthetic recrop",
                "expected_revision": original["revision"],
                "base_run_id": original["run"]["id"],
            },
        )
        assert response.status_code == 200, response.text[:300]
        current = http.get(path + "/workspace", headers=HEADERS).json()
        assert current["run"]["id"] != original["run"]["id"]
        body = {
            "kind": "reading_metadata",
            "target_id": obs["id"],
            "after": {"language_candidates": ["English"]},
            "reason": "Stale target",
            "expected_revision": current["revision"],
            "base_record_version_id": current["record_version_id"],
        }
        assert (
            http.post(path + "/decisions", headers=HEADERS, json=body).status_code
            == 422
        )
        retained = http.get(
            path
            + "/observations/"
            + obs["id"]
            + "/declarations?revision="
            + str(original["revision"]),
            headers=HEADERS,
        )
        assert (
            retained.status_code == 200
            and retained.json()["run_id"] == original["run"]["id"]
        )


def test_changed_declaration_artifact_blocks_approval(tmp_path):
    app = app_at(tmp_path)
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        ref = work["observations"][0]["declaration_evidence"]["blob_ref"]
        (tmp_path / "blobs" / ref).write_bytes(b"changed synthetic artifact")
        approved = http.post(
            path + "/decisions",
            headers=HEADERS,
            json={
                "kind": "approve",
                "reason": "Synthetic integrity test",
                "expected_revision": work["revision"],
                "base_record_version_id": work["record_version_id"],
            },
        )
        assert approved.status_code == 200
        assert approved.json()["disposition"] is None
        assert approved.json()["blocker"] == "evidence_integrity_failure"


def test_declaration_action_only_advertised_to_review_roles(tmp_path):
    from specimen_digitization.application.api import summary
    from specimen_digitization.application.domain import Scope
    from test_application import SYNTHETIC_ORG, SYNTHETIC_COLLECTION

    app = app_at(tmp_path)
    with TestClient(app) as http:
        row = intake(http)
        specimen = app.state.workflow.repository.get(
            Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION),
            row["specimen_id"],
        )
        for role in ("viewer", "operator"):
            assert (
                "reading_metadata" not in summary(specimen, role)["available_actions"]
            )
        for role in ("reviewer", "manager", "admin"):
            assert "reading_metadata" in summary(specimen, role)["available_actions"]


def label_for(*groups):
    """Run the label policy over one region holding the given declaration groups."""
    region = SimpleNamespace(id="region-1")
    specimen = SimpleNamespace(
        run=SimpleNamespace(
            id="run-1",
            regions=[region],
            profile=SimpleNamespace(language_handling=LanguageHandling()),
        )
    )
    return label_handling(specimen, {region.id: list(groups)})["labels"][0]


@pytest.mark.parametrize(
    "first,second,conflicting",
    [
        (("en",), ("English",), False),
        (("English",), ("english",), False),
        (("eng",), ("English",), False),
        (("en-US",), ("English",), False),
        (("en_GB",), ("eng",), False),
        (("en", "English"), ("English",), False),
        (("deu",), ("German",), False),
        (("en",), ("fr",), True),
        (("English",), ("French",), True),
        (("en",), ("French",), True),
        (("English",), ("Sundanese",), True),
    ],
)
def test_reader_vocabulary_does_not_fake_a_language_conflict(
    first, second, conflicting
):
    """Two routes naming one language differently is not a disagreement."""
    label = label_for(
        DeclarationCandidates(language_candidates=first, script_candidates=("Latin",)),
        DeclarationCandidates(language_candidates=second, script_candidates=("Latin",)),
    )
    assert label["conflicting_candidates"] is conflicting
    assert label["review_required"] is conflicting
    assert label["language_candidates"] == sorted({*first, *second})


def test_one_reader_spelling_a_language_two_ways_is_not_ambiguous():
    label = label_for(DeclarationCandidates(language_candidates=("en", "English")))
    assert not label["conflicting_candidates"]
    assert label["language_candidates"] == ["English", "en"]


@pytest.mark.parametrize(
    "candidates,relation,mixed,conflicting",
    [
        (("English", "German"), "cooccurring", True, False),
        (("English", "German"), "alternatives", False, True),
        (("English", "German"), "unspecified", False, True),
        (("en", "English"), "alternatives", False, True),
        (("en", "English"), "cooccurring", True, False),
    ],
)
def test_declared_relations_are_never_folded_away(
    candidates, relation, mixed, conflicting
):
    """An explicit reader declaration outranks any equivalence of label forms."""
    label = label_for(
        DeclarationCandidates(
            language_candidates=candidates, language_relation=relation
        )
    )
    assert label["mixed_declared"] is mixed
    assert label["conflicting_candidates"] is conflicting


@pytest.mark.parametrize(
    "label,key",
    [
        ("en", "english"),
        ("ENG", "english"),
        ("  English  ", "english"),
        ("en-US", "english"),
        ("pt_BR", "portuguese"),
        ("Kiswahili", "kiswahili"),
        ("Old English", "old english"),
    ],
)
def test_language_key_folds_known_vocabulary_and_leaves_the_rest_distinct(label, key):
    assert language_key(label) == key


def test_dual_route_vocabulary_split_does_not_force_review(tmp_path):
    """The observed dual-read symptom, through the whole stored evidence path."""
    with TestClient(app_at(tmp_path, "vocabulary")) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        label = work["run"]["label_language_handling"]["labels"][0]
        assert not label["conflicting_candidates"] and not label["mixed_declared"]
        assert not label["review_required"] and label["reasons"] == []
        declared = set()
        for obs in work["observations"]:
            metadata = http.get(
                path + "/observations/" + obs["id"] + "/metadata", headers=HEADERS
            ).json()
            declared.update(
                item["value"]
                for item in metadata["declarations"]
                if item["kind"] == "language"
            )
        assert declared == {"en", "English"}
        assert label["language_candidates"] == ["English", "en"]


def test_reviewer_restating_a_declaration_is_not_a_second_candidate(tmp_path):
    """Model and human vocabularies merge into one observation; both are retained."""
    with TestClient(app_at(tmp_path, "vocabulary")) as http:
        row = intake(http)
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()

        def metadata_for(observation_id):
            return http.get(
                path + "/observations/" + observation_id + "/metadata", headers=HEADERS
            ).json()

        # The route that declared the coded form; the reviewer restates it in words.
        target = [
            o["id"]
            for o in work["observations"]
            if any(d["value"] == "en" for d in metadata_for(o["id"])["declarations"])
        ]
        assert len(target) == 1
        response = http.post(
            path + "/decisions",
            headers={**HEADERS, "Idempotency-Key": "reviewer-vocabulary"},
            json={
                "kind": "reading_metadata",
                "target_id": target[0],
                "after": {
                    "language_candidates": ["English"],
                    "script_candidates": ["Latn"],
                },
                "reason": "Reviewer restating the declared label",
                "expected_revision": work["revision"],
                "base_record_version_id": work["record_version_id"],
            },
        )
        assert response.status_code == 200, response.text[:500]
        metadata = metadata_for(target[0])
        assert metadata["language_state"] == "declared"
        assert metadata["script_state"] == "declared"
        assert metadata["reasons"] == []
        assert {(d["kind"], d["value"]) for d in metadata["declarations"]} == {
            ("language", "en"),
            ("language", "English"),
            ("script", "Latin"),
            ("script", "Latn"),
        }
        label = response.json()["run"]["label_language_handling"]["labels"][0]
        assert not label["conflicting_candidates"] and not label["review_required"]
