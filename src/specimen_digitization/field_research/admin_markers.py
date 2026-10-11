"""Administrative-level markers: the words a label writes beside a place name
to say which level of place it is ("Yepocapa, Mun." for the municipio of
Yepocapa, "Kreis Ahrweiler", "Distr. Kandy", "Cook Co.").

Such a word names no place itself. A precise location whose only text, beside
the country, province or state, county and city settled for the record, is
one of these words gives no place finer than those (step._admin_markers;
FIELD_RESEARCH.md, "Fields the label does not state").

The list is data: each word as georef_locality.fold leaves it (letter case,
accents and punctuation aside, so "Mun.", "MUN" and "mun." are all "mun").
Words that are part of a place's name, or name a feature or a place finer
than a county, are left off: "St." ("St. Louis"), "Mt." (a mountain), "Lk." (a
lake), "Arr." (arroyo, a stream), "Brgy." (a barangay, a village) and
"Frazione" (a hamlet); so are words a label may use for something else
("Dep.", "Par.", "Reg.", "Terr.", "Land") and "Canton", also a city's name.
"""

from __future__ import annotations

ADMIN_MARKERS = frozenset({
    # English.
    "county", "co", "cty", "parish", "district", "distr", "dist", "province", "prov", "state",
    "region", "department", "dept", "territory", "township", "twp", "municipality", "prefecture",
    "pref",
    # Spanish and Portuguese.
    "municipio", "mun", "munic", "mpio", "mpo", "departamento", "depto", "dpto", "provincia", "pcia",
    "distrito", "estado", "edo", "cant", "corregimiento", "comuna", "parroquia", "parr",
    "concelho", "freguesia",
    # French.
    "departement", "dpt", "arrondissement", "commune", "cne",
    # Italian.
    "comune", "regione",
    # German and Dutch.
    "kreis", "kr", "landkreis", "lkr", "bezirk", "bez", "gemeinde", "gem", "gemeente", "kanton",
    "kt", "amt", "provincie",
    # Nordic.
    "kommune", "kommun", "fylke", "socken", "sogn", "herred",
    # Slavic, transliterated.
    "oblast", "obl", "raion", "krai", "kray", "okrug", "gmina", "powiat", "wojewodztwo", "woj",
    "okres",
    # South Asia.
    "taluk", "taluka", "tehsil", "tahsil",
})

# Markers that mark a county only when written after its name ("Cook Co."):
# before a name, "Co." is also the Spanish "Cerro", a hill ("Co. Chirripo"),
# which is a place finer than any county.
AFTER_A_NAME = frozenset({"co"})
