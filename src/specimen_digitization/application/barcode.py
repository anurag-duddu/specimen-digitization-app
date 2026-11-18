"""The slide's QR code: decoded once, in the workflow's segment step, and stored as evidence.

The catalogue number of a Field Museum insect slide is printed on its barcode label
twice: as digits after "FMNHINS", and as a QR code (Model 2, version 1, numeric; its
payload is the seven digits alone). The readers read the digits, which are about 12
pixels high on a flatbed scan and are misread ("4486518" for "4486618"); the code is
not, as its error correction either restores what was printed or decodes nothing.
Lane V2 of the autonomy program (2026-11-17, off-repo notes) measured this decoder on
100 real slides: 98 decoded, every one equal to the truth set's catalogue number, none
wrong; restricted to QR Code Model 2 with exactly seven digits, none wrong in 300,000
damaged synthetic codes either (a looser format setting found Micro QR codes in the
damage).

`record` runs in the segment step, where the specimen's canonical pixels are at hand.
It never raises and never calls a network: anything that goes wrong, or a slide whose
decode breaks the acceptance rule, stores nothing, and the run goes on exactly as it
would have without a decoder. A decode it accepts is one evidence row on the run (kind
"derived", source SOURCE, locator LOCATOR), whose excerpt names the number, the decoder
and its version and the ladder rung that first decoded it, and whose stored record holds
every symbol it found. Field research reads it back for the catalogue number alone
(stored_code; field_research/catalogue_code.py).

The acceptance rule, every part of it required:
- the decoder is zxing-cpp, asked for QR Code Model 2 only, and each symbol it returns is
  a valid QR Code (not Micro QR, not rMQR), of a version that is a number;
- each symbol's text is exactly seven digits;
- every symbol found on every rung of the ladder has the same text;
- one and the same label region of the slide holds every symbol's centre (a code on no label,
  such as a neighbouring slide's in the scan, is no decode).
A missing decoder is logged once a process at warning level and decodes nothing;
research_harness.package_qualification checks the pinned version (DECODER_PIN) where the
application images check their packages.
The ladder: the whole image and the image in grey with a light contrast stretch (2 % cut
at each end), each at its own size, then at twice and at three times it; a rung larger than MAX_PIXELS is skipped, so
the work is bounded by the image and never by a clock.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass

from .domain import Evidence

LOGGER = logging.getLogger(__name__)

FIELD = "fmnh_ins_number"
SOURCE = "barcode"
KIND = "derived"
LOCATOR = "check:barcode_decode"
DECODER = "zxing-cpp"
# The version pyproject.toml pins.
DECODER_PIN = "3.1.1"
SYMBOLOGY = "QRCodeModel2"
PAYLOAD = re.compile(r"[0-9]{7}")
# A rung's image is decoded only up to this many pixels (a 1,780 by 600 slide scan at three
# times its size is 9.6 million).
MAX_PIXELS = 24_000_000
# zxing-cpp reads an image's luminance, so a plain grey rung would be the whole rung again;
# the grey one here is stretched.
RUNGS = ("whole", "gray_stretch", "whole_x2", "gray_stretch_x2", "whole_x3", "gray_stretch_x3")
# The excerpt names the number first, so field research reads it without the stored record.
EXCERPT = "{field}: {payload} (QR code read by {decoder} {version}, ladder rung {rung})"
_EXCERPT = re.compile(r"fmnh_ins_number: (?P<payload>[0-9]{7}) \(QR code read by ")


@dataclass(frozen=True)
class Symbol:
    """One symbol a rung found: its text, its box in the source image's pixels
    (left, top, right, bottom), its version and error-correction level as the decoder
    reports them, and the share of the error correction it left unused (zxing-cpp's
    "UEC", 1.0 when no codeword was corrected)."""

    rung: str
    text: str
    box: tuple[int, int, int, int]
    version: str
    ec_level: str
    unused_correction: float | None


@dataclass(frozen=True)
class Decode:
    """An accepted decode: the payload, the decoder and its version, the first rung that
    found it, every symbol found, and the label (region id) whose box holds the first
    symbol's centre, when exactly one does."""

    payload: str
    decoder: str
    decoder_version: str
    symbology: str
    rung: str
    symbols: tuple[Symbol, ...]
    region_id: str | None


def decoder_version() -> str | None:
    """The installed zxing-cpp's version, or None when it is not installed."""
    try:
        from importlib.metadata import version

        return version("zxing-cpp")
    except Exception:  # noqa: BLE001 - no decoder is no decode
        return None


def _rungs(image) -> Iterator[tuple[str, int, object]]:
    """(name, scale, image) for each rung of the ladder, made only when it is reached."""
    from PIL import Image, ImageOps

    base = image if image.mode in ("L", "RGB") else image.convert("RGB")
    gray = base.convert("L")
    looks = {"whole": base, "gray_stretch": ImageOps.autocontrast(gray, cutoff=2)}
    for name in RUNGS:
        look, _, times = name.partition("_x")
        scale = int(times) if times else 1
        width, height = base.size[0] * scale, base.size[1] * scale
        if width * height > MAX_PIXELS:
            continue
        source = looks[look]
        yield name, scale, source if scale == 1 else source.resize((width, height), Image.Resampling.BICUBIC)


