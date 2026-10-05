"""Bounded reads of committed georeferencing objects using the worker identity."""
from __future__ import annotations

from specimen_digitization.application.worker_deadline import deadline_call
from .persistence import HeldUnknown


class GcsPinnedDatasetReader:
    """Reuse the canonical blob store, including its authenticated bounded reader.

    Object metadata supplies only a generation to pin. The committed manifest,
    then the returned bytes, supply the scientific identity. No source URL is
    requested and missing objects have no download fallback.
    """

    def __init__(self, graph_blobs):
        self.graph_blobs = graph_blobs

    def __call__(self, entry):
        from specimen_digitization.application.georef_datasets import Dataset, dataset, verified

        if type(entry) is not Dataset:
            raise HeldUnknown("georeference_dataset_pin_unproved")
        try:
            canonical = dataset(entry.id)
        except KeyError:
            raise HeldUnknown("georeference_dataset_pin_unproved") from None
        if (entry != canonical or entry.object_name != "application/sha256/" + entry.sha256
            or type(entry.size) is not int or not 0 < entry.size <= 64 * 1024 * 1024):
            raise HeldUnknown("georeference_dataset_pin_unproved")
        blob = self.graph_blobs.bucket.blob(entry.object_name)
        deadline_call(blob.reload, timeout=30, retry=None)
        generation = str(blob.generation)
        if (type(blob.size) is not int or blob.size != entry.size
            or not generation.isdecimal() or int(generation) <= 0):
            raise HeldUnknown("georeference_dataset_object_unproved")
        # GcsBlobs pins the generation in a streamed, no-redirect media GET,
        # reads at most size+1 bytes, and independently verifies the digest.
        data = self.graph_blobs.get_bounded(f"{entry.sha256}:{generation}", entry.size)
        return verified(canonical, data)
