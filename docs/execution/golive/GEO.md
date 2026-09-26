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

**What shows.** The reader's patterns read the text without what `fold` drops:
format characters such as a zero-width space, a word joiner or a soft hyphen,
combining marks, and the invisible Hangul fillers. What a pattern finds is cut
from the text as written, so nothing it drops splits a number, a unit or a word.
"Elev. 1463" U+200B ",5 m" reads as written, with the number "1463,5"; "Mt. Apo
1" U+200B ",463 m" reads "1,463 m"; and "14 m" U+00AD "arzo 1948" reads nothing. A
soft hyphen that ends a line, with only spaces and what `fold` drops after it,
shows as a hyphen and is read as one, so "Elev. 1500" U+00AD / "2000 m" is a range
broken across lines, set aside. A spacing mark, whose compatibility form is a
space and combining marks ("˜" U+02DC, "‾" U+203E), shows, and is a mark
(**Unsure numbers**, below).

**Lines and parts.** Commas and semicolons separate parts, except a comma inside a
number. That is a thousands group led by one to three digits ("1,463 m",
"1,463,200"), or a one- or two-digit decimal ("0,5 km", "1463,5 m"). Any other
comma between digits separates: after a four-digit year even before three digits
("6-Sept-1946,640'"), and before four digits ("6-Sept-1946,6400'"). A line break
separates parts too, except after a word that needs the next one:
- a feature notation ("E. Slope Mt." / "McKinley" on 105526322);
- a unit written before its name ("Yepocapa, Mun." / "Yepocapa," on 105526328);
- a linking word, "de", "del" or "of" ("Departamento de" / "Chimaltenango").

A line that starts with "of", in any case, joins the line before ("E. slope" /
"of Mt. Apo", "5 KM NE" / "OF YEPOCAPA"), since "of" begins no name. So does a
line that starts with a lowercase "de" or "del"; a capitalized one begins a name
("Del Carmen", "De la Paz"). Such a line joins before a month word too ("Viña" /
"del Mar", "Isle" / "of May", "Plaza" / "de Mayo", "E. slope" / "of May Hill" /
"1500 m", "5 km N" / "of Mar Chiquita"), unless it begins a date: a number comes
right after the month, glued to it or not, or after a "de", "del" or "of" after
it ("de julio,1946", "de julio de 1946"), or, when the month or such a link ends
the line, starts the next line that holds more than what folds to nothing or an
institution code ("de julio" / "1946"). Institution codes and what `fold` drops
are no words here, and the number may come after an apostrophe-shaped letter
(U+02BB to U+02BD), which Python counts as a letter: "Mindanao" / "de julio, ʼ46"
keeps "Mindanao" (**Months**, below).

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
kept aside with its offset ("10 m S of Camp 3", "5 km N of 1946"), as is an offset
with a malformed distance ("1,5,3 km N of Davao"). A heading keeps its written
form and its bearing in degrees, and a distance stays as written; points and
radii are tier 3's.

**Elevations (G27, G38, G41).** Elevation phrases ("4800 ft.", "4800ft.", "6400'",
"Elev. 6400'", "1,463 m", "1.463 m", "6.400 ft.", "4000-4500 ft") leave the place
text and are kept as written, as G27 keeps a verbatim and G38 keeps each layer:
the numbers whole as written, dots and commas included, and the unit as feet,
metres, or none when the label gives none ("Elev.6400" on 105526322). A range
joins its numbers by a dash of any kind or a slash, or by "to", "a", "and" or
"y" between spaces ("4000—4500 ft", "1,200/1,500 m", "1500 a 2000 m",
"1500 y 2000 m"), runs upward, and is kept whole.
An elevation's prefix is read in any case, with an optional colon after it. The
coordinator's reading at 15:32Z on 2026-09-25 (below) names "Elev.", "Alt." and
the like, as the profile's notations list them. "Elev." is how the pilot's labels
write it, and the Insects profile lists "Alt." and "el." (with its period).
"Elevation", "Altitude", the forms without a period and the colon are S8's
reading of "and the like". A word between a prefix and its number leaves the
prefix unread, so "Elev. ca. 1800-2200 m" is set aside.
An elevation in brackets takes its brackets with it: "Mt. Apo (1463 m)" leaves
"Mt. Apo". This module fills nothing and stores no converted value; it compares
a phrase in feet with one in metres only to pair them (below). G41's "Convert
and fill" (the label's own number fills From and To, and the other unit is
converted exactly, each marked derived) happens in S4's later derivation layer.

