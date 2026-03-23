import re

LANGUAGE_LABELS = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "ar": "Arabic",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "tr": "Turkish",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "pa": "Punjabi",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "sw": "Swahili",
    "ha": "Hausa",
    "ur": "Urdu",
    "fa": "Persian",
    "pl": "Polish",
    "ro": "Romanian",
    "sv": "Swedish",
    "da": "Danish",
    "nl": "Dutch",
    "gu": "Gujarati",
}

SUPPORTED_LANGS = set(LANGUAGE_LABELS.keys())


def language_label(lang: str) -> str:
    return LANGUAGE_LABELS.get(lang, "English")


def detect_lang(question: str) -> str:
    s = (question or "").strip()
    if not s:
        return "en"

    for ch in s:
        if "\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F" or "\u08A0" <= ch <= "\u08FF":
            if re.search(r"[\u0600-\u06FF]{3,}", s):
                ur_markers = [" کا ", " کی ", " ہے ", " میں ", " نہیں ", " اور ", " سے ", " کے ", " کیا ", " ہیں"]
                fa_markers = [" است ", " در ", " از ", " با ", " برای ", " این ", " آن "]
                ur_hits = sum(1 for m in ur_markers if m in s)
                fa_hits = sum(1 for m in fa_markers if m in s)
                if ur_hits >= 1:
                    return "ur"
                if fa_hits >= 2:
                    return "fa"
                return "ar"
            return "ar"

        if "\u0900" <= ch <= "\u097F":
            mr_markers = ["आहे", "काय", "कोणत", "शिफारस", "साठी", "चे ", "ची ", "चा "]
            if any(m in s for m in mr_markers):
                return "mr"
            return "hi"
        if "\u0980" <= ch <= "\u09FF":
            return "bn"
        if "\u0B80" <= ch <= "\u0BFF":
            return "ta"
        if "\u0C00" <= ch <= "\u0C7F":
            return "te"
        if "\u0A00" <= ch <= "\u0A7F":
            return "pa"
        if "\u0A80" <= ch <= "\u0AFF":
            return "gu"
        if "\u0E00" <= ch <= "\u0E7F":
            return "th"
        if "\u4E00" <= ch <= "\u9FFF" or "\u3400" <= ch <= "\u4DBF":
            return "zh"
        if "\u3040" <= ch <= "\u309F" or "\u30A0" <= ch <= "\u30FF":
            return "ja"
        if "\uAC00" <= ch <= "\uD7AF" or "\u1100" <= ch <= "\u11FF":
            return "ko"
        if "\u0400" <= ch <= "\u04FF":
            return "ru"

    sl = s.lower()

    if re.search(r"[şğıİ]", sl):
        return "tr"

    if re.search(r"[àâéèêëîïôûùÿœæ]", sl) and not re.search(r"[şğı]", sl):
        if re.search(r"[çü]", sl):
            tr_quick = sum(1 for m in [" bir ", " ve ", " ile ", " için ", " değil ", " nedir", " neler"] if m in sl)
            if tr_quick >= 1:
                return "tr"

        it_quick = sum(1 for m in [" il ", " lo ", " la ", " le ", " di ", " è ", " del ", " per ", " con ", "qual ", "quali "] if m in sl)
        fr_quick = sum(1 for m in [" le ", " la ", " les ", " des ", " du ", " de ", " une "] if m in sl)
        if it_quick > fr_quick and it_quick >= 2:
            return "it"
        if fr_quick >= 2:
            return "fr"

    fr_markers = [
        " le ", " la ", " les ", " des ", " du ", " de ", " une ", " un ",
        "pour ", "avec ", "sans ", "chez ", "dans ", "sur ", "est ", "sont ",
        "comment ", "pourquoi ", "quand ", "quel ", "quelle ", "quelles ", "quels ",
        "prise en charge", "recommandation", "contre-indication", "effets indésirables",
        "toxine botulinique", "acide hyaluronique",
    ]
    es_markers = [
        " el ", " la ", " los ", " las ", " del ",
        "para ", "con ", "sin ", "cómo ", "por qué ", "cuándo ", "qué ",
        "manejo", "recomendación", "contraindicación", "efectos adversos",
        "toxina botulínica", "ácido hialurónico",
    ]
    de_markers = [
        " der ", " die ", " das ", " ein ", " eine ", " und ", " oder ",
        " ist ", " sind ", " wird ", " werden ", " für ", " mit ",
        "behandlung", "nebenwirkung", "kontraindikation",
    ]
    it_markers = [
        " il ", " lo ", " gli ", " uno ", " una ",
        " è ", " sono ", " per ", " con ", " senza ",
        "trattamento", "controindicazione",
    ]
    pt_markers = [
        " o ", " os ", " um ", " uma ",
        " é ", " são ", " para ", " com ", " sem ",
        "tratamento", "contraindicação",
    ]
    tr_markers = [
        " bir ", " ve ", " ile ", " için ", " değil ",
        "tedavi", "komplikasyon",
        " nedir", " neler", " olan", " hangi ",
        " önerilen", " karşılaştıran", " riskleri",
    ]
    id_markers = [
        " dan ", " yang ", " untuk ", " dengan ", " tidak ", " adalah ",
        "pengobatan", "komplikasi",
        " di ", " apa ", " ini ", " itu ", " dari ", " pada ",
        "risiko", "injeksi", "filler",
    ]
    vi_markers = [
        " và ", " của ", " cho ", " không ", " là ",
        "điều trị", "biến chứng",
    ]
    pl_markers = [
        " jest ", " są ", " i ", " w ", " na ", " do ", " z ", " się ",
        "jakie ", "leczenie", "powikłania", "ryzyko", "zagrożenia",
        "kwasu hialuronowego", "wypełniacze", "związane",
        " nie ", " co ", " jak ", " czy ",
    ]
    ro_markers = [
        " este ", " sunt ", " și ", " cu ", " în ", " de ", " la ", " un ", " o ",
        "tratament", "complicații", "riscuri", "acidului hialuronic",
        " care ", " ce ", " cum ", " pentru ",
    ]
    sv_markers = [
        " är ", " och ", " med ", " för ", " att ", " en ", " ett ", " av ",
        "behandling", "komplikationer", "risker",
        " vilka ", " vad ", " hur ", " den ", " det ",
    ]
    da_markers = [
        " er ", " og ", " med ", " for ", " at ", " en ", " et ", " af ",
        "behandling", "komplikationer", "risici",
        " hvad ", " hvilke ", " den ", " det ", " ved ",
    ]
    nl_markers = [
        " is ", " en ", " met ", " voor ", " van ", " de ", " het ", " een ",
        "behandeling", "complicaties", "risico",
        " wat ", " welke ", " zijn ", " worden ",
    ]

    scores = {
        "fr": sum(1 for m in fr_markers if m in sl),
        "es": sum(1 for m in es_markers if m in sl),
        "de": sum(1 for m in de_markers if m in sl),
        "it": sum(1 for m in it_markers if m in sl),
        "pt": sum(1 for m in pt_markers if m in sl),
        "tr": sum(1 for m in tr_markers if m in sl),
        "id": sum(1 for m in id_markers if m in sl),
        "vi": sum(1 for m in vi_markers if m in sl),
        "pl": sum(1 for m in pl_markers if m in sl),
        "ro": sum(1 for m in ro_markers if m in sl),
        "sv": sum(1 for m in sv_markers if m in sl),
        "da": sum(1 for m in da_markers if m in sl),
        "nl": sum(1 for m in nl_markers if m in sl),
    }

    best_lang = max(scores, key=scores.get)  # type: ignore
    if scores[best_lang] >= 2:
        return best_lang

    return "en"
