import re
import pandas as pd


def normalize(text):
    """Metni standartlaştırır: Büyük harf, gereksiz noktalama ve boşluk temizliği."""
    if not isinstance(text, str):
        return ""
    return text.upper().replace("(", " ").replace(")", " ").replace("-", " ").replace("  ", " ").strip()


def classify_fund(fund_name):
    """
    Fon ismini analiz edip (Ana Kategori, Alt Kategori) tuple'ı döndürür.
    Precedence (Öncelik) sırası: En spesifikten genele doğru.
    """
    f = normalize(fund_name)

    # 1. PPF (TL)
    if re.search(r"PARA PİYASASI", f):
        return "PPF (TL)", "-"

    # 2. Hisse (TL)
    if re.search(r"HİSSE SENEDİ|HİSSE", f):
        # Yabancı hisseyi Döviz bucket'ına bırakmak için eliyoruz
        if not re.search(r"YABANCI|DÖVİZ", f):
            return "Hisse (TL)", "-"

    # 3. Tahvil (TL)
    if re.search(r"BORÇLANMA ARAÇLARI|KAMU|ÖZEL SEKTÖR", f):
        if not re.search(r"DÖVİZ|EUROBOND|YABANCI", f):
            return "Tahvil (TL)", "-"

    # 4. Döviz Bucket (Hiyerarşik Alt Kategoriler)
    if re.search(r"DÖVİZ|EURO|USD|AVRO|YABANCI|ALTIN|GÜMÜŞ|EMTİA|KIYMETLİ", f):

        if re.search(r"ALTIN|GÜMÜŞ|KIYMETLİ MADEN|EMTİA", f):
            return "Döviz", "Kıymetli Maden / Emtia"

        if re.search(r"EUROBOND", f):
            return "Döviz", "Eurobond"

        if re.search(r"YABANCI.*HİSSE|HİSSE.*YABANCI", f):
            return "Döviz", "Yabancı Hisse"

        if re.search(r"YABANCI.*BORÇLANMA|BORÇLANMA.*YABANCI", f):
            return "Döviz", "Yabancı Tahvil"

        return "Döviz", "Genel Döviz"

    # 5. Kapsama Girmeyenler (Şemsiye fonlar, karma fonlar vs.)
    return "Diğer", "-"
