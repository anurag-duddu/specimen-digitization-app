"""Explicit current pins and retained text for historical prompt audit tests."""
from pathlib import Path

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, SpecialistRole

ACTIVE_PROMPTS = {
    SpecialistRole.TAXONOMY: ("specimen_taxonomy-v7.txt", "taxonomy-reader-reconciliation-v7-2026-10-07"),
    SpecialistRole.GEOGRAPHY: ("specimen_geography-v10.txt", "geography-progress-batch-v10-2026-10-08"),
    SpecialistRole.TEMPORAL: ("specimen_temporal-v8.txt", "temporal-event-links-v8-2026-10-07"),
    SpecialistRole.MEASUREMENT: ("specimen_measurement-v10.txt", "measurement-evidence-v10-2026-10-07"),
    SpecialistRole.PARTIES: ("specimen_parties-v7.txt", "parties-original-reading-v7-2026-10-08"),
    SpecialistRole.COLLECTION: ("specimen_collection-v7.txt", "collection-original-reading-v7-2026-10-08"),
}
ACTIVE_ROLE_DIGESTS = {
    SpecialistRole.TAXONOMY: "ba33889e495c286e089b517366117c5167e788283d8a44eaae02ca14b3a6fc72",  # pragma: allowlist secret
    SpecialistRole.GEOGRAPHY: "4b7ca0c8a7632342b2cd58ee9413e03651b1d4aef81bb5a369b85268fa4ef592",  # pragma: allowlist secret
    SpecialistRole.TEMPORAL: "9ab59d117839d45b79d9ad7a7658218b0506514da3fa07e344385ef2c7ceefa2",  # pragma: allowlist secret
    SpecialistRole.MEASUREMENT: "b745c0dae603f181182fbf95ffc47fd50d29a05b69e23f0bd30df0ad83506111",  # pragma: allowlist secret
    SpecialistRole.PARTIES: "10c577e9a8927527d50658b3e4e64fecb759b4e2f0ca381c677b833bfb9cdb9f",  # pragma: allowlist secret
    SpecialistRole.COLLECTION: "0b4175ecce82d37af4fc5b844157d6c6273ac4bda2c96f7529378cc6dc979558",  # pragma: allowlist secret
}


def retained_text(role, version):
    """Read the immutable historical pin, without changing the active resolver."""
    path = Path(prompts.__file__).parent
    return ((path / "common-v1.txt").read_text(encoding="utf-8") + "\n"
        + (path / f"{role.value}-v{version}.txt").read_text(encoding="utf-8")
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n")