**Unsure numbers.** A phrase whose number is unsure is set aside rather than read.
These rules keep a date's number out of every elevation, and let a range read
only whole, in the forms the tests generate (**Tests**, below). These numbers are
unsure:
- a number glued to the text before it: an elevation needs a space, the part's
  start, an opening bracket (full-width ones too) or another elevation right
  before it. So "12.IV.1948,95 m", "12/4/48,95 m", "Sept. '46,95 m",
  "6-Sept-1946-640'", "4'800 m", "4000a4500 ft", "Yepocapa:1500 m" and
  "Altitud:1500 m" are set aside, and "4800 ft/1463 m" reads both. A number
  with no unit is unsure too when it runs straight into more letters or digits,
  or has a decimal part that a number or a month follows, in its part or the
  next, since a date's day or year may have run into it: "Elev.6400,13.XI",
  "alt 1.463,27-of jun.", "el. 6400,12 Sep", "Elev.6400,12, XI.1946" and
  "Elev.3300,12 4 1948" are set aside, while "Elev. 1463,5, Mt. Apo" reads. An
  elevation unit the reader does not list, glued on, is such a run, so its
  phrase is set aside, a cost: "Alt. 2100msnm", "Elev.6400pies";
- a range, or a number whose first digits could be a year (two or four digits
  before its first comma or dot), after other text in its part or in a part
  right after one that holds a number or only a month (**Months**, below). A
  part that folds to nothing between them ("?", a Hangul filler, or "CNHM" in
  any width once the institution leaves it) passes that on, so "Sept., ?,
  1946,95 m" and "IV" / "CNHM." / "1948.950 m" are set aside. Its prefix or
  another elevation right before it clears it, and an opening bracket at the
  part's start is no text ("(12,300 ft)" reads). So "Sept. 1946 - 850 m",
  "Camp 3 and 1500 m", "Km 42 a 1500 m", "Sept. 6, 1946 a 950 m",
  "12 IV 1948,95 m", "IV-26" / "1948.950 m" and "July, 1946.950 m" are set
  aside. The cost: "Mt. Apo 1500-2000 m", "between 1500 and 2000 m" and "Mt. Apo
  12,300 ft" are set aside too, while "Mt. Apo, 1500-2000 m" and "Mt. Apo Elev.
  1500-2000 m" read, and a bare "1946,63 m" stays the decimal it is;
- a number with four digits after a mark, which could be a date's year
  ("4.1948-950 m");
- a range that runs downward, its numbers compared by their whole parts in any
  digits ("1946 - 850 m", "4500-４０００ m", "2,000-1,463.5 ft"), or either of whose
  numbers has a decimal part, in thousands groups or not, since a year may have
  run into it: "4-1948,95 m", "Mindanao, 1946,95-2500 m", "Guatemala, 26,5-850 m",
  "Elev. 1946,95-2500 m", "Alt. 620,31 -9500 m", "ELEV: 1.463,26 -9500 ft" and
  "1,200-1,463.5 ft" are set aside, while "1,946-2,500 m" reads. This rule is
  S8's, not the coordinator's, and a prefix does not clear it, as it clears the
  year rule below: "Elev. 1946,95-2500 m" is set aside;
- a range whose lower number could be a year, two digits or four from 1700 to
  2099, in any digits, unless its prefix comes first: "Mindanao, 1946 - 2500 m"
  in ASCII, full-width, Devanagari or Arabic-Indic digits, "1800-2200 m" and
  "10-50 m" are set aside, while "Elev. 1800-2200 m", "el. 1800-2200 m",
  "1500-2000 m" and "4000-4500 ft" read. This is the coordinator's reading of G36
  and G40 at 15:32Z on 2026-09-25. Beside another elevation, such a range reads
  only when the two convert to each other, in either order: each end, by the
  exact factor (1 ft = 0.3048 m, as G41), within the larger of 10 m and 2% of the
  metric value, compared exactly. So "6000-7000 ft 1829-2134 m", "1829-2134 m
  6000-7000 ft", "6000-7000 ft 1866-2134 m" and "6375-7375 ft 1905-2248 m" (2% off
  at its low end) read both, while "6000-7000 ft 1867-2134 m" and "4800 ft
  1946-2500 m" set the metric range aside and read the feet. This is the
  coordinator's reading at 17:40Z, extending the one at 15:32Z. With the range
  first and set aside, the elevation after it is checked against the range's
  numbers (below), so "1946-2500 m 4800 ft" and "1792-2134 m 6000-7000 ft" read
  nothing;
