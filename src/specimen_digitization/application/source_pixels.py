"""Load the retained canonical pixel basis without re-running optional codecs."""

import hashlib
import io
from PIL import Image
from .storage import Conflict


def source_image(asset, blobs):
    if asset.processing_derivative:
        metadata = asset.processing_derivative
        data = blobs.get_bounded(metadata["blob_ref"], 25 * 1024 * 1024)
        if (
            metadata["original_sha256"] != asset.sha256
            or hashlib.sha256(data).hexdigest() != metadata["derivative_sha256"]
        ):
            raise Conflict("Canonical pixels integrity failure")
    else:
        data = blobs.get_bounded(asset.blob_ref, 25 * 1024 * 1024)
    image = Image.open(io.BytesIO(data))
    image.load()
    if image.size != (asset.width, asset.height):
        image.close()
        raise Conflict("Canonical pixel dimensions mismatch")
    return image
