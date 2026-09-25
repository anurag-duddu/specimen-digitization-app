# Go-live georeferencing workstream (S8): spec deltas

The retrospective georeferencing tool behind the harness's `geography_lookup`
interface, which the owner asked for on 2026-09-24 (G34): "clear with place ID byt
I want the harness for location retrospective georeferencing fully implemented".
Its plan is `docs/product-requirements/GEOREFERENCING.md` (#94), and the owner set
its design the same day (G35 to G40): three tiers (historical gazetteers with
curator-confirmed entries, Google given the modernized name, and a final
point-radius uncertainty), fields derived with evidence when the label leaves
them out, and a layer for every value. The point-radius is computed in-house by
D13, the coordinator's ruling of 2026-09-24. The tool replaces the Google module
behind the same interface only once two gates pass: the owner accepts the plan
as G35 to G42 revise it (G12), and the acceptance lab shows the tool matches or
beats the Google module (coordinator ruling, 2026-09-24). Until then the Google
module stays in production (G12). Each pull request adds its section here before
its tests and implementation.

## 1. Reading locality text

`georef_locality.py` reads one locality literal, exactly as a reading has it, into
the parts the later tiers compare locally. It makes no request, decides no
outcome and never changes the literal: the result keeps it verbatim (G27).
Nothing it produces leaves the tool except through PLAN 4.8's filter. No part,
name or reading is sent as it stands, and a part can hold text that is no place,
such as a collector's name.

**Lines and parts.** Commas and semicolons separate parts, except a comma with a
digit on each side, which is inside a number ("1,463 m", "0,5 km", "1463,5 m"). A
line break separates parts too, except after a word that needs the next one:
- a feature notation ("E. Slope Mt." / "McKinley" on 105526322);
- a unit written before its name ("Yepocapa, Mun." / "Yepocapa," on 105526328);
- a linking word, "de", "del" or "of" ("Departamento de" / "Chimaltenango").

**Notations (G29).** The Insects harness reads these whole words in any case,
with or without the period; they come from the pilot's labels and from the unit
words the Google tool already drops. Other collections add their own tables (G29).

| Kind | Written | Read as |
|---|---|---|
| unit after its name | Prov., Province; Dept., Department; Co., County; State; Region | the part's unit: province, department, county, state, region |
| unit before its name | Mun., Municipio, Municipality; Depto., Departamento; Provincia; Estado | municipality, department, province, state |
| feature | Mt., Mount | "Mount", a mountain |
| country | P.I. | "Philippine Islands" |
| institution | CNHM, FMNH | the museum's own names, never a place |

A part that is only a unit word joins the part its position points to, or,
failing that, the part on its other side: "Davao, Prov. 3300'" (105526326) reads
as one part, "Davao Prov.", and so does "Prov., Davao". A part's readings are the
full names it is compared by locally, most specific first: "Davao Prov." gives
"Davao Province" and "Davao". A notation outside the table stays as written.
Nothing a tier sends comes from these readings: a request carries the literal as
PLAN 4.8's filter returns it, and the filter expands notations itself, after its
cuts.

**Slopes and offsets.** A heading followed by "slope", "side" or "flank" belongs
to the feature beside it: "E. slope Mt. McKinley", "E Slope Mt. McKinley", a
reader's joined "ESlope Mt. McKinley", and "Mt. Apo, east slope". A heading is
one of the 16 compass points abbreviated, with or without periods ("NNE",
"N.E."), or one of the eight main points written as a word ("north",
"northeast", "eastern"). Standing in its own part, such a phrase joins an
adjacent feature, the one before first; failing that, the part before it, or
else the part after it. "5 km NE of Yepocapa" is an offset. A heading followed by
"slope", "side" or "flank" never heads an offset, so in "1500 m N slope Mt. Apo"
the "1500 m" is an elevation. An offset's place follows the rules for any part:
its elevation phrases leave it, and a place with a digit or without a letter is
kept aside with its offset ("10 m S of Camp 3", "5 km N of 1946"). A heading keeps
its written form and its bearing in degrees, and a distance stays as written;
points and radii are tier 3's.

**Elevations (G27, G38, G41).** Elevation phrases ("4800 ft.", "4800ft.", "6400'",
"Elev. 6400'", "1,463 m", "1.463 m", "6.400 ft.", "4000-4500 ft") leave the place
text and are kept as written, as G27 keeps a verbatim and G38 keeps each layer:
the numbers whole as written, dots and commas included, and the unit as feet,
metres, or none when the label gives none ("Elev.6400" on 105526322). This module
converts and fills nothing. G41's "Convert and fill" (the label's own number
fills From and To, and the other unit is converted exactly, each marked derived)
happens in S4's later derivation layer.

**Unplaced text.** A part left with a digit or without a letter, such as a date
("IV-26") or a camp number, and a heading phrase with no part to join, are kept
aside and never searched: gazetteer place names carry no digits. A part is kept
aside whole, so "Mindanao, P.I. 3 Sept. '46" keeps only "Mindanao" as a part and
sets "P.I. 3 Sept. '46" aside, "P.I." with it.

**Comparing names (G34, as the coordinator read it on 2026-09-24).** Names
compare by a key: case folded, diacritics and format characters (such as a
zero-width space) removed, punctuation turned into spaces, feature notations read
("Mt." compares as "mount"), and unit words dropped with a "de", "del" or "of"
after a leading one. So "Chimaltenago" and "Departamento de Chimaltenango" have
keys one letter apart. `letters_apart` counts the single-character insertions,
deletions and substitutions between two keys, up to a cap of 2; it looks only
within that band, so its work grows with the keys' length, not its square. The
one-letter gate compares full names only, never codes or abbreviations. A word is
not part of a full name when it:
- has a period inside it ("P.I."),
- ends in a period after at most four letters ("Phil.") and is not a notation in
  the table,
- has a digit,
- has no letter at all ("-"), or
- is written in capitals of at most three letters ("PH", "PHL", "RP").

A name made of notations alone ("Mt.", "Mount") is not a full name either.

A candidate one letter off settles the place only when it is the only such
candidate, and every other admin field of the same reading, all of them and at
least one, matches it by fold or alias. The field then carries a `near_spelling`
warning finding that never routes the record. This is the coordinator's reading
of G34 (PLAN 2.1), which #94's D15 applies to this tool. The tool tests that; this
module does not.

**Readers (G19, G20).** Each reader's literal is read on its own and keeps its
observation id. Literals whose parts share their keys form one variant, so a
lookup can tell whose literal it confirmed. The variant keeps each literal's own
reading, its headings, offsets and elevations included. Handwriting-qwen's
"Chimaltenango" and handwriting-muse's "Chimaltenago" on 105526329 are two
variants.

**Tests.** `tests/test_georef_locality.py` reads the ten pilot labels' locality
lines two ways, as S8 read them and as the S7 baseline readers wrote them. The
readers' versions include their slips ("ESlope", "Elev.6400", "Yepocapa,4800
ft.") and handwriting-qwen's silent correction of the label's own "Chimaltenago"
to "Chimaltenango". Further tests cover:
- the notations in any case, with or without their periods;
- headings between two features or beside none;
- offsets and their places;
- numbers read whole;
- the elevation forms;
- line joins;
- variants;
- the comparison rules.
