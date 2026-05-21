"""TEFAS fund name -> SPK-style category classifier.

`classify_fund` returns a (main_category, sub_category) tuple. Categories
follow the canonical SPK groupings — PPF, Hisse, Tahvil, Döviz (with
several sub-buckets), Serbest, Fon Sepeti, Katılım, Değişken, Karma.

Match order matters: more specific patterns must come before more general
ones (e.g. "Hisse Senedi Yabancı" gets caught by the Döviz rule because
its Yabancı qualifier outranks the plain Hisse rule).
"""
from __future__ import annotations

import re
from typing import Tuple

# Compile patterns once at import time; classify_fund is called per row,
# potentially hundreds of thousands of times during a full ETL.
_PARA_PIYASASI = re.compile(r"PARA PİYASASI")
_HISSE = re.compile(r"HİSSE SENEDİ|HİSSE")
_BORCLANMA = re.compile(r"BORÇLANMA ARAÇLARI|KAMU|ÖZEL SEKTÖR")
_DOVIZ_FAMILY = re.compile(r"DÖVİZ|EURO|USD|AVRO|YABANCI|ALTIN|GÜMÜŞ|EMTİA|KIYMETLİ")
_DOVIZ_EXCLUDE_HISSE = re.compile(r"YABANCI|DÖVİZ")
_DOVIZ_EXCLUDE_BORCLANMA = re.compile(r"DÖVİZ|EUROBOND|YABANCI")
_DOVIZ_METAL = re.compile(r"ALTIN|GÜMÜŞ|KIYMETLİ MADEN|EMTİA")
_DOVIZ_EUROBOND = re.compile(r"EUROBOND")
_DOVIZ_YABANCI_HISSE = re.compile(r"YABANCI.*HİSSE|HİSSE.*YABANCI")
_DOVIZ_YABANCI_TAHVIL = re.compile(r"YABANCI.*BORÇLANMA|BORÇLANMA.*YABANCI")
_SERBEST = re.compile(r"SERBEST")
_FON_SEPETI = re.compile(r"FON SEPETİ")
_KATILIM = re.compile(r"KATILIM")
_DEGISKEN = re.compile(r"DEĞİŞKEN")
_KARMA = re.compile(r"KARMA")


def _normalize(text: str) -> str:
    """Upper-case and strip punctuation so regex matches are stable across
    minor formatting differences in TEFAS fund names."""
    if not isinstance(text, str):
        return ""
    return (
        text.upper()
        .replace("(", " ")
        .replace(")", " ")
        .replace("-", " ")
        .replace("  ", " ")
        .strip()
    )


def classify_fund(fund_name: str) -> Tuple[str, str]:
    """Return (main_category, sub_category) for a TEFAS fund name."""
    f = _normalize(fund_name)

    if _PARA_PIYASASI.search(f):
        return "PPF (TL)", "-"

    # Hisse (TL): equity funds with no foreign-currency / overseas qualifier.
    if _HISSE.search(f) and not _DOVIZ_EXCLUDE_HISSE.search(f):
        return "Hisse (TL)", "-"

    # Tahvil (TL): domestic-currency debt-instrument funds.
    if _BORCLANMA.search(f) and not _DOVIZ_EXCLUDE_BORCLANMA.search(f):
        return "Tahvil (TL)", "-"

    # Döviz family — break into sub-buckets by qualifier.
    if _DOVIZ_FAMILY.search(f):
        if _DOVIZ_METAL.search(f):
            return "Döviz", "Kıymetli Maden / Emtia"
        if _DOVIZ_EUROBOND.search(f):
            return "Döviz", "Eurobond"
        if _DOVIZ_YABANCI_HISSE.search(f):
            return "Döviz", "Yabancı Hisse"
        if _DOVIZ_YABANCI_TAHVIL.search(f):
            return "Döviz", "Yabancı Tahvil"
        return "Döviz", "Döviz PPF"

    if _SERBEST.search(f):
        return "Serbest Fon", "-"
    if _FON_SEPETI.search(f):
        return "Fon Sepeti", "-"
    if _KATILIM.search(f):
        return "Katılım Fonu", "-"
    if _DEGISKEN.search(f):
        return "Değişken Fon", "-"
    if _KARMA.search(f):
        return "Karma Fon", "-"

    return "Diğer", "-"
