"""The Flutter app validates every research response against a copy of the Python schemas.

The copy is embedded in research_models.dart with additionalProperties false, so a field the server
adds and the copy lacks makes the app reject the whole thread. Nothing compared the two: FieldValue
gained ``layer`` and ``derived_from`` (c8e4d931) and every value in every thread carries both keys.
"""

import json
import re
from pathlib import Path

import pytest

from specimen_digitization.research_harness.service import RetryAccepted
from specimen_digitization.research_harness.thread_view import ResearchThread

DART = Path(__file__).parents[2] / "apps" / "specimen_digitization" / "lib" / "src" / "research" / "research_models.dart"
REGENERATE = (
    "Regenerate the embedded schema: python -c \"import json; from specimen_digitization.research_harness."
    "thread_view import ResearchThread as T; print(json.dumps(T.model_json_schema(), separators=(',', ':'), "
    "ensure_ascii=False))\" and paste it into research_models.dart (_threadSchemaJson)."
)


def embedded(name):
    match = re.search(rf"const {name} =\s*r'''(.*?)'''", DART.read_text(), re.DOTALL)
    assert match, f"{name} not found in research_models.dart"
    return json.loads(match.group(1))


def test_the_embedded_thread_schema_is_the_servers_current_thread_schema():
    assert embedded("_threadSchemaJson") == ResearchThread.model_json_schema(), REGENERATE


def test_the_embedded_retry_schema_is_the_servers_current_retry_schema():
    assert embedded("_retrySchemaJson") == RetryAccepted.model_json_schema()


@pytest.mark.parametrize("key", ["layer", "derived_from"])
def test_every_value_the_server_sends_carries_the_keys_the_app_schema_must_know(key):
    from specimen_digitization.application.domain import FieldValue

    assert key in FieldValue().model_dump(mode="json")
    assert key in embedded("_threadSchemaJson")["$defs"]["FieldValue"]["properties"]
