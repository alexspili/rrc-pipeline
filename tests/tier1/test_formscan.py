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


# ------------------------------------------- forms older than the numbering

def test_a_bare_numbered_form_is_a_form():
    """Origin: DEFECTS #17. The RRC completion report predates the G-1 and W-2
    numbering, and the older sheets are simply "Form 2" and "Form 3". The
    pattern required a hyphen, so the scanner returned nothing at all on the
    family it most needed to report.

    Real OCR from records 1494483 page 2 and 1494905 page 8.
    """
    assert header_tokens("FORM 3\n\nOIL AND GAS DIVISION") == {"FORM 3"}
    assert header_tokens("Form 2\nWell Record") == {"FORM 2"}


def test_a_lowercased_form_word_still_carries_its_number():
    """Real OCR from record 1494408 page 4: the scan renders the word itself
    as "fORM". The token has to be found from the digit, not from a clean
    spelling of the word in front of it.
    """
    assert header_tokens("fORM 3 . .\n\nRAILROAD CO^d'.IfISSFON OF TE^CAS") \
        == {"FORM 3"}


def test_a_three_letter_form_prefix_is_a_form():
    """`GWT-1` is the gas well test sheet that precedes the G-1. Two letters
    was not a rule, it was the longest prefix anybody had happened to look at.

    Synthetic, and deliberately so: the one GWT-1 in this corpus, record
    1493455 page 16, reads "8ern GW':'.>>i" in the text layer and no pattern
    recovers it. The scanner stays a floor.
    """
    assert header_tokens("Form GWT-1 Back Pressure Test") == {"GWT-1"}


def test_a_bare_number_without_the_word_form_is_not_a_form():
    """The guard on the change above. A loose digit would match half the
    corpus: these pages are covered in depths, dates and file numbers.
    """
    assert header_tokens("File No. 3 ... 2 copies ... within 10 days") == set()
    assert header_tokens("RECEIVED 3 1965") == set()


def test_a_referenced_bare_form_is_still_a_reference():
    assert header_tokens("HEADER TEXT see Form 3 for the older wells") == set()


def test_a_three_letter_prefix_standing_alone_is_not_a_form():
    """The guard on the three-letter branch, all real text from this corpus.
    Allowing a bare three-letter prefix invented six families in one pass.

    HR-4, a Halliburton cement retarder in that same additive list, is not
    covered here. It is a two-letter prefix, so it has always been matched and
    has always been in the counts at 2 pages, which is what the coverage
    threshold exists to tolerate. Fixing it is not this change.
    """
    for line in [
        "PO Box 12967 Austin TX 78711-2967 www.rrc.state.tx.us $/02-WWW-1",
        "Texas Lambert for South Central Zone, NAQ-27.",
        "FAMCOR OIL APR-23-2009 13:01 P.05 Schlumberger",
        "13. (a) C. H. .75x CFB-2, b. 2x",
        "WHEELER & PICKENS FEE NCT-6 (10539) HUMBLE FIELD",
        "4. Lease Name and Lease Identification No. Chambers Barbers Hill SWD-1",
    ]:
        assert header_tokens(line) == set(), line


def test_a_bare_number_does_not_swallow_a_hyphenated_one():
    """"a Form 11-5 (Organization Report)" is a reference to Form 11-5, and
    the bare branch would report a Form 11 that does not exist.
    """
    assert "FORM 11" not in header_tokens(
        "Before this application can be processed, a Form 11-5 "
        "(Organization Report) showing the exact operator name")
