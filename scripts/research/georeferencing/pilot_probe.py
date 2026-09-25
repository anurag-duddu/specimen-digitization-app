"""Read-only probe: what public sources say about the pilot slides' four localities.

Research prototype for docs/product-requirements/GEOREFERENCING.md (session S8,
2026-09-23). It reads anonymous public endpoints only (Wikidata, the GeoNames
country dumps and OpenTopoData), needs no key, makes no paid call and writes
only under --out. It is not production code and nothing imports it. A default
run sends no date and no occurrence query: GBIF's occurrence search runs only
with --held-steps, which D4's hold leaves off. GADM is not used, not even as a
measurement (PLAN 4.8), so the probe has no containment step.

    uv run python scripts/research/georeferencing/pilot_probe.py --out <dir>
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import math
import re
import time
import zipfile
from dataclasses import asdict, dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import httpx

# Research only: this names the project's public repository. The tool's own User-Agent names no
# person (PLAN 4.8).
USER_AGENT = (
    "specimen-digitization-georef-research/0.1 "
    "(+https://github.com/anurag-duddu/specimen-digitization-app)"
)
FOOT_M = 0.3048  # a label's feet become metres only as a derived value
ELEVATION_TOLERANCE_M = 150  # proposal default; the plan lists it as an owner decision
ABBREVIATIONS = {"mt": "Mount", "prov": "Province", "mun": "Municipality"}
COUNTRY_ABBREVIATIONS = {"p.i": "Philippine Islands"}
BEARINGS = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}
# One entry of the curator-reviewed crosswalk the plan proposes. The modern name is a
# hypothesis for review, not a fact: Hoogstraal (1951, Fieldiana Zoology 33(1), p. 40)
# says the name "Mount McKinley" appears on no map; the camps were reached via Toril.
CROSSWALK = {("PH", "Mount McKinley"): "Mount Talomo"}
SLOPE = re.compile(r"^(?P<direction>[NSEW]{1,2})\.?\s+slope\s+(?:of\s+)?(?P<feature>.+)$", re.I)
ELEVATION = re.compile(r"^(?:elev\.?\s*)?\d{3,5}\s*(?:'|ft\.?|feet)$", re.I)


@dataclass(frozen=True)
class Locality:
    key: str
    verbatim: str  # the label as S8 read it, line breaks folded into commas
    subjects: tuple[str, ...]
    year: int
    elevation_ft: int | None


PILOT = (
    Locality("mckinley-6400", "E. slope Mt. McKinley, Davao Prov., Mindanao, P.I.",
             ("105526321", "105526322", "105526323"), 1946, 6400),
    Locality("mckinley-3300", "E. slope Mt. McKinley, 3300', Davao Prov., Mindanao, Philippine Islands",
             ("105526324", "105526325", "105526326"), 1946, 3300),
    Locality("apo", "E. slope Mt. Apo, Davao Prov., Mindanao, P.I.", ("105526327",), 1946, None),
    Locality("yepocapa", "Yepocapa, Mun. Yepocapa, Chimaltenago, Guatemala.",
             ("105526328", "105526329", "105526330"), 1948, 4800),
)


def expand(text: str) -> str:
    """Expand label abbreviations from a fixed table; nothing else is rewritten."""
    return " ".join(ABBREVIATIONS.get(w.lower().rstrip("."), w) for w in text.split())


def parse(locality: Locality) -> dict[str, Any]:
    """Split the verbatim text into feature, direction, admin and country parts."""
    parts = [p.strip().rstrip(".") for p in locality.verbatim.split(",") if p.strip()]
    literal = parts.pop()
    parsed: dict[str, Any] = {"country_literal": literal, "direction": None, "admin": [],
                              "country_name": COUNTRY_ABBREVIATIONS.get(literal.casefold(), literal)}
    feature = parts.pop(0)
    if match := SLOPE.match(feature):
        parsed["direction"], feature = match["direction"].upper(), match["feature"]
    parsed["feature"] = expand(feature)
    for part in parts:
        name = expand(part)
        if ELEVATION.match(part) or name == f"Municipality {parsed['feature']}":
            continue
        parsed["admin"].append(name)
    return parsed


class Client:
    """One polite HTTP client: a pause per host, Retry-After honoured once, raw bodies kept."""

    def __init__(self, out: Path):
        self.raw = out / "raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.http = httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)
        self.last: dict[str, float] = {}
        self.calls: list[dict[str, Any]] = []

    async def get(self, url: str, **params: Any) -> tuple[str, Any]:
        host = httpx.URL(url).host
        for attempt in (1, 2):
            wait = self.last.get(host, 0) + 1.1 - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self.last[host] = time.monotonic()
            try:
                response = await self.http.get(url, params=params)
            except httpx.TimeoutException:
                return self._record(url, params, "timeout", None, b"")
            if response.status_code == 429 and attempt == 1:
                await asyncio.sleep(min(int(response.headers.get("Retry-After", "60")), 180))
                continue
            break
        outcome = {401: "authentication_error", 403: "authorization_error", 429: "rate_limited"}.get(
            response.status_code, "provider_error" if response.status_code >= 400 else "success")
        body = response.content
        if outcome != "success" or url.endswith(".zip"):
            return self._record(url, params, outcome, body if outcome == "success" else None, body)
        try:
            return self._record(url, params, outcome, response.json(), body)
        except ValueError:
            return self._record(url, params, "malformed_response", None, body)

    def _record(self, url: str, params: dict[str, Any], outcome: str, data: Any, body: bytes) -> tuple[str, Any]:
        digest = hashlib.sha256(body).hexdigest()
        if body and not url.endswith(".zip"):
            (self.raw / f"{digest[:16]}.json").write_bytes(body)
        self.calls.append({"url": url, "params": params, "outcome": outcome, "sha256": digest,
                           "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return outcome, data


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lat1, lon1), (lat2, lon2) = (tuple(map(math.radians, p)) for p in (a, b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return round(12742 * math.asin(math.sqrt(h)), 2)


def destination(start: tuple[float, float], bearing: float, distance_km: float) -> tuple[float, float]:
    lat, lon, b, d = *map(math.radians, start), math.radians(bearing), distance_km / 6371
    lat2 = math.asin(math.sin(lat) * math.cos(d) + math.cos(lat) * math.sin(d) * math.cos(b))
    lon2 = lon + math.atan2(math.sin(b) * math.sin(d) * math.cos(lat), math.cos(d) - math.sin(lat) * math.sin(lat2))
    return round(math.degrees(lat2), 5), round(math.degrees(lon2), 5)


async def wikidata_search(client: Client, name: str) -> list[dict[str, Any]]:
    outcome, data = await client.get("https://www.wikidata.org/w/api.php", action="wbsearchentities",
                                     search=name, language="en", uselang="en", type="item", limit=7, format="json")
    hits = (data or {}).get("search", []) if outcome == "success" else []
    return [{"id": h["id"], "label": h.get("label"), "matched": h.get("match", {}).get("type")} for h in hits]


# Enrichment for items already found by search: validity window, successors, parents, point.
# Labels go through STR() so an "en" and a "mul" label with the same text count once.
ENRICH = """
SELECT ?item (SAMPLE(STR(?label)) AS ?name) (SAMPLE(?coord) AS ?point) (MIN(?from) AS ?validFrom)
       (MAX(?to) AS ?validTo) (GROUP_CONCAT(DISTINCT ?iso; separator=" ") AS ?countries)
       (GROUP_CONCAT(DISTINCT STR(?classLabel); separator="; ") AS ?classes)
       (GROUP_CONCAT(DISTINCT STR(?nextLabel); separator="; ") AS ?replacedBy)
       (GROUP_CONCAT(DISTINCT STR(?parentLabel); separator="; ") AS ?parents)
WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item rdfs:label ?label FILTER(LANG(?label) IN ("en", "mul")) }
  OPTIONAL { ?item wdt:P625 ?coord }
  OPTIONAL { ?item wdt:P571|wdt:P580 ?from }
  OPTIONAL { ?item wdt:P576|wdt:P582 ?to }
  OPTIONAL { ?item wdt:P17/wdt:P297 ?iso }
  OPTIONAL { ?item wdt:P31 ?class . ?class rdfs:label ?classLabel FILTER(LANG(?classLabel) = "en") }
  OPTIONAL { ?item wdt:P1366 ?next . ?next rdfs:label ?nextLabel FILTER(LANG(?nextLabel) IN ("en", "mul")) }
  OPTIONAL { ?item wdt:P131 ?parent . ?parent rdfs:label ?parentLabel FILTER(LANG(?parentLabel) IN ("en", "mul")) }
}
GROUP BY ?item
"""


async def wikidata_enrich(client: Client, ids: list[str]) -> dict[str, dict[str, Any]]:
    outcome, data = await client.get("https://query.wikidata.org/sparql",
                                     query=ENRICH % " ".join(f"wd:{i}" for i in ids), format="json")
    enriched = {}
    for row in (data or {}).get("results", {}).get("bindings", []) if outcome == "success" else []:
        values = {k: v["value"] for k, v in row.items()}
        point = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", values.get("point", ""))
        enriched[values["item"].rsplit("/", 1)[1]] = {
            **{k: values.get(k) for k in ("name", "classes", "replacedBy", "parents", "countries")},
            "valid_from": values.get("validFrom", "")[:10] or None, "valid_to": values.get("validTo", "")[:10] or None,
            "point": (float(point[2]), float(point[1])) if point else None,
        }
    return enriched


def valid_in(entry: dict[str, Any], year: int) -> str:
    start, end = entry.get("valid_from"), entry.get("valid_to")
    if not start and not end:
        return "undated"
    ok = (not start or int(start[:4]) <= year) and (not end or int(end[:4]) >= year)
    return "valid" if ok else "not valid"


async def geonames(client: Client, country: str) -> list[list[str]]:
    outcome, body = await client.get(f"https://download.geonames.org/export/dump/{country}.zip")
    if outcome != "success":
        return []
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        return [line.split("\t") for line in archive.read(f"{country}.txt").decode("utf-8").splitlines()]


def geonames_match(rows: list[list[str]], name: str, feature_class: str) -> list[dict[str, Any]]:
    """Exact name or alternate-name matches; a fuzzy match only when nothing matches exactly."""
    wanted, hits, how = name.casefold(), [], "exact"
    names_of = {id(r): {r[1], r[2], *filter(None, r[3].split(","))} for r in rows}
    hits = [r for r in rows if wanted in {n.casefold() for n in names_of[id(r)]}]
    if not hits:
        pool: dict[str, list[list[str]]] = {}
        for r in rows:
            if r[6] == feature_class:
                for n in names_of[id(r)]:
                    pool.setdefault(n, []).append(r)
        close = get_close_matches(name, list(pool), n=3, cutoff=0.85)
        unique = {r[0]: r for n in close for r in pool[n]}
        hits, how = list(unique.values()), f"fuzzy {close}"
    return [{"geonameid": r[0], "name": r[1], "code": f"{r[6]}.{r[7]}", "point": (float(r[4]), float(r[5])),
             "elevation": r[15] or r[16], "match": "name" if r[1].casefold() == wanted else
             ("alternate name" if how == "exact" else how)} for r in hits]


async def gbif_prior(client: Client, country: str, year: int, core: str) -> list[dict[str, Any]]:
    """The museum's own published georeferences for records whose locality names the feature."""
    window, word = f"{year - 1},{year + 1}", re.compile(rf"\b{re.escape(core)}\b", re.I)
    outcome, data = await client.get("https://api.gbif.org/v1/occurrence/search", institutionCode="FMNH",
                                     country=country, year=window, facet="locality", facetLimit=500, limit=0)
    facets = (data or {}).get("facets", [{}])[0].get("counts", []) if outcome == "success" else []
    clusters: dict[tuple[float, float], dict[str, Any]] = {}
    for locality in [f["name"] for f in facets if word.search(f["name"])][:8]:
        outcome, data = await client.get("https://api.gbif.org/v1/occurrence/search", institutionCode="FMNH",
                                         country=country, year=window, locality=locality, hasCoordinate="true",
                                         limit=300)
        for rec in (data or {}).get("results", []):
            point = (rec["decimalLatitude"], rec["decimalLongitude"])
            cluster = clusters.setdefault(point, {"point": point, "records": 0, "localities": set(),
                                                  "georeferencedBy": rec.get("georeferencedBy"),
                                                  "protocol": rec.get("georeferenceProtocol"),
                                                  "uncertainty_m": rec.get("coordinateUncertaintyInMeters")})
            cluster["records"] += 1
            cluster["localities"].add(locality)
    return [{**c, "localities": sorted(c["localities"])} for c in clusters.values()]


