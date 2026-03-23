# aestheticite_refusals_i18n.py
"""
Internationalized refusal templates for AesthetiCite.
Used when the system cannot provide a reliable answer.
"""

from typing import Dict

REFUSAL_TEMPLATES: Dict[str, Dict[str, str]] = {

    "en": {
        "INSUFFICIENT_EVIDENCE":
            "There is currently insufficient high-quality medical evidence to answer this question reliably.",
        "CONFLICTING_EVIDENCE":
            "Available medical evidence is conflicting or inconsistent, so a reliable conclusion cannot be provided.",
        "OUT_OF_SCOPE":
            "This request falls outside evidence-based aesthetic medical practice."
    },

    "fr": {
        "INSUFFICIENT_EVIDENCE":
            "Les données scientifiques disponibles sont insuffisantes pour répondre de manière fiable à cette question.",
        "CONFLICTING_EVIDENCE":
            "Les données scientifiques disponibles sont contradictoires, ce qui ne permet pas de conclure de façon fiable.",
        "OUT_OF_SCOPE":
            "Cette demande ne relève pas d'une pratique médicale esthétique fondée sur des preuves."
    },

    "ar": {
        "INSUFFICIENT_EVIDENCE":
            "لا تتوفر حاليًا أدلة علمية طبية كافية للإجابة على هذا السؤال بشكل موثوق.",
        "CONFLICTING_EVIDENCE":
            "الأدلة الطبية المتاحة متضاربة، ولا تسمح باستخلاص استنتاج موثوق.",
        "OUT_OF_SCOPE":
            "هذا الطلب خارج نطاق الممارسة الطبية التجميلية المبنية على الأدلة."
    },

    "es": {
        "INSUFFICIENT_EVIDENCE":
            "Actualmente no existe evidencia médica de alta calidad suficiente para responder esta pregunta de manera confiable.",
        "CONFLICTING_EVIDENCE":
            "La evidencia médica disponible es contradictoria o inconsistente, por lo que no se puede proporcionar una conclusión confiable.",
        "OUT_OF_SCOPE":
            "Esta solicitud está fuera del ámbito de la práctica médica estética basada en evidencia."
    },

    "de": {
        "INSUFFICIENT_EVIDENCE":
            "Derzeit gibt es keine ausreichende hochwertige medizinische Evidenz, um diese Frage zuverlässig zu beantworten.",
        "CONFLICTING_EVIDENCE":
            "Die verfügbare medizinische Evidenz ist widersprüchlich oder inkonsistent, sodass keine zuverlässige Schlussfolgerung gezogen werden kann.",
        "OUT_OF_SCOPE":
            "Diese Anfrage liegt außerhalb der evidenzbasierten ästhetischen Medizin."
    },

    "pt": {
        "INSUFFICIENT_EVIDENCE":
            "Atualmente não há evidências médicas de alta qualidade suficientes para responder a esta pergunta de forma confiável.",
        "CONFLICTING_EVIDENCE":
            "As evidências médicas disponíveis são conflitantes ou inconsistentes, portanto não é possível fornecer uma conclusão confiável.",
        "OUT_OF_SCOPE":
            "Esta solicitação está fora do escopo da prática médica estética baseada em evidências."
    },

    "it": {
        "INSUFFICIENT_EVIDENCE":
            "Attualmente non esistono prove mediche di alta qualità sufficienti per rispondere a questa domanda in modo affidabile.",
        "CONFLICTING_EVIDENCE":
            "Le prove mediche disponibili sono contrastanti o incoerenti, quindi non è possibile fornire una conclusione affidabile.",
        "OUT_OF_SCOPE":
            "Questa richiesta non rientra nella pratica medica estetica basata sull'evidenza."
    },

    "zh": {
        "INSUFFICIENT_EVIDENCE":
            "目前没有足够的高质量医学证据来可靠地回答这个问题。",
        "CONFLICTING_EVIDENCE":
            "现有的医学证据相互矛盾或不一致，因此无法提供可靠的结论。",
        "OUT_OF_SCOPE":
            "此请求超出了循证美容医学实践的范围。"
    },

    "ja": {
        "INSUFFICIENT_EVIDENCE":
            "この質問に確実に回答するための十分な質の高い医学的証拠が現在ありません。",
        "CONFLICTING_EVIDENCE":
            "利用可能な医学的証拠は矛盾しているか一貫性がないため、信頼できる結論を提供することができません。",
        "OUT_OF_SCOPE":
            "このリクエストはエビデンスに基づく美容医療の範囲外です。"
    },

    "ko": {
        "INSUFFICIENT_EVIDENCE":
            "현재 이 질문에 신뢰성 있게 답변할 수 있는 충분한 고품질 의학적 증거가 없습니다.",
        "CONFLICTING_EVIDENCE":
            "사용 가능한 의학적 증거가 상충되거나 일관성이 없어 신뢰할 수 있는 결론을 제공할 수 없습니다.",
        "OUT_OF_SCOPE":
            "이 요청은 근거 기반 미용 의학 분야의 범위를 벗어납니다."
    },

    "hi": {
        "INSUFFICIENT_EVIDENCE":
            "वर्तमान में इस प्रश्न का विश्वसनीय उत्तर देने के लिए पर्याप्त उच्च-गुणवत्ता वाले चिकित्सा साक्ष्य उपलब्ध नहीं हैं।",
        "CONFLICTING_EVIDENCE":
            "उपलब्ध चिकित्सा साक्ष्य परस्पर विरोधी या असंगत हैं, इसलिए विश्वसनीय निष्कर्ष प्रदान नहीं किया जा सकता।",
        "OUT_OF_SCOPE":
            "यह अनुरोध साक्ष्य-आधारित सौंदर्य चिकित्सा अभ्यास के दायरे से बाहर है।"
    },

    "ru": {
        "INSUFFICIENT_EVIDENCE":
            "В настоящее время недостаточно высококачественных медицинских данных для надежного ответа на этот вопрос.",
        "CONFLICTING_EVIDENCE":
            "Имеющиеся медицинские данные противоречивы или непоследовательны, поэтому надежный вывод не может быть сделан.",
        "OUT_OF_SCOPE":
            "Этот запрос выходит за рамки доказательной эстетической медицины."
    },

    "tr": {
        "INSUFFICIENT_EVIDENCE":
            "Şu anda bu soruyu güvenilir bir şekilde yanıtlamak için yeterli yüksek kaliteli tıbbi kanıt bulunmamaktadır.",
        "CONFLICTING_EVIDENCE":
            "Mevcut tıbbi kanıtlar çelişkili veya tutarsızdır, bu nedenle güvenilir bir sonuç sağlanamaz.",
        "OUT_OF_SCOPE":
            "Bu talep kanıta dayalı estetik tıp uygulamasının kapsamı dışındadır."
    },

    "vi": {
        "INSUFFICIENT_EVIDENCE":
            "Hiện tại không có đủ bằng chứng y khoa chất lượng cao để trả lời câu hỏi này một cách đáng tin cậy.",
        "CONFLICTING_EVIDENCE":
            "Bằng chứng y khoa hiện có mâu thuẫn hoặc không nhất quán, do đó không thể đưa ra kết luận đáng tin cậy.",
        "OUT_OF_SCOPE":
            "Yêu cầu này nằm ngoài phạm vi thực hành y học thẩm mỹ dựa trên bằng chứng."
    },

    "th": {
        "INSUFFICIENT_EVIDENCE":
            "ปัจจุบันยังไม่มีหลักฐานทางการแพทย์คุณภาพสูงเพียงพอที่จะตอบคำถามนี้ได้อย่างน่าเชื่อถือ",
        "CONFLICTING_EVIDENCE":
            "หลักฐานทางการแพทย์ที่มีอยู่ขัดแย้งหรือไม่สอดคล้องกัน จึงไม่สามารถให้ข้อสรุปที่น่าเชื่อถือได้",
        "OUT_OF_SCOPE":
            "คำขอนี้อยู่นอกขอบเขตของการปฏิบัติทางการแพทย์เสริมความงามตามหลักฐาน"
    },

    "fa": {
        "INSUFFICIENT_EVIDENCE":
            "در حال حاضر شواهد پزشکی با کیفیت بالای کافی برای پاسخ قابل اعتماد به این سوال وجود ندارد.",
        "CONFLICTING_EVIDENCE":
            "شواهد پزشکی موجود متناقض یا ناسازگار است، بنابراین نمی‌توان نتیجه‌گیری قابل اعتمادی ارائه داد.",
        "OUT_OF_SCOPE":
            "این درخواست خارج از محدوده طب زیبایی مبتنی بر شواهد است."
    },

    "ur": {
        "INSUFFICIENT_EVIDENCE":
            "اس وقت اس سوال کا قابل اعتماد جواب دینے کے لیے کافی اعلیٰ معیار کے طبی شواہد موجود نہیں ہیں۔",
        "CONFLICTING_EVIDENCE":
            "دستیاب طبی شواہد متضاد یا متضاد ہیں، اس لیے قابل اعتماد نتیجہ فراہم نہیں کیا جا سکتا۔",
        "OUT_OF_SCOPE":
            "یہ درخواست ثبوت پر مبنی جمالیاتی طبی عمل کے دائرے سے باہر ہے۔"
    },

    "bn": {
        "INSUFFICIENT_EVIDENCE":
            "এই প্রশ্নের নির্ভরযোগ্য উত্তর দেওয়ার জন্য বর্তমানে পর্যাপ্ত উচ্চ-মানের চিকিৎসা প্রমাণ নেই।",
        "CONFLICTING_EVIDENCE":
            "উপলব্ধ চিকিৎসা প্রমাণ পরস্পরবিরোধী বা অসঙ্গত, তাই নির্ভরযোগ্য সিদ্ধান্ত প্রদান করা সম্ভব নয়।",
        "OUT_OF_SCOPE":
            "এই অনুরোধ প্রমাণ-ভিত্তিক নান্দনিক চিকিৎসা অনুশীলনের সুযোগের বাইরে।"
    },

    "id": {
        "INSUFFICIENT_EVIDENCE":
            "Saat ini tidak ada cukup bukti medis berkualitas tinggi untuk menjawab pertanyaan ini secara andal.",
        "CONFLICTING_EVIDENCE":
            "Bukti medis yang tersedia saling bertentangan atau tidak konsisten, sehingga kesimpulan yang andal tidak dapat diberikan.",
        "OUT_OF_SCOPE":
            "Permintaan ini berada di luar cakupan praktik kedokteran estetika berbasis bukti."
    },

    "sw": {
        "INSUFFICIENT_EVIDENCE":
            "Kwa sasa hakuna ushahidi wa matibabu wa kiwango cha juu unaotosha kujibu swali hili kwa uhakika.",
        "CONFLICTING_EVIDENCE":
            "Ushahidi wa matibabu unaopatikana unapingana au hauendani, kwa hivyo hitimisho la kuaminika haliwezi kutolewa.",
        "OUT_OF_SCOPE":
            "Ombi hili liko nje ya upeo wa mazoezi ya dawa za urembo yanayotegemea ushahidi."
    },

    "ha": {
        "INSUFFICIENT_EVIDENCE":
            "A halin yanzu babu isasshen shaidar likitanci mai inganci don amsa wannan tambayar ta hanyar amincewa.",
        "CONFLICTING_EVIDENCE":
            "Shaidar likitanci da ake da ita ta sabawa ko rashin daidaituwa, don haka ba za a iya ba da cikakkiyar ƙarshe ba.",
        "OUT_OF_SCOPE":
            "Wannan bukata tana waje da iyakokin aikin likitancin kyautata jiki na shaida."
    },

    "pa": {
        "INSUFFICIENT_EVIDENCE":
            "ਇਸ ਸਮੇਂ ਇਸ ਸਵਾਲ ਦਾ ਭਰੋਸੇਯੋਗ ਜਵਾਬ ਦੇਣ ਲਈ ਕਾਫ਼ੀ ਉੱਚ-ਗੁਣਵੱਤਾ ਵਾਲੇ ਡਾਕਟਰੀ ਸਬੂਤ ਉਪਲਬਧ ਨਹੀਂ ਹਨ।",
        "CONFLICTING_EVIDENCE":
            "ਉਪਲਬਧ ਡਾਕਟਰੀ ਸਬੂਤ ਵਿਰੋਧੀ ਜਾਂ ਅਸੰਗਤ ਹਨ, ਇਸ ਲਈ ਭਰੋਸੇਯੋਗ ਸਿੱਟਾ ਪ੍ਰਦਾਨ ਨਹੀਂ ਕੀਤਾ ਜਾ ਸਕਦਾ।",
        "OUT_OF_SCOPE":
            "ਇਹ ਬੇਨਤੀ ਸਬੂਤ-ਅਧਾਰਿਤ ਸੁੰਦਰਤਾ ਡਾਕਟਰੀ ਅਭਿਆਸ ਦੇ ਦਾਇਰੇ ਤੋਂ ਬਾਹਰ ਹੈ।"
    },

    "te": {
        "INSUFFICIENT_EVIDENCE":
            "ఈ ప్రశ్నకు నమ్మదగిన సమాధానం ఇవ్వడానికి ప్రస్తుతం తగినంత అధిక-నాణ్యత వైద్య సాక్ష్యం లేదు.",
        "CONFLICTING_EVIDENCE":
            "అందుబాటులో ఉన్న వైద్య సాక్ష్యం వైరుధ్యంగా లేదా అసంగతంగా ఉంది, కాబట్టి నమ్మదగిన నిర్ణయం అందించలేము.",
        "OUT_OF_SCOPE":
            "ఈ అభ్యర్థన సాక్ష్య-ఆధారిత సౌందర్య వైద్య అభ్యాసం పరిధిలో లేదు."
    },

    "mr": {
        "INSUFFICIENT_EVIDENCE":
            "सध्या या प्रश्नाचे विश्वासार्ह उत्तर देण्यासाठी पुरेसा उच्च-गुणवत्तेचा वैद्यकीय पुरावा उपलब्ध नाही.",
        "CONFLICTING_EVIDENCE":
            "उपलब्ध वैद्यकीय पुरावा विरोधाभासी किंवा असंगत आहे, त्यामुळे विश्वासार्ह निष्कर्ष प्रदान करता येत नाही.",
        "OUT_OF_SCOPE":
            "ही विनंती पुरावा-आधारित सौंदर्य वैद्यकीय सरावाच्या व्याप्तीच्या बाहेर आहे."
    },

    "ta": {
        "INSUFFICIENT_EVIDENCE":
            "இந்தக் கேள்விக்கு நம்பகமான பதில் அளிக்க தற்போது போதுமான உயர்தர மருத்துவ ஆதாரம் இல்லை.",
        "CONFLICTING_EVIDENCE":
            "கிடைக்கக்கூடிய மருத்துவ ஆதாரம் முரண்பாடாக அல்லது சீரற்றதாக உள்ளது, எனவே நம்பகமான முடிவை வழங்க இயலாது.",
        "OUT_OF_SCOPE":
            "இந்த கோரிக்கை ஆதார அடிப்படையிலான அழகியல் மருத்துவ நடைமுறையின் எல்லைக்கு அப்பாற்பட்டது."
    },
}


def render_refusal(reason_code: str, lang: str) -> str:
    """
    Render a refusal message in the specified language.
    Falls back to English if the language or reason code is not found.
    """
    lang_templates = REFUSAL_TEMPLATES.get(lang, REFUSAL_TEMPLATES["en"])
    return lang_templates.get(
        reason_code,
        REFUSAL_TEMPLATES["en"]["INSUFFICIENT_EVIDENCE"]
    )


def get_refusal_codes() -> list[str]:
    """Return all available refusal reason codes."""
    return list(REFUSAL_TEMPLATES["en"].keys())
