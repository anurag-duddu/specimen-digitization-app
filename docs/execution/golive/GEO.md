# Go-live georeferencing workstream (S8): spec deltas

The retrospective georeferencing tool behind the harness's `geography_lookup`
interface, which the owner asked for on 2026-09-24 (G34): "clear with place ID byt
I want the harness for location retrospective georeferencing fully implemented".
Its plan is `docs/product-requirements/GEOREFERENCING.md` (#94), and the owner set
its design the same day (G35 to G40): three tiers (historical gazetteers with
curator-confirmed entries, Google given the modernized name, the in-house
point-radius), fields derived with evidence when the label leaves them out, and
a layer for every value. The tool replaces the Google module behind the same
interface only once two gates pass: the owner accepts the plan as G35 to G42
revise it (G12), and the acceptance lab shows the tool matches or beats the
Google module (coordinator ruling). Until then the Google module stays in
production (G6). Each pull request adds its section here before its tests and
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
the full names it is compared by locally, most specific first: "Davao Prov."
gives "Davao Province" and "Davao". A notation outside the table stays as
written. Nothing a tier sends comes from these readings: a request carries the
literal as PLAN 4.8's filter returns it, and the filter expands notations itself,
after its cuts.

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
- the credit text, taken from the source's own terms.

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
