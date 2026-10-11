"""The deterministic checks a field's expert may call (HARNESS.md sections 8 and 13)."""

from __future__ import annotations

import pytest

from specimen_digitization.application.collection_profiles import DateRules
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.field_research.checks import (
    check_catalog_number,
    feet_to_metres,
    longer_name,
    metres_to_feet,
    parse_date,
    parse_elevation,
    taxon_queries,
    taxon_query_grounded,
)

# The pilot profile's rules (application/profiles/published.json).
PILOT = {"version": "date-rules-v1", "two_digit_year_century": 1900, "roman_numeral_months": True}
READINGS = [
    "Mindanao, P.I.\nDavao 12.VI.1946\nF. G. Werner",
    "XI.'46 4-5-48\nslide IV-29-68-4",
    "alt. 1500 ft\n300-450 m ca. 1200 m 6,400 ft\nFMNH INS 0012345 IX-17-66-2",
]


def test_a_roman_month_date_reads_at_day_precision():
    result = parse_date("12.VI.1946", reading_texts=READINGS, date_rules=PILOT)

    assert result.status == LookupStatus.SUCCESS
    assert [(r.iso, r.precision) for r in result.readings] == [("1946-06-12", "day")]
    assert result.values == ("1946-06-12",)


def test_a_two_digit_year_follows_the_profile_century_rule():
    result = parse_date("XI.'46", reading_texts=READINGS, date_rules=DateRules(
        two_digit_year_century=1900, roman_numeral_months=True))

    assert result.status == LookupStatus.SUCCESS
    assert result.values == ("1946-11",)
    assert result.readings[0].precision == "month"
    assert result.readings[0].century_rule == "date-rules-v1:two_digit_year_century=1900"
    # Without the profile's rules neither the Roman month nor the century is read.
    assert parse_date("XI.'46", reading_texts=READINGS).status == LookupStatus.NO_MATCH


def test_a_numeric_date_gives_both_orders():
    result = parse_date("4-5-48", reading_texts=READINGS, date_rules=PILOT)

    assert result.status == LookupStatus.AMBIGUOUS
    assert set(result.values) == {"1948-04-05", "1948-05-04"}
    assert "several_readings" in result.notes
    assert result.as_dict()["readings"][0]["order"] in {"month-day-year", "day-month-year"}


def test_a_slide_code_is_never_a_date():
    for literal in ("IV-29-68", "IV-29-68-4"):
        result = parse_date(literal, reading_texts=READINGS, date_rules=PILOT)
        assert result.status == LookupStatus.NO_MATCH
        assert result.notes == ("slide_code",) and result.values == ()


def test_a_date_inside_a_code_in_any_reading_is_no_date():
    # One reader drops the code's last part; the other shows it is a code.
    readings = ["Date IV-29-68", "Date IV-29-68-4"]

    result = parse_date("IV-29-68", reading_texts=readings, date_rules=PILOT)

    assert result.status == LookupStatus.NO_MATCH and "slide_code" in result.notes


def test_a_check_answers_only_for_a_literal_in_the_readings():
    for result in (
        parse_date("13.VI.1946", reading_texts=READINGS, date_rules=PILOT),
        parse_elevation("1600 ft", reading_texts=READINGS),
        check_catalog_number("0099999", reading_texts=READINGS),
        parse_date("  ", reading_texts=["  "], date_rules=PILOT),
    ):
        assert result.status == LookupStatus.POLICY
        assert result.notes == ("literal_not_in_source",)
        assert result.values == ()


def test_a_year_literal_must_be_in_the_same_reading():
    readings = ["IV-25 1946", "IV-25"]

    with_year = parse_date("IV-25", reading_texts=readings, date_rules=PILOT, year_literal="1946")
    elsewhere = parse_date("IV-25", reading_texts=["IV-25", "1946"], date_rules=PILOT,
                           year_literal="1946")

    assert "1946-04-25" in with_year.values
    assert elsewhere.status == LookupStatus.POLICY


@pytest.mark.parametrize(
    ("literal", "unit", "low", "high", "single", "approximate"),
    [
        ("alt. 1500 ft", "ft", "1500", "1500", True, False),
        ("1500 ft", "ft", "1500", "1500", True, False),
        ("300-450 m", "m", "300", "450", False, False),
        ("ca. 1200 m", "m", "1200", "1200", True, True),
        ("6,400 ft", "ft", "6400", "6400", True, False),
    ],
)
def test_elevations(literal, unit, low, high, single, approximate):
    result = parse_elevation(literal, reading_texts=READINGS)

    assert result.status == LookupStatus.SUCCESS
    assert (result.unit, result.low, result.high, result.single, result.approximate) == (
        unit, low, high, single, approximate)
    assert result.values == tuple(dict.fromkeys((low, high)))


def test_a_unit_is_never_guessed():
    result = parse_elevation("1500", reading_texts=READINGS)

    assert result.status == LookupStatus.NO_MATCH
    assert result.notes == ("unit_not_written",) and result.values == ()


def test_exact_conversions_to_hundredths():
    assert feet_to_metres("1500") == "457.2"
    assert feet_to_metres("3,300") == "1005.84"
    assert metres_to_feet("1200") == "3937.01"
    assert metres_to_feet("300") == "984.25"
    with pytest.raises(ValueError):
        feet_to_metres("about 3")


def test_a_taxon_query_is_the_whole_name_the_label_writes():
    # Genus, species and any infraspecific epithet with its marker, as written;
    # the author and year may be left off.
    trinomial = "Danaus plexippus megalippe"
    assert taxon_query_grounded(trinomial, trinomial)
    assert taxon_query_grounded(trinomial, trinomial + " (Hubner, 1819)")
    assert taxon_query_grounded(trinomial + " (Hubner, 1819)", trinomial + " (Hubner, 1819)")
    assert not taxon_query_grounded("Danaus plexippus", trinomial)
    assert taxon_query_grounded("Aus bus var. cus", "Aus bus var. cus")
    assert not taxon_query_grounded("Aus bus cus", "Aus bus var. cus")
    # Another name on the literal's line is not its name.
    assert taxon_query_grounded("Bombus impatiens", "Bombus impatiens on Solidago canadensis")
    assert not taxon_query_grounded("Solidago canadensis", "Bombus impatiens on Solidago canadensis")
    # A sex sign and a count are no part of the name.
    assert taxon_query_grounded("Danaus plexippus", "Danaus plexippus \u2640 3")
    # G25: a genus-level identification is asked as its genus.
    assert taxon_query_grounded("Epipsocus", "Epipsocus sp.")
    assert not taxon_query_grounded("Epipsocus", "Epipsocus pallidus")


