"""Catalog envelopes keep private bytes out of public release artifacts."""
import base64
import copy
import hashlib
import importlib
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import release_catalog_envelope as envelope


@pytest.fixture(autouse=True)
def local_coordinator_context(monkeypatch):
    # All test keys are newly generated synthetic keys. Production runner code
    # never receives a private key; local decrypt tests retain that API guard.
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)


@pytest.fixture(scope='module')
def recipient():
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    private = key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return key, public, private, hashlib.sha256(public).hexdigest()


@pytest.fixture
def provenance():
    return {'repository': 'anurag-duddu/specimen-digitization-app',
            'source_sha': 'a' * 40, 'run_id': 123, 'run_attempt': 1}


@pytest.fixture
def sealed(recipient, provenance):
    return envelope.encrypt_catalog(b' { "private_role": "SYNTHETIC_CANARY" }\n', recipient[1],
                                    public_key_sha256=recipient[3], provenance=provenance)


def open_catalog(value, recipient, provenance):
    return envelope.decrypt_catalog(value, recipient[2], public_key_sha256=recipient[3],
                                    provenance=provenance)


def test_catalog_ciphertext_hides_canary_and_recovers_exact_bytes():
    envelope = importlib.import_module('release_catalog_envelope')
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    private = key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    key_sha = hashlib.sha256(public).hexdigest()
    provenance = {'repository': 'anurag-duddu/specimen-digitization-app',
                  'source_sha': 'a' * 40, 'run_id': 123, 'run_attempt': 1}
    raw = b'{ "roles": ["PRIVATE_CATALOG_CANARY_672951"], "acl": "owner=arwd" }\n'
    sealed = envelope.encrypt_catalog(raw, public, public_key_sha256=key_sha,
                                      provenance=provenance)
    assert b'PRIVATE_CATALOG_CANARY_672951' not in json.dumps(sealed).encode()
    assert envelope.decrypt_catalog(sealed, private, public_key_sha256=key_sha,
                                    provenance=provenance) == raw


