import re
import pandas as pd


def normalize(text):
    if not isinstance(text, str):
        return ""
    return text.upper().replace("(", " ").replace(")", " ").replace("-", " ").replace("  ", " ").strip()


def classify_fund(fund_name):
    f = normalize(fund_name)

    # 1. PPF (TL)
    if re.search(r"PARA PİYASASI", f):
        return "PPF (TL)", "-"

    # 2. Hisse (TL)
    if re.search(r"HİSSE SENEDİ|HİSSE", f):
        if not re.search(r"YABANCI|DÖVİZ", f):
            return "Hisse (TL)", "-"

    # 3. Tahvil (TL)
    if re.search(r"BORÇLANMA ARAÇLARI|KAMU|ÖZEL SEKTÖR", f):
        if not re.search(r"DÖVİZ|EUROBOND|YABANCI", f):
            return "Tahvil (TL)", "-"

    # 4. Döviz Bucket (KRİTİK DÜZELTME: Serbest kısıtlamasını kaldırdık)
    # Artık isminde Serbest geçse bile Döviz ise buraya düşecek!
    if re.search(r"DÖVİZ|EURO|USD|AVRO|YABANCI|ALTIN|GÜMÜŞ|EMTİA|KIYMETLİ", f):
        if re.search(r"ALTIN|GÜMÜŞ|KIYMETLİ MADEN|EMTİA", f):
            return "Döviz", "Kıymetli Maden / Emtia"
        if re.search(r"EUROBOND", f):
            return "Döviz", "Eurobond"
        if re.search(r"YABANCI.*HİSSE|HİSSE.*YABANCI", f):
            return "Döviz", "Yabancı Hisse"
        if re.search(r"YABANCI.*BORÇLANMA|BORÇLANMA.*YABANCI", f):
            return "Döviz", "Yabancı Tahvil"
        return "Döviz", "Döviz PPF"

    # 5. Serbest Fonlar (Sadece varlık sınıfı belirtilmeyen "Saf" serbest fonlar buraya düşecek)
    if re.search(r"SERBEST", f):
        return "Serbest Fon", "-"

    # 6. Fon Sepeti
    if re.search(r"FON SEPETİ", f):
        return "Fon Sepeti", "-"

    # 7. Katılım (Faizsiz)
    if re.search(r"KATILIM", f):
        return "Katılım Fonu", "-"

    # 8. Değişken ve Karma
    if re.search(r"DEĞİŞKEN", f):
        return "Değişken Fon", "-"
    if re.search(r"KARMA", f):
        return "Karma Fon", "-"

    # 9. Gerçekten Kapsam Dışı Kalanlar
    return "Diğer", "-"
