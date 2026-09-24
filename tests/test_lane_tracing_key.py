"""The Geocoding key never reaches a trace or a log (docs/execution/golive/LANE.md, T5d)."""

import logging
import re

import httpx
import logfire
import pytest
from logfire.testing import TestExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from specimen_digitization import observability

# A fake key; the scrubber keys on the parameter's name, not the value's shape.
KEY = "fake-geocoding-key-" + "k" * 20
URL = f"https://maps.googleapis.com/maps/api/geocode/json?address=Davao&key={KEY}"
SCRUBBED = "https://maps.googleapis.com/maps/api/geocode/json?address=Davao&key=[Scrubbed]"


@pytest.fixture
def exported():
    """Logfire configured with the lane's scrubbing, spans captured in memory."""
    exporter = TestExporter()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        scrubbing=observability.scrubbing_options(),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
    )
    return exporter


@pytest.fixture
def records(monkeypatch):
    """The process's log-record factory, restored after the test."""
    monkeypatch.setattr(logging, "_logRecordFactory", logging.getLogRecordFactory())
    observability.install_key_scrubbing()


def attributes(exporter):
    return [s["attributes"] for s in exporter.exported_spans_as_dict()]


def test_an_attribute_keeps_the_url_and_loses_the_key(exported):
    logfire.info("Geocoding request", url=URL)
    [log] = attributes(exported)
    assert log["url"] == SCRUBBED
    assert KEY not in str(exported.exported_spans_as_dict())


def test_a_message_loses_the_key_too(exported):
    with logfire.span("Geocode {url}", url=URL):
        pass
    [span] = attributes(exported)
    assert KEY not in span["logfire.msg"] and KEY not in span["url"]


def test_a_value_with_anything_else_sensitive_is_redacted_whole(exported):
    logfire.info("Geocoding request", url=URL + "&password=hunter2")
    [log] = attributes(exported)
    assert log["url"].startswith("[Scrubbed due to")
    assert KEY not in log["url"] and "hunter2" not in log["url"]


def test_other_values_are_scrubbed_as_before(exported):
    logfire.info("Lookup", note="the api_key is here", place="Davao del Sur")
    [log] = attributes(exported)
    assert log["note"] == "[Scrubbed due to 'api_key']"
    assert log["place"] == "Davao del Sur"


def test_log_records_lose_the_key(records, caplog):
    with caplog.at_level(logging.INFO, logger="httpx"):
        logging.getLogger("httpx").info(
            'HTTP Request: %s %s "%s %d %s"', "GET", httpx.URL(URL), "HTTP/1.1", 403, "Forbidden"
        )
    [record] = caplog.records
    message = record.getMessage()
    assert KEY not in message
    # The URL keeps its shape. The geography tool's own httpx filter (S4, #113)
    # marks the value "[redacted]" when it runs after the factory's "[Scrubbed]".
    assert re.search(r"json\?address=Davao&key=\[(Scrubbed|redacted)\]", message)


def test_installing_twice_scrubs_once(records):
    observability.install_key_scrubbing()
    record = logging.getLogger("lane").makeRecord("lane", logging.INFO, __file__, 1, URL, (), None)
    assert record.getMessage() == SCRUBBED


def test_the_lanes_configuration_scrubs_the_key(monkeypatch):
    options = {}
    monkeypatch.setattr(observability, "_configured_settings", None)
    monkeypatch.setattr(logging, "_logRecordFactory", logging.getLogRecordFactory())
    monkeypatch.setattr(logfire, "configure", lambda **kwargs: options.update(kwargs))
    monkeypatch.setattr(logfire, "instrument_pydantic_ai", lambda **kwargs: None)
    monkeypatch.delenv("SPECIMEN_TRACE_EXPORT_MODE", raising=False)
    observability.configure_observability(send_to_logfire=False)
    assert options["scrubbing"].extra_patterns == [observability.KEY_QUERY]
    record = logging.getLogger("lane").makeRecord("lane", logging.INFO, __file__, 1, URL, (), None)
    assert record.getMessage() == SCRUBBED
