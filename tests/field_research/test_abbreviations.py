"""The letter rule an abbreviation the label writes must meet to be looked up by
its expansion (field_research/abbreviations.py; FIELD_RESEARCH.md, P4)."""

from __future__ import annotations

import pytest

from specimen_digitization.field_research.abbreviations import abbreviated, fit, fits, initialism, shown


@pytest.mark.parametrize(("abbreviation", "expansion"), [
    # Initials: countries, states and provinces on labels from anywhere. "P.I."
    # spells several island groups alike.
    ("P.I.", "Philippine Islands"),
    ("P.I.", "Pacific Islands"),
    ("P.I.", "Pitcairn Islands"),
    ("P. I.", "Philippine Islands"),
    ("N.S.W.", "New South Wales"),
    ("B.C.", "British Columbia"),
    ("B.C.S.", "Baja California Sur"),
    ("U.S.A.", "United States of America"),
    # Truncations: the word's first letters, at most 60% of them.
    ("Phil. Is.", "Philippine Islands"),
    ("Guat.", "Guatemala"),
    ("GUAT.", "Guatemala"),
    ("Guate.", "Guatemala"),
    ("Mex.", "Mexico"),
    ("Ill.", "Illinois"),
    ("Prov.", "Province"),
    ("Co.", "County"),
    ("Is.", "Island"),
    ("Is.", "Islands"),
    ("Is. of Man", "Isle of Man"),
    ("R. de Jan.", "Rio de Janeiro"),
    # Contractions: the word's first and last letters, letters between them in order.
    ("Sta.", "Santa"),
    ("Sta. Cruz", "Santa Cruz"),
    ("Ft.", "Fort"),
    ("Ft. Lauderdale", "Fort Lauderdale"),
    ("Mts.", "Mountains"),
    ("Dpto.", "Departamento"),
    ("Qld.", "Queensland"),
    ("Edo.", "Estado"),
    ("Pto.", "Puerto"),
    ("Gtmla.", "Guatemala"),
    ("Edo. Mex.", "Estado de Mexico"),
    # Accents aside, either way.
    ("M\u00e9x.", "Mexico"),
    ("Mex.", "M\u00e9xico"),
    ("Edo. M\u00e9x.", "Estado de M\u00e9xico"),
    # A place name with its unit word written out (105526326's "Davao, Prov.",
    # 105526323's "Davao" above "Prov.").
    ("Davao, Prov.", "Davao Province"),
    ("Davao\nProv.", "Davao Province"),
    ("Cook Co.", "Cook County"),
    ("Edo. de Mexico", "Estado de Mexico"),
    ("Dpto. Cusco", "Departamento Cusco"),
    # Written without a period.
    ("Mt Apo", "Mount Apo"),
    ("St Helena", "Saint Helena"),
    ("Falkland Is", "Falkland Islands"),
    # Capitals with no period: initials only, one letter a word.
    ("NSW", "New South Wales"),
    ("USA", "United States of America"),
    ("UK", "United Kingdom"),
    # A hyphen splits groups as a period does.
    ("S.-Afr.", "South Africa"),
    # One set of initials, three expansions: the letters alone do not decide.
    ("S.A.", "South Australia"),
    ("S.A.", "South Africa"),
    ("S.A.", "Saudi Arabia"),
    # The rule's limit: a whole word with a trailing period reads as a
    # truncation when it is short enough. The gazetteer's level, the parent
    # check and a rival are what stand behind it.
    ("Lima.", "Limassol"),
])
def test_an_abbreviation_fits_the_expansion_its_letters_spell_in_order(abbreviation, expansion):
    assert fits(abbreviation, expansion)


