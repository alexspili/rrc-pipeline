"""Tier 1: telling a form's own header from a mention of another form.

Pure string work on OCR text. The whole taxonomy-coverage check rests on this
distinction, so it is pinned before the corpus-wide test that uses it.
"""

from __future__ import annotations

from pipeline.formscan import header_tokens


def test_finds_a_form_number_in_the_header():
    assert header_tokens("RAILROAD COMMISSION OF TEXAS  FORM P-4  5/90") == {"P-4"}


def test_finds_a_form_number_written_without_the_word_form():
    assert "W-15" in header_tokens("OIL AND GAS DIVISION  W-15 (Rev. 11-1-69)")


def test_ignores_a_reference_to_another_form():
    """Origin: the P-4 face says "Operator name exactly as shown on Form P-5
    Organization Report" in its third field. Counting that as a P-5 header
    reported P-5 on 373 pages, nearly all of them P-4s.
    """
    text = ("RAILROAD COMMISSION OF TEXAS FORM P-4  "
            "3. Operator name exactly as shown on Form P-5 Organization Report")
    assert header_tokens(text) == {"P-4"}


def test_ignores_several_flavours_of_cross_reference():
    for phrase in ["as shown on Form W-1", "see Form W-3", "per Form G-5",
                   "attached Form P-6", "copy of Form W-2",
                   "pursuant to Form L-1", "filed with Form P-12"]:
        assert header_tokens(f"HEADER TEXT {phrase}") == set(), phrase


def test_only_looks_at_the_header_region():
    """A form number in the body is not this page's identity. The number is
    printed top-right, which lands early in OCR reading order.
    """
    text = "FORM W-2 " + ("x" * 500) + " FORM G-1"
    assert header_tokens(text) == {"W-2"}


def test_handles_multi_letter_and_suffixed_numbers():
    assert "GT-1" in header_tokens("FORM GT-1 something")
    assert "W-4A" in header_tokens("Form W-4A (Rev' 8-27-69)")


def test_empty_and_textless_pages_do_not_raise():
    assert header_tokens("") == set()
    assert header_tokens("   \n\n  ") == set()


def test_does_not_match_dates_or_measurements():
    """Revision dates and depths are everywhere on these forms and must not
    read as form numbers.
    """
    assert header_tokens("Rev. 4/1/83  API No. 42-039-31674") == set()
    assert header_tokens("setting depth 8276 ft, 9 7/8 bit") == set()


# ------------------------------------------------- survey abstract numbers

def test_survey_abstract_numbers_are_not_forms():
    """Origin: DEFECTS #11. In a Texas land description "A-38" is the abstract
    number of an original survey, not an RRC form. Plats are covered in them,
    so the scanner invented a dozen phantom form families: A-1, A-5, A-6, A-11,
    A-12, A-13, A-15, A-18, A-22, A-30, A-38, A-55, A-69, A-74, A-92.

    Real text from corpus plats.
    """
    for line in [
        "L. McLaughlin A-38 C Robertson County, Texas Scale 1 = 2000",
        "WM. ROBINSON - A-55 /07J Ac.",
        "ELIZA PEAKS A-92 WILLIAM H NEINAST and wife",
        "BURLESON COUNTY, TEXAS JOHN COX A-15 J.W.GIESENSCHLAG",
        "LEE JOHN Y. WALLACE A-22 UNIT",
    ]:
        assert header_tokens(line) == set(), line


def test_a_prefixed_token_is_rejected_even_beside_the_word_form():
    """No RRC form number begins with A. Being adjacent to "Form" does not
    make an abstract number one.
    """
    assert header_tokens("SURVEY Form A-38 tract") == set()


def test_real_forms_beginning_with_other_letters_still_parse():
    assert header_tokens("CERTIFICATE OF POOLING AUTHORITY P-12 Revised 05/2001") == {"P-12"}
    assert header_tokens("Form P-15 (5-5-71) STATEMENT OF PRODUCTIVITY") == {"P-15"}
    assert header_tokens("Form G-6 Rev. 7/5/64 APPLICATION FOR EXCEPTION") == {"G-6"}


# ------------------------------------------------- forms named in a list

def test_a_plural_reference_is_still_a_reference():
    """`(FORM\\s+)?` in the cross-reference pattern does not match "Forms ",
    so every phrase in the list above leaks the moment the word is plural.
    """
    assert header_tokens("HEADER TEXT filed with Forms W-2") == set()
    assert header_tokens("HEADER TEXT as shown on Forms P-5") == set()


def test_with_form_is_a_reference():
    assert header_tokens("HEADER TEXT with Form W-3 for plugging") == set()


def test_the_rest_of_a_list_inherits_the_reference():
    """Only the first token in "Forms W-2, G-1, and GT-1" is preceded by
    cross-referencing wording. The others are separated from it by nothing but
    list punctuation and inherit its status.
    """
    assert header_tokens("HEADER TEXT with Forms W-2, G-1, and GT-1 filed") == set()
    assert header_tokens("HEADER TEXT see Form W-2 or G-1") == set()


def test_the_l_1_face_reports_only_its_own_number():
    """Origin: DEFECTS #15. Real OCR from the L-1 face, which occurs on 46
    pages of this corpus and names both extraction targets in its own
    instructions. Counting those as headers put G-1 on 80 pages when it is on
    51 and W-2 on 109 when it is on 84, and lifted the OCR floor that guards
    the census headline from 68 records to 72.
    """
    text = ("RA,3LROAf7 COMMISSION OF TEXAS\nOil and Gas Division\n"
            "ELECTRIC LOG\nPlease Read Instructions\nSTATUS REPORT\n"
            "When the L-1 is NOT required\n"
            "• with Forms W-2, G-1, and GT-1 filed for injec tion wells,\n"
            "disposal , wells, water supply wells, service well s, re-test\n"
            "wells, re-classifications, and plugbacks of oil, gas, and\n"
            "geothermal wells\n"
            "• with Form W-3 for plugging of other than a ")
    assert header_tokens(text) == {"L-1"}
