"""Shared validation for legacy upload completion and private draft staging."""
import io
import hashlib
from PIL import Image
from .image_quality import ImageLimits, orientation_view
from .workflow import OperationalBlock


def verify_photo(content, doc, blobs, codec_policy=None):
    processing = None
    pixel_basis = "original_pixel_edges"
    special = doc["media_type"] in {
        "image/heic",
        "image/heif",
        "image/dng",
        "image/x-adobe-dng",
    }
    if special:
        from .image_codecs import CodecPolicy, decode_image

        policy = codec_policy or CodecPolicy()
        family = (
            "HEIC" if doc["media_type"] in {"image/heic", "image/heif"} else "DNG"
        )
        result, derivative = decode_image(content, family, policy)
        if result.status == "blocked":
            raise OperationalBlock("image_codec_" + result.reason)
        if result.status != "decoded" or derivative is None:
            raise ValueError("Invalid image: " + result.reason)
        provenance = result.provenance
        if provenance.actual_format != family:
            raise ValueError("Decoded image family mismatch")
        # HEIF's primary raster is already container-oriented. DNG's retained
        # view must be inverted to its explicitly recorded active-area basis.
        with Image.open(io.BytesIO(derivative)) as displayed:
            canonical = displayed.convert("RGB")
            orientation = provenance.transform.orientation
            inverse = {
                2: Image.Transpose.FLIP_LEFT_RIGHT,
                3: Image.Transpose.ROTATE_180,
                4: Image.Transpose.FLIP_TOP_BOTTOM,
                5: Image.Transpose.TRANSPOSE,
                6: Image.Transpose.ROTATE_90,
                7: Image.Transpose.TRANSVERSE,
                8: Image.Transpose.ROTATE_270,
            }.get(orientation)
            if inverse is not None:
                canonical = canonical.transpose(inverse)
            dimensions = canonical.size
            pixels = io.BytesIO()
            canonical.save(pixels, format="PNG")
            canonical_bytes = pixels.getvalue()
        processing = dict(
            provenance.model_dump(mode="json"),
            blob_ref=blobs.put(canonical_bytes),
            derivative_sha256=hashlib.sha256(canonical_bytes).hexdigest(),
            canonicalization="inverse_view_affine_to_declared_pixel_basis",
        )
        pixel_basis = provenance.coordinate_space
        actual_type = "image/heic" if family == "HEIC" else "image/dng"
    else:
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                actual_type = Image.MIME.get(image.format)
                if actual_type not in {"image/png", "image/jpeg", "image/tiff"}:
                    raise ValueError("Image decoder format not supported")
                if actual_type != doc["media_type"]:
                    raise ValueError("Declared image media type mismatch")
                if image.width * image.height > 40000000 or max(image.size) > 20000:
                    raise ValueError("Decoded image resolution limit exceeded")
                image.load()
                dimensions = image.size
        except (
            OSError,
            SyntaxError,
            EOFError,
            Image.DecompressionBombError,
        ) as exc:
            raise ValueError("Invalid or truncated image content") from exc
        derivative, provenance = orientation_view(
            content, ImageLimits(allowed_formats=("JPEG", "PNG", "TIFF"))
        )
    if doc["width"] is not None and dimensions != (doc["width"], doc["height"]):
        raise ValueError("Declared image dimensions mismatch")

    view = dict(provenance.model_dump(mode="json"), blob_ref=blobs.put(derivative))
    return dict(media_type=actual_type, width=dimensions[0], height=dimensions[1],
                view_derivative=view, processing_derivative=processing,
                pixel_basis=pixel_basis, blob_ref=blobs.put(content))
