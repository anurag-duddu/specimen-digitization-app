"""The letter rule an abbreviation the label writes must meet to be looked up by
its expansion (field_research/abbreviations.py; FIELD_RESEARCH.md, P4)."""

from __future__ import annotations

import pytest

from specimen_digitization.field_research.abbreviations import abbreviated, fit, fits, shown


@pytest.mark.parametrize(("abbreviation", "expansion"), [
    # Countries, states and provinces on labels from anywhere.
    ("P.I.", "Philippine Islands"),
    ("P. I.", "Philippine Islands"),
    ("Phil. Is.", "Philippine Islands"),
    ("N.S.W.", "New South Wales"),
    ("Qld.", "Queensland"),
    ("Guat.", "Guatemala"),
    ("GUAT.", "Guatemala"),
    ("Guate.", "Guatemala"),
    ("Mex.", "Mexico"),
    ("B.C.", "British Columbia"),
    ("B.C.S.", "Baja California Sur"),
    ("Ill.", "Illinois"),
    # Spanish and Portuguese unit words and names.
    ("Edo.", "Estado"),
    ("Dpto.", "Departamento"),
    ("Sta.", "Santa"),
    ("Sta. Cruz", "Santa Cruz"),
    ("Pto.", "Puerto"),
    ("Edo. Mex.", "Estado de Mexico"),
    ("R. de Jan.", "Rio de Janeiro"),
    # Accents aside, either way.
    ("M\u00e9x.", "Mexico"),
    ("Mex.", "M\u00e9xico"),
    ("Edo. M\u00e9x.", "Estado de M\u00e9xico"),
    # Feature and unit words.
    ("Co.", "County"),
    ("Mts.", "Mountains"),
    ("Ft.", "Fort"),
    ("Ft. Lauderdale", "Fort Lauderdale"),
    ("Prov.", "Province"),
    ("Is.", "Island"),
    ("Is.", "Islands"),
    ("Is. of Man", "Isle of Man"),
    # Written without a period.
    ("Mt Apo", "Mount Apo"),
    ("St Helena", "Saint Helena"),
    ("Falkland Is", "Falkland Islands"),
    # Capitals only, read whole or one letter a word.
    ("GUAT", "Guatemala"),
    ("NSW", "New South Wales"),
    ("USA", "United States of America"),
    ("U.S.A.", "United States of America"),
    # A hyphen splits groups as a period does.
    ("S.-Afr.", "South Africa"),
    # One abbreviation, two expansions: the letters alone do not decide.
    ("S.A.", "South Australia"),
    ("S.A.", "South Africa"),
    ("S.A.", "Saudi Arabia"),
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


def test_the_fit_names_the_word_each_group_stands_for():
    """What the evidence row shows, so the record says how the letters fit."""
    assert fit("P.I.", "Philippine Islands") == (("P", "Philippine"), ("I", "Islands"))
    assert shown(fit("Edo. Mex.", "Estado de Mexico")) == "Edo = Estado, Mex = Mexico"
    assert shown(fit("NSW", "New South Wales")) == "N = New, S = South, W = Wales"
    assert fit("P.I.", "Peru") is None