def test_a_label_with_no_genus_has_no_groundable_taxon_query():
    # 105526321's taxon line: a morphocode and a sex sign, no genus.
    assert taxon_queries("sp. 30 \u2640") == frozenset()
    for query in ("sp. 30", "sp.", "sp. 30 \u2640"):
        assert not taxon_query_grounded(query, "sp. 30 \u2640")


@pytest.mark.parametrize(("literal", "no_genus"), [
    # Morphocodes with no genus (owner decision B): 105526321, 105526326, 105526327.
    ("sp. 30 \N{FEMALE SIGN}", True),
    ("Sp. 22", True),
    ("sp 22", True),
    ("Sp 22", True),
    ("sp aa", True),
    ("sp #1", True),
    ("sp. 3a", True),
    ("sp. 1 \N{MALE SIGN}\N{FEMALE SIGN}", True),
    ("sp.  30\n\N{FEMALE SIGN}", True),
    # A genus, written or misread, anywhere on the line.
    ("Epipsocus sp. 1", False),
    ("epipsocus sp. 1", False),
    ("Ep1psocus sp. 1", False),
    ("sp. 30 \N{FEMALE SIGN} Epipsocus", False),
    # A name read in part is a name, not a morphocode.
    ("Aus bus n. sp.", False),
    # Not a morphocode: no number or code, a new species, a plural, a longer code.
    ("sp.", False),
    ("sp. nov.", False),
    ("spp. 2", False),
    # A plural or a qualifier is no code (N3 of #289's review).
    ("spp", False),
    ("sp nov", False),
    ("sp aff", False),
    ("sp cf", False),
    ("sp. n.", False),
    ("sp n", False),
    ("sp. nr.", False),
    ("sp gr", False),
    ("sp. aff.", False),
    ("sp. cf.", False),
    ("sp. ABC", False),
    ("cf. sp. 1", False),
    ("", False),
    (None, False),
])
def test_names_no_genus(literal, no_genus):
    from specimen_digitization.field_research import checks

    assert checks.names_no_genus(literal) is no_genus


@pytest.mark.parametrize(("literal", "code"), [
    # Two readers of one label (105526321, 105526326, 105526329): the same code.
    ("sp. 30 \N{FEMALE SIGN}", "30"),
    ("Sp.30 \N{FEMALE SIGN}", "30"),
    ("Sp. 22", "22"),
    ("sp 22", "22"),
    ("sp #1 \N{MALE SIGN}", "1"),
    ("Sp.#1", "1"),
    ("sp aa", "aa"),
    ("sp. 3a", "3a"),
    ("sp. 39", "39"),
    # Not a name with no genus.
    ("Epipsocus sp. 1", None),
    ("sp. nov.", None),
    (None, None),
    # A plural or a qualifier is no code (N3 of #289's review).
    ("spp", None),
    ("sp nov", None),
    ("sp aff", None),
    ("sp cf", None),
])
def test_a_morphocode_is_its_number_or_code(literal, code):
    from specimen_digitization.field_research import checks

    assert checks.morphocode(literal) == code


FEMALE, MALE = "\N{FEMALE SIGN}", "\N{MALE SIGN}"
# The pilot's labels that write a morphocode, each reader's text as read
# (owner decision B; B1 of #289's review): the code, the readers' texts, and
# whether the label names no genus for it.
PILOT_CODE_LABELS = {
    "105526321": ("30", [
        "10-6-78-la\nE. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\nF.G. Werner\n3 sept. '46\n"
        "Mossy forest 6400'\nsp. 30 " + FEMALE,
        "10-6-78-1a\nE.slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\nF.G. Wermer\n3 Sept. '46\n"
        "Mossy forest 6400'\nSp.30 " + FEMALE], True),
    "105526326": ("22", ["sp. 22\n" + FEMALE + " wings", "Sp. 22\n" + FEMALE + " wings"], True),
    "105526327": ("22", ["V-4-67-1\nsp 22\nlegs", "V-4-67-1\nsp 22\nlegs"], True),
    # A body part or a collector with initials right before the code is no
    # genus (the real-model run of the ten pilots, 2026-10-09): "head",
    # "legs", "R.D.mitchell". Each was read as a genus before.
    "105526322": ("30", ["wings + head\nsp. 30 " + FEMALE, "Wings 4 head\nSp.30 " + FEMALE + "\np-95-81-16"], True),
    "105526323": ("30", ["genitalia + legs\nSp 30 " + FEMALE, "genitalia " + FEMALE + " legs\nSp 30 " + FEMALE], True),
    "105526329": ("1", ["R.D.mitchell\nsp #1 " + MALE + "\nhead & legs", "R.D.mitchell\nSp #1 " + MALE + "\nhead & legs"],
        True),
    "105526330": ("1", ["Guatemala, IV-25\n1948, R.D. Mitchell\n" + FEMALE + " legs Sp.#1"], True),
    # The genus on the line above the code, as each reader reads it.
    "105526328": ("1", ["VI-24-68-7.\nEpipocus\nsp. 1\n" + FEMALE + " terminalia\nVII-18-66-1",
        "VI-24-68-7.\nEpipsocus\nsp. 1\n" + FEMALE + " terminalia\nVII-18-66-1"], False),
}


@pytest.mark.parametrize(("code", "texts", "no_genus"), PILOT_CODE_LABELS.values(), ids=PILOT_CODE_LABELS)
def test_a_pilot_label_names_no_genus_only_when_no_genus_is_written_beside_its_code(code, texts, no_genus):
    from specimen_digitization.field_research import checks

    assert checks.label_names_no_genus(code, texts) is no_genus


