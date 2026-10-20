"""Read-only import adapters and a DNS-pinned public HTTPS image reader."""
from __future__ import annotations
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit

from .bulk_intake import problem
from .intake_models import SourceReference, MAX_BYTES
from .source_reader import sniff_media_type
from .source_registry import SourceRegistry, validate_object_name


class ImportProblem(RuntimeError):
    def __init__(self, code, message, action='retry', retryable=True):
        self.intake_problem = problem(code, message, action, retryable)
        super().__init__(code)  # Never put a token, source URL or provider body in logs.


def public_url(value):
    try:
        url = urlsplit(value)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.fragment or url.port not in (None, 443)
                or any(ord(c) < 33 for c in value)):
            raise ValueError()
    except ValueError:
        raise ImportProblem('unsupported_link', 'Use a direct HTTPS image link.', 'choose_source', False) from None
    return url


class PinnedConnection(http.client.HTTPSConnection):
    def __init__(self, hostname, address, timeout):
        super().__init__(hostname, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # DNS is resolved and checked once. Connecting to that exact address
        # prevents DNS rebinding between validation and the actual request.
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


class PublicImageReader:
    def __init__(self, *, resolve=socket.getaddrinfo, connect=PinnedConnection, clock=time.monotonic):
        self.resolve, self.connect, self.clock = resolve, connect, clock

    def read(self, value):
        deadline = self.clock() + 60
        for _ in range(4):
            url = public_url(value)
            addresses = {r[4][0] for r in self.resolve(url.hostname, 443, type=socket.SOCK_STREAM)}
            if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
                raise ImportProblem('private_link', 'This link does not point to a public image.', 'choose_source', False)
            connection = self.connect(url.hostname, sorted(addresses)[0], timeout=10)
            try:
                connection.request('GET', (url.path or '/') + ('?' + url.query if url.query else ''),
                                   headers={'Accept': 'image/*', 'Accept-Encoding': 'identity'})
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader('Location')
                    if not location:
                        raise ImportProblem('invalid_redirect', 'This image link could not be followed.', 'choose_source', False)
                    value = urljoin(value, location)
                    continue
                if response.status in {401, 403, 404, 410}:
                    raise ImportProblem('link_unavailable', 'This link expired or does not allow access. Use a new link or connect its provider.', 'choose_source', False)
                if response.status == 429:
                    raise ImportProblem('rate_limited', 'The source is busy. Retry shortly.')
                if response.status != 200:
                    raise ImportProblem('source_unavailable', 'The source could not provide this image. Retry later.')
                if response.getheader('Content-Encoding', 'identity') != 'identity':
                    raise ImportProblem('unsupported_encoding', 'Use an uncompressed image download link.', 'choose_source', False)
                size = response.getheader('Content-Length')
                if size is not None and (not size.isdecimal() or int(size) > MAX_BYTES):
                    raise ImportProblem('image_too_large', 'Photos must be 25 MB or smaller.', 'choose_source', False)
                data = bytearray()
                while True:
                    if self.clock() > deadline:
                        raise ImportProblem('transfer_timeout', 'This download took too long. Retry the photo.')
                    block = response.read(min(65536, MAX_BYTES + 1 - len(data)))
                    if not block:
                        break
                    data.extend(block)
                    if len(data) > MAX_BYTES:
                        raise ImportProblem('image_too_large', 'Photos must be 25 MB or smaller.', 'choose_source', False)
                media_type = sniff_media_type(bytes(data))
                if not media_type.startswith('image/'):
                    raise ImportProblem('not_image', 'This link opens a webpage or unsupported file. Use a direct image link.', 'choose_source', False)
                return bytes(data), media_type
            finally:
                connection.close()
        raise ImportProblem('redirect_limit', 'This link redirects too many times. Use the final image link.', 'choose_source', False)


class IntakeSources:
    def __init__(self, *, source_registry=None, source_reader=None, providers=None, url_reader=None):
        self.registry = source_registry or SourceRegistry(())
        self.storage = source_reader
        self.providers = providers or {}
        self.url_reader = url_reader or PublicImageReader()

    def capabilities(self, p):
        return [dict(provider=name, available=True) for name in ('files', 'camera', 'url')] + [
            dict(provider='storage', available=bool(self.registry.for_collections([p.scope.collection_id]))),
            *[dict(provider=name, available=name in self.providers,
                   reason=None if name in self.providers else 'Connection setup is required')
              for name in ('google_drive', 'dropbox')]]

    def required_sensitive(self, p, source):
        return source.provider == 'storage' and self.registry.get(source.source_id, [p.scope.collection_id]).sensitive

    def validate(self, p, source):
        if source.provider == 'url':
            url = public_url(source.url or '')
            if url.hostname in {'drive.google.com', 'docs.google.com', 'dropbox.com', 'www.dropbox.com'}:
                raise ImportProblem('provider_link', 'Connect this provider to import its files.', 'connect', False)
        elif source.provider == 'storage':
            registered = self.registry.get(source.source_id, [p.scope.collection_id])
            validate_object_name(registered, source.object_id)
            if not source.version or not source.version.isdecimal() or not self.storage:
                raise ValueError('Choose a current object from registered storage')
        elif source.provider in self.providers:
            self.providers[source.provider].validate(p, source)
        else:
            raise ImportProblem('provider_not_configured', 'This connection needs administrator setup. Choose another source for now.', 'administrator', False)

    def read(self, p, reference):
        source = SourceReference.model_validate(reference)
        self.validate(p, source)
        if source.provider == 'url':
            return self.url_reader.read(source.url)
        if source.provider == 'storage':
            registered = self.registry.get(source.source_id, [p.scope.collection_id])
            data = self.storage.read(registered.bucket, source.object_id, source.version)
            media_type = sniff_media_type(data)
            if media_type not in registered.media_types:
                raise ImportProblem('source_format_policy', 'This file type is not allowed by the registered source.', 'choose_source', False)
            return data, media_type
        return self.providers[source.provider].read(p, source)
