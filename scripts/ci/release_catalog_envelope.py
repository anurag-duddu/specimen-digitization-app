"""Encrypt exact private catalog bytes for public artifacts; no filesystem or CLI.

Only a coordinator-provided, reviewed public key enters the runner. Decryption
is for local coordination and is refused in GitHub Actions. This envelope gives
confidentiality and tamper detection, not producer authentication: the caller
must still verify the artifact's protected-workflow attestation and provenance.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re

from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = "specimen-catalog-envelope/v1"
ALGORITHM = "RSA-OAEP-SHA256+A256GCM"
REPOSITORY = "anurag-duddu/specimen-digitization-app"
MAX_CATALOG_BYTES = 4 * 1024 * 1024
MAX_PUBLIC_KEY_BYTES = 4096
MAX_PRIVATE_KEY_BYTES = 16384
_HEADER_KEYS = {"version", "algorithm", "public_key_sha256", "provenance",
                "plaintext_sha256", "plaintext_size"}
_ENVELOPE_KEYS = _HEADER_KEYS | {"wrapped_key_b64", "nonce_b64", "ciphertext_b64"}


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("invalid catalog envelope input")


def _digest(value: str) -> None:
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None)


def _provenance(value: dict) -> dict:
    _require(type(value) is dict and set(value) == {
        "repository", "source_sha", "run_id", "run_attempt"})
    _require(value["repository"] == REPOSITORY)
    _require(type(value["source_sha"]) is str
             and re.fullmatch(r"[0-9a-f]{40}", value["source_sha"]) is not None)
    for name in ("run_id", "run_attempt"):
        _require(type(value[name]) is int and 1 <= value[name] <= 2**63 - 1)
    return dict(value)


def _rsa_key(key: rsa.RSAPublicKey) -> None:
    _require(isinstance(key, rsa.RSAPublicKey) and 3072 <= key.key_size <= 8192)
    _require(key.public_numbers().e == 65537)


def _public_bytes(key: rsa.RSAPublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.PEM,
                            serialization.PublicFormat.SubjectPublicKeyInfo)


def _public_key(public_key_pem: bytes, public_key_sha256: str) -> rsa.RSAPublicKey:
    _digest(public_key_sha256)
    _require(type(public_key_pem) is bytes and 1 <= len(public_key_pem) <= MAX_PUBLIC_KEY_BYTES)
    _require(hashlib.sha256(public_key_pem).hexdigest() == public_key_sha256)
    try:
        key = serialization.load_pem_public_key(public_key_pem)
        _rsa_key(key)
        # One pinned encoding; reject trailers, extra PEM blocks and alternate keys.
        _require(_public_bytes(key) == public_key_pem)
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise ValueError("invalid catalog recipient public key") from None
    return key


def validate_public_key(public_key_pem: bytes, public_key_sha256: str) -> None:
    """Require pinned canonical SPKI PEM, RSA3072+ and exponent 65537."""
    _public_key(public_key_pem, public_key_sha256)


def _aad(header: dict) -> bytes:
    return json.dumps(header, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _oaep() -> padding.OAEP:
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                        algorithm=hashes.SHA256(), label=None)


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: str, minimum: int, maximum: int) -> bytes:
    _require(type(value) is str and 1 <= len(value) <= 4 * ((maximum + 2) // 3))
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("invalid catalog envelope encoding") from None
    _require(minimum <= len(decoded) <= maximum and _encode(decoded) == value)
    return decoded


def encrypt_catalog(catalog_bytes: bytes, public_key_pem: bytes, *,
                    public_key_sha256: str, provenance: dict) -> dict:
    """Return only an authenticated metadata header and ciphertext fields.

    The caller must publish this envelope instead of raw observations, including
    failure observations. No private key, raw catalog or exception detail is
    logged or written by this function. Exact input bytes are not reserialized.
    """
    _require(type(catalog_bytes) is bytes and 1 <= len(catalog_bytes) <= MAX_CATALOG_BYTES)
    key = _public_key(public_key_pem, public_key_sha256)
    header = {"version": VERSION, "algorithm": ALGORITHM,
              "public_key_sha256": public_key_sha256, "provenance": _provenance(provenance),
              "plaintext_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
              "plaintext_size": len(catalog_bytes)}
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(data_key).encrypt(nonce, catalog_bytes, _aad(header))
    return {**header, "wrapped_key_b64": _encode(key.encrypt(data_key, _oaep())),
            "nonce_b64": _encode(nonce), "ciphertext_b64": _encode(ciphertext)}


def decrypt_catalog(envelope: dict, private_key_pem: bytes, *,
                    public_key_sha256: str, provenance: dict) -> bytes:
    """Local coordinator only; authenticate expected recipient and provenance.

    The caller must parse bounded artifact JSON with duplicate-key rejection
    and verify its workflow attestation before using this cryptographic helper.
    Only unencrypted in-memory PKCS8/PEM key bytes are accepted here; key-file
    protection and any local password prompt belong to the coordinator.
    """
    _require(os.environ.get("GITHUB_ACTIONS", "").lower() != "true")
    _digest(public_key_sha256)
    expected = _provenance(provenance)
    _require(type(envelope) is dict and set(envelope) == _ENVELOPE_KEYS)
    _require(envelope["version"] == VERSION and envelope["algorithm"] == ALGORITHM)
    _require(envelope["public_key_sha256"] == public_key_sha256)
    _require(_provenance(envelope["provenance"]) == expected)
    _digest(envelope["plaintext_sha256"])
    size = envelope["plaintext_size"]
    _require(type(size) is int and 1 <= size <= MAX_CATALOG_BYTES)
    header = {name: envelope[name] for name in _HEADER_KEYS}
    nonce = _decode(envelope["nonce_b64"], 12, 12)
    wrapped = _decode(envelope["wrapped_key_b64"], 384, 1024)
    ciphertext = _decode(envelope["ciphertext_b64"], size + 16, size + 16)
    _require(type(private_key_pem) is bytes and 1 <= len(private_key_pem) <= MAX_PRIVATE_KEY_BYTES)
    try:
        key = serialization.load_pem_private_key(private_key_pem, password=None)
        _require(isinstance(key, rsa.RSAPrivateKey))
        public = key.public_key()
        _rsa_key(public)
        _require(hashlib.sha256(_public_bytes(public)).hexdigest() == public_key_sha256)
        _require(len(wrapped) == (key.key_size + 7) // 8)
        data_key = key.decrypt(wrapped, _oaep())
        _require(len(data_key) == 32)
        raw = AESGCM(data_key).decrypt(nonce, ciphertext, _aad(header))
        _require(len(raw) == size and hashlib.sha256(raw).hexdigest() == envelope["plaintext_sha256"])
    except (ValueError, TypeError, InvalidTag, UnsupportedAlgorithm):
        raise ValueError("catalog envelope authentication failed") from None
    return raw