@pytest.mark.parametrize(("text", "no_genus"), [
    # A genus, written, misread, abbreviated or in capitals, right before the code.
    ("Epipsocus sp. 1", False),
    ("Epipsocus\nsp. 1", False),
    ("Epipsocus,\n" + FEMALE + "\nsp. 1", False),
    ("Epipsocus cf.\nsp. 1", False),
    ("(Epipsocus) sp. 1", False),
    ("Ep1psocus sp. 1", False),
    ("E. sp. 1", False),
    ("EPIPSOCUS sp. 1", False),
    # Or after it on its line.
    ("sp. 1 " + FEMALE + " Epipsocus", False),
    # One reader's genus is enough, and another place the label writes the code.
    ("sp. 1\nEpipsocus sp. 1", False),
    # Any other word with a letter and no digit right before it (B2 of #289's third review).
    ("Mitchell\nsp. 1", False),
    ("Legs sp. 1", False),
    # A genus past a body part on the line read (NOT_GENERA are passed over).
    ("Epipsocus legs sp. 1", False),
    ("Epipsocus\n" + FEMALE + " legs Sp.#1", False),
    ("sp. 1 legs Epipsocus", False),
    # A genus after initials that may spell "cf." or "nr.", or after a whole name.
    ("C.F. Epipsocus\nsp. 1", False),
    ("C.F.Epipsocus sp. 1", False),
    ("N.R. Epipsocus sp. 1", False),
    ("R.D. Mitchell Epipsocus sp. 1", False),
    ("sp. 1 C.F. Epipsocus", False),
    # A genus that is also a word for a body part, and one capital, abbreviated.
    ("Perna sp. 1", False),
    ("perna sp. 1", False),
    ("Ala sp. 1", False),
    ("E.\nsp. 1", False),
    # A word with a digit right before it, or the genus further away.
    ("Mossy forest 6400'\nsp. 1", True),
    ("Epipsocus\nV-4-67-1\nsp. 1", True),
    # Behind a line of body parts, or one body part, the genus is not read,
    # nor right after initials, read as a name.
    ("Epipsocus\nwings + head\nsp. 1", True),
    ("Epipsocus\nlegs\nsp. 1", True),
    ("R.D. Epipsocus\nsp. 1", True),
    ("legs sp. 1", True),
    # Another code beside the genus.
    ("Epipsocus sp. 2\nsp. 1", True),
    # The code is not written at all.
    ("sp. 2", False),
    ("wasp 1", False),
])
def test_the_label_names_no_genus_when_no_word_beside_its_code_may_be_one(text, no_genus):
    from specimen_digitization.field_research import checks

    assert checks.label_names_no_genus("1", [text]) is no_genus


# B2 of #289's third review: an unclear word beside the code may be its genus.
UNCLEAR_BESIDE = [
    # The reader's marker, and a genus marked doubtful, qualified or abbreviated.
    "[unreadable] sp. 1 " + FEMALE,
    "Epipsocus? sp. 1 " + FEMALE,
    "?Epipsocus sp. 1 " + FEMALE,
    "Epipsocus(?) sp. 1 " + FEMALE,
    "E.? sp. 1 " + FEMALE,
    "cf.Epipsocus sp. 1",
    "epipsocus? sp. 1",
    # 105526328's label 2 with its genus line unreadable or doubtful.
    "VI-24-68-7.\n[unreadable]\nsp. 1\n" + FEMALE + " terminalia",
    "VI-24-68-7.\nEpipsocus?\nsp. 1\n" + FEMALE + " terminalia",
    "VI-24-68-7.\n?Epipsocus\nsp. 1\n" + FEMALE + " terminalia",
    # Other qualifiers, curly quotes, emphasis, an accented capital.
    "AFF.Epipsocus sp. 1",
    "Epipsocus prob. sp. 1",
    "Epipsocus nr. sp. 1",
    "\N{LEFT DOUBLE QUOTATION MARK}Epipsocus\N{RIGHT DOUBLE QUOTATION MARK} sp. 1",
    "_Epipsocus_ sp. 1",
    "\N{LATIN CAPITAL LETTER E WITH ACUTE}pipsocus sp. 1",
    # After the code on its line, a word that is not one of NOT_GENERA.
    "sp. 1 [unreadable]",
    "sp. 1 " + FEMALE + " cf. Epipsocus",
    "sp. 1 Legs",
    # Above a keyed "taxon:" line, a line that is not keyed.
    "Epipsocus\ntaxon: sp. 1",
]


@pytest.mark.parametrize("text", UNCLEAR_BESIDE)
def test_an_unclear_word_beside_the_code_may_be_its_genus(text):
    from specimen_digitization.field_research import checks

    assert not checks.label_names_no_genus("1", [text])


@pytest.mark.parametrize("text", [
    # 105526321, 105526326 and 105526327 as their readers write them.
    "Mossy forest 6400'\nsp. 1 " + FEMALE,
    "Sp. 1\n" + FEMALE + " wings",
    "V-4-67-1\nsp 1\nlegs",
    # A token with a digit right before the code, after "?" or a qualifier alone.
    "V-4-67-1 sp. 1\nlegs",
    "IX-14-46 sp. 1",
    "6400' ? sp. 1",
    "6400' cf. sp. 1",
    # The taxon's keyed line, another field's keyed line above it.
    "verbatim_dts: Synthetic D/T/S\ntaxon: sp. 1 " + FEMALE,
])
def test_a_code_with_no_word_beside_it_that_may_be_a_genus_names_no_genus(text):
    from specimen_digitization.field_research import checks

    assert checks.label_names_no_genus("1", [text])


# The real-model run of the ten pilots (2026-10-09): a collector's name with
# initials beside the code is no genus. Each was read as a genus before.
PERSONS_BESIDE = [
    "R.D.mitchell\nsp #1 " + MALE,
    "R.D.Mitchell\nsp. 1",
    "R. D. Mitchell\nsp. 1",
    "1948, R.D. Mitchell\nsp. 1",
    "leg. R.D. Mitchell\nsp. 1",
    "R.D. Mitchell.\nsp. 1",
    "H. Hoogstraal\nsp. 1",
    "Mitchell, R.D.\nsp. 1",
    "Mitchell, R. D.\nsp. 1",
    "R.D.\nsp. 1",
    "sp. 1 R.D. Mitchell",
    "sp. 1 " + FEMALE + " Mitchell, R.D.",
]


@pytest.mark.parametrize("text", PERSONS_BESIDE)
def test_a_persons_name_with_initials_beside_the_code_is_no_genus(text):
    from specimen_digitization.field_research import checks

    assert checks.label_names_no_genus("1", [text])


ENGLISH = {"head", "leg", "legs", "wing", "wings", "abdomen", "antenna", "antennae", "genitalia", "terminalia", "slide",
    "mount", "male", "males", "female", "females"}
SPANISH = {"cabeza", "pata", "patas", "ala", "alas", "antena", "antenas", "l\N{LATIN SMALL LETTER A WITH ACUTE}mina",
    "montaje", "macho", "machos", "hembra", "hembras"}
