"""The export-only PNG codec is fixed bytes; production still encodes its views."""

import ast
import binascii
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import sys
from unittest.mock import patch
import zlib

from PIL import Image
import pytest


def load_exporter():
    # PYTHONPATH also lets external mutation qualification select its copied
    # exporter. The runner separately verifies the imported source identity.
    try:
        spec = importlib.util.find_spec('scripts.ci.export_general_api_contract_fixtures')
    except ModuleNotFoundError:
        # The pytest entry point need not put the repository root on sys.path.
        path = Path(__file__).resolve().parents[1] / 'scripts/ci/export_general_api_contract_fixtures.py'
        spec = importlib.util.spec_from_file_location('general_api_seam_exporter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def exporter():
    # Each test owns its module; no mutable exporter fixture crosses tests.
    return load_exporter()


def writer(exporter):
    result = getattr(exporter, '_stored_png', None)
    assert callable(result), 'Exporter needs the portable _stored_png encoder seam'
    return result


def pixels(size):
    return bytes(index % 256 for index in range(size[0] * size[1] * 3))


@pytest.mark.parametrize('size,expected', [
    # pragma: allowlist nextline secret -- Fixed synthetic pixel PNG SHA-256.
    ((2, 2), '664fc93c785dc4c415cee8fde6f7e0ff2c0a5d5b706c8654bde19c935862dceb'),
    # pragma: allowlist nextline secret -- Fixed multiblock synthetic PNG SHA-256.
    ((257, 90), '8e0c464a58e062943c1ecc148598c3b2f14d840852cf02782fd0298e4e90cc6f'),
])
def test_stored_png_fixed_bytes_and_exact_pixels(exporter, size, expected):
    source = pixels(size)
    encoded = writer(exporter)(Image.frombytes('RGB', size, source))
    assert hashlib.sha256(encoded).hexdigest() == expected, 'Portable PNG bytes changed'
    with Image.open(io.BytesIO(encoded)) as decoded:
        assert decoded.format == 'PNG'
        assert decoded.mode == 'RGB'
        assert decoded.size == size
        assert decoded.tobytes() == source, 'Portable encoder changed input pixels'

    # Inspect the actual container and block headers, independently of Pillow.
    assert encoded[:8] == b'\x89PNG\r\n\x1a\n'
    chunks = []
    offset = 8
    while offset < len(encoded):
        length = int.from_bytes(encoded[offset:offset + 4], 'big')
        tag = encoded[offset + 4:offset + 8]
        data = encoded[offset + 8:offset + 8 + length]
        crc = int.from_bytes(encoded[offset + 8 + length:offset + 12 + length], 'big')
        assert crc == binascii.crc32(tag + data), 'PNG chunk checksum mismatch'
        chunks.append((tag, data))
        offset += length + 12
    assert offset == len(encoded)
    assert [tag for tag, _ in chunks] == [b'IHDR', b'IDAT', b'IEND']
    assert chunks[0][1] == struct.pack('>IIBBBBB', *size, 8, 2, 0, 0, 0)
    assert chunks[2][1] == b''
    stream = chunks[1][1]
    assert stream[:2] == b'\x78\x01', 'Expected the fixed no-compression zlib header'
    raw = b''.join(b'\0' + source[row * size[0] * 3:(row + 1) * size[0] * 3]
                   for row in range(size[1]))
    offset = 2
    for start in range(0, len(raw), 65535):
        block = raw[start:start + 65535]
        assert stream[offset] == int(start + 65535 >= len(raw)), 'Expected STORED BTYPE 00'
        assert struct.unpack('<HH', stream[offset + 1:offset + 5]) == (len(block), 65535 - len(block))
        assert stream[offset + 5:offset + 5 + len(block)] == block
        offset += 5 + len(block)
    assert stream[offset:] == struct.pack('>I', zlib.adler32(raw))


@pytest.fixture(scope='module')
def journey(tmp_path_factory):
    exporter = load_exporter()
    encode = writer(exporter)
    calls = []
    original_save = Image.Image.save
    sample = Image.frombytes('RGB', (2, 2), pixels((2, 2)))
    before = io.BytesIO()
    sample.save(before, format='PNG')

    def observe(image):
        frame = sys._getframe(1)
        sites = []
        while frame:
            sites.append((Path(frame.f_code.co_filename).name, frame.f_code.co_name))
            frame = frame.f_back
        result = encode(image)
        calls.append((tuple(sites), result))
        return result

    try:
        with patch.object(exporter, '_stored_png', observe):
            wire = exporter.export_fixture_bytes(tmp_path_factory.mktemp('portable-wire'))
        restored = Image.Image.save is original_save
        after = io.BytesIO()
        native_encoders = []
        getencoder = Image._getencoder

        def observe_native(mode, name, *args, **kwargs):
            native_encoders.append(name)
            return getencoder(mode, name, *args, **kwargs)

        with patch.object(Image, '_getencoder', observe_native):
            sample.save(after, format='PNG')
        return wire, tuple(calls), restored, before.getvalue(), after.getvalue(), tuple(native_encoders)
    finally:
        # A broken implementation must fail without poisoning subsequent tests.
        Image.Image.save = original_save


def test_export_observes_production_orientation_and_region_encodes(journey):
    _, calls, *_ = journey
    for site in [('image_quality.py', 'orientation_view'), ('region_pixels.py', 'region_png')]:
        matched = [encoded for stack, encoded in calls if site in stack]
        assert matched, f'Production {site[1]} must still call the PNG encoder seam'
        assert all(encoded.startswith(b'\x89PNG') for encoded in matched)


def test_export_restores_normal_pillow_png_codec(journey):
    _, _, restored, before, after, encoders = journey
    assert restored, 'Exporter leaked the Image.save seam beyond its context'
    assert 'zip' in encoders, 'Pillow PNG save after export must use its normal encoder'
    assert after == before, 'Pillow PNG encoding changed outside the export context'


def test_export_restores_codec_when_encoding_raises(exporter, tmp_path):
    writer(exporter)
    original_save = Image.Image.save

    def fail(image):
        raise RuntimeError('deliberate encoder failure')

    try:
        with patch.object(exporter, '_stored_png', fail):
            with pytest.raises(RuntimeError, match='deliberate encoder failure'):
                exporter.export_fixture_bytes(tmp_path / 'failed-export')
        assert Image.Image.save is original_save, 'Failed export leaked its codec seam'
    finally:
        Image.Image.save = original_save


def test_writer_and_export_never_use_a_compressor(exporter, monkeypatch, tmp_path):
    writer(exporter)
    tree = ast.parse(Path(exporter.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'zlib':
            assert not {'compress', 'compressobj'} & {alias.name for alias in node.names}, (
                'Exporter must not import a compressor, including under an alias')

    def forbidden(*args, **kwargs):
        pytest.fail('Portable PNG writer/export called a compressor')

    monkeypatch.setattr(zlib, 'compress', forbidden)
    monkeypatch.setattr(zlib, 'compressobj', forbidden)
    getencoder = Image._getencoder

    def no_native_compression(mode, name, *args, **kwargs):
        assert name == 'raw', f'Export reached a platform encoder: {name}'
        return getencoder(mode, name, *args, **kwargs)

    monkeypatch.setattr(Image, '_getencoder', no_native_compression)
    # Install guards before loading too, so a compressor alias cannot have
    # captured an unguarded function during exporter import.
    exporter = load_exporter()
    encode = writer(exporter)
    encode(Image.frombytes('RGB', (2, 2), pixels((2, 2))))
    exporter.export_fixture_bytes(tmp_path / 'no-compressor')


def test_seam_only_intercepts_png_and_restores_on_exit(exporter):
    seam = getattr(exporter, '_portable_png_encoder', None)
    assert callable(seam), 'Exporter needs a scoped _portable_png_encoder context manager'
    sample = Image.frombytes('RGB', (2, 2), pixels((2, 2)))
    original = Image.Image.save
    before = io.BytesIO()
    sample.save(before, format='BMP')
    with seam():
        png = io.BytesIO()
        sample.save(png, format='PNG')
        assert png.getvalue() == writer(exporter)(sample)
        bmp = io.BytesIO()
        sample.save(bmp, format='BMP')
        assert bmp.getvalue() == before.getvalue(), 'Seam changed a non-PNG save'
    assert Image.Image.save is original
