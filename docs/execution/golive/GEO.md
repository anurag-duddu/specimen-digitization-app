# Go-live georeferencing workstream (S8): spec deltas

The retrospective georeferencing tool behind the harness's `geography_lookup`
interface, which the owner asked for on 2026-09-24 (G34): "clear with place ID byt
I want the harness for location retrospective georeferencing fully implemented".
Its design is `docs/product-requirements/GEOREFERENCING.md` (#94), whose open
decisions D1 to D7 and D9 are with the owner; nothing here depends on them. The
coordinator ruled on 2026-09-24 that the tool replaces the Google module behind
the same interface only once D1 is ruled and the acceptance lab shows it resolves
the pilot slides at least as well; until then the Google module stays in
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

**Elevations (G22).** Elevation phrases ("4800 ft.", "4800ft.", "6400'", "Elev.
6400'", "1,463 m", "4000-4500 ft") leave the place text and are kept as written:
the numbers as written, and the unit as feet, metres, or none when the label
gives none ("Elev.6400" on 105526322). Nothing is converted.

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

A candidate one letter off may settle the place only when it is unique and fits
the other place fields (G34). The tool tests that; this module does not.

**Readers (G19, G20).** Each reader's literal is read on its own and keeps its
observation id. Literals whose parts share their keys form one variant, so a
lookup can tell whose literal it confirmed: handwriting-qwen's "Chimaltenango"
and handwriting-muse's "Chimaltenago" on 105526329 are two variants.

**Tests.** `tests/test_georef_locality.py` reads the ten pilot labels' locality
lines two ways, as S8 read them and as the S7 baseline readers wrote them. The
readers' versions include their slips ("ESlope", "Elev.6400", "Yepocapa,4800
ft.", "Chimaltenago"). Further tests cover the notations, headings, offsets and
elevation forms, and the comparison rules.
