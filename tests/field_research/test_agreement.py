"""The agreement rules the real runs of 2026-10-09 on the ten pilot specimens
questioned (agreement.py; FIELD_RESEARCH.md, step 5), with labels from other
countries and languages beside the pilot's.

The step's cases run the ordinary workflow's run through the scripted
resolver and sources of test_step.
"""

from __future__ import annotations

import pytest
from test_step import (
    Gazetteer,
    Scripted,
    ValueState,
    answering,
    build_rig,
    confirming,
    from_tgn,
    label_with,
    LACKS,
    reasons_for,
    settle,
)

from specimen_digitization.field_research import agreement
from specimen_digitization.field_research.contracts import PlaceRef, SourceCandidate

E_ACUTE, E_GRAVE, U_UMLAUT, A_ACUTE = (
    "\N{LATIN SMALL LETTER E WITH ACUTE}", "\N{LATIN SMALL LETTER E WITH GRAVE}",
    "\N{LATIN SMALL LETTER U WITH DIAERESIS}", "\N{LATIN SMALL LETTER A WITH ACUTE}")


# ---- G34: a near spelling is checked against the larger places only ---------
# 105526330's province: the decided reading writes "Chimaltenago", Getty TGN
# knows only "Chimaltenango", and the reading also writes the town Yepocapa.
# The step checked the town as a parent of the department and left the
# province for review. A place's parents are only larger places.

def place(name, authority_id, *parents):
    """A source's candidate with its parents (name, authority_id), nearest first."""
    return SourceCandidate(name, authority_id, "place", None, tuple(PlaceRef(*parent) for parent in parents))


def field(*texts, authority_id=None):
    return agreement.PlaceField(tuple(texts), authority_id)


FRANCE = field("France", authority_id="tgn:1000070")
GERMANY = field("Deutschland", authority_id="tgn:7000084")
BRAZIL = field("Brasil", authority_id="tgn:1000047")


@pytest.mark.parametrize(("key", "candidate", "written", "settled"), [
    # A French departement one letter off ("Finistre"), in its region and country, with the
    # town of Brest below it on the reading.
    ("county", place("Finist" + E_GRAVE + "re", "tgn:7002849", ("Bretagne", "tgn:7002848"),
        ("France", "tgn:1000070")),
     {"country": FRANCE, "province_state": field("Bretagne", authority_id="tgn:7002848"), "city": field("Brest")},
     {"country": FRANCE, "province_state": field("Bretagne", authority_id="tgn:7002848")}),
    # A German Land one letter off ("Bayer" for Bayern), with Muenchen below it.
    ("province_state", place("Bayern", "tgn:7003686", ("Deutschland", "tgn:7000084")),
     {"country": GERMANY, "city": field("M" + U_UMLAUT + "nchen")}, {"country": GERMANY}),
    # A Brazilian state one letter off ("Minas Geras"), with a county and a city below it.
    ("province_state", place("Minas Gerais", "tgn:1001780", ("Brasil", "tgn:1000047")),
     {"country": BRAZIL, "county": field("Sabar" + A_ACUTE), "city": field("Belo Horizonte")},
     {"country": BRAZIL}),
], ids=["french-departement-above-its-town", "german-land-above-its-city", "brazilian-state-above-county-and-city"])
def test_a_near_spelled_place_is_not_checked_against_the_places_below_it(key, candidate, written, settled):
    """On origin/main each is refused: the town below is no parent of the place."""
    assert agreement.parents_refusal(key, candidate, agreement.NEAR_SPELLING, written=written,
        settled=settled) is None


@pytest.mark.parametrize(("literal", "nation", "authority_id", "town"), [
    # Spanish: "Mexco" beside the city "Mexico" (with its accent), TGN's nation lists itself.
    ("Mexco", "Mexico", "tgn:1000077", "M" + E_ACUTE + "xico"),
    # German and French spellings of Luxembourg, the city of the same name below it.
    ("Luxemburg", "Luxembourg", "tgn:7006830", "Luxembourg"),
    # Spanish: "Panma" beside the city "Panama" (with its accent).
    ("Panma", "Panam" + A_ACUTE, "tgn:1000149", "Panam" + A_ACUTE),
], ids=["mexico", "luxembourg", "panama"])
def test_a_near_spelled_country_never_settles_on_a_city_of_its_name(literal, nation, authority_id, town):
    """On origin/main each settles: a nation lists itself as its parent, and
    the city below it has the nation's name. A country has no larger place."""
    candidate = place(nation, authority_id, (nation, authority_id))
    refused = agreement.parents_refusal("country", candidate, agreement.NEAR_SPELLING,
        written={"city": field(town)}, settled={})
    assert refused is not None and refused.reason == agreement.NEAR_UNFIT


def test_a_near_spelled_city_still_needs_every_larger_place_as_its_parent():
    """The control, unchanged: a Brazilian city one letter off ("Bello
    Horizonte") whose reading writes a state it does not lie in."""
    candidate = place("Belo Horizonte", "tgn:7012345", ("Minas Gerais", "tgn:1001780"), ("Brasil", "tgn:1000047"))
    refused = agreement.parents_refusal("city", candidate, agreement.NEAR_SPELLING,
        written={"country": BRAZIL, "province_state": field("S" + A_ACUTE + "o Paulo")}, settled={"country": BRAZIL})
    assert refused is not None and refused.reason == agreement.NEAR_UNFIT


def test_105526330s_province_settles_one_letter_off_beside_its_town(tmp_path):
    """The real run's shape: country Guatemala, the decided province
    "Chimaltenago" and the town Yepocapa. Getty TGN's department
    Chimaltenango, one letter off, lies in Guatemala: the province settles
    with a near_spelling warning, and the town settles inside it. On
    origin/main the province goes to review (NEAR_UNFIT)."""
    rig = build_rig(tmp_path, label_with(country="Guatemala", province_state="Chimaltenago", county=None,
        city="Yepocapa"))
    run = rig.specimen.run
    settle(rig, Scripted({"country": from_tgn("Guatemala", "Guatemala", None, "tgn:7005493"),
        "province_state": from_tgn("Chimaltenango", "Chimaltenago", "Chimaltenango", "tgn:1000565"),
        "county": answering(LACKS),
        "city": confirming("Yepocapa", reading="1A", within=("Chimaltenango", "Guatemala"))}),
        tools=Gazetteer(rig.blobs))
    province = run.fields["province_state"]
    assert (province.state, province.literal, province.normalized, province.authority_id) == (
        ValueState.SUPPORTED, "Chimaltenago", "Chimaltenango", "tgn:1000565")
    assert [f.reason_code for f in run.findings] == ["near_spelling:province_state"]
    assert run.fields["city"].state == ValueState.SUPPORTED
    assert not reasons_for(run, "province_state") and not reasons_for(run, "city")