FRENCH = {"t\N{LATIN SMALL LETTER E WITH CIRCUMFLEX}te", "patte", "pattes", "aile", "ailes", "antenne", "antennes",
    "lame", "montage", "m\N{LATIN SMALL LETTER A WITH CIRCUMFLEX}le", "m\N{LATIN SMALL LETTER A WITH CIRCUMFLEX}les",
    "femelle", "femelles"}
GERMAN = {"Kopf", "Bein", "Beine", "Fl\N{LATIN SMALL LETTER U WITH DIAERESIS}gel",
    "F\N{LATIN SMALL LETTER U WITH DIAERESIS}hler", "Pr\N{LATIN SMALL LETTER A WITH DIAERESIS}parat",
    "M\N{LATIN SMALL LETTER A WITH DIAERESIS}nnchen", "Weibchen"}
PORTUGUESE = {"cabe\N{LATIN SMALL LETTER C WITH CEDILLA}a", "pernas", "asa", "asas",
    "l\N{LATIN SMALL LETTER A WITH CIRCUMFLEX}mina", "montagem", "f\N{LATIN SMALL LETTER E WITH CIRCUMFLEX}mea",
    "f\N{LATIN SMALL LETTER E WITH CIRCUMFLEX}meas"}


def test_the_words_beside_a_code_that_are_no_genus_are_one_list():
    """NOT_GENERA, as written, in five languages: passed over before the
    code and after it (the real-model run of the ten pilots)."""
    from specimen_digitization.field_research import checks

    assert checks.NOT_GENERA == ENGLISH | SPANISH | FRENCH | GERMAN | PORTUGUESE | {FEMALE, MALE}
    for word in checks.NOT_GENERA - {FEMALE, MALE}:
        assert checks.label_names_no_genus("1", ["sp. 1 " + word, "sp. 1 " + FEMALE + " " + word + ","]), word
        before = [word + " sp. 1", word + "\nsp. 1", FEMALE + " " + word + " sp. 1"]
        assert checks.label_names_no_genus("1", before), word
    assert checks.label_names_no_genus("1", ["sp. 1 " + FEMALE + MALE])
    # As written: "t\N{LATIN SMALL LETTER E WITH CIRCUMFLEX}te" decomposed is the same word.
    assert checks.label_names_no_genus("1", ["te\N{COMBINING CIRCUMFLEX ACCENT}te\nsp. 1"])


@pytest.mark.parametrize(("part", "token"), [
    ("[unreadable]", "unreadable"),
    ("Epipsocus?", "Epipsocus"),
    ("?Epipsocus", "Epipsocus"),
    ("Epipsocus(?)", "Epipsocus"),
    ("E.?", "E."),
    ("cf.Epipsocus", "Epipsocus"),
    ("(Prob.Epipsocus?)", "Epipsocus"),
    ("Epipsocus,aff.", "Epipsocus"),
    ("*Epipsocus*", "Epipsocus"),
    ("\N{LEFT SINGLE QUOTATION MARK}Epipsocus\N{RIGHT SINGLE QUOTATION MARK}", "Epipsocus"),
    ("6400'", "6400"),
    ("legs,", "legs"),
    ("cf.", ""),
    ("aff.", ""),
    # Every qualifier of the doubt signs' list, its periods aside (B4 of #289's fifth review).
    ("cfr.Epipsocus", "Epipsocus"),
    ("c.f.Epipsocus", "Epipsocus"),
    ("Conf.Epipsocus", "Epipsocus"),
    ("Epipsocus,poss.", "Epipsocus"),
    ("vic.", ""),
    ("c.f.", ""),
    # Capitals each followed by a period are initials, never a qualifier.
    ("C.F.", "C.F."),
    ("C.F.Baker", "C.F.Baker"),
    ("Baker,N.R.", "Baker,N.R."),
    # "vic." counts in lower case only; "Vic." is Victoria.
    ("Vic.", "Vic."),
    # A qualifier's letters ending a longer word are no qualifier.
    ("Staff.", "Staff."),
    ("?", ""),
    ("(?)", ""),
])
def test_a_token_sheds_marks_quotes_brackets_and_qualifiers_at_either_end(part, token):
    from specimen_digitization.field_research import checks

    assert checks._token(part) == token


@pytest.mark.parametrize(("token", "genus"), [
    ("Epipsocus", True),
    ("epipsocus", True),
    ("E.", True),
    ("unreadable", True),
    ("R.D.mitchell", True),
    ("Ep1psocus", True),
    ("V-4-67-1", False),
    ("6400", False),
    ("IX-14-46", False),
    ("10-6-78-la", False),
    ("p-95-81-16", False),
])
def test_a_token_with_a_letter_and_no_digit_may_be_a_genus(token, genus):
    from specimen_digitization.field_research import checks

    assert checks.may_be_genus(token) is genus


# N2 of #289's fourth review: a genus misread with a digit.
@pytest.mark.parametrize("token", ["Epipsocu5", "epipsocu5", "ep1psocus", "3pipsocus", "Epi5"])
def test_a_token_with_three_letters_and_one_digit_at_most_may_be_a_misread_genus(token):
    """In the label check, beside the code, and in the query check alike."""
    from specimen_digitization.field_research import checks

    assert checks.may_be_genus(token)
    assert not checks.label_names_no_genus("1", [token + " sp. 1"])
    assert not checks.label_names_no_genus("1", ["sp. 1 " + FEMALE + " " + token])
    assert checks.query_names_a_genus(token)


@pytest.mark.parametrize("token", ["V-4-67-1", "6400'", "IX-14-46", "Epipsocu55", "1a", "10-6-78-la"])
def test_a_token_with_two_digits_or_fewer_than_three_letters_is_no_misread_genus(token):
    """Codes, dates and numbers; the rule's bounds."""
    from specimen_digitization.field_research import checks

    assert not checks.may_be_genus(checks._token(token))
    assert checks.label_names_no_genus("1", [token + " sp. 1"])
    assert not checks.query_names_a_genus(token)


@pytest.mark.parametrize("token", ["ep1psocus", "epipsoc1s", "ep1psocus?"])
def test_the_label_check_and_the_query_check_normalise_case_alike(token):
    """A lower-case token with a digit: the query check read it with a
    capital, the label check as written (N2 of #289's fourth review)."""
    from specimen_digitization.field_research import checks

    assert checks.label_names_no_genus("1", [token + " sp. 1"]) is not checks.query_names_a_genus(token)


