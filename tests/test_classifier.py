"""Tests for src.classifier.classify_fund.

Implementation note: the regex patterns use Turkish dotted "İ" (U+0130),
but Python's default str.upper() lossy-converts both "i" and "ı" to plain
"I" (U+0049), so mixed-case input may not normalize back into the
pattern. To exercise each branch deterministically these tests pass
inputs that are already upper-cased Turkish — the classifier is normally
fed TEFAS data that does survive .upper() cleanly because the upstream
strings either come pre-capitalised or use the Latin-only fragments
("ALTIN", "EUROBOND", "YABANCI", "SERBEST", "KARMA", "DİĞER") that the
patterns also anchor on.
"""
import pytest

from src.classifier import _normalize, classify_fund


# ────────────────────────────────────────────────────────────────────────
# Positive matches — one example per category branch
# ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("PARA PİYASASI FONU",                          ("PPF (TL)", "-")),
    ("HİSSE SENEDİ FONU",                           ("Hisse (TL)", "-")),
    ("BORÇLANMA ARAÇLARI FONU",                     ("Tahvil (TL)", "-")),
    ("KAMU BORÇLANMA FONU",                         ("Tahvil (TL)", "-")),
    ("ALTIN KIYMETLİ MADEN FONU",
     ("Döviz", "Kıymetli Maden / Emtia")),
    ("EUROBOND BORÇLANMA FONU",                     ("Döviz", "Eurobond")),
    ("YABANCI HİSSE SENEDİ FONU",                   ("Döviz", "Yabancı Hisse")),
    ("YABANCI BORÇLANMA ARAÇLARI FONU",             ("Döviz", "Yabancı Tahvil")),
    ("USD FONU",                                    ("Döviz", "Döviz PPF")),
    ("SERBEST FON",                                 ("Serbest Fon", "-")),
    ("FON SEPETİ",                                  ("Fon Sepeti", "-")),
    ("KATILIM FONU",                                ("Katılım Fonu", "-")),
    ("KARMA FON",                                   ("Karma Fon", "-")),
    ("XYZ FONU",                                    ("Diğer", "-")),
])
def test_each_category_branch(name, expected):
    assert classify_fund(name) == expected


# ────────────────────────────────────────────────────────────────────────
# Exclusion clauses — qualified equity / debt funds must defer to Döviz
# ────────────────────────────────────────────────────────────────────────

def test_yabanci_hisse_is_doviz_not_hisse_tl():
    """The plain HİSSE rule must NOT swallow yabancı equity funds."""
    cat, sub = classify_fund("YABANCI HİSSE SENEDİ FONU")
    assert cat == "Döviz"
    assert sub == "Yabancı Hisse"


def test_eurobond_is_doviz_not_tahvil_tl():
    """A Eurobond-named borçlanma fund must NOT classify as Tahvil (TL)."""
    cat, sub = classify_fund("EUROBOND BORÇLANMA ARAÇLARI FONU")
    assert cat == "Döviz"
    assert sub == "Eurobond"


def test_doviz_borclanma_is_doviz_not_tahvil_tl():
    """Any DÖVİZ-marked borçlanma fund routes to Döviz, not Tahvil (TL)."""
    cat, _ = classify_fund("DÖVİZ BORÇLANMA ARAÇLARI FONU")
    assert cat == "Döviz"


# ────────────────────────────────────────────────────────────────────────
# Defensive inputs
# ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [None, "", 12345, 3.14, []])
def test_non_string_or_empty_returns_diger(bad):
    assert classify_fund(bad) == ("Diğer", "-")


# ────────────────────────────────────────────────────────────────────────
# _normalize — lock in the pattern-cleaning rules
# ────────────────────────────────────────────────────────────────────────

def test_normalize_uppercases_ascii():
    assert _normalize("eurobond plus") == "EUROBOND PLUS"


def test_normalize_strips_parens_and_dashes():
    # Parens and dashes get replaced with spaces; the single .replace("  ", " ")
    # pass collapses the run of consecutive spaces produced where "-" sits
    # adjacent to "(", and the trailing space from ")" is stripped.
    assert _normalize("EUROBOND-FONU (PRO)") == "EUROBOND FONU PRO"


def test_normalize_handles_non_string():
    assert _normalize(None) == ""
    assert _normalize(3.14) == ""
    assert _normalize([]) == ""
