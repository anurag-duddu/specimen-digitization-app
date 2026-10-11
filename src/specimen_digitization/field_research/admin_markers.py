"""Administrative-level markers: the words a label writes beside a place name
to say which level of place it is ("Yepocapa, Mun." for the municipio of
Yepocapa, "Kreis Ahrweiler", "Distr. Kandy", "Cook Co.").

Such a word names no place itself. A precise location whose only text, beside
the settled places, is such a word, standing next to the settled place of the
level it marks, gives no place of its own (step._admin_markers;
FIELD_RESEARCH.md, "An administrative marker is no precise location").

The lists are data: each word as georef_locality.fold leaves it (letter case,
accents and punctuation aside, so "Mun.", "MUN" and "mun." are all "mun").

ADMIN_MARKERS maps each marker to the fields of the level it marks. A
municipality marker marks the municipio, which this schema holds as the city
or the county; a county marker the county; a province marker the province or
state. Units below the county or the municipio are left off, as they name a
place of their own inside it: township ("Twp."), parish ("Parish", "Parr.",
"Parroquia", "Freguesia", "Socken", "Sogn"), corregimiento, gmina, district of
a province ("Distrito"), sub-district ("Taluk", "Tehsil"), borough
("Bezirk"), arrondissement and comuna. So are words that are part of a
place's name or name a feature ("St.", "Mt.", "Lk.", "Arr.", "Brgy.",
"Frazione"), words whose level differs between countries ("Cant.", "Amt",
"Fylke", "Okrug"), words a label may use for something else ("Dep.", "Par.",
"Reg.", "Terr.", "Land") and "Canton", also a city's name.
"""

from __future__ import annotations

MUNICIPIO = frozenset({"city", "county"})
COUNTY = frozenset({"county"})
PROVINCE = frozenset({"province_state"})

ADMIN_MARKERS = {
    # Municipality, municipio, Gemeinde, comune, commune, kommune.
    **dict.fromkeys(("municipio", "municipality", "mun", "munic", "mpio", "mpo", "comune", "gemeinde",
        "gemeente", "gem", "commune", "cne", "kommune", "kommun", "concelho"), MUNICIPIO),
    # County, Kreis, district.
    **dict.fromkeys(("county", "co", "cty", "kreis", "landkreis", "lkr", "kr", "district", "distr", "dist",
        "powiat", "okres", "raion"), COUNTY),
    # Province, department, state, prefecture, region, canton.
    **dict.fromkeys(("province", "prov", "provincia", "pcia", "provincie", "department", "dept", "departamento",
        "depto", "dpto", "dpt", "departement", "state", "estado", "edo", "prefecture", "pref", "region",
        "regione", "territory", "oblast", "obl", "krai", "kray", "wojewodztwo", "woj", "kanton", "kt"),
        PROVINCE),
}

# Markers that count only when written after the name they mark ("Cook
# Co."): before a name, "Co." is also the Spanish "Cerro", a hill ("Co.
# Chirripo").
AFTER_A_NAME = frozenset({"co"})

# Words and abbreviations for a place's features, in several languages. A
# reader's word one letter from a marker is taken as a misreading of the
# marker only when it is none of these ("Mum." for "Mun."; never "Mtn.", a
# mountain, or "Cr.", a creek).
PLACE_FEATURE_WORDS = frozenset({
    # Mountains, hills, peaks, volcanoes.
    "mt", "mtn", "mtns", "mte", "mts", "mont", "monte", "mount", "mountain", "cerro", "co", "pk", "peak",
    "pico", "vol", "volc", "volcan", "kt",
    # Water.
    "cr", "ck", "crk", "creek", "run", "r", "rio", "riv", "river", "l", "lago", "lac", "lake", "lk", "b",
    "bay", "bahia", "arr", "arroyo", "qda", "quebrada", "fk", "fork", "spr", "spring",
    # Islands, points, coasts.
    "is", "isl", "isla", "island", "pt", "pta", "punta", "point", "cab", "cabo", "pto", "puerto",
    # Farms, estates, settlements, saints.
    "fca", "finca", "hda", "hacienda", "rch", "rancho", "est", "sta", "sto", "san", "santa", "santo", "st",
    "ft", "fort",
    # Valleys, roads, bridges.
    "val", "valle", "vall", "rd", "road", "pte", "puente", "cno", "camino",
})