@pytest.mark.parametrize(("query", "is_the_code"), [
    # The code itself, case, spaces, punctuation and sex signs aside.
    ("sp. 30 " + FEMALE, True),
    ("Sp.30 " + FEMALE, True),
    ("SP 30", True),
    ("sp #30 " + MALE, True),
    ("sp-30", True),
    # Anything else: a misread genus, a slide number, another code, a name, nothing.
    ("Epipsocu55", False),
    ("Epipsocu5", False),
    ("V-4-67-1", False),
    ("sp. 39 " + FEMALE, False),
    ("Epipsocus sp. 30", False),
    ("30", False),
    ("", False),
])
def test_a_gbif_query_is_the_code_itself_only_case_spaces_punctuation_and_sex_signs_aside(query, is_the_code):
    from specimen_digitization.field_research import checks

    assert checks.query_is_the_code(query, "sp. 30 " + FEMALE) is is_the_code


@pytest.mark.parametrize(("query", "genus"), [
    # A name the parser reads, as written or with a capital and no emphasis marks.
    ("Epipsocus", True),
    ("Epipsocus sp. 1 " + FEMALE, True),
    ("Epipsocus prob. sp. 1 " + FEMALE, True),
    ("epipsocus", True),
    ("*Epipsocus*", True),
    ("_Epipsocus_ sp. 1", True),
    ("epipsocus sp. 1 " + FEMALE, True),
    # One word that may be a genus, case and brackets aside.
    ("EPIPSOCUS", True),
    ("Ep1psocus", True),
    ("ep1psocus", True),
    ("(epipsocus)", True),
    ('"Epipsocus"', True),
    # A genus marked doubtful, qualified, abbreviated or with an accented
    # capital, and the reader's marker (B2 of #289's third review).
    ("Epipsocus(?)", True),
    ("Epipsocus?", True),
    ("?Epipsocus", True),
    ("E.?", True),
    ("E. sp. 1", True),
    ("cf.Epipsocus", True),
    ("\N{LATIN CAPITAL LETTER E WITH ACUTE}pipsocus", True),
    ("[unreadable] sp. 1", True),
    # A code with only "?" or a qualifier beside it.
    ("sp. 1?", False),
    ("cf. sp. 1", False),
    ("?", False),
    # The pilots' codes, as their readers write them, and nothing asked.
    ("sp. 30 " + FEMALE, False),
    ("Sp.30 " + FEMALE, False),
    ("Sp. 22", False),
    ("sp 22", False),
    ("sp aa", False),
    ("sp #1 " + MALE, False),
    ("Sp.#1", False),
    ("", False),
    (None, False),
])
def test_a_gbif_query_names_a_genus_when_a_name_or_a_genus_shaped_word_is_asked(query, genus):
    from specimen_digitization.field_research import checks

    assert checks.query_names_a_genus(query) is genus


# B3 of #289's fourth review: the signs of a doubtful or unreadable name that
# hold rule B back wherever on the specimen they show.
def test_the_signs_of_a_doubtful_or_unreadable_name_are_one_list():
    from specimen_digitization.field_research import checks

    assert [name for name, _ in checks.DOUBT_SIGNS] == ["question_mark", "qualifier", "placeholder", "unreadable_span"]
    assert checks.DOUBT_QUALIFIERS == ("cf", "cfr", "aff", "affin", "affinis", "nr", "near", "prob", "probably", "poss",
        "possibly", "conf", "vic", "prope")
    # Three periods are read on their own (N3 of #289's sixth review: a
    # longer run is a printed form's dot leader).
    assert checks.DOUBT_PLACEHOLDERS == ("[unreadable]", "(unreadable)", "[illegible]", "(illegible)", "[illeg.]",
        "[illeg]", "(illeg.)", "[unclear]", "(unclear)", "[?]", "???", "[...]", "\N{HORIZONTAL ELLIPSIS}")
    assert checks.PLACEHOLDER_WORDS == ("illegible", "unreadable")
    assert checks.PLACE_QUALIFIERS == ("near", "nr", "vic")
    assert dict(checks.DOUBT_SIGNS)["placeholder"] is checks.shows_placeholder
    assert checks.doubt_signs(["Epipsocus?", "V-4-67-1", "cf. Epipsocus"]) == ("question_mark", "qualifier")
    assert checks.doubt_signs(["sp. 1 " + FEMALE], unreadable=True) == ("unreadable_span",)
    assert checks.doubt_signs([]) == ()


@pytest.mark.parametrize(("text", "sign"), [
    # A "?" attached to a word that holds a letter, or standing beside one.
    ("Epipsocus?", "question_mark"),
    ("?Epipsocus", "question_mark"),
    ("Epipsocus(?)", "question_mark"),
    ("E.?", "question_mark"),
    ("Epipsocus ?", "question_mark"),
    ("(?) Epipsocus", "question_mark"),
    ("Epipsocus\n?", "question_mark"),
    ("Epipsocus? VI-24-68-7.", "question_mark"),
    ("V-4-67-1\nsp. 1 " + FEMALE + " terminalia Epipsocus?", "question_mark"),
    # Whatever the label check reads beside the code: it reads no genus here.
    ("6400' ? sp. 1", "question_mark"),
    # A qualifier, against a word or apart, in any case, with or without its period.
    *((form, "qualifier") for word in ("cf", "aff", "nr", "prob")
        for form in (word + ". Epipsocus", word.upper() + ".Epipsocus", "Epipsocus " + word.capitalize() + ".",
            "(" + word + ") Epipsocus")),
    ("near Epipsocus", "qualifier"),
    ("Epipsocus NEAR", "qualifier"),
    ("Near Epipsocus", "qualifier"),
    ("Epipsocus nr", "qualifier"),
    # A locality's qualifier is one too.
    ("5 km nr. Davao", "qualifier"),
])
def test_a_doubt_sign_shows_wherever_a_text_writes_it(text, sign):
    from specimen_digitization.field_research import checks

    assert checks.doubt_signs([text]) == (sign,)
    assert checks.doubt_signs(["V-4-67-1\nsp. 1 " + FEMALE, text]) == (sign,)


# B4 of #289's fifth review: every qualifier of the list, whatever its
# spelling: in any case, with or without its periods, apart or against the
# genus, before or after it.
QUALIFIER_SPELLINGS = [
    *(form for word in ("cfr", "affin", "affinis", "probably", "poss", "possibly", "conf", "prope")
        for form in (word + ". Epipsocus", word.upper() + " Epipsocus", word.capitalize() + ".Epipsocus",
            "Epipsocus " + word)),
    # "vic" in lower case only.
    "vic. Epipsocus", "vic.Epipsocus", "Epipsocus vic", "v.i.c. Epipsocus",
    "c.f. Epipsocus", "C.f. Epipsocus", "c.f.Epipsocus", "(c.f.) Epipsocus", "n.r. Epipsocus",
    "a.f.f. Epipsocus", "c.f.r. Epipsocus", "Epipsocus c.f.",
    # Neither a nature reserve, nor a number, nor confirmed by a person.
    "NR. Epipsocus", "Nr. Epipsocus", "conf. Yoshizawa", "conf. E.",
]