@pytest.mark.parametrize(("abbreviation", "expansion"), [
    # Two groups never fit one word, nor one group two.
    ("P.I.", "Peru"),
    ("P.I.", "Philippines"),
    ("Phil.", "Philippine Islands"),
    ("Mex.", "Mexico City"),
    ("B.C.", "Baja California Sur"),
    ("N.S.W.", "New Wales"),
    # A letter the word does not have, or not in order.
    ("Ill.", "Iowa"),
    ("Qld.", "Queens"),
    ("Mts.", "Mount"),
    ("Gtua.", "Guatemala"),
    # A group starts with its word's first letter.
    ("Guat.", "Antigua Guatemala"),
    ("A.", "South Africa"),
    ("S.A.", "Asia"),
    ("I.P.", "Philippine Islands"),
    # A word between the groups is skipped only when it is minor.
    ("N.W.", "New South Wales"),
    ("Edo. Mex.", "Estado Norte Mexico"),
    # A name with a letter or two dropped is no abbreviation, period or not
    # (the review of #295, H1 to H3): it is a near spelling (G34) or nothing.
    ("Chimaltenago.", "Chimaltenango"),
    ("Chimaltango.", "Chimaltenango"),
    ("Guatmala.", "Guatemala"),
    ("Mindano.", "Mindanao"),
    ("Philipines.", "Philippines"),
    ("Yepocpa.", "Yepocapa"),
    # Neither a truncation nor a contraction, or more than 60% of the word.
    ("Chmltngo.", "Chimaltenango"),
    ("Guatem.", "Guatemala"),
    ("Gtml.", "Guatemala"),
    # Every group written in full: nothing is abbreviated.
    ("Rio Janeiro.", "Rio de Janeiro"),
    # Capitals with no period are initials only, of two words or more.
    ("GUAT", "Guatemala"),
    ("UK", "Ukraine"),
    ("MALI", "Malawi"),
    ("IRAN", "Ireland"),
    ("SA", "Samoa"),
    ("PERU", "Peruvian Republic"),
    ("S", "South"),
    # Not written as an abbreviation: no period, more than four letters or not
    # all capitals, and no form written without one.
    ("Lima", "Limassol"),
    ("Peru", "Peruvia"),
    ("Guatemala", "Guatemala City"),
    ("CHIMAL", "Chimaltenango"),
    # The expansion has no more letters than the abbreviation.
    ("Guat.", "Guat"),
    ("Mex.", "Mex"),
    ("P.I.", "P I"),
    ("Peru.", "Peru"),
    # Nothing to expand.
    ("...", "Philippine Islands"),
    ("P.I.", ""),
])
def test_an_abbreviation_does_not_fit_a_name_its_letters_do_not_spell(abbreviation, expansion):
    assert not fits(abbreviation, expansion)


@pytest.mark.parametrize(("text", "written_as_one"), [
    ("P.I.", True), ("Guat.", True), ("NSW", True), ("GUAT", True), ("PI", True),
    ("Mt Apo", True), ("St Helena", True), ("Cook Co", True),
    ("Lima", False), ("CHIMAL", False), ("Guatemala", False), ("Mindanao", False),
])
def test_an_abbreviation_is_written_as_one(text, written_as_one):
    """A period, four capitals or fewer and nothing else lower case, or a form
    written without a period ("Mt", "St", "Co")."""
    assert abbreviated(text) is written_as_one


@pytest.mark.parametrize(("abbreviation", "expansion", "initials"), [
    ("P.I.", "Philippine Islands", True),
    ("S.A.", "Saudi Arabia", True),
    ("N.S.W.", "New South Wales", True),
    ("UK", "United Kingdom", True),
    ("R. de J.", "Rio de Janeiro", True),
    ("Guat.", "Guatemala", False),
    ("Phil. Is.", "Philippine Islands", False),
    ("R. de Jan.", "Rio de Janeiro", False),
    ("S.-Afr.", "South Africa", False),
    ("Davao, Prov.", "Davao Province", False),
])
def test_initials_are_a_fit_of_single_letters(abbreviation, expansion, initials):
    """Every group one letter, or a minor word written in full: such a fit
    settles a place only when another place on the label confirms it."""
    assert initialism(fit(abbreviation, expansion)) is initials


def test_the_fit_names_the_word_each_group_stands_for():
    """What the evidence row shows, so the record says how the letters fit."""
    assert fit("P.I.", "Philippine Islands") == (("P", "Philippine"), ("I", "Islands"))
    assert shown(fit("Edo. Mex.", "Estado de Mexico")) == "Edo = Estado, Mex = Mexico"
    assert shown(fit("NSW", "New South Wales")) == "N = New, S = South, W = Wales"
    # A group shows without the punctuation at its ends.
    assert shown(fit("Davao, Prov.", "Davao Province")) == "Davao = Davao, Prov = Province"
    assert fit("P.I.", "Peru") is None
