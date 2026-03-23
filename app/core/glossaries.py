# aestheticite_glossaries.py

from typing import Dict, List

# Canonical term = English medical standard
# Values = language-specific clinician-facing equivalents

AESTHETIC_GLOSSARIES: Dict[str, Dict[str, List[str]]] = {

    "fr": {
        "botulinum toxin": ["toxine botulique", "botox"],
        "dermal filler": ["produit de comblement", "filler"],
        "hyaluronic acid": ["acide hyaluronique"],
        "vascular occlusion": ["occlusion vasculaire"],
        "necrosis": ["nécrose"],
        "laser resurfacing": ["laser ablatif", "resurfaçage laser"],
        "chemical peel": ["peeling chimique"],
        "thread lift": ["fils tenseurs"],
        "local anesthetic": ["anesthésique local"],
        "lidocaine": ["lidocaïne"],
        "epinephrine": ["adrénaline"],
        "bruise": ["ecchymose", "hématome"],
        "infection": ["infection"],
    },

    "ar": {
        "botulinum toxin": ["توكسين البوتولينوم", "بوتوكس"],
        "dermal filler": ["الفيلر", "مواد الحشو"],
        "hyaluronic acid": ["حمض الهيالورونيك"],
        "vascular occlusion": ["انسداد وعائي"],
        "necrosis": ["نخر"],
        "laser resurfacing": ["إعادة تسطيح الجلد بالليزر"],
        "chemical peel": ["تقشير كيميائي"],
        "thread lift": ["شد بالخيوط"],
        "local anesthetic": ["مخدر موضعي"],
        "lidocaine": ["ليدوكايين"],
        "epinephrine": ["إبينفرين", "أدرينالين"],
        "bruise": ["كدمة"],
        "infection": ["عدوى"],
    },

    "es": {
        "botulinum toxin": ["toxina botulínica", "botox"],
        "dermal filler": ["relleno dérmico", "filler"],
        "hyaluronic acid": ["ácido hialurónico"],
        "vascular occlusion": ["oclusión vascular"],
        "necrosis": ["necrosis"],
        "laser resurfacing": ["rejuvenecimiento con láser", "láser ablativo"],
        "chemical peel": ["peeling químico"],
        "thread lift": ["hilos tensores"],
        "local anesthetic": ["anestésico local"],
        "lidocaine": ["lidocaína"],
        "epinephrine": ["epinefrina", "adrenalina"],
        "bruise": ["hematoma", "moretón"],
        "infection": ["infección"],
    },

    "de": {
        "botulinum toxin": ["botulinumtoxin", "botox"],
        "dermal filler": ["dermalfiller", "filler"],
        "hyaluronic acid": ["hyaluronsäure"],
        "vascular occlusion": ["gefäßverschluss"],
        "necrosis": ["nekrose"],
        "laser resurfacing": ["laserbehandlung", "hauterneuerung"],
        "chemical peel": ["chemisches peeling"],
        "thread lift": ["fadenlifting"],
        "local anesthetic": ["lokalanästhetikum"],
        "lidocaine": ["lidocain"],
        "epinephrine": ["adrenalin", "epinephrin"],
        "bruise": ["bluterguss", "hämatom"],
        "infection": ["infektion"],
    },

    "pt": {
        "botulinum toxin": ["toxina botulínica", "botox"],
        "dermal filler": ["preenchedor dérmico", "filler"],
        "hyaluronic acid": ["ácido hialurônico"],
        "vascular occlusion": ["oclusão vascular"],
        "necrosis": ["necrose"],
        "laser resurfacing": ["resurfacing a laser"],
        "chemical peel": ["peeling químico"],
        "thread lift": ["fios de sustentação"],
        "local anesthetic": ["anestésico local"],
        "lidocaine": ["lidocaína"],
        "epinephrine": ["epinefrina", "adrenalina"],
        "bruise": ["hematoma", "equimose"],
        "infection": ["infecção"],
    },

    "it": {
        "botulinum toxin": ["tossina botulinica", "botox"],
        "dermal filler": ["filler dermico", "filler"],
        "hyaluronic acid": ["acido ialuronico"],
        "vascular occlusion": ["occlusione vascolare"],
        "necrosis": ["necrosi"],
        "laser resurfacing": ["laser resurfacing", "ringiovanimento laser"],
        "chemical peel": ["peeling chimico"],
        "thread lift": ["fili di sospensione"],
        "local anesthetic": ["anestetico locale"],
        "lidocaine": ["lidocaina"],
        "epinephrine": ["epinefrina", "adrenalina"],
        "bruise": ["ematoma", "livido"],
        "infection": ["infezione"],
    },

    "zh": {
        "botulinum toxin": ["肉毒杆菌毒素", "肉毒素", "botox"],
        "dermal filler": ["皮肤填充剂", "玻尿酸填充"],
        "hyaluronic acid": ["透明质酸", "玻尿酸"],
        "vascular occlusion": ["血管栓塞", "血管闭塞"],
        "necrosis": ["坏死"],
        "laser resurfacing": ["激光换肤"],
        "chemical peel": ["化学换肤"],
        "thread lift": ["线雕", "埋线提升"],
        "local anesthetic": ["局部麻醉剂"],
        "lidocaine": ["利多卡因"],
        "epinephrine": ["肾上腺素"],
        "bruise": ["瘀伤", "青肿"],
        "infection": ["感染"],
    },

    "ja": {
        "botulinum toxin": ["ボツリヌストキシン", "ボトックス"],
        "dermal filler": ["皮膚充填剤", "フィラー"],
        "hyaluronic acid": ["ヒアルロン酸"],
        "vascular occlusion": ["血管閉塞"],
        "necrosis": ["壊死"],
        "laser resurfacing": ["レーザーリサーフェシング"],
        "chemical peel": ["ケミカルピーリング"],
        "thread lift": ["糸リフト", "スレッドリフト"],
        "local anesthetic": ["局所麻酔薬"],
        "lidocaine": ["リドカイン"],
        "epinephrine": ["エピネフリン", "アドレナリン"],
        "bruise": ["あざ", "打撲傷"],
        "infection": ["感染症"],
    },

    "ko": {
        "botulinum toxin": ["보툴리눔 독소", "보톡스"],
        "dermal filler": ["피부 필러", "필러"],
        "hyaluronic acid": ["히알루론산"],
        "vascular occlusion": ["혈관 폐색"],
        "necrosis": ["괴사"],
        "laser resurfacing": ["레이저 리서페이싱"],
        "chemical peel": ["화학적 박피"],
        "thread lift": ["실 리프팅"],
        "local anesthetic": ["국소 마취제"],
        "lidocaine": ["리도카인"],
        "epinephrine": ["에피네프린", "아드레날린"],
        "bruise": ["멍", "타박상"],
        "infection": ["감염"],
    },

    "hi": {
        "botulinum toxin": ["बोटुलिनम टॉक्सिन", "बोटॉक्स"],
        "dermal filler": ["डर्मल फिलर", "फिलर"],
        "hyaluronic acid": ["हाइलूरोनिक एसिड"],
        "vascular occlusion": ["रक्त वाहिका अवरोध"],
        "necrosis": ["नेक्रोसिस", "ऊतक मृत्यु"],
        "laser resurfacing": ["लेज़र रिसर्फेसिंग"],
        "chemical peel": ["केमिकल पील"],
        "thread lift": ["थ्रेड लिफ्ट"],
        "local anesthetic": ["स्थानीय एनेस्थेटिक"],
        "lidocaine": ["लिडोकेन"],
        "epinephrine": ["एपिनेफ्रिन", "एड्रेनालिन"],
        "bruise": ["चोट", "नील"],
        "infection": ["संक्रमण"],
    },

    "ru": {
        "botulinum toxin": ["ботулотоксин", "ботокс"],
        "dermal filler": ["дермальный филлер", "филлер"],
        "hyaluronic acid": ["гиалуроновая кислота"],
        "vascular occlusion": ["сосудистая окклюзия"],
        "necrosis": ["некроз"],
        "laser resurfacing": ["лазерная шлифовка"],
        "chemical peel": ["химический пилинг"],
        "thread lift": ["нитевой лифтинг"],
        "local anesthetic": ["местный анестетик"],
        "lidocaine": ["лидокаин"],
        "epinephrine": ["эпинефрин", "адреналин"],
        "bruise": ["синяк", "гематома"],
        "infection": ["инфекция"],
    },
}


def expand_query_with_glossary(query: str, lang: str) -> str:
    """
    Enriches query with canonical English terms for better retrieval.
    """
    if lang not in AESTHETIC_GLOSSARIES:
        return query

    additions = []
    q_lower = query.lower()

    for canonical, variants in AESTHETIC_GLOSSARIES[lang].items():
        for v in variants:
            if v.lower() in q_lower:
                additions.append(canonical)
                break

    if not additions:
        return query

    return f"{query} ({', '.join(additions)})"
