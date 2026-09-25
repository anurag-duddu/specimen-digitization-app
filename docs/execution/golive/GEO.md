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

## 10. Geometry: a unit's extent, and a circle inside it

Two derivations read a unit's boundary. County and city are derived only when
the whole uncertainty circle lies inside one unit (the coordinator's reading of
G37), and a location found only as its county sits at the county's precision
(the coordinator's reading of G38). `georef_geometry.py` answers both. It is
pure: the caller passes a boundary it has read, and distances use the
ellipsoid's meters per degree (section 9).

**Boundaries.** A boundary is a GeoJSON Polygon or MultiPolygon in longitude and
latitude, as geoBoundaries publishes it: each polygon is an outer ring and its
holes. A ring needs three distinct points. A boundary spanning more than 180
degrees of longitude, which may cross the antimeridian, is refused.

**Inside.** A point is inside when a ray from it crosses the boundary's rings an
odd number of times, so a point in a hole is outside.

**Clearance.** The distance from a point to the boundary's nearest edge, in
meters, on the meters per degree at the point's latitude.

**A circle inside a unit (G37).** The whole circle lies inside when its center is
inside and the clearance is at least its radius plus a margin. The margin is the
simplification error of the file the boundary came from. The coordinator ruled
that the Philippine units come from geoBoundaries' simplified files, with
containment widened by that error, and that a circle which doesn't clear its
unit by it derives nothing (#191's 4.8 row). geoBoundaries' build simplifies
with mapshaper's Douglas-Peucker at 100 m and snaps at 0.00001 degree, about
1.1 m (wmgeolab/geoBoundaryBot, the builder's simplify step), so the margin
for a simplified file is 101.2 m. The dataset manifest (section 3) will carry
each file's margin when the files are pinned.

**A unit's extent (G38).** The corrected center and the geographic radial (the
Quick Reference Guide, 1.6.2 and 1.6.3):
- The center of the smallest circle around the unit's outer rings, found on
  their convex hull in the meters per degree at the unit's middle latitude. The
  radial is that circle's radius.
- When that center falls outside the unit, as in a hole or a notch, the Guide
  puts the center on the unit's boundary instead. The center is then the
  boundary point whose farthest hull vertex is nearest, and the radial is that
  distance. Along each edge the farthest-vertex distance is convex, so each edge
  is searched to its minimum. An edge is skipped when even its nearest possible
  point is farther than the best found: the farthest hull vertex from the edge
  itself bounds it.

The flat projection is exact at the latitude it is taken at. East-west
distances away from it are off by the ratio of the cosines, about 0.2% across a
unit two degrees tall near the pilot's latitudes.

**Tests.** `tests/test_georef_geometry.py` uses synthetic boundaries:
- a square with a hole, and two islands, for inside, clearance and the margin;
- a plain square, whose circle is centered inside;
- the framed square, whose center moves onto the hole's edge;
- a U, whose center moves onto the notch's floor. No vertex of the U reaches its
  corners with a smaller radius.
- boundaries that cannot be read.

## 11. Elevations from GLO-30

Where a label states no elevation, the elevation fields are derived from the
settled location with Copernicus GLO-30 (G37; D11, the coordinator's ruling):
the lowest and the highest ground within the uncertainty circle (PLAN 4.8).
`georef_elevation.py` reads the tiles pinned in section 3. It sends nothing and
decodes only the parts of a tile that a circle touches.

**The tiles.** Each tile is a Cloud Optimized GeoTIFF on WGS 84. It holds 3,600
by 3,600 float32 elevations in meters for one square degree, in internal tiles
of 1,024 pixels, deflated with TIFF's floating-point predictor. A pixel's value
is at its center (GeoTIFF's point raster type), and the first pixel lies on the
tile's north-west corner.

**Reading.** `read_tile` reads the first image's structure. It accepts one
float32 sample per pixel in internal tiles, deflated or stored, with or without
the floating-point predictor, on a point or an area raster. Anything else is
refused.

**The range.** `elevation_range(tiles, center, radius)` returns the lowest and
highest value among the pixels whose centers lie inside the circle. Distances
use the meters per degree at the center (section 9).
- When no pixel center lies inside, as for a circle smaller than a pixel, it
  returns the value of the pixel whose cell holds the center.
- A value the file marks as missing is skipped.
- A circle that reaches beyond the tiles passed in is refused, so the caller
  passes every tile the circle touches.

The derived value names its settled inputs and the tile's dataset id and
SHA-256, as PLAN 4.8 asks. The derivation itself comes with S4's #144.

**Checked on the pinned tiles.** This check ran locally, not in CI, because the
tiles are 26 to 45 MB. At the pilot's points GLO-30 gives:
- Yepocapa's town (GeoNames 3587636): 1,395.8 m;
- Wikidata's Yepocapa point: 1,417.8 m;
- the municipio's centroid: 1,128.2 m;
- Mount Apo's summit: 2,946.2 m;
- Mount Talomo's summit: 2,607.8 m.

The research's figures at the same points were SRTM's 1,396, 1,427, 1,134 and
2,620 m, and 2,954 m stated for Mount Apo (#94, 3.6). Each reading took a few
milliseconds, and circles that crossed a tile's edge were refused.

**Tests.** `tests/test_georef_elevation.py` writes small GeoTIFFs in the pinned
tiles' layout, with the floating-point predictor as TIFF Technical Note 3
defines it, and checks:
- a pixel under a point, across internal tiles;
- the range over a circle: the four neighbours at one step, the diagonals at
  √2 steps;
- a circle smaller than a pixel;
- big-endian files, stored tiles and files without the predictor;
- an area raster;
- a missing value;
- a circle across two tiles, and one that reaches beyond the tiles given;
- files that are not tiled float GeoTIFFs.
