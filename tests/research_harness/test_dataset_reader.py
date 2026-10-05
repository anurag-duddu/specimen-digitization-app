"""Pinned reference bytes, generation custody, and production factory wiring."""
import hashlib
from dataclasses import replace
from types import ModuleType, SimpleNamespace
import sys

import pytest

from specimen_digitization.research_harness.dataset_reader import GcsPinnedDatasetReader
from specimen_digitization.research_harness.persistence import HeldUnknown

datasets = pytest.importorskip("specimen_digitization.application.georef_datasets")


@pytest.fixture
def reader(monkeypatch):
    payload = b"immutable dataset"
    entry = replace(datasets.MANIFEST[0], id="offline-known-dataset", size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest())
    monkeypatch.setitem(datasets._BY_ID, entry.id, entry)
    calls = []
    def reload(**kwargs):
        calls.append(("reload", kwargs))
    metadata = SimpleNamespace(size=entry.size, generation="12345", reload=reload)
    def blob(name):
        calls.append(("object", name))
        return metadata
    def get_bounded(ref, limit):
        calls.append(("read", ref, limit))
        return state.payload
    state = SimpleNamespace(entry=entry, metadata=metadata, payload=payload, calls=calls)
    state.blobs = SimpleNamespace(bucket=SimpleNamespace(blob=blob), get_bounded=get_bounded)
    state.reader = GcsPinnedDatasetReader(state.blobs)
    return state


def test_exact_object_generation_and_manifest_size_are_read(reader):
    assert reader.reader(reader.entry) == reader.payload
    assert reader.calls == [("object", reader.entry.object_name),
        ("reload", {"timeout": 30, "retry": None}),
        ("read", reader.entry.sha256 + ":12345", reader.entry.size)]


@pytest.mark.parametrize("change", [{"id": "unregistered"}, {"size": 1}, {"sha256": "0" * 64},
    {"source_url": "https://unregistered.invalid/dataset"}])
def test_caller_cannot_substitute_another_manifest_entry(reader, change):
    with pytest.raises(HeldUnknown, match="georeference_dataset_pin_unproved"):
        reader.reader(replace(reader.entry, **change))
    assert reader.calls == []


@pytest.mark.parametrize("metadata", [{"size": 1}, {"size": "17"}, {"generation": None},
    {"generation": "0"}, {"generation": "unproved"}])
def test_unproved_metadata_prevents_media_download(reader, metadata):
    for key, value in metadata.items():
        setattr(reader.metadata, key, value)
    with pytest.raises(HeldUnknown, match="georeference_dataset_object_unproved"):
        reader.reader(reader.entry)
    assert not any(call[0] == "read" for call in reader.calls)


@pytest.mark.parametrize("payload", [b"short", b"immutable dataseX", b"immutable dataset extra"])
def test_bytes_reverified_even_if_storage_reader_returns_unproved_content(reader, payload):
    reader.payload = payload
    with pytest.raises(datasets.DigestMismatch):
        reader.reader(reader.entry)


def test_missing_object_has_no_source_url_fallback(reader):
    def missing(**kwargs):
        raise FileNotFoundError("immutable object missing")
    reader.metadata.reload = missing
    with pytest.raises(FileNotFoundError):
        reader.reader(reader.entry)
    assert reader.calls == [("object", reader.entry.object_name)]


def test_runtime_adapter_uses_the_existing_scoped_worker_blob_store(reader, monkeypatch):
    from specimen_digitization.research_harness.production_runtime import _georeferencing_adapter
    module = ModuleType("specimen_digitization.research_harness.georeferencing")
    module.GeoreferencingAdapter = lambda read_dataset: SimpleNamespace(read_dataset=read_dataset)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    adapter = _georeferencing_adapter(SimpleNamespace(graph_blobs=reader.blobs))
    assert adapter.read_dataset.graph_blobs is reader.blobs
    assert adapter.read_dataset(reader.entry) == reader.payload
