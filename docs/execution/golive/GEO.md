# Go-live georeferencing workstream (S8): spec deltas

The retrospective georeferencing tool behind the harness's `geography_lookup`
interface, which the owner asked for on 2026-09-24 (G34): "clear with place ID byt
I want the harness for location retrospective georeferencing fully implemented".
Its plan is `docs/product-requirements/GEOREFERENCING.md` (#94), and the owner set
its design the same day (G35 to G40): three tiers (historical gazetteers with
curator-confirmed entries, Google given the modernized name, the in-house
point-radius), fields derived with evidence when the label leaves them out, and
a layer for every value. The coordinator ruled that the tool replaces the Google
module behind the same interface once the acceptance lab shows it resolves the
pilot slides at least as well; until then the Google module stays in production
(G6). Each pull request adds its section here before its tests and
implementation.

## 1. Reading locality text

`georef_locality.py` reads one locality literal, exactly as a reading has it, into
the parts the later tiers search. It makes no request, decides no outcome and
never changes the literal: the result keeps it verbatim (G27).

**Lines and parts.** Commas and semicolons separate parts, except a comma inside a
number ("1,463 m"). A line break separates parts too, except after a notation
that needs the next word: a feature notation ("E. Slope Mt." / "McKinley" on
105526322) or a unit written before its name ("Yepocapa, Mun." / "Yepocapa," on
105526328).

**Notations (G29).** The Insects harness reads these whole words in any case,
with or without the period; they come from the pilot's labels and from the unit
words the Google tool already drops. Other collections add their own tables (G29).

| Kind | Written | Read as |
|---|---|---|
| unit after its name | Prov., Province; Dept., Department; Co., County; State; Region | the part's unit: province, department, county, state, region |
| unit before its name | Mun., Municipio, Municipality; Depto., Departamento; Provincia; Estado | municipality, department, province, state |
| feature | Mt. | "Mount", a mountain |
| country | P.I. | "Philippine Islands" |
| institution | CNHM, FMNH | the museum's own names, never a place |

A part that is only a unit word joins the part its position points to: "Davao,
Prov. 3300'" (105526326) reads as one part, "Davao Prov.". A part's readings are
the full names it can be searched by, most specific first: "Davao Prov." gives
"Davao Province" and "Davao". A notation outside the table stays as written.

**Slopes and offsets.** A heading (the 16 compass points, abbreviated with or
without periods, or written as words) followed by "slope", "side" or "flank"
belongs to the feature beside it: "E. slope Mt. McKinley", "E Slope Mt.
McKinley", a reader's joined "ESlope Mt. McKinley", and "Mt. Apo, east slope".
Standing in its own part, such a phrase joins an adjacent feature, the one before
first; failing that, the part before it, or else the part after it. "5 km NE of
Yepocapa" is an offset. A heading keeps its written form and its bearing in
degrees, and a distance stays as written; points and radii are tier 3's.

**Elevations (G22, G37).** Elevation phrases ("4800 ft.", "4800ft.", "6400'", "Elev.
6400'", "1,463 m", "4000-4500 ft") leave the place text and are kept as written:
the numbers as written, and the unit as feet, metres, or none when the label
gives none ("Elev.6400" on 105526322). Nothing is converted: an elevation the
label states stays as written, and a derived value belongs to a later layer
(G37, G38).

**Unplaced text.** A part left with a digit or without a letter, such as a date
("IV-26") or a camp number, and a heading phrase with no part to join, are kept
aside and never searched: gazetteer place names carry no digits.

**Comparing names (G34, as the coordinator read it on 2026-09-24).** Names
compare by a key: case folded, diacritics removed, punctuation turned into
spaces, feature notations read ("Mt." compares as "mount"), and unit words
dropped with a "de", "del" or "of" after a leading one. So "Chimaltenago" and
"Departamento de Chimaltenango" have keys one letter apart. `letters_apart`
counts the single-character insertions, deletions and substitutions between two
keys, up to a cap of 2. The one-letter gate compares full names only, never codes
or abbreviations. A word is not part of a full name when it:
- has a period inside it ("P.I."),
- ends in a period after at most four letters ("Phil.") and is not a notation in
  the table,
- has a digit, or
- is written in capitals of at most three letters ("PH", "PHL", "RP").

A name made of notations alone ("Mt.") is not a full name either.

A candidate one letter off settles the place only when it is the only such
candidate and every other place field of the same reading, at least one, matches
it exactly; the field then carries a `near_spelling` warning that never routes
the record (G34 as the coordinator reads it in #124). The tool tests that; this
module does not.

**Readers (G19, G20).** Each reader's literal is read on its own and keeps its
observation id. Literals whose parts share their keys form one variant, so a
lookup can tell whose literal it confirmed: handwriting-qwen's "Chimaltenango"
and handwriting-muse's "Chimaltenago" on 105526329 are two variants.

**Tests.** `tests/test_georef_locality.py` reads the ten pilot labels' locality
lines two ways, as S8 read them and as the S7 baseline readers wrote them. The
readers' versions include their slips ("ESlope", "Elev.6400", "Yepocapa,4800
ft.", "Chimaltenago"). Further tests cover the notations, headings, offsets and
elevation forms, and the comparison rules.

## 2. Tier 1: Wikidata

The owner's tier 1 (G35) asks gazetteers for "the historical name and when it
was in use", returning modern equivalents. `georef_places.py` holds the record
that every gazetteer returns. `georef_wikidata.py` builds Wikidata's requests
and reads the answers into those records. It sends nothing itself: the tool,
specified in a later section, sends each request with retries, and records its
provenance as a sub-call (G23).

**The record.** A `Place` holds:
- the source and its record id;
- the name, and the other names as the source gives them;
- a description;
- its classes;
- the country it lies in;
- the ISO code, when the place is itself a country;
- the units it lies in, each with the start and end the source states;
- a point;
- the earliest start and the latest end;
- the places it replaced and those that replaced it;
- the license.

A class, a country, a unit or a successor is a reference: an id and the name
the source gives it.

**Requests.** Both requests go to the Action API. During the research it answered
more than twenty calls without throttling, whereas the query service throttled
after two (HTTP 429, a 120 s `Retry-After`) (#94, S15 and S16).
- `wbsearchentities` finds items for each search string PLAN 4.8's filter
  returns: English, items only, seven hits.
- `wbgetentities` reads up to 50 items at a time. It returns labels and aliases
  in English, Spanish and the multilingual default, the English description, and
  these statements:
  - P31, instance of;
  - P17, country;
  - P131, located in, with its P580 and P582 qualifiers;
  - P571 and P580, start;
  - P576 and P582, end;
  - P625, point;
  - P1365, replaces;
  - P1366, replaced by;
  - P297, ISO 3166-1 code.
- A second `wbgetentities` call names the items those statements point to.
- What a request carries follows PLAN 4.8. Every search string comes from S4's
  filter (`place_request_text`), item ids come from Wikidata's own answers, and
  the fixed parameters (action, language, type, limit, properties) are reviewed
  constants that carry no label text.

**Reading.**
- **Statement order.** Deprecated statements are ignored, and preferred ones come
  first.
- **Name.** A place's name is its English label, else the multilingual one, else
  the Spanish one, else its id. Its other labels and aliases follow, without
  repeats.
- **Dates.** A date keeps the precision Wikidata states: day, month or year. A
  coarser date keeps the year Wikidata stores.
- **Point.** A point is read only on Earth.
- **Missing items.** An item Wikidata reports as missing is skipped.

**Outcomes.**

| Answer | Outcome |
|---|---|
| HTTP 200 with one or more items | `success` |
| HTTP 200 with none, or error `no-such-entity` | `no_match` |
| HTTP 200 with an empty body | `empty_response` |
| a body that isn't a JSON object | `malformed_response` |
| HTTP 429, or error `maxlag` or `ratelimited` | `rate_limited` |
| HTTP 401 | `authentication_error` |
| HTTP 403 (Wikimedia refuses requests without a descriptive User-Agent) | `authorization_error` |
| any other status, or any other API error | `provider_error` |

A timeout is the caller's to record.

Every place carries the license CC0-1.0.

**Tests.** `tests/test_georef_wikidata.py` reads recorded answers from
`tests/fixtures/georeferencing/`:
- S8's searches of 2026-09-23 for the nine pilot names;
- the pilot places' items and the names of the items they point to, retrieved
  2026-09-24 and reduced to the fields read here.

The tests check:
- "Mount McKinley" finds Denali first and nothing in the Philippines.
- "Davao Province" finds only the province of 1914 to 1967, with its three
  successors.
- Mount Apo Natural Park starts in 2004.
- The Philippines' aliases include the code "RP", which section 1's full-name
  test excludes.
- Every row of the outcome table.

## 3. Reference datasets in the project's storage

Some sources are read as files, not asked as services:
- Copernicus GLO-30 elevation tiles (D11, the coordinator's ruling), for
  measurements and for derived elevations (G37);
- the GeoNames country dumps, for tier-1 names (G35). Nothing is sent to GeoNames
  (PLAN 4.8 in #124).
- geoBoundaries' open release, for containment (the coordinator's ruling). Its
  entries come with the derivations.

`georef_datasets.py` is their manifest. Each entry gives:
- an id and its purpose;
- the source URL and the date the bytes were retrieved;
- the byte size and the SHA-256 of the exact bytes;
- the license and its URL;
- the credit text, taken from the source's own terms;
- the content type the upload sets.

The credit goes into `georeferenceSources` and into the dataset metadata (G35's
follow-up, D2).

**Storage and upload.** S2 stores each file as `application/sha256/<digest>` in
the bucket the runtime configures, and the repository never names that bucket.
The owner uploads with a command S2 writes from the merged manifest. It checks
each size and digest, stops on any mismatch, and never overwrites (S2 and the
coordinator, 2026-09-24).
- The tiles are downloaded again from their source URLs, which serve the same
  bytes.
- GeoNames regenerates its dumps daily and keeps no archive. The pinned bytes
  are therefore the only copy. S8 keeps them read-only outside the repository,
  and the command uploads them from there, never downloading them again. Each
  such entry says so. Refreshing a dump means a new download, a new manifest
  pull request and a new upload.

**Verify on read.** A reader recomputes the SHA-256 of what it reads and refuses
a mismatch. The worker can also write under that prefix, so only the digest
proves the bytes are the reviewed ones.

**The pilot's files.**
- Three GLO-30 tiles, one per 1-degree cell:
  - N07 E125, for the McKinley camps and Mount Talomo;
  - N06 E125, for Mount Apo;
  - N14 W091, for Yepocapa.

  A point's tile is the cell its latitude and longitude fall in, named for the
  cell's south-west corner. The tiles were read from the anonymous open-data
  bucket on 2026-09-24. Each MD5 equalled the bucket's ETag, and each size its
  `Content-Length`.
- The Philippines and Guatemala dumps of 2026-09-24.

**Credits.**
- GLO-30: the Copernicus notice for adapted data, as the licensing section of
  the Copernicus Data Space page for the DEM gives it (checked 2026-09-24):
  "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus
  Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European
  Union and ESA; all rights reserved". It applies because derived elevations
  adapt the data.
- GeoNames: its dumps' own readme states CC BY 4.0 and supplies the data as it
  is. The credit names GeoNames and that license.

**Tests.** `tests/test_georef_datasets.py` checks:
- the manifest's shape: unique ids, 64-character digests, object names built
  from digests, a credit on every entry, and no bucket names;
- the three tiles and the tile each pilot place falls in;
- that a point outside the manifest's tiles has no tile;
- the two GeoNames pins, marked as the only copy;
- that bytes of the wrong size or digest are refused.

## 4. Tier 1: the GeoNames dumps

`georef_geonames.py` reads the GeoNames country dumps pinned in section 3. The
caller passes a pinned dump's bytes after `verified` has checked them, so nothing
is sent to GeoNames (PLAN 4.8). The rows stay as the dump gives them, and a
search returns its matches as the shared `Place` records of section 2.

**Reading a dump.** `read_dump(country, bytes)` opens the zip's `<country>.txt`,
which is 19 tab-separated columns per row, as the dump's readme lists them. It
indexes every name a row carries by section 1's comparison key: the name, the
ASCII name and each alternate name.

| Dump | Outcome |
|---|---|
| empty | `empty_response` |
| not a zip, missing the country's file, or a row without 19 columns | `malformed_response` |

**A place.**
- Its **parents** are the administrative units its codes name (the ADM3, the
  ADM2, then the ADM1), taken from the same dump's rows, nearest first.
- Its **country** is the dump's ISO code, with the name of the dump's country row.
- A **country row** carries the ISO code itself.
- Its **kind** is the feature class and code, such as `A.ADM2` or `T.MT`.
- It carries **no dates**. GeoNames gives none, so history (a later section)
  leans on Wikidata.

**Finding a reading.** `find(dump, reading, kinds)` returns:
- the places whose names have the reading's key, limited to feature classes
  ("A") or to a class and code ("A.ADM2");
- the places one letter off (G34), but only when there are no such places and
  the reading is a full name. Such a place qualifies only through a name that is
  itself a full name, never a code or an abbreviation.

Uniqueness and the fit with the other place fields are the tool's to test.

**Tests.** `tests/test_georef_geonames.py` reads 23 rows copied from the pinned
Philippines and Guatemala dumps of 2026-09-24. The fixtures' README credits
them under CC BY 4.0. The tests check:
- "Davao Province" names modern Davao del Norte, the 1967 successor, which is
  #94's trap. Without its level, the key also names the region and the city.
- "Chimaltenago" is one letter from both the department and the municipio of
  Chimaltenango.
- Three features are called Mount Apo, each in a different province.
- There is no Philippine Mount McKinley.
- "Mindanao" is an island in one dump and a village in the other.
- Yepocapa's town lies inside its municipio and department.
- Codes never reach the one-letter gate.
- Every row of the outcome table.