@pytest.mark.parametrize("text", QUALIFIER_SPELLINGS)
def test_a_qualifier_in_any_spelling_of_the_list_is_a_doubt_sign(text):
    from specimen_digitization.field_research import checks

    assert checks.doubt_signs([text]) == ("qualifier",)
    assert checks.doubt_signs(["V-4-67-1\nsp. 1 " + FEMALE, text + "\ndet. E. L. Mockford"]) == ("qualifier",)
    # Above the slide number above the code, where the label check does not read.
    assert checks.label_names_no_genus("1", [text + "\nV-4-67-1\nsp. 1 " + FEMALE])


# The full-width and the inverted question marks are a "?" wherever "?" is a
# doubt sign (the fifth review's two remaining probes).
FULLWIDTH, INVERTED = "\N{FULLWIDTH QUESTION MARK}", "\N{INVERTED QUESTION MARK}"


@pytest.mark.parametrize("text", ["Epipsocus" + FULLWIDTH, INVERTED + "Epipsocus", "Epipsocus " + FULLWIDTH,
    INVERTED + " Epipsocus", "Epipsocus\n" + FULLWIDTH, INVERTED + "Epipsocus" + FULLWIDTH])
def test_a_full_width_or_inverted_question_mark_is_a_doubt_sign(text):
    from specimen_digitization.field_research import checks

    assert checks.QUESTION_MARKS == ("?", FULLWIDTH, INVERTED)
    assert checks.doubt_signs([text]) == ("question_mark",)
    assert checks.doubt_signs(["V-4-67-1\nsp. 1 " + FEMALE, text + "\nV-4-67-1"]) == ("question_mark",)


@pytest.mark.parametrize(("text", "doubtful"), [
    ("Epipsocus" + FULLWIDTH, True),
    (INVERTED + "Epipsocus", True),
    (INVERTED + " Epipsocus", True),
    ("1946" + FULLWIDTH + "\nEpipsocus", False),
    (INVERTED + "\nEpipsocus", False),
])
def test_a_full_width_or_inverted_question_mark_on_the_genus_marks_it_as_doubtful(text, doubtful):
    from specimen_digitization.field_research import checks

    assert checks.genus_in_doubt(text, "Epipsocus") is doubtful


# N1 of #289's fourth review: a placeholder for a word a reader could not
# read, on a line of its own, in any case.
@pytest.mark.parametrize("placeholder", ["[unreadable]", "[UNREADABLE]", "[illegible]", "[Illegible]", "[?]", "???",
    "...", "[...]", "\N{HORIZONTAL ELLIPSIS}",
    # N1 of #289's fifth review: the placeholder list rule A shares.
    "(unreadable)", "(illegible)", "[illeg.]", "[ILLEG]", "(illeg.)", "[unclear]", "(Unclear)", "illegible",
    "Illegible", "UNREADABLE", "unreadable",
    # Three periods in round brackets, and a longer run in brackets.
    "(...)", "[....]", "(.....)"])
def test_a_placeholder_for_an_unread_word_is_a_doubt_sign(placeholder):
    from specimen_digitization.field_research import checks

    assert checks.doubt_signs([placeholder]) == ("placeholder",)
    assert "placeholder" in checks.doubt_signs(["VI-24-68-7.\n" + placeholder + "\nsp. 1\n" + FEMALE + " terminalia"])
    assert checks.shows_placeholder("Mossy " + placeholder)


@pytest.mark.parametrize("text", ["legible", "readable", "Illegibly", "unreadably", "unclear", "Unclear River", "illeg",
    "..", "Mossy forest 6400'", "V-4-67-1"])
def test_text_with_no_placeholder_shows_none(text):
    """The placeholder words count only whole; the bracketed forms only
    with their brackets."""
    from specimen_digitization.field_research import checks

    assert not checks.shows_placeholder(text)


# N3 of #289's sixth review: a printed form's dot leader, four periods or
# more outside brackets, and "etc..." leave no word out. Each was a
# placeholder before.
@pytest.mark.parametrize("text", ["....", "Det. ..........", "Loc. ......", "Loc. ........ Davao",
    "Coll. J. Smith etc...", "ETC...", "Etc...", "etc...."])
def test_a_dot_leader_or_etc_is_no_placeholder(text):
    from specimen_digitization.field_research import checks

    assert not checks.shows_placeholder(text)
    assert checks.doubt_signs([text]) == ()


# Exactly three periods for a missing word, with or without a space before
# them, "[...]" and the ellipsis character stay placeholders, as does
# "etc" ending a longer word.
@pytest.mark.parametrize("text", ["Mossy ...", "Mossy...", "... sp. 1", "Det. ...", "[...]", "Mossy [...]",
    "Mossy \N{HORIZONTAL ELLIPSIS}", "Detc...", "etc. ..."])
def test_three_periods_for_a_missing_word_stay_a_placeholder(text):
    from specimen_digitization.field_research import checks

    assert checks.shows_placeholder(text)
    assert checks.doubt_signs([text]) == ("placeholder",)


# The real readings of every label of the pilot's 105526321, 105526326 and
# 105526327, as both readers wrote them (the ten-pilot simulation's data).
PILOT_READINGS = {
    "105526321": ["FMNHINS\n4486784", PILOT_CODE_LABELS["105526321"][1][0], PILOT_CODE_LABELS["105526321"][1][1]],
    "105526326": ["FMNHINS\n4486779",
        "IX-3-66-10\nE. slope Mt. McKinley\nDavao, Prov. 3300'\nMindanao, P.I.\nIX-14-46\nH. Hoogstraal",
        "IX - 3 - 66 - 10\nE. slope Mt. McKinley\nDavao, Prov. 3300'\nMindanao, P.I.\nIX - 14 - 46\nH. Hoogstraal",
        "sp. 22\n" + FEMALE + " wings", "Sp. 22\n" + FEMALE + " wings"],
    "105526327": ["FMNHINS\n4486778", "E. slope Mt. Apo,\nDavao Prov.\nMindanao, P.I.\nH. Hoogstraal\nXI .46",
        "E. slope Mt. Apo,\nDavao Prov.,\nMindanao, P.I.\nH. Hoogstraal\nXI .46", "V-4-67-1\nsp 22\nlegs"],
}