async def elevations(client: Client, points: list[tuple[float, float]]) -> dict[tuple[float, float], float | None]:
    found: dict[tuple[float, float], float | None] = {}
    for start in range(0, len(points), 90):
        batch = points[start:start + 90]
        outcome, data = await client.get("https://api.opentopodata.org/v1/srtm30m",
                                         locations="|".join(f"{lat},{lon}" for lat, lon in batch))
        for point, row in zip(batch, (data or {}).get("results", [None] * len(batch))):
            found[point] = row.get("elevation") if row else None
    return found


def elevation_check(label_ft: int | None, dem_m: float | None) -> str:
    if label_ft is None or dem_m is None:
        return "not assessable"
    delta = dem_m - label_ft * FOOT_M
    return f"{'supports' if abs(delta) <= ELEVATION_TOLERANCE_M else 'conflicts'} ({delta:+.0f} m)"


def in_country(hits: list[dict[str, Any]], enriched: dict[str, Any], iso: str, year: int) -> list[dict[str, Any]]:
    return [{**h, **enriched.get(h["id"], {}), "valid_in_year": valid_in(enriched.get(h["id"], {}), year)}
            for h in hits if iso and iso in (enriched.get(h["id"], {}).get("countries") or "").split()]


async def probe(out: Path, held_steps: bool = False) -> dict[str, Any]:
    client, report = Client(out), {}
    parsed = {loc.key: parse(loc) for loc in PILOT}
    countries = {n: await wikidata_search(client, n) for n in sorted({p["country_name"] for p in parsed.values()})}
    names = sorted({n for p in parsed.values() for n in (p["feature"], *p["admin"])} | set(CROSSWALK.values()))
    searches = {n: await wikidata_search(client, n) for n in names}
    ids = sorted({h["id"] for hits in [*searches.values(), *countries.values()] for h in hits})
    enriched = await wikidata_enrich(client, ids)
    iso = {n: next(((enriched.get(h["id"], {}).get("countries") or "").split()[0] for h in hits
                    if (enriched.get(h["id"], {}).get("countries") or "").split()), "") for n, hits in countries.items()}
    dumps = {code: await geonames(client, code) for code in sorted(set(iso.values()) - {""})}
    for loc in PILOT:
        p = parsed[loc.key]
        code = iso[p["country_name"]]
        modern = CROSSWALK.get((code, p["feature"]))
        entry: dict[str, Any] = {"locality": asdict(loc), "parsed": p, "iso": code, "crosswalk": modern, "names": {}}
        for name in (p["feature"], *p["admin"], *([modern] if modern else [])):
            feature_class = "T" if name.startswith("Mount ") else "A" if name in p["admin"] else "P"
            entry["names"][name] = {"feature": name in (p["feature"], modern),
                                    "wikidata": in_country(searches[name], enriched, code, loc.year),
                                    "wikidata_elsewhere": len(searches[name]),
                                    "geonames": geonames_match(dumps.get(code, []), name, feature_class)}
        core = p["feature"].removeprefix("Mount ")
        # Held (D4, PLAN 4.8): the occurrence search sends a year range and facet strings.
        held = held_steps and code
        entry["gbif_prior"] = await gbif_prior(client, code, loc.year, core) if held else []
        spread = [c["point"] for c in entry["gbif_prior"]]
        entry["gbif_prior_max_km"] = max((km(a, b) for a in spread for b in spread), default=0.0)
        report[loc.key] = entry
    candidates = [(e, x) for e in report.values() for v in e["names"].values() if v["feature"]
                  for x in v["wikidata"] + v["geonames"] if x.get("point")]
    candidates += [(e, c) for e in report.values() for c in e["gbif_prior"]]
    transects = {}
    for entry in report.values():
        target = entry["crosswalk"] or entry["parsed"]["feature"]
        start = next((x["point"] for x in entry["names"].get(target, {}).get("wikidata", []) if x.get("point")), None)
        if start and entry["parsed"]["direction"] and entry["locality"]["elevation_ft"]:
            bearing = BEARINGS[entry["parsed"]["direction"]]
            transects[entry["locality"]["key"]] = [(d / 2, destination(start, bearing, d / 2)) for d in range(0, 31)]
    points = sorted({tuple(x["point"]) for _, x in candidates} | {pt for t in transects.values() for _, pt in t})
    dem = await elevations(client, points)
    for entry, candidate in candidates:
        point = tuple(candidate["point"])
        candidate.update(dem_m=dem.get(point),
                         elevation=elevation_check(entry["locality"]["elevation_ft"], dem.get(point)))
    for key, samples in transects.items():
        report[key]["transect"] = [{"km": d, "point": pt, "dem_m": dem.get(pt)} for d, pt in samples]
    report["_calls"] = client.calls
    report["_held_steps"] = held_steps
    await client.http.aclose()
    return report


