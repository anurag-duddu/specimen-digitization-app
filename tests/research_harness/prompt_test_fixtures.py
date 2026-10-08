"""Explicit current pins and retained text for historical prompt audit tests."""
from pathlib import Path

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, SpecialistRole

ACTIVE_PROMPTS = {
    SpecialistRole.TAXONOMY: ("specimen_taxonomy-v7.txt", "taxonomy-reader-reconciliation-v7-2026-10-07"),
    SpecialistRole.GEOGRAPHY: ("specimen_geography-v9.txt", "geography-research-loop-v9-2026-10-07"),
    SpecialistRole.TEMPORAL: ("specimen_temporal-v8.txt", "temporal-event-links-v8-2026-10-07"),
    SpecialistRole.MEASUREMENT: ("specimen_measurement-v10.txt", "measurement-evidence-v10-2026-10-07"),
    SpecialistRole.PARTIES: ("specimen_parties-v6.txt", "parties-role-evidence-v6-2026-10-07"),
    SpecialistRole.COLLECTION: ("specimen_collection-v6.txt", "collection-qualified-evidence-v6-2026-10-07"),
}
ACTIVE_ROLE_DIGESTS = {
    SpecialistRole.TAXONOMY: "ba33889e495c286e089b517366117c5167e788283d8a44eaae02ca14b3a6fc72",  # pragma: allowlist secret
    SpecialistRole.GEOGRAPHY: "dcab62c201542e53d11e51c93269cb1a6391b2fcb5235a882290bee6b4303277",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "9ab59d117839d45b79d9ad7a7658218b0506514da3fa07e344385ef2c7ceefa2",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "b745c0dae603f181182fbf95ffc47fd50d29a05b69e23f0bd30df0ad83506111",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "6d281d2f407e3df3270aa2b715ab184775368e51c00c15a94d0b2299baa81df8",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "c8be41841669a1e9cfb0c21bf435ecc9e78db7925e0132031f64eb924637ebeb",  # pragma: allowlist secret
}


def retained_text(role, version):
    """Read the immutable historical pin, without changing the active resolver."""
    path = Path(prompts.__file__).parent
    return ((path / "common-v1.txt").read_text(encoding="utf-8") + "\n"
        + (path / f"{role.value}-v{version}.txt").read_text(encoding="utf-8")
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n")
