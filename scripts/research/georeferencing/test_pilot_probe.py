"""The research probe never reads or stores GADM, not even as a measurement (PLAN 4.8)."""

import asyncio
import json
import re
from pathlib import Path

import httpx

import pilot_probe

HERE = Path(__file__).parent
# #216's pattern for GADM's and GBIF's geocoder names (tests/test_gadm_not_used.py:39-43).
# A bare "GADM" is left out on purpose: the comments that say it is not used name it.
GADM = re.compile(
    r"gbif[_-]gadm|gadm_search|geocode/(gadm|reverse)|api\.gbif\.org/v1/geocode"
    r"|gadm\.org|ucdavis\.edu/(data/)?gadm|gadm\d",
    re.I,
)


def test_no_research_script_names_a_gadm_source():
    scripts = [path for path in sorted(HERE.glob("*.py")) if not path.name.startswith("test_")]
    assert scripts
    for script in scripts:
        assert not GADM.search(script.read_text(encoding="utf-8")), script.name


def test_held_step_output_stores_no_gadm_block(tmp_path):
    # GBIF's occurrence records carry GADM's divisions in a "gadm" block.
    record = {"key": 1, "gadm": {"level0": {"gid": "PHL", "name": "Philippines"}}, "country": "PH"}
    client = pilot_probe.Client(tmp_path)

    async def search():
        await client.http.aclose()
        client.http = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"results": [record]}))
        )
        try:
            return await client.get("https://api.gbif.org/v1/occurrence/search", limit=1)
        finally:
            await client.http.aclose()

    outcome, data = asyncio.run(search())
    assert (outcome, data) == ("success", {"results": [{"key": 1, "country": "PH"}]})
    stored = [json.loads(path.read_text(encoding="utf-8")) for path in (tmp_path / "raw").iterdir()]
    assert stored == [{"results": [{"key": 1, "country": "PH"}]}]