- a number that another number comes before, since the last elevation read, with
  words or marks between them, opening brackets aside, since they may join a
  range no rule lists: "4000 hasta 4500 ft", "4000~ 4500 m", "4000-- 4500 m",
  "4000 - 4500 - 5000 m", and "4000" with twenty "~ " before "4500 m". A number
  with no unit is unsure the same way when another number comes after it, that
  number's own prefix aside: "Elev. 1500 ~ 2000 m" is set aside whole, and so is
  "Elev.6400,12-IV-1948". "Camp 3 at 1500 m", "Camp 3a 1500 m" and "Elev.6400
  Camp 3" are set aside too, while right after another elevation a number is its
  pair ("4800 ft 1463 m", "Elev. 1500 Elev. 2000 m");
- a malformed grouping ("1,5,3 m", "12,34,567 m");
- a number beside another digit group across a space ("4 800 ft.", "1 463 m",
  "'4 800 ft."). A two-digit year after an apostrophe is no such group:
  "3 Sept. '46 850 m" keeps "850 m".

A line break can fall inside a range, so the check between two numbers reads
across line breaks as across spaces, with every line break Python's
`str.splitlines` knows (U+2028 and U+0085 among them): "4000 -" / "4500 ft",
"1500-" / "2000 m", "entre 1500 y" / "2000 m", "4000" / "hasta 4500 m" and
"Elev. 1500-" / "2000 m" are set aside. A part with no number passes the check
on ("4000" / "to" / "4500 m"). The check reads across commas and semicolons the
same way from a bare number, one with no unit or prefix of its own and nothing
glued before it (a space, the part's start or an opening bracket comes first, as
an elevation's number needs), which could be a range's low: any word or mark
after it continues the check, so that number's range is never read by its top
alone. This is the coordinator's reading at 22:22Z on 2026-09-25, from G36 and
G40, as the coordinator refined it at 00:38Z on 2026-09-26 and ruled at 00:52Z.
So "4000, hasta 4500 m", "4000, up to 4500 m", "1500, bis 2000 m", "4000, até
4500 m", "4000, à 4500 m", "4000 hasta, 4500 m", "4000, ~ 4500 m", "4000 ~,
4500 m", "4000, ?, 4500 m" and "4000 to, 4500 m" are set aside. So are "Camp 3,
Mt. Apo 1500 m" and "Km 42, a 1500 m", a missed reading rather than a wrong one. A
number with its own unit ("4800 ft.") or prefix ("Elev. 6400") is a complete
elevation and ends the check, and so does a glued one, such as a date's year,
which can be no range's low. So "6-Sept-1946, Elev.6400", "12-IV-1948, Yepocapa,
1500 m", "12-IV-1948, Yepocapa, Elev. 1500 m" and "12-IV-1948," / "Chimaltenango
1500 m" read, as "1946, 950 m" does with nothing but the comma between. So do the
six elevations stated in the two baseline readers' whole transcripts of 105526322,
105526329 and 105526330, which round 9's reading set aside: "Elev. 6400",
"Elev.6400", "4800ft." twice and "4800 ft." twice. Counted off-branch on the 35
pilot readings on this machine (19 of the 20 in the reader baseline of
2026-09-23, where 105526326's handwriting-qwen read failed, and S8's 16), the
refined reading changes none from ec8d73b, while round 9's lost those six. The
coordinator's three stated costs (00:52Z): a prefixed low with a comma or
semicolon in its join reads both ends as separate elevations ("Elev. 4000, hasta
4500 m", "alt 6000 & ; 7000 ft."); a date's glued year before such a join reads
only the elevation after it ("ene.-1983, to 950 ft."); and a low glued into the
number before it by a comma reads the top ("Elevation 3300,10 - ; 50 m"), and the
number before too when it reads, the low's digits in it ("Elev.3300,26 up to ;
750 feet" reads "Elev.3300,26" and "750 feet"). None lets a date's number into an
elevation or a date fragment become a part, and a range word left over ("hasta")
is a lookup candidate that matches no place. What `fold` drops is no word and no
mark here: with a Hangul filler between "3 Sept. '46" and "850 m", "850 m" still
reads. The cost of reading line breaks as spaces:
after a part that ends in a number no elevation took, an elevation that words
come before in the next parts is set aside, as on one line, when only line breaks
stand between or the number is bare. So "12-IV-1948" / "Chimaltenango" / "1500 m"
keeps "Chimaltenango" and sets "1500 m" aside, "12-IV-1948" / "Chimaltenango
1500 m" sets the second line aside, and "Elev.6400" / "Sept. 3, 1946" sets
"Elev.6400" aside. The pilot's own readings pay it: both baseline
readers' transcripts of 105526321, read whole as one literal, hold "3 sept. '46"
/ "Mossy forest 6400'" and set "6400'" aside. The tool reads each place field's
own literal, the exact transcript substring of that field, with the date and
elevation literals passed apart (`GEOREFERENCING.md` 1.1, "Input"), so a literal
leaves such lines out. An elevation or its prefix starting the next part still
reads ("3 Sept. '46" / "Elev. 6400'", "3 Sept. '46" / "850 m"). A range word
still becomes a place part in three ways. Alone in its own part between two
numbers, it stays a part as any part of words does: "4000" / "hasta" / "4500 m"
and "4000, hasta, 4500 m" keep "hasta", and "12-IV-1948, Yepocapa, 1500 m" keeps
"Yepocapa". The coordinator's ruling at 22:25Z on 2026-09-25 keeps this cost: a
place part is a lookup candidate the lookups verify, not a conclusion. After an
elevation read, as on one line: "4000 m hasta 4500 m" keeps "hasta", and "4000 m
up to 4500 m" keeps "up to". And in the stated costs above. "to", "a", "and" or
"y" alone is kept aside (**Unplaced text**, below).

**Months.** A part of only a month is kept aside, never a place, and the part
after it counts as one after a number, since the year may follow: "July,
1946.950 m", "Sept." / "1946,95 m", "IV" / "1948.950 m" and "Sept., 1946,95 m"
read no elevation and no part, and neither do "Sept." / "CNHM" / "1946,95 m" and
"Sept., ?, 1946,95 m", since a part that folds to nothing passes the month on.
Whether it folds to nothing is `fold`'s own reading, so a part of a Hangul
filler, or of any other letter `fold` drops, passes it on too. An institution
code is matched as `fold` reads it, in any width, so "Sept." / "ＣＮＨＭ" /
"1946,95 m" reads nothing either. A month is a word the Insects profile lists
for PLAN 4.8's filter (S4's #183), in any case, with or without its period:
each month in full and abbreviated, in English and in Spanish, in the usual
forms and older ones ("Sept.", "setiembre", "Agto."). A Roman month I to XII
(G29) is one too, and "de", "del" or "of" may stand beside them ("de julio",
"julio del", "VIII/IX"). A line that starts with "de", "del" or "of" and a month
begins a date, not the name on the line before, when a number comes right after
the month (**Lines and parts**, above): "Mindanao" / "de julio, 1946,95 m",
"Mindanao" / "de julio,1946,95 m", "Mindanao" / "de julio de 1946" and
"Mindanao" / "de julio" / "1946,95 m" keep "Mindanao" alone. The steward's
round-6 review (comment 5836896549) left the route to S8, and this one was chosen
over reading every part after another as one after a number, which would also
set aside "Mt. Apo, 12,300 ft" and "Mt. Apo, 1500-2000 m". Its costs:
- a part of only month words is no place: "Mar", "May", "Set", "Ene", "Ag", a
  lone "I", "V" or "X", "de Mayo" and "Del Mar";
- a name of a link and a month reads as a date when a number comes right after
  the month: "Viña" / "del Mar" / "1500-2000 m" keeps only "Viña" and reads no
  elevation, and "Isle" / "of May" / "1500 m" keeps "Isle". A date with no
  number right after its month reads as a name: "Mindanao" / "de julio" and
  "Mindanao" / "de julio" / "Camp 3" read the part "Mindanao de julio";
- after such a part, a range or a number whose first digits could be a year is
  set aside: "Mayo, 1500-2000 m" and "Mayo, 12,300 ft" read no elevation;
- a month that shares its part with another word, such as a qualifier, is read as
  a name, and so is a month in a form the list does not hold: the part stays a
  place, and the part after it reads as after any name, so "mid-Sept., 1946.950
  m", "late Aug., 1946,95 m" and "Sepbr., 1946.950 m" read the year. A list of
  qualifiers would be new design (G5), so this cost is stated, not closed.

The year rule is for ranges: a single elevation whose number could be a year
reads as written ("1946 m") unless another rule above sets it aside. Set-aside
text stays verbatim for the harness to read in context (G40). In the same
coordinator reading, this reader's output is georeferencing evidence, the
elevation fields settle from the harness's own reading of the label, and a
set-aside range never counts as "no elevation stated", so G37's derivation does
not fill it.

**Unplaced text.** These are kept aside and never searched, since gazetteer place
names carry no digits:
- a part left with a number (a digit, or another numeral such as "½", "Ⅳ" or
  "㏠") or without a letter, such as a date ("IV-26") or a camp number;
- a part of only a month ("Sept.", "IV"; **Months**, above);
- a name that is only linking words ("de", "of") or a range's joining words
  ("to", "a", "and", "y"), or that keys to nothing ("Prov. Dept.");
- a heading phrase with no part to join.

A part is kept aside whole, so "Mindanao, P.I. 3 Sept. '46" keeps only
"Mindanao" as a part and sets "P.I. 3 Sept. '46" aside, "P.I." with it.

**Comparing names (G34, as the coordinator read it on 2026-09-24).** Names
compare by a key: case folded, diacritics, other marks, format characters (such
as a variation selector or a zero-width space) and invisible Hangul fillers
removed, punctuation turned into spaces, feature notations read ("Mt." compares
as "mount"), and unit words dropped with a "de", "del" or "of" after a leading
one. So "Chimaltenago" and "Departamento de Chimaltenango" have keys one letter
apart. `letters_apart` counts the single-character insertions, deletions and
substitutions between two keys, up to a cap of 2; it looks only within that
band, so its work grows with the keys' length, not its square. The one-letter
gate compares full names only, never codes or abbreviations. A word is not part
of a full name when it:
- has a period inside it ("P.I."),
- ends in a period after at most four letters ("Phil.") and is not a notation in
  the table,
- has a digit or another numeral,
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
to "Chimaltenango". Tables generated across the axes the reviews named check
that no elevation holds a date's number, no month or date fragment becomes a
part, and no range is read by one of its numbers alone. The first takes 51 date
forms, with the year as
written or moved after ", ", "," or a line break (which puts a part of only a
month before it), then a glued comma or dot, a space, a line break, or each range
join unspaced, spaced, touching either number or beside a line break, then each
tail and unit. It runs again in full-width, Devanagari and Arabic-Indic digits
with the tails "95" and "9500" in metres, and every other line break
`str.splitlines` knows reads as a newline does where each form's year is moved
and after ten of its marks. The second joins two
numbers by each of 28 joins, the listed ones and others such as "hasta", "~" and
"up to": unspaced, spaced, touching either number or broken across lines, with no
prefix or with "Elev.", "Alt." or "el.", in the four digit scripts. A seeded
random generator then mixes every token class the reviews found (months with and
without qualifiers and links; years, decimals and grouped numbers; parts that
fold to nothing, letters `fold` drops among them, and institution codes in any
width; prefixes, marks and every join, beside a comma or semicolon too; line
breaks and commas; digit scripts and units; and now and then a character `fold`
drops, anywhere) into 16,000 layouts from 16 fixed seeds, and checks the same
three properties in each. Two kinds of stated cost are exempt, by name: a month
that shares its part with a qualifier reads as a name, and a range in one of the
comma rule's three stated costs reads its ends apart, though no elevation holds
both. Another 2,000 of its layouts are read again with up to four characters
`fold` drops put anywhere, a soft hyphen never where it would end a line, and must
read the same. Further tests
cover every notation in any case and with or without its period, the letters
`fold` drops outright, every spacing mark in the Unicode data Python holds (50
under Python 3.11), the six baseline transcripts' stated elevations, headings
between features or beside none, offsets and their places, numbers read whole or
set aside, line joins, variants, months, the
elevation forms, and the comparison rules.