@pytest.mark.parametrize("texts", [
    *PILOT_READINGS.values(),
    # A "?" with no word that holds a letter beside it.
    ["6400 ?", "1946?", "? 3300'"],
    # Words that hold a qualifier's letters.
    ["Nearctic", "Staff", "Cfx", "nrs", "Affine", "Probability", "Possum", "Conform", "Victoria", "Proper",
        "Cfrs"],
    # A person's initials, capitals each followed by a period.
    ["leg. C.F. Baker", "C.F.Baker", "Baker, C.F.", "N.R. Smith", "det. A.F.F. Jones", "C.F. Epipsocus"],
    # "Vic." and "VIC" with a capital: Victoria, never "vic." (vicinity).
    ["Melbourne, Vic.", "Ballarat VIC", "Vic. Epipsocus", "Vic.Epipsocus"],
], ids=[*PILOT_READINGS, "question-mark-beside-numbers", "qualifier-letters-inside-words", "initials",
    "capital-vic"])
def test_no_doubt_sign_shows_where_none_is_written(texts):
    from specimen_digitization.field_research import checks

    assert checks.doubt_signs(texts) == ()


# N3 of #289's sixth review: ordinary label words that hold a qualifier's
# letters and say nothing about a name. Each was a doubt sign before.
ORDINARY_LABEL_WORDS = {
    # A nature reserve: "NR", all capitals, with no period.
    "nature-reserve": "Sabah, Danum Valley NR",
    "nature-reserve-mid-line": "Danum Valley NR, Sabah",
    # German "Nummer" before a number.
    "german-number": "Praep. Nr. 1234",
    "german-number-no-period": "Praep. Nr 1234",
    "german-number-capitals": "PRAEP. NR. 1234",
    # "conf." meaning "confirmed by": "by", or a person's initials.
    "confirmed-by-initials": "det. E. L. Mockford 1968, conf. K. Yoshizawa",
    "confirmed-by-run-together-initials": "conf. E.L. Mockford",
    "confirmed-by-initials-alone": "Conf. E.L.M.",
    "confirmed-by": "conf. by J. Smith",
    "confirmed-by-capitals": "CONF BY J. SMITH",
    "confirmed-by-on-the-next-line": "det. Mockford, conf.\nK. Yoshizawa",
    "confirmed-by-by-on-the-next-line": "det. Mockford, conf.\nby K. Yoshizawa",
    # A person's initials without the final period.
    "initials-ending-a-line": "leg. Baker, C.F",
    "initials-before-a-surname": "C.F Baker",
    "initials-n-r": "N.R Smith",
}


@pytest.mark.parametrize("text", ORDINARY_LABEL_WORDS.values(), ids=ORDINARY_LABEL_WORDS)
def test_ordinary_label_words_are_no_doubt_sign(text):
    from specimen_digitization.field_research import checks

    assert checks.doubt_signs([text]) == ()
    assert checks.doubt_signs(["V-4-67-1\nsp. 1 " + FEMALE, text]) == ()


# The same narrowing reads "C.F Epipsocus" as initials and "NR EPIPSOCUS"
# as a nature reserve: no doubt sign shows. Right before the genus,
# genus_in_doubt still reads both as qualifiers (below).
@pytest.mark.parametrize("text", ["C.F Epipsocus", "NR EPIPSOCUS"])
def test_initials_or_a_reserve_before_a_genus_show_no_doubt_sign(text):
    from specimen_digitization.field_research import checks

    assert checks.doubt_signs([text]) == ()
    assert checks.genus_in_doubt(text, text.split()[1])


# "near", "nr." and "vic." beside a place the label's place fields settled,
# on the line that writes it, compared by the place comparison key: a
# locality, not a doubtful name.
@pytest.mark.parametrize(("text", "places"), [
    ("5 mi near Chicago", ["Chicago"]),
    ("nr. Chicago", ["Chicago"]),
    ("NEAR CHICAGO", ["Chicago"]),
    ("near Chicago, Cook Co.", ["Chicago", "Cook"]),
    ("near San Pedro Sacatepequez", ["San Pedro"]),
    ("Chicago vic.", ["Chicago"]),
    ("Chicago, vic.", ["Chicago"]),
    ("vic. Chicago", ["Chicago"]),
    ("Mindanao, Davao vic.", ["Davao"]),
    ("Kinabalu N.R.\nnr. Chicago\nV-4-67-1", ["Illinois", "Chicago"]),
])
def test_near_or_vicinity_beside_a_settled_place_is_no_doubt_sign(text, places):
    from specimen_digitization.field_research import checks

    assert checks.doubt_signs([text], places=places) == ()
    # With no settled place it stays a sign.
    assert checks.doubt_signs([text]) == ("qualifier",)


@pytest.mark.parametrize(("text", "places"), [
    # A place no place field settled.
    ("5 km nr. Davao", ["Chicago"]),
    # A genus after the qualifier, or a place only on another line.
    ("near Epipsocus", ["Chicago"]),
    ("nr. Epipsocus", ["Chicago"]),
    ("nr. Epipsocus\nChicago", ["Chicago"]),
    ("NR. Epipsocus Chicago", ["Chicago"]),
    # A longer word than the place, and "near" or "nr." after it.
    ("near Chicagoland", ["Chicago"]),
    ("Chicago near", ["Chicago"]),
    ("Chicago nr. Epipsocus", ["Chicago"]),
    # "vic." beside a genus, and "cf." beside a place.
    ("Epipsocus vic.", ["Chicago"]),
    ("cf. Chicago", ["Chicago"]),
])
def test_a_qualifier_beside_no_settled_place_stays_a_doubt_sign(text, places):
    from specimen_digitization.field_research import checks

    assert checks.doubt_signs([text], places=places) == ("qualifier",)