def summary(report: dict[str, Any]) -> str:
    lines = []
    ran = report.get("_held_steps", False)
    for key, entry in report.items():
        if key.startswith("_"):
            continue
        p = entry["parsed"]
        lines.append(f"\n## {key}: {entry['locality']['verbatim']}")
        lines.append(f"parsed: feature={p['feature']!r} direction={p['direction']} admin={p['admin']} "
                     f"country {p['country_literal']!r} -> {p['country_name']!r} -> {entry['iso'] or 'unresolved'}"
                     + (f"; crosswalk -> {entry['crosswalk']!r} (hypothesis for curator review)" if entry["crosswalk"] else ""))
        for name, found in entry["names"].items():
            wd = "; ".join(f"{h['id']} {h.get('name')} [{h['valid_in_year']}] {h.get('point')}"
                           + (f" replaced by {h['replacedBy']}" if h.get("replacedBy") else "")
                           + (f" dem={h.get('dem_m')} {h.get('elevation')}" if found["feature"] else "")
                           for h in found["wikidata"]) or "none in country"
            gn = "; ".join(f"{g['geonameid']} {g['name']} {g['code']} ({g['match']}) {g['point']}"
                           + (f" dem={g.get('dem_m')} {g.get('elevation')}" if found["feature"] else "")
                           for g in found["geonames"]) or "none"
            lines.append(f"- {name}: Wikidata {wd} [{found['wikidata_elsewhere']} search hits in all] | GeoNames {gn}")
        for c in entry["gbif_prior"]:
            lines.append(f"- FMNH published {c['point']} x{c['records']} by {c['georeferencedBy']} ({c['protocol']}), "
                         f"uncertainty {c['uncertainty_m']}, {c.get('elevation')}: {c['localities']}")
        spread = f"{entry['gbif_prior_max_km']} km" if ran else "held (D4)"
        lines.append(f"- published points spread: {spread}")
        if entry.get("transect"):
            profile = ", ".join(f"{s['km']:g} km {s['dem_m']:.0f} m" for s in entry["transect"] if s["dem_m"] is not None)
            lines.append(f"- DEM transect {p['direction']} from {entry['crosswalk'] or p['feature']}: {profile}")
    calls = report["_calls"]
    lines.append(f"\n{len(calls)} requests: " + ", ".join(
        f"{o} {sum(c['outcome'] == o for c in calls)}" for o in sorted({c["outcome"] for c in calls})))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for report.json and raw responses")
    parser.add_argument(
        "--held-steps",
        action="store_true",
        help="also run GBIF's occurrence search; off by default, because D4 is held",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(probe(args.out, held_steps=args.held_steps))
    (args.out / "report.json").write_text(json.dumps(report, indent=2, default=list))
    text = summary(report)
    (args.out / "summary.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
