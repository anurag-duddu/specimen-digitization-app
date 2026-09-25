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
- `wbsearchentities` finds items for each reading (section 1): English, items
  only, seven hits.
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
- A request carries place text only: one reading's name, or item ids. It never
  carries collectors, dates or other transcribed text (the coordinator's ruling
  for every gazetteer and Google, PLAN 4.8 in #124).

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

## 5. History: was a place in use, and what replaced it

The owner's tier 1 evaluates "the historical name + date active" and returns
modern equivalents (G35). `georef_history.py` answers those two questions for a
`Place` (section 2). It is pure: it makes no request.

**Dates are intervals.** A label's date is read at the precision written (G24):
"1946" means the whole year and "1946-09" the whole month. A place's start and
end are intervals too, at the precision its source states. `use_on(place,
date)` returns one of five states:

| State | When |
|---|---|
| `in_use` | the place certainly started before the label's first day and certainly lasted past its last |
| `partly` | it was in use for only part of the label's interval |
| `ended` | its latest possible end falls before the label's first day; the gap in days is recorded as a finding |
| `not_started` | its earliest possible start falls after the label's last day |
| `undated` | the source gives neither a start nor an end |

The owner held D5, so no tolerance widens a place's dates. A name used after
its place ended, such as "P.I." on a label of September 1946, two months after
the Commonwealth ended, is `ended`, and its 59 days are a finding. The tool
decides nothing from that gap.

**Roles.** A place its source says ended is `historical`, and any other place is
`modern`. The two roles map onto `PlaceCandidate.role`.

**Units on a date.** `parents_on(place, date)` keeps the units a place lay in on
the label's date. A unit counts when its link states no start or end, or when
the stated start and end (Wikidata's P580 and P582 qualifiers on P131) cover
the whole date.

**Successors.** `modern_successors(place, places)` follows "replaced by" (P1366)
through the places the tool has read, until it reaches a successor without an
end. A successor the tool has not read is kept as it is. A cycle stops.

**Tests.** `tests/test_georef_history.py` uses the recorded Wikidata items of
section 2 and checks:
- The 1914-1967 Davao province is `in_use` on 3 September 1946 and in 1946,
  `partly` in 1914 and in May 1967, `ended` in 1970 (969 days), and
  `not_started` in 1900.
- Mount Apo Natural Park, founded 2004, is `not_started` in November 1946.
- The Commonwealth, ended 4 July 1946 and built with Wikidata's dates, is
  `ended` for September 1946 with a gap of 59 days.
- The Philippines is `in_use`.
- Mount Apo is `undated`.
- The 1946 province has three modern successors: Davao del Norte, Davao del
  Sur and Davao Oriental.
- A successor chain is followed and a cycle is stopped.
- Units are selected by the dates of their links.

## 6. Curated entries: places and itineraries only the museum's records know

The owner ruled (G36): "Curator confirms". S8 drafts each place and itinerary
entry with its sources. The Insects collection manager, or a curator they name,
confirms it. A confirmed entry settles a field, an unconfirmed one never does,
and the owner added "We cant make wrong conclusions". `georef_curated.py` holds
the entries. The curated entries feed tier 1 (G35).

**Confirmation.** An entry becomes confirmed only in a pull request that cites
the owner's recorded confirmation (PLAN 4.8 in #124). That pull request adds a
`Confirmation` to the entry, with the confirming role, the ISO date and the
owner's record. It never names a person (G36). `settles(entry)` is true only for
a confirmed entry. Every entry drafted here is unconfirmed, and the curator's
review sheets are with the owner.

**Place entries.** A place entry covers names no gazetteer holds for one
country, together with the units the name must lie within, the modern place S8
proposes, that place's gazetteer ids, and the sources.
`curated_place(country, written)` finds the entry by section 1's key.
- The one entry drafted so far is "Mt. McKinley" in Davao, Mindanao: Hoogstraal
  (1951, p. 40) reports that the name appears on no map. S8 proposes Mount
  Talomo (Wikidata Q31472786, GeoNames 1683778). The Denali that Wikidata
  returns first is excluded, because the entry is scoped to the Philippines.

**Itineraries.** An itinerary lists an expedition's dated camps on one
mountain, from a published narrative: each camp's elevation in feet, its dates,
and the slope where the narrative states one. `matching_camps(itinerary,
collector, date, elevation, slope)` returns the camps a label fits:
- a collector the itinerary names, matched on the surname within the
  collector's literal;
- a label date whose interval (G24) overlaps the camp's dates, so that a label
  written to the month fits every camp that month;
- when the label states them, the camp's elevation in feet, and a slope the
  camp shares or leaves unstated.

S8 drafts two itineraries:
- the McKinley camps, August to October 1946 (Hoogstraal 1951, pp. 23 and
  41-42);
- the Mount Apo camps of October and November 1946 (p. 24), on the massif
  (Wikidata Q455963), not the "Mount Apo" near Malita.

**Tests.** `tests/test_georef_curated.py` checks:
- An unconfirmed entry never settles.
- A confirmation records a role, a date and the owner's record, and a
  confirmation without them is refused.
- The Davao "Mt. McKinley" entry is found, and neither a US "Mount McKinley" nor
  Mount Apo matches it.
- The McKinley labels fit their camps, taking collector, date and elevation
  from the pilot labels: 105526321 and 105526322 fit the 6,400-foot camp, and
  105526324 fits the base camp. Another collector, or a later date, fits none.
- The Apo label fits the six camps of November 1946 whose slope is east or
  unstated.

## 7. Tier 1: Getty TGN

The owner's tier 1 names Getty TGN (G35). `georef_tgn.py` builds requests to two
Getty services and reads the answers into section 2's `Place` records. It sends
nothing itself: the tool sends each request and records it as a sub-call. Both
services answer anonymously under ODC-By 1.0, so no access is needed, and
Getty's token-gated gateway is not used (PLAN 2.3; #94, S32).

**Requests.**
- The reconciliation service finds TGN places by one reading's name: type
  `/tgn`, ten results. The tool passes only text S4's place-request filter
  returns (PLAN 4.8). The type and the limit are reviewed constants.
- The SPARQL endpoint reads up to 50 records at a time by TGN id. One query
  reads each record's GVP name, place types, point and chain of preferred
  parents; a second reads every name with its language. An id is digits only
  and is checked before a query is built, so no record value enters SPARQL.

**Reading.**
- **Name.** A place's name is its English preferred name when TGN has one, else
  its GVP name, which TGN often writes inverted ("Apo, Mount"). Its other names
  follow, the preferred ones first, codes included.
- **Kinds.** Each place type is an AAT reference with its name, the preferred
  type first.
- **Country and parents.** The country is the nearest place on the chain of
  preferred parents, the place itself included, whose preferred type is
  "nations" (`aat:300128207`). The parents are the places between the place and
  its country, nearest first. A country or a parent keeps its GVP name.
- **Point.** TGN's point, read only when its latitude and longitude are in
  range.
- **Dates.** TGN dates names, not places, so a place carries no dates and
  section 5 reads it as `undated`. The dates of names, such as "Commonwealth of
  the Philippines" (1935 to 1946), are not read yet.
- **Missing ids.** An id TGN does not hold is skipped.

**Outcomes.** One table covers both services.

| Answer | Outcome |
|---|---|
| HTTP 200 with one or more results or records | `success` |
| HTTP 200 with none | `no_match` |
| HTTP 200 with an empty body | `empty_response` |
| a body that isn't the expected JSON object | `malformed_response` |
| HTTP 429 | `rate_limited` |
| HTTP 401 | `authentication_error` |
| HTTP 403 | `authorization_error` |
| any other status | `provider_error` |

A timeout is the caller's to record.

**Credit.** Every place carries the license ODC-By-1.0. The credit is the line
Getty's data-services page asks for (checked 2026-09-24): "Contains information
from the J. Paul Getty Trust, Getty Research Institute, Thesaurus of Geographic
Names, which is made available under the ODC Attribution License".

**Tests.** `tests/test_georef_tgn.py` reads answers recorded on 2026-09-24: the
reconciliation service's for twelve pilot names, and the SPARQL endpoint's for
the 24 records they led to. The tests check:
- "Mount Apo" finds the mountain first, filed under Cotabato, with "Mount Apo"
  among its names.
- Every place "Mount McKinley" finds lies in the United States; one is Denali.
- TGN holds no Yepocapa, no Mount Talomo and no "Chimaltenago".
- "Davao Province" finds a city first. TGN files that name under a record typed
  "special cities" that also carries "Davao City", and it has no record of the
  1914-1967 province: #94's trap again.
- "Philippine Islands" finds a ridge in Wisconsin first. The Philippines carries
  that name too, and its English name is "Philippines".
- Codes among the names ("RP", "PHL", "GT03") are not full names (section 1).
- The Chimaltenango department and its capital lie in Guatemala.
- Every row of the outcome table.

## 8. Tier 1: NGA GNS

The owner's follow-up to G35 names NGA among the openly licensed sources whose
coordinates are stored, credited. `georef_nga.py` builds requests to the GEOnet
Names Server's ArcGIS REST service and reads the answers into section 2's
`Place` records. It sends nothing itself. The service answers anonymously.

**Requests.**
- A name search finds the features whose names match one reading's name
  exactly, case and diacritics aside: it compares the name with each full name
  and with its form without diacritics. The tool passes only text S4's
  place-request filter returns (PLAN 4.8). The name enters a fixed where clause
  as one quoted literal, its quotes doubled. A name that is empty, longer than
  200 characters or holds a control character is refused.
- A features request reads every name of up to 50 features by GNS feature id,
  and a units request names up to 50 first-order units by code. Each value is
  checked against its pattern before a request is built.
- The fields, the order and the format are reviewed constants.

**Reading.**
- **Name.** A feature's name is its first name in this order of GNS name types:
  approved, conventional, approved non-authoritative, approved transitional,
  provisional, anglicized, variant. Names in non-Roman scripts come last. Every
  other name follows, each with its form without diacritics.
- **Kind.** The feature class and designation, such as `T.MT` or `P.PPLA2`, as
  GeoNames writes them (section 4).
- **Country.** The first two letters of the feature's first-order code, which
  GNS writes in the GENC form "PH-DAV". For the pilot's countries these are the
  ISO codes GeoNames uses. A country's own feature carries the code as its ISO
  code.
- **Parents.** The first-order unit, named by the units request. The
  country-wide code ("PH-000") is not a unit.
- **Point.** GNS's point, read only when its latitude and longitude are in
  range.
- **Terminated features.** GNS marks a feature that no longer exists with a
  termination date, and the date can trail the event by years. Kalinga-Apayao,
  divided into two provinces by Republic Act 7878 of 14 February 1995, is marked
  terminated on 2012-03-15, while Maguindanao's date, 2022-09-17, is the day of
  the plebiscite that ratified its division (Republic Act 11550 of 2021; both
  statutes read on lawphil.net on 2026-09-24). Read as a place's end, such a
  date would make a unit look in use for years after it ended. The reader
  therefore skips terminated features: NGA answers with current features only,
  and history leans on Wikidata (section 5). A feature carries no dates.

**Outcomes.** GNS reports its own errors inside an HTTP 200 answer, each with a
code.

| Answer | Outcome |
|---|---|
| HTTP 200 with one or more current features or units | `success` |
| HTTP 200 with none | `no_match` |
| a name search cut short: more features share the name than one answer lists | `ambiguous` |
| HTTP 200 with an empty body | `empty_response` |
| a body that isn't the expected JSON object; error 400, a query the service cannot run; a features answer cut short | `malformed_response` |
| HTTP 429 or error 429 | `rate_limited` |
| HTTP 401, or error 401, 498 or 499 | `authentication_error` |
| HTTP 403 or error 403 | `authorization_error` |
| any other status or error | `provider_error` |

A timeout is the caller's to record.

**Credit.** NGA's pages state no license and ask for no citation (#94, S33), so
a place carries no license id. The owner stores NGA's coordinates credited (G35),
and the credit is "NGA GEOnet Names Server" (PLAN 4.8).

**Tests.** `tests/test_georef_nga.py` reads answers recorded on 2026-09-24: name
searches for twelve pilot names, the features they found, and those features'
first-order units. The tests check:
- "Mount Apo" names three mountains, in Cotabato, in Davao Occidental and in
  Iloilo, the last through a variant name, and a street in Makati.
- There is no "Mount McKinley" and no "Chimaltenago".
- "Davao Province" names only modern Davao del Norte, through a variant name:
  #94's trap again.
- Yepocapa is a municipio and a town in Chimaltenango, at GeoNames' points.
- Mount Talomo lies in PH-DVC, Davao City, which GNS keeps as a first-order unit.
- The country code comes from the first-order code, and the Philippines carries
  it as its ISO code.
- A terminated feature is skipped.
- Every row of the outcome table, and the checks on names, ids and codes.

## 9. Tier 3: the point-radius uncertainty

The owner's tier 3 "Calculates final Point-Radius Uncertainty" (G35), and the
coordinator ruled that the tool computes it in-house (D13): the point-radius
method of the Georeferencing Best Practices, porting the Georeferencing
Calculator's arithmetic, tested against the Calculator's own worked examples.
`georef_radius.py` computes. It sends nothing and reads no file.

**The Calculator's method.** S8 read it from the Calculator's published code
(VertNet/georefcalculator at commit 1cc9f4c, Apache-2.0: `support.js` and
`gci_ui.js`) and took the worked examples from `test_data.js` in the same
commit. The code was read, never run. Best Practices 3.4.7 defers to the
Calculator for combining uncertainties, and the Calculator adds its sources for
every locality type, with two exceptions listed below.

**Sources of uncertainty, in meters.**
- **Radial.** The feature's geographic radial: the distance from its corrected
  center to the farthest point of its boundary.
- **Source.** The coordinate source's own error: none for a gazetteer or a
  locality description, and the Calculator's value for a map, such as 40 ft
  for a USGS 1:24,000 map.
- **Measurement.** The sum of every measurement's error.
- **Precision.** The diagonal of one degree of latitude and one of longitude at
  the point, on the datum's ellipsoid, times the coordinates' precision in
  degrees: 1/3600 for the nearest second, 0.00001 for five decimals.
- **Datum.** None for a recorded datum. Every tier-1 source gives WGS84
  points, so a gazetteer point adds nothing. For an unrecorded datum, the caller
  gives the value for the place; without one, the Calculator's worst case,
  5,359 m, applies, so an unknown datum never shrinks a radius.
- **Offset precision.** Half the unit a distance is written to: 0.5 mi for
  "5 mi" written to the mile, 5 mi for "10 mi" written to ten miles.
- **Heading precision.** Half the angle between neighbouring points of the
  compass the heading is written with: ±45° for N, E, S and W; ±22.5° for NE,
  SE, SW and NW; ±11.25° for the eight three-letter points; ±5.625° for the
  sixteen "by" points; ±1° for a heading in degrees.

**Combining them.**

| Locality type | Uncertainty |
|---|---|
| coordinates only | datum + source + measurement + precision |
| a feature only | the same, plus the radial |
| a distance only ("5 mi from X") | a feature's, plus the offset and its precision |
| a distance along a path | a feature's, plus the offset precision |
| distances along two orthogonal directions | a feature's, plus the offset precision times √2 |
| a distance at a heading | the error of a cone, plus precision |

For a distance d at a heading of precision α, with e the sum of the datum,
radial, measurement, offset precision and source, the cone's error is the
distance from the point d + e along the heading to the point d along the
cone's edge: √((d + e − d cos α)² + (d sin α)²).

**Points.** An offset moves the point by the ellipsoid's meters per degree at
the starting latitude (NIMA 8350.2, as the Calculator does), rounded to seven
decimals. The ellipsoid is WGS84 unless the datum names another: Clarke 1866
for NAD27, GRS80 for NAD83.

**A heading alone.** "E. slope of X" is the part of X's circle within the
heading's cone (#94, 3.8). For a cone of ±45° or wider, the smallest circle
around that part has the chord between the arc's ends as diameter: its center
lies R cos α from X's center along the heading, and its radius is R sin α. For
a narrower cone, the circle passes through X's center and the arc's ends: its
center and its radius are both R / (2 cos α). That circle is then the feature
(the Quick Reference Guide, 2.2.2).

**Units.** Everything is in meters, with exact factors: 1 mi = 1,609.344 m and
1 ft = 0.3048 m. The Calculator's own mile is 1,609.3445 m. That half
millimetre changes no worked example at the precision the Calculator shows.

**Tests.** `tests/test_georef_radius.py` checks:
- The Calculator's eight worked examples, each uncertainty to the decimals the
  Calculator shows: two with coordinates only, one with a named place only,
  one each with a distance only, along a path and along orthogonal
  directions, and two at a heading. The four whose datum was not recorded used
  the Calculator's 2015 grid of datum errors, 79 m at Bakersfield. The tests
  pass that value, since the grid has changed: its 2019 version gives 3,045 m
  there.
- The three examples' new points, to seven decimals. One of them, the
  orthogonal example, is 1e-7 degree (about 1 cm) off in longitude, and both
  mile factors give the same point.
- The datum rule, the offset precision, and the heading precision of every
  compass point.
- The sector's circle: it encloses X's center and the whole arc, for ±45° and
  ±22.5°.