def _box(position, scale: int) -> tuple[int, int, int, int]:
    xs = [point.x for point in (position.top_left, position.top_right, position.bottom_right, position.bottom_left)]
    ys = [point.y for point in (position.top_left, position.top_right, position.bottom_right, position.bottom_left)]
    return (min(xs) // scale, min(ys) // scale, -(-max(xs) // scale), -(-max(ys) // scale))


def _symbols(image) -> list[Symbol] | None:
    """Every symbol of every rung, or None when one breaks the acceptance rule's first two
    parts (a symbol that is no valid QR Code Model 2, or whose text is not seven digits)."""
    import zxingcpp

    found = []
    for rung, scale, look in _rungs(image):
        for result in zxingcpp.read_barcodes(look, formats=zxingcpp.BarcodeFormat.QRCodeModel2):
            extra = dict(result.extra or {})
            version = str(extra.get("Version", ""))
            if (not result.valid or result.format != zxingcpp.BarcodeFormat.QRCode
                    or not version.isdigit() or not PAYLOAD.fullmatch(result.text or "")):
                return None
            unused = extra.get("UEC")
            found.append(Symbol(rung=rung, text=result.text, box=_box(result.position, scale), version=version,
                ec_level=str(extra.get("ECLevel", result.ec_level or "")),
                unused_correction=float(unused) if isinstance(unused, (int, float)) else None))
    return found


def _regions_holding(box: tuple[int, int, int, int], regions: Sequence) -> set[str]:
    """The labels whose boxes hold the symbol's centre."""
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return {region.id for region in regions
        if region.x <= x < region.x + region.width and region.y <= y < region.y + region.height}


def _label_of(symbols: Sequence[Symbol], regions: Sequence) -> str | None:
    """The one label whose box holds every symbol's centre, or None: a code on none of the
    slide's labels (a neighbour's slide in the scan, say), or on more than one, is no decode."""
    common = set.intersection(*(_regions_holding(symbol.box, regions) for symbol in symbols))
    return next(iter(common)) if len(common) == 1 else None


_MISSING_LOGGED = False


def _missing_decoder() -> None:
    """Log, once a process, that no decoder is installed: the feature is off for every record."""
    global _MISSING_LOGGED
    if not _MISSING_LOGGED:
        _MISSING_LOGGED = True
        LOGGER.warning("barcode decoder zxing-cpp is not installed: no slide's QR code is decoded")


def decode(image, regions: Sequence = ()) -> Decode | None:
    """The image's accepted decode (the module's acceptance rule), on the one label of
    `regions` that holds every symbol's centre; or None. Never raises."""
    version = decoder_version()
    if version is None:
        _missing_decoder()
        return None
    try:
        symbols = _symbols(image)
    except Exception:  # noqa: BLE001 - a decoder failure is no decode
        LOGGER.warning("barcode decode failed", exc_info=True)
        return None
    if not symbols or len({symbol.text for symbol in symbols}) != 1:
        return None
    if (label := _label_of(symbols, regions)) is None:
        return None
    first = symbols[0]
    return Decode(payload=first.text, decoder=DECODER, decoder_version=version, symbology=SYMBOLOGY,
        rung=first.rung, symbols=tuple(symbols), region_id=label)


def evidence_row(found: Decode, asset_id: str, blobs) -> Evidence:
    """The decode as the run's evidence row; its stored record holds the whole decode."""
    record = json.dumps({"field_key": FIELD, **asdict(found)}, sort_keys=True).encode()
    return Evidence(kind=KIND, asset_id=asset_id, region_id=found.region_id, source=SOURCE, locator=LOCATOR,
        excerpt=EXCERPT.format(field=FIELD, payload=found.payload, decoder=found.decoder,
            version=found.decoder_version, rung=found.rung),
        raw_ref=blobs.put(record), digest=hashlib.sha256(record).hexdigest())


def is_code_row(row: Evidence) -> bool:
    return row.kind == KIND and row.source == SOURCE and row.locator == LOCATOR


def record(run, specimen, blobs) -> Evidence | None:
    """Decode the specimen's canonical pixels and store an accepted decode as the run's one
    code row, replacing any earlier one (a segment step done again); the row, or None.
    Never raises: a failure anywhere stores nothing."""
    try:
        from .source_pixels import source_image

        run.evidence[:] = [row for row in run.evidence if not is_code_row(row)]
        with source_image(specimen.asset, blobs) as image:
            found = decode(image, run.regions)
        if found is None:
            return None
        row = evidence_row(found, specimen.asset.id, blobs)
        run.evidence.append(row)
        return row
    except Exception:  # noqa: BLE001 - the segment step never fails on the decoder
        LOGGER.warning("barcode decode not stored", exc_info=True)
        return None


@dataclass(frozen=True)
class StoredCode:
    """The run's code row and the payload its excerpt names."""

    row: Evidence
    payload: str


def stored_code(run) -> StoredCode | None:
    """The run's one code row (record), or None: none, more than one, or one whose excerpt
    names no seven-digit number."""
    rows = [row for row in getattr(run, "evidence", None) or () if is_code_row(row)]
    if len(rows) != 1 or (match := _EXCERPT.match(rows[0].excerpt)) is None:
        return None
    return StoredCode(rows[0], match["payload"])