def test_independent_standard_primitives_open_envelope(recipient, provenance):
    # Verify interoperability without using the module's decrypt/AAD helpers.
    raw = b'  {"roles":["CANARY_NATIVE_ROLE"],"acl":"SECRET_ACL"}\n\t'
    value = envelope.encrypt_catalog(raw, recipient[1], public_key_sha256=recipient[3],
                                     provenance=provenance)
    header = {k: v for k, v in value.items()
              if k not in {'wrapped_key_b64', 'nonce_b64', 'ciphertext_b64'}}
    assert header == {'version': 'specimen-catalog-envelope/v1',
        'algorithm': 'RSA-OAEP-SHA256+A256GCM', 'public_key_sha256': recipient[3],
        'provenance': provenance, 'plaintext_sha256': hashlib.sha256(raw).hexdigest(),
        'plaintext_size': len(raw)}
    key = recipient[0].decrypt(base64.b64decode(value['wrapped_key_b64']),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    assert len(key) == 32
    aad = json.dumps(header, sort_keys=True, separators=(',', ':')).encode('ascii')
    assert AESGCM(key).decrypt(base64.b64decode(value['nonce_b64']),
                               base64.b64decode(value['ciphertext_b64']), aad) == raw


def test_each_encryption_uses_fresh_randomness(recipient, provenance, sealed):
    second = envelope.encrypt_catalog(b' { "private_role": "SYNTHETIC_CANARY" }\n', recipient[1],
                                       public_key_sha256=recipient[3], provenance=provenance)
    for field in ('wrapped_key_b64', 'nonce_b64', 'ciphertext_b64'):
        assert second[field] != sealed[field]


@pytest.mark.parametrize('field', ['wrapped_key_b64', 'nonce_b64', 'ciphertext_b64'])
def test_ciphertext_or_nonce_tampering_rejected(sealed, recipient, provenance, field):
    raw = bytearray(base64.b64decode(sealed[field]))
    raw[0] ^= 1
    sealed[field] = base64.b64encode(raw).decode('ascii')
    with pytest.raises(ValueError):
        open_catalog(sealed, recipient, provenance)


def test_wrong_private_key_rejected(sealed, recipient, provenance):
    wrong = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private = wrong.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with pytest.raises(ValueError):
        envelope.decrypt_catalog(sealed, private, public_key_sha256=recipient[3], provenance=provenance)


@pytest.mark.parametrize('field,value', [('source_sha', 'b' * 40), ('run_id', 124), ('run_attempt', 2)])
def test_expected_provenance_mismatch_rejected(sealed, recipient, provenance, field, value):
    provenance[field] = value
    with pytest.raises(ValueError):
        open_catalog(sealed, recipient, provenance)


@pytest.mark.parametrize('field,value', [('source_sha', 'b' * 40), ('run_id', 124), ('run_attempt', 2)])
def test_modified_header_cannot_be_rebound(sealed, recipient, provenance, field, value):
    # Matching caller expectation cannot rescue a header changed after encryption.
    provenance[field] = value
    sealed['provenance'][field] = value
    with pytest.raises(ValueError):
        open_catalog(sealed, recipient, provenance)


@pytest.mark.parametrize('field,value', [
    ('version', 'specimen-catalog-envelope/v2'), ('algorithm', 'none'),
    ('plaintext_sha256', '0' * 64), ('plaintext_size', 1),
    ('plaintext_size', True), ('plaintext_size', envelope.MAX_CATALOG_BYTES + 1),
    ('public_key_sha256', '0' * 64), ('raw_catalog', 'unexpected'),
])
def test_modified_metadata_or_extra_fields_rejected(sealed, recipient, provenance, field, value):
    sealed[field] = value
    with pytest.raises(ValueError):
        open_catalog(sealed, recipient, provenance)


def test_missing_metadata_rejected(sealed, recipient, provenance):
    del sealed['algorithm']
    with pytest.raises(ValueError):
        open_catalog(sealed, recipient, provenance)


@pytest.mark.parametrize('field,value', [
    ('wrapped_key_b64', 'AA=='), ('nonce_b64', 'AA=='), ('ciphertext_b64', 'AA=='),
    ('nonce_b64', '!' * 16), ('nonce_b64', 'A' * 17),
    ('ciphertext_b64', 'A' * (4 * (envelope.MAX_CATALOG_BYTES + 17))),
])
def test_malformed_or_oversized_encoding_rejected(sealed, recipient, provenance, field, value):
    sealed[field] = value
    with pytest.raises(ValueError):
        open_catalog(sealed, recipient, provenance)


@pytest.mark.parametrize('change', [
    lambda p: p.update(repository='another/repository'),
    lambda p: p.update(source_sha='a' * 39),
    lambda p: p.update(run_id=True), lambda p: p.update(run_id=0),
    lambda p: p.update(run_attempt=1.0), lambda p: p.update(run_attempt=2**63),
    lambda p: p.update(private_identity='canary'), lambda p: p.pop('run_attempt'),
])
def test_provenance_has_only_bounded_public_fields(recipient, provenance, change):
    change(provenance)
    with pytest.raises(ValueError):
        envelope.encrypt_catalog(b'private', recipient[1], public_key_sha256=recipient[3],
                                  provenance=provenance)


@pytest.mark.parametrize('raw', [b'', 'not bytes', b'x' * (envelope.MAX_CATALOG_BYTES + 1)])
def test_plaintext_size_and_type_bounded(recipient, provenance, raw):
    with pytest.raises(ValueError):
        envelope.encrypt_catalog(raw, recipient[1], public_key_sha256=recipient[3], provenance=provenance)


def test_maximum_plaintext_roundtrip(recipient, provenance):
    raw = b'x' * envelope.MAX_CATALOG_BYTES
    value = envelope.encrypt_catalog(raw, recipient[1], public_key_sha256=recipient[3], provenance=provenance)
    assert open_catalog(value, recipient, provenance) == raw


@pytest.mark.parametrize('kind', ['small-rsa', 'ec', 'legacy-exponent'])
def test_unapproved_public_keys_rejected(kind):
    if kind == 'ec':
        key = ec.generate_private_key(ec.SECP256R1())
    else:
        key = rsa.generate_private_key(public_exponent=3 if kind == 'legacy-exponent' else 65537,
                                       key_size=2048 if kind == 'small-rsa' else 3072)
    public = key.public_key().public_bytes(serialization.Encoding.PEM,
                                           serialization.PublicFormat.SubjectPublicKeyInfo)
    with pytest.raises(ValueError):
        envelope.validate_public_key(public, hashlib.sha256(public).hexdigest())


def test_larger_approved_rsa_key_roundtrip(provenance):
    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    public = key.public_key().public_bytes(serialization.Encoding.PEM,
                                           serialization.PublicFormat.SubjectPublicKeyInfo)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
    pin = hashlib.sha256(public).hexdigest()
    value = envelope.encrypt_catalog(b'exact bytes', public, public_key_sha256=pin, provenance=provenance)
    assert envelope.decrypt_catalog(value, private, public_key_sha256=pin, provenance=provenance) == b'exact bytes'


@pytest.mark.parametrize('change', [
    lambda p: p + b'\n', lambda p: p + p,
    lambda p: p + b'PRIVATE KEY TRAILER', lambda p: b'x' * 4097,
])
def test_noncanonical_or_oversized_public_pem_rejected(recipient, change):
    public = change(recipient[1])
    with pytest.raises(ValueError):
        envelope.validate_public_key(public, hashlib.sha256(public).hexdigest())


def test_public_key_pin_required(recipient, provenance):
    with pytest.raises(ValueError):
        envelope.encrypt_catalog(b'private', recipient[1], public_key_sha256='0' * 64, provenance=provenance)


def test_runner_cannot_decrypt(sealed, recipient, provenance, monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    with pytest.raises(ValueError):
        open_catalog(sealed, recipient, provenance)


def test_no_plaintext_or_key_output(recipient, provenance, capsys):
    raw = b'PRIVATE_CATALOG_ERROR_CANARY_947103'
    value = envelope.encrypt_catalog(raw, recipient[1], public_key_sha256=recipient[3], provenance=provenance)
    public_artifact = json.dumps(value).encode()
    assert raw not in public_artifact
    assert base64.b64encode(raw) not in public_artifact
    assert recipient[2] not in public_artifact
    value['plaintext_sha256'] = '0' * 64
    with pytest.raises(ValueError) as error:
        open_catalog(value, recipient, provenance)
    assert raw.decode() not in str(error.value)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''


def test_caller_metadata_not_mutated(recipient, provenance):
    original = copy.deepcopy(provenance)
    value = envelope.encrypt_catalog(b'private', recipient[1], public_key_sha256=recipient[3], provenance=provenance)
    value['provenance']['run_id'] += 1
    assert provenance == original