# 1c of #289's fifth review: the label marks a taxon literal's genus as
# doubtful, a qualifier or a "?" right before it or on it, wherever the text
# writes the literal.
@pytest.mark.parametrize(("text", "literal", "doubtful"), [
    ("cfr. Epipsocus", "Epipsocus", True),
    ("conf. Epipsocus", "Epipsocus", True),
    ("c.f. Epipsocus", "Epipsocus", True),
    ("cfr.Epipsocus", "Epipsocus", True),
    ("Possibly Epipsocus sp. 1", "Epipsocus sp. 1", True),
    ("Epipsocus?", "Epipsocus", True),
    ("?Epipsocus", "Epipsocus", True),
    ("Epipsocus(?)", "Epipsocus", True),
    ("(?) Epipsocus", "Epipsocus", True),
    ("V-4-67-1 ? Epipsocus", "Epipsocus", True),
    ("cf.\nEpipsocus sp. 1", "Epipsocus sp. 1", True),
    ("V-4-67-1\nnr. Epipsocus\nsp. 1 " + FEMALE, "Epipsocus", True),
    ("Epipsocus\ncfr. Epipsocus", "Epipsocus", True),
    # A qualifier alone on the line above, a blank line between or not, in
    # any spelling (N2 of #289's sixth review); right before the genus, "NR"
    # and initials without the final period stay qualifiers.
    ("NR\nEpipsocus sp. 1", "Epipsocus sp. 1", True),
    ("  (cf.)\n\nEpipsocus sp. 1", "Epipsocus sp. 1", True),
    ("Det. Mockford\nnr.\nEpipsocus sp. 1", "Epipsocus sp. 1", True),
    ("nr. Epipsocus", "Epipsocus", True),
    ("NR Epipsocus sp. 1", "Epipsocus sp. 1", True),
    ("C.F Epipsocus", "Epipsocus", True),
    # A qualifier ending a longer line above belongs to that line.
    ("Sabah, Danum Valley NR\nEpipsocus sp. 1", "Epipsocus sp. 1", False),
    ("Mindanao, Davao vic.\nEpipsocus sp. 1", "Epipsocus sp. 1", False),
    ("5 km nr.\nEpipsocus sp. 1", "Epipsocus sp. 1", False),
    ("conf. K. Yoshizawa\nEpipsocus sp. 1", "Epipsocus sp. 1", False),
    # No doubt right before the genus or on it.
    ("Epipsocus", "Epipsocus", False),
    ("Epipsocus\nV-4-67-1\nsp. 1 " + FEMALE, "Epipsocus", False),
    ("Epipsocus cf. sp. 1", "Epipsocus cf. sp. 1", False),
    ("Epipsocus sp. 1?", "Epipsocus", False),
    ("taxon: Danaus plexippus", "Danaus plexippus", False),
    ("Mossy forest 6400'\nsp. 30 " + FEMALE, "sp. 30 " + FEMALE, False),
    ("cfr. Epipsocus", "Danaus plexippus", False),
    # A person's initials before the genus are no qualifier.
    ("C.F. Epipsocus", "Epipsocus", False),
    ("Baker, C.F.\nEpipsocus sp. 1", "Epipsocus sp. 1", False),
    # A "?" on another word, on the line above, or after the genus is not on the genus.
    ("Davao? Epipsocus", "Epipsocus", False),
    ("1946?\nEpipsocus sp. 1", "Epipsocus sp. 1", False),
    ("?\nEpipsocus", "Epipsocus", False),
    ("(?)\nEpipsocus sp. 1", "Epipsocus sp. 1", False),
    ("Epipsocus\n?", "Epipsocus", False),
    ("Epipsocus sp. 1 ?", "Epipsocus", False),
    # A "?" standing alone right after the genus on its line is on the genus.
    ("Epipsocus ?", "Epipsocus", True),
    ("Epipsocus ? sp. 1", "Epipsocus", True),
    ("Epipsocus (?)", "Epipsocus", True),
    ("Epipsocus \N{FULLWIDTH QUESTION MARK}", "Epipsocus", True),
])
def test_a_genus_the_text_marks_as_doubtful(text, literal, doubtful):
    from specimen_digitization.field_research import checks

    assert checks.genus_in_doubt(text, literal) is doubtful


@pytest.mark.parametrize(("quote", "literal", "longer"), [
    # The third review's N3: an organiser candidate that cuts the subspecies off its line.
    ("Danaus plexippus megalippe", "Danaus plexippus", "Danaus plexippus megalippe"),
    ("Danaus plexippus megalippe \u2640 3 Sept. '46", "Danaus plexippus", "Danaus plexippus megalippe"),
    ("Danaus plexippus", "Danaus", "Danaus plexippus"),
    ("Aus bus var. cus", "Aus bus", "Aus bus var. cus"),
    # The same name: a keyed line's key, an author and year, a sex sign, a genus-level "sp. 1".
    ("taxon: Danaus plexippus", "Danaus plexippus", None),
    ("Danaus plexippus (Linnaeus, 1758)", "Danaus plexippus", None),
    ("Danaus plexippus \u2640", "Danaus plexippus", None),
    ("Epipsocus sp. 1 \u2640", "Epipsocus sp. 1", None),
    # No name on the quote at all.
    ("sp. 30 \u2640", "sp. 30", None),
    # A genus before a literal that has none (B1 of #289's review), on its line or the line above.
    ("Epipsocus sp. 1 " + FEMALE, "sp. 1 " + FEMALE, "Epipsocus"),
    ("VI-24-68-7.\nEpipsocus\nsp. 1 " + FEMALE, "sp. 1 " + FEMALE, "Epipsocus"),
    ("Danaus plexippus megalippe", "plexippus megalippe", "Danaus plexippus megalippe"),
    # No genus before it: the habitat line above 105526321's code.
    ("Mossy forest 6400'\nsp. 30 " + FEMALE, "sp. 30 " + FEMALE, None),
    # A word before a literal that names its own genus is no part of its name.
    ("Det. F. G. Werner\nDanaus plexippus", "Danaus plexippus", None),
    ("Mindanao Danaus plexippus", "Danaus plexippus", None),
])
def test_a_taxon_candidates_quote_may_write_a_longer_name_than_its_literal(quote, literal, longer):
    assert longer_name(quote, literal) == longer


def test_catalog_numbers():
    prefixed = check_catalog_number("FMNH INS 0012345", reading_texts=READINGS)
    bare = check_catalog_number("0012345", reading_texts=READINGS)
    code = check_catalog_number("IX-17-66-2", reading_texts=READINGS)

    assert (prefixed.status, prefixed.catalog_number) == (LookupStatus.SUCCESS, "0012345")
    assert bare.values == ("0012345",)
    assert code.status == LookupStatus.NO_MATCH and code.values == ()
    assert prefixed.as_dict() == {
        "check": "catalog_number_validator", "literal": "FMNH INS 0012345",
        "status": "success", "catalog_number": "0012345",
    }
