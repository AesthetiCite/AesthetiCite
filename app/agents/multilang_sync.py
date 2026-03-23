"""
AesthetiCite Multilingual Publication Sync - MAXIMUM COVERAGE

Downloads medical publications in ALL 25 supported languages across ALL fields of medicine.
Configured for maximum publication download starting from January 30, 2026.

Supported Languages:
- Latin Script: English, French, Spanish, German, Italian, Portuguese, Turkish, Indonesian, Swahili, Vietnamese, Hausa
- Asian: Chinese, Japanese, Korean, Thai, Hindi, Bengali, Tamil, Telugu, Marathi, Punjabi
- Arabic Script: Arabic, Urdu, Persian
- Cyrillic: Russian

Medical Fields Covered:
- Aesthetic Medicine, Dermatology
- Dental Medicine, Oral Surgery
- Cardiology, Cardiovascular Surgery
- Oncology, Hematology
- Endocrinology, Diabetology
- Psychiatry, Neurology, Psychology
- Orthopedics, Rheumatology
- Pulmonology, Respiratory Medicine
- Gastroenterology, Hepatology
- Nephrology, Urology
- Obstetrics, Gynecology
- Pediatrics, Neonatology
- Emergency Medicine, Critical Care
- Infectious Disease, Immunology
- Ophthalmology, Otolaryngology
- General Surgery, Trauma Surgery
- Radiology, Nuclear Medicine
- Anesthesiology, Pain Medicine
- Geriatrics, Palliative Care
- Sports Medicine, Rehabilitation
- Preventive Medicine, Public Health

Uses PubMed Central's multilingual indexing and language filters.
Schedule: Daily at 02:00 UTC starting January 30, 2026.
"""

import os
import sys
import time
import logging
import requests
import defusedxml.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.db.session import SessionLocal, engine
from app.rag.embedder import embed_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

LANGUAGE_CODES = {
    # Latin Script Languages
    "en": "english",
    "fr": "french",
    "es": "spanish",
    "de": "german",
    "it": "italian",
    "pt": "portuguese",
    "tr": "turkish",
    "id": "indonesian",
    "sw": "swahili",
    "vi": "vietnamese",
    "ha": "hausa",
    # Asian Languages
    "zh": "chinese",
    "ja": "japanese",
    "ko": "korean",
    "th": "thai",
    "hi": "hindi",
    "bn": "bengali",
    "ta": "tamil",
    "te": "telugu",
    "mr": "marathi",
    "pa": "punjabi",
    # Arabic Script Languages
    "ar": "arabic",
    "ur": "urdu",
    "fa": "persian",
    # Cyrillic Languages
    "ru": "russian",
}

COMPREHENSIVE_MEDICAL_QUERIES_EN = [
    # Aesthetic Medicine & Dermatology
    "aesthetic medicine", "dermal filler complication", "botulinum toxin aesthetic",
    "facial rejuvenation", "laser skin treatment", "chemical peel dermatology",
    "acne treatment", "eczema management", "skin cancer melanoma",
    "hair transplant", "liposuction complications", "rhinoplasty outcomes",
    
    # Dental Medicine
    "dental implant", "periodontal disease treatment", "orthodontic treatment",
    "oral surgery", "root canal treatment", "dental caries prevention",
    "temporomandibular joint disorder", "wisdom tooth extraction",
    
    # Cardiology & Cardiovascular
    "heart failure therapy", "hypertension treatment", "stroke prevention",
    "atrial fibrillation", "coronary artery disease", "myocardial infarction",
    "cardiac arrhythmia", "heart valve disease", "peripheral artery disease",
    "cardiac rehabilitation", "lipid management statin",
    
    # Oncology & Hematology
    "cancer immunotherapy", "breast cancer treatment", "lung cancer therapy",
    "colorectal cancer screening", "prostate cancer", "leukemia treatment",
    "lymphoma therapy", "chemotherapy side effects", "radiation oncology",
    "palliative care cancer", "tumor marker", "targeted cancer therapy",
    
    # Endocrinology & Metabolism
    "diabetes management", "thyroid disorder", "obesity treatment",
    "metabolic syndrome", "adrenal insufficiency", "growth hormone deficiency",
    "polycystic ovary syndrome", "osteoporosis treatment",
    
    # Psychiatry & Mental Health
    "depression antidepressant", "anxiety disorder treatment", "schizophrenia therapy",
    "bipolar disorder", "PTSD treatment", "ADHD management",
    "substance abuse treatment", "eating disorder", "insomnia therapy",
    
    # Neurology
    "multiple sclerosis treatment", "Parkinson disease", "Alzheimer dementia",
    "epilepsy seizure", "migraine headache", "stroke rehabilitation",
    "neuropathic pain", "amyotrophic lateral sclerosis",
    
    # Orthopedics & Rheumatology
    "rheumatoid arthritis biologic", "osteoarthritis treatment", "joint replacement",
    "fracture management", "spine surgery", "sports injury",
    "fibromyalgia", "gout treatment", "lupus erythematosus",
    
    # Pulmonology & Respiratory
    "asthma treatment", "COPD management", "pulmonary fibrosis",
    "sleep apnea", "pneumonia treatment", "tuberculosis",
    "lung transplant", "cystic fibrosis",
    
    # Gastroenterology & Hepatology
    "inflammatory bowel disease", "Crohn disease", "ulcerative colitis",
    "gastroesophageal reflux", "liver cirrhosis", "hepatitis treatment",
    "pancreatitis", "colorectal screening", "celiac disease",
    
    # Nephrology & Urology
    "chronic kidney disease", "dialysis treatment", "kidney transplant",
    "urinary tract infection", "prostate hyperplasia", "kidney stone",
    "bladder cancer", "erectile dysfunction",
    
    # Obstetrics & Gynecology
    "pregnancy complications", "cesarean section", "preeclampsia",
    "infertility treatment", "menopause management", "endometriosis",
    "cervical cancer screening", "contraception", "gestational diabetes",
    
    # Pediatrics & Neonatology
    "pediatric vaccination", "neonatal intensive care", "childhood obesity",
    "pediatric asthma", "developmental delay", "autism spectrum",
    "pediatric infectious disease", "premature infant care",
    
    # Emergency & Critical Care
    "sepsis treatment", "trauma management", "cardiac arrest resuscitation",
    "acute respiratory distress", "shock management", "burn treatment",
    "poisoning antidote", "intensive care sedation",
    
    # Infectious Disease & Immunology
    "COVID-19 treatment", "antibiotic resistance", "HIV AIDS treatment",
    "vaccination immunization", "autoimmune disease", "allergy treatment",
    "malaria treatment", "influenza therapy",
    
    # Ophthalmology & ENT
    "cataract surgery", "glaucoma treatment", "macular degeneration",
    "hearing loss", "tinnitus treatment", "sinusitis",
    "tonsillectomy", "cochlear implant",
    
    # Surgery & Anesthesiology
    "minimally invasive surgery", "anesthesia complications", "postoperative pain",
    "surgical site infection", "bariatric surgery", "transplant surgery",
    "regional anesthesia", "enhanced recovery surgery",
    
    # Geriatrics & Rehabilitation
    "elderly care frailty", "fall prevention elderly", "rehabilitation therapy",
    "physical therapy outcomes", "occupational therapy",
    "palliative care end of life",
    
    # Preventive Medicine & Public Health
    "preventive screening", "health promotion", "epidemiology outbreak",
    "vaccination program", "lifestyle intervention", "tobacco cessation",
]

MULTILINGUAL_QUERIES = {
    "en": COMPREHENSIVE_MEDICAL_QUERIES_EN,
    "fr": [
        # All medical fields in French
        "médecine esthétique", "complication injection acide hyaluronique", "toxine botulique",
        "rajeunissement facial", "traitement laser peau", "peeling chimique",
        "implant dentaire", "maladie parodontale", "traitement orthodontique",
        "chirurgie buccale", "traitement canal radiculaire",
        "insuffisance cardiaque", "traitement hypertension", "prévention AVC",
        "fibrillation auriculaire", "maladie coronarienne", "infarctus myocarde",
        "immunothérapie cancer", "cancer du sein", "cancer du poumon",
        "cancer colorectal", "leucémie", "lymphome", "chimiothérapie",
        "gestion diabète", "trouble thyroïdien", "traitement obésité",
        "syndrome métabolique", "ostéoporose",
        "dépression antidépresseur", "trouble anxieux", "schizophrénie",
        "trouble bipolaire", "TDAH", "insomnie",
        "sclérose en plaques", "maladie de Parkinson", "démence Alzheimer",
        "épilepsie", "migraine", "douleur neuropathique",
        "polyarthrite rhumatoïde", "arthrose", "prothèse articulaire",
        "fibromyalgie", "goutte", "lupus",
        "traitement asthme", "BPCO", "fibrose pulmonaire", "apnée du sommeil",
        "maladie de Crohn", "colite ulcéreuse", "reflux gastro-œsophagien",
        "cirrhose hépatique", "hépatite", "pancréatite",
        "maladie rénale chronique", "dialyse", "greffe de rein",
        "infection urinaire", "hypertrophie prostate",
        "complications grossesse", "césarienne", "prééclampsie",
        "traitement infertilité", "ménopause", "endométriose",
        "vaccination pédiatrique", "soins intensifs néonatals", "obésité infantile",
        "septicémie", "traumatisme", "arrêt cardiaque",
        "traitement COVID-19", "résistance antibiotiques", "traitement VIH",
        "maladie auto-immune", "traitement allergie",
        "chirurgie cataracte", "traitement glaucome", "perte auditive",
        "chirurgie mini-invasive", "complications anesthésie", "douleur postopératoire",
        "soins gériatriques", "prévention chutes", "rééducation",
        "médecine préventive", "promotion santé", "sevrage tabagique",
    ],
    "es": [
        # All medical fields in Spanish
        "medicina estética", "complicación relleno dérmico", "toxina botulínica",
        "rejuvenecimiento facial", "tratamiento láser piel", "peeling químico",
        "implante dental", "enfermedad periodontal", "tratamiento ortodoncia",
        "cirugía oral", "tratamiento conducto radicular",
        "insuficiencia cardíaca", "tratamiento hipertensión", "prevención ictus",
        "fibrilación auricular", "enfermedad coronaria", "infarto miocardio",
        "inmunoterapia cáncer", "cáncer de mama", "cáncer de pulmón",
        "cáncer colorrectal", "leucemia", "linfoma", "quimioterapia",
        "manejo diabetes", "trastorno tiroideo", "tratamiento obesidad",
        "síndrome metabólico", "osteoporosis",
        "depresión antidepresivo", "trastorno ansiedad", "esquizofrenia",
        "trastorno bipolar", "TDAH", "insomnio",
        "esclerosis múltiple", "enfermedad Parkinson", "demencia Alzheimer",
        "epilepsia", "migraña", "dolor neuropático",
        "artritis reumatoide", "artrosis", "reemplazo articular",
        "fibromialgia", "gota", "lupus",
        "tratamiento asma", "EPOC", "fibrosis pulmonar", "apnea del sueño",
        "enfermedad de Crohn", "colitis ulcerosa", "reflujo gastroesofágico",
        "cirrosis hepática", "hepatitis", "pancreatitis",
        "enfermedad renal crónica", "diálisis", "trasplante renal",
        "infección urinaria", "hiperplasia prostática",
        "complicaciones embarazo", "cesárea", "preeclampsia",
        "tratamiento infertilidad", "menopausia", "endometriosis",
        "vacunación pediátrica", "cuidados intensivos neonatales", "obesidad infantil",
        "sepsis", "traumatismo", "paro cardíaco",
        "tratamiento COVID-19", "resistencia antibióticos", "tratamiento VIH",
        "enfermedad autoinmune", "tratamiento alergia",
        "cirugía cataratas", "tratamiento glaucoma", "pérdida auditiva",
        "cirugía mínimamente invasiva", "complicaciones anestesia", "dolor postoperatorio",
        "cuidados geriátricos", "prevención caídas", "rehabilitación",
        "medicina preventiva", "promoción salud", "cesación tabaco",
    ],
    "de": [
        # All medical fields in German
        "ästhetische Medizin", "Dermalfiller Komplikation", "Botulinumtoxin",
        "Gesichtsverjüngung", "Laser Hautbehandlung", "chemisches Peeling",
        "Zahnimplantat", "Parodontalerkrankung", "kieferorthopädische Behandlung",
        "Oralchirurgie", "Wurzelkanalbehandlung",
        "Herzinsuffizienz", "Bluthochdruck Behandlung", "Schlaganfall Prävention",
        "Vorhofflimmern", "koronare Herzkrankheit", "Herzinfarkt",
        "Krebs Immuntherapie", "Brustkrebs", "Lungenkrebs",
        "Darmkrebs", "Leukämie", "Lymphom", "Chemotherapie",
        "Diabetes Management", "Schilddrüsenerkrankung", "Adipositas Behandlung",
        "metabolisches Syndrom", "Osteoporose",
        "Depression Antidepressivum", "Angststörung", "Schizophrenie",
        "bipolare Störung", "ADHS", "Schlaflosigkeit",
        "Multiple Sklerose", "Parkinson Krankheit", "Alzheimer Demenz",
        "Epilepsie", "Migräne", "neuropathischer Schmerz",
        "rheumatoide Arthritis", "Arthrose", "Gelenkersatz",
        "Fibromyalgie", "Gicht", "Lupus",
        "Asthma Behandlung", "COPD", "Lungenfibrose", "Schlafapnoe",
        "Morbus Crohn", "Colitis ulcerosa", "gastroösophagealer Reflux",
        "Leberzirrhose", "Hepatitis", "Pankreatitis",
        "chronische Nierenerkrankung", "Dialyse", "Nierentransplantation",
        "Harnwegsinfektion", "Prostatahyperplasie",
        "Schwangerschaftskomplikationen", "Kaiserschnitt", "Präeklampsie",
        "Unfruchtbarkeit Behandlung", "Menopause", "Endometriose",
        "Kinderimpfung", "neonatale Intensivpflege", "kindliche Adipositas",
        "Sepsis", "Trauma", "Herzstillstand",
        "COVID-19 Behandlung", "Antibiotikaresistenz", "HIV Behandlung",
        "Autoimmunerkrankung", "Allergie Behandlung",
        "Kataraktoperation", "Glaukom Behandlung", "Hörverlust",
        "minimal-invasive Chirurgie", "Anästhesie Komplikationen", "postoperativer Schmerz",
        "Altenpflege", "Sturzprävention", "Rehabilitation",
        "Präventivmedizin", "Gesundheitsförderung", "Raucherentwöhnung",
    ],
    "it": [
        # All medical fields in Italian
        "medicina estetica", "complicazione filler dermico", "tossina botulinica",
        "ringiovanimento facciale", "trattamento laser pelle", "peeling chimico",
        "impianto dentale", "malattia parodontale", "trattamento ortodontico",
        "chirurgia orale", "trattamento canalare",
        "insufficienza cardiaca", "trattamento ipertensione", "prevenzione ictus",
        "fibrillazione atriale", "malattia coronarica", "infarto miocardico",
        "immunoterapia cancro", "cancro al seno", "cancro ai polmoni",
        "cancro colorettale", "leucemia", "linfoma", "chemioterapia",
        "gestione diabete", "disturbo tiroideo", "trattamento obesità",
        "sindrome metabolica", "osteoporosi",
        "depressione antidepressivo", "disturbo d'ansia", "schizofrenia",
        "disturbo bipolare", "ADHD", "insonnia",
        "sclerosi multipla", "malattia di Parkinson", "demenza Alzheimer",
        "epilessia", "emicrania", "dolore neuropatico",
        "artrite reumatoide", "artrosi", "sostituzione articolare",
        "fibromialgia", "gotta", "lupus",
        "trattamento asma", "BPCO", "fibrosi polmonare", "apnea del sonno",
        "malattia di Crohn", "colite ulcerosa", "reflusso gastroesofageo",
        "cirrosi epatica", "epatite", "pancreatite",
        "malattia renale cronica", "dialisi", "trapianto renale",
        "infezione urinaria", "ipertrofia prostatica",
        "complicazioni gravidanza", "taglio cesareo", "preeclampsia",
        "trattamento infertilità", "menopausa", "endometriosi",
        "vaccinazione pediatrica", "terapia intensiva neonatale", "obesità infantile",
        "sepsi", "trauma", "arresto cardiaco",
        "trattamento COVID-19", "resistenza antibiotici", "trattamento HIV",
        "malattia autoimmune", "trattamento allergia",
        "chirurgia cataratta", "trattamento glaucoma", "perdita uditiva",
        "chirurgia mini-invasiva", "complicazioni anestesia", "dolore postoperatorio",
        "assistenza geriatrica", "prevenzione cadute", "riabilitazione",
        "medicina preventiva", "promozione salute", "cessazione fumo",
    ],
    "pt": [
        # All medical fields in Portuguese
        "medicina estética", "complicação preenchedor dérmico", "toxina botulínica",
        "rejuvenescimento facial", "tratamento laser pele", "peeling químico",
        "implante dentário", "doença periodontal", "tratamento ortodôntico",
        "cirurgia oral", "tratamento canal radicular",
        "insuficiência cardíaca", "tratamento hipertensão", "prevenção AVC",
        "fibrilação atrial", "doença coronária", "infarto miocárdio",
        "imunoterapia câncer", "câncer de mama", "câncer de pulmão",
        "câncer colorretal", "leucemia", "linfoma", "quimioterapia",
        "gestão diabetes", "distúrbio tireoide", "tratamento obesidade",
        "síndrome metabólica", "osteoporose",
        "depressão antidepressivo", "transtorno ansiedade", "esquizofrenia",
        "transtorno bipolar", "TDAH", "insônia",
        "esclerose múltipla", "doença Parkinson", "demência Alzheimer",
        "epilepsia", "enxaqueca", "dor neuropática",
        "artrite reumatoide", "osteoartrite", "substituição articular",
        "fibromialgia", "gota", "lúpus",
        "tratamento asma", "DPOC", "fibrose pulmonar", "apneia do sono",
        "doença de Crohn", "colite ulcerativa", "refluxo gastroesofágico",
        "cirrose hepática", "hepatite", "pancreatite",
        "doença renal crônica", "diálise", "transplante renal",
        "infecção urinária", "hiperplasia prostática",
        "complicações gravidez", "cesárea", "pré-eclâmpsia",
        "tratamento infertilidade", "menopausa", "endometriose",
        "vacinação pediátrica", "terapia intensiva neonatal", "obesidade infantil",
        "sepse", "trauma", "parada cardíaca",
        "tratamento COVID-19", "resistência antibióticos", "tratamento HIV",
        "doença autoimune", "tratamento alergia",
        "cirurgia catarata", "tratamento glaucoma", "perda auditiva",
        "cirurgia minimamente invasiva", "complicações anestesia", "dor pós-operatória",
        "cuidados geriátricos", "prevenção quedas", "reabilitação",
        "medicina preventiva", "promoção saúde", "cessação tabagismo",
    ],
    "ar": [
        # All medical fields in Arabic
        "الطب التجميلي", "حقن البوتوكس", "تجديد الوجه", "علاج الليزر للبشرة",
        "زراعة الأسنان", "أمراض اللثة", "تقويم الأسنان", "جراحة الفم",
        "قصور القلب", "علاج ارتفاع ضغط الدم", "الوقاية من السكتة الدماغية",
        "الرجفان الأذيني", "مرض الشريان التاجي", "احتشاء عضلة القلب",
        "العلاج المناعي للسرطان", "سرطان الثدي", "سرطان الرئة",
        "سرطان القولون", "سرطان الدم", "الليمفوما", "العلاج الكيميائي",
        "إدارة مرض السكري", "اضطرابات الغدة الدرقية", "علاج السمنة",
        "متلازمة الأيض", "هشاشة العظام",
        "الاكتئاب ومضادات الاكتئاب", "اضطرابات القلق", "الفصام",
        "الاضطراب ثنائي القطب", "اضطراب فرط الحركة", "الأرق",
        "التصلب المتعدد", "مرض باركنسون", "الخرف الزهايمر",
        "الصرع", "الصداع النصفي", "الألم العصبي",
        "التهاب المفاصل الروماتويدي", "التهاب المفاصل", "استبدال المفاصل",
        "الألم العضلي الليفي", "النقرس", "الذئبة",
        "علاج الربو", "مرض الانسداد الرئوي المزمن", "تليف الرئة", "انقطاع النفس أثناء النوم",
        "مرض كرون", "التهاب القولون التقرحي", "الارتجاع المعدي المريئي",
        "تليف الكبد", "التهاب الكبد", "التهاب البنكرياس",
        "مرض الكلى المزمن", "غسيل الكلى", "زراعة الكلى",
        "عدوى المسالك البولية", "تضخم البروستاتا",
        "مضاعفات الحمل", "الولادة القيصرية", "تسمم الحمل",
        "علاج العقم", "سن اليأس", "بطانة الرحم المهاجرة",
        "تطعيم الأطفال", "العناية المركزة لحديثي الولادة", "سمنة الأطفال",
        "تسمم الدم", "الإصابات", "توقف القلب",
        "علاج كوفيد-19", "مقاومة المضادات الحيوية", "علاج فيروس نقص المناعة",
        "أمراض المناعة الذاتية", "علاج الحساسية",
        "جراحة المياه البيضاء", "علاج الجلوكوما", "فقدان السمع",
        "الجراحة طفيفة التوغل", "مضاعفات التخدير", "ألم ما بعد الجراحة",
        "رعاية المسنين", "الوقاية من السقوط", "إعادة التأهيل",
        "الطب الوقائي", "تعزيز الصحة", "الإقلاع عن التدخين",
    ],
    "tr": [
        # Turkish - All medical fields
        "estetik tıp", "dolgu komplikasyonu", "botulinum toksini",
        "diş implantı", "periodontal hastalık", "ortodonti",
        "kalp yetmezliği", "hipertansiyon tedavisi", "inme önleme",
        "kanser immünoterapi", "meme kanseri", "akciğer kanseri",
        "diyabet yönetimi", "tiroid bozukluğu", "obezite tedavisi",
        "depresyon antidepresan", "anksiyete bozukluğu", "şizofreni",
        "multipl skleroz", "Parkinson hastalığı", "Alzheimer demans",
        "romatoid artrit", "osteoartrit", "eklem değişimi",
        "astım tedavisi", "KOAH", "uyku apnesi",
        "Crohn hastalığı", "ülseratif kolit", "hepatit",
        "kronik böbrek hastalığı", "diyaliz", "böbrek nakli",
        "gebelik komplikasyonları", "sezaryen", "preeklampsi",
        "pediatrik aşılama", "neonatal yoğun bakım",
        "sepsis", "travma", "kardiyak arrest",
        "COVID-19 tedavisi", "antibiyotik direnci", "HIV tedavisi",
        "katarakt ameliyatı", "glokom tedavisi", "işitme kaybı",
        "minimal invaziv cerrahi", "anestezi komplikasyonları",
        "geriatrik bakım", "rehabilitasyon", "koruyucu tıp",
    ],
    "zh": [
        # Chinese - All medical fields
        "医学美容", "肉毒杆菌", "面部年轻化", "激光皮肤治疗",
        "牙科植入物", "牙周病", "正畸治疗", "口腔外科",
        "心力衰竭", "高血压治疗", "中风预防",
        "心房颤动", "冠状动脉疾病", "心肌梗塞",
        "癌症免疫治疗", "乳腺癌", "肺癌",
        "结直肠癌", "白血病", "淋巴瘤", "化疗",
        "糖尿病管理", "甲状腺疾病", "肥胖治疗",
        "代谢综合征", "骨质疏松症",
        "抑郁症抗抑郁药", "焦虑症", "精神分裂症",
        "双相情感障碍", "多动症", "失眠",
        "多发性硬化症", "帕金森病", "阿尔茨海默氏痴呆",
        "癫痫", "偏头痛", "神经性疼痛",
        "类风湿关节炎", "骨关节炎", "关节置换",
        "纤维肌痛", "痛风", "狼疮",
        "哮喘治疗", "慢性阻塞性肺病", "肺纤维化", "睡眠呼吸暂停",
        "克罗恩病", "溃疡性结肠炎", "胃食管反流",
        "肝硬化", "肝炎", "胰腺炎",
        "慢性肾病", "透析", "肾移植",
        "尿路感染", "前列腺增生",
        "妊娠并发症", "剖宫产", "子痫前期",
        "不孕不育治疗", "更年期", "子宫内膜异位症",
        "儿童疫苗接种", "新生儿重症监护", "儿童肥胖",
        "脓毒症", "创伤", "心脏骤停",
        "新冠肺炎治疗", "抗生素耐药性", "艾滋病治疗",
        "自身免疫性疾病", "过敏治疗",
        "白内障手术", "青光眼治疗", "听力损失",
        "微创手术", "麻醉并发症", "术后疼痛",
        "老年护理", "跌倒预防", "康复治疗",
        "预防医学", "健康促进", "戒烟",
    ],
    "ja": [
        # Japanese - All medical fields
        "美容医学", "ボツリヌス毒素", "顔面若返り", "レーザー皮膚治療",
        "歯科インプラント", "歯周病", "矯正治療", "口腔外科",
        "心不全", "高血圧治療", "脳卒中予防",
        "心房細動", "冠動脈疾患", "心筋梗塞",
        "がん免疫療法", "乳がん", "肺がん",
        "大腸がん", "白血病", "リンパ腫", "化学療法",
        "糖尿病管理", "甲状腺疾患", "肥満治療",
        "メタボリック症候群", "骨粗鬆症",
        "うつ病抗うつ薬", "不安障害", "統合失調症",
        "双極性障害", "ADHD", "不眠症",
        "多発性硬化症", "パーキンソン病", "アルツハイマー型認知症",
        "てんかん", "片頭痛", "神経障害性疼痛",
        "関節リウマチ", "変形性関節症", "人工関節置換",
        "線維筋痛症", "痛風", "全身性エリテマトーデス",
        "喘息治療", "COPD", "肺線維症", "睡眠時無呼吸症候群",
        "クローン病", "潰瘍性大腸炎", "胃食道逆流症",
        "肝硬変", "肝炎", "膵炎",
        "慢性腎臓病", "透析", "腎移植",
        "尿路感染症", "前立腺肥大症",
        "妊娠合併症", "帝王切開", "子癇前症",
        "不妊治療", "更年期", "子宮内膜症",
        "小児予防接種", "新生児集中治療", "小児肥満",
        "敗血症", "外傷", "心停止",
        "COVID-19治療", "抗生物質耐性", "HIV治療",
        "自己免疫疾患", "アレルギー治療",
        "白内障手術", "緑内障治療", "難聴",
        "低侵襲手術", "麻酔合併症", "術後疼痛",
        "高齢者ケア", "転倒予防", "リハビリテーション",
        "予防医学", "健康増進", "禁煙",
    ],
    "ko": [
        # Korean - All medical fields
        "미용의학", "보툴리눔 독소", "안면 회춘", "레이저 피부 치료",
        "치과 임플란트", "치주 질환", "교정 치료", "구강 외과",
        "심부전", "고혈압 치료", "뇌졸중 예방",
        "심방세동", "관상동맥 질환", "심근경색",
        "암 면역요법", "유방암", "폐암",
        "대장암", "백혈병", "림프종", "화학요법",
        "당뇨병 관리", "갑상선 질환", "비만 치료",
        "대사 증후군", "골다공증",
        "우울증 항우울제", "불안 장애", "조현병",
        "양극성 장애", "ADHD", "불면증",
        "다발성 경화증", "파킨슨병", "알츠하이머 치매",
        "간질", "편두통", "신경병성 통증",
        "류마티스 관절염", "골관절염", "관절 치환술",
        "섬유근육통", "통풍", "루푸스",
        "천식 치료", "COPD", "폐섬유증", "수면 무호흡증",
        "크론병", "궤양성 대장염", "위식도 역류",
        "간경변", "간염", "췌장염",
        "만성 신장병", "투석", "신장 이식",
        "요로 감염", "전립선 비대증",
        "임신 합병증", "제왕절개", "자간전증",
        "불임 치료", "폐경", "자궁내막증",
        "소아 예방접종", "신생아 집중치료", "소아 비만",
        "패혈증", "외상", "심정지",
        "COVID-19 치료", "항생제 내성", "HIV 치료",
        "자가면역 질환", "알레르기 치료",
        "백내장 수술", "녹내장 치료", "청력 손실",
        "최소 침습 수술", "마취 합병증", "수술 후 통증",
        "노인 케어", "낙상 예방", "재활",
        "예방 의학", "건강 증진", "금연",
    ],
    "ru": [
        # Russian - All medical fields
        "эстетическая медицина", "ботулотоксин", "омоложение лица", "лазерное лечение кожи",
        "зубной имплантат", "пародонтоз", "ортодонтия", "челюстно-лицевая хирургия",
        "сердечная недостаточность", "лечение гипертонии", "профилактика инсульта",
        "фибрилляция предсердий", "ишемическая болезнь сердца", "инфаркт миокарда",
        "иммунотерапия рака", "рак молочной железы", "рак легких",
        "колоректальный рак", "лейкемия", "лимфома", "химиотерапия",
        "управление диабетом", "заболевания щитовидной железы", "лечение ожирения",
        "метаболический синдром", "остеопороз",
        "депрессия антидепрессант", "тревожное расстройство", "шизофрения",
        "биполярное расстройство", "СДВГ", "бессонница",
        "рассеянный склероз", "болезнь Паркинсона", "деменция Альцгеймера",
        "эпилепсия", "мигрень", "нейропатическая боль",
        "ревматоидный артрит", "остеоартрит", "эндопротезирование суставов",
        "фибромиалгия", "подагра", "волчанка",
        "лечение астмы", "ХОБЛ", "легочный фиброз", "апноэ во сне",
        "болезнь Крона", "язвенный колит", "гастроэзофагеальный рефлюкс",
        "цирроз печени", "гепатит", "панкреатит",
        "хроническая болезнь почек", "диализ", "трансплантация почки",
        "инфекция мочевыводящих путей", "гиперплазия предстательной железы",
        "осложнения беременности", "кесарево сечение", "преэклампсия",
        "лечение бесплодия", "менопауза", "эндометриоз",
        "детская вакцинация", "неонатальная интенсивная терапия", "детское ожирение",
        "сепсис", "травма", "остановка сердца",
        "лечение COVID-19", "устойчивость к антибиотикам", "лечение ВИЧ",
        "аутоиммунные заболевания", "лечение аллергии",
        "операция катаракты", "лечение глаукомы", "потеря слуха",
        "малоинвазивная хирургия", "осложнения анестезии", "послеоперационная боль",
        "гериатрическая помощь", "профилактика падений", "реабилитация",
        "профилактическая медицина", "укрепление здоровья", "отказ от курения",
    ],
    "hi": [
        # Hindi - Key medical terms
        "सौंदर्य चिकित्सा", "बोटॉक्स", "चेहरे का कायाकल्प",
        "दंत प्रत्यारोपण", "दंत चिकित्सा", "मौखिक सर्जरी",
        "हृदय विफलता", "उच्च रक्तचाप", "स्ट्रोक रोकथाम",
        "कैंसर इम्यूनोथेरेपी", "स्तन कैंसर", "फेफड़ों का कैंसर",
        "मधुमेह प्रबंधन", "थायरॉइड विकार", "मोटापा उपचार",
        "अवसाद उपचार", "चिंता विकार", "सिज़ोफ्रेनिया",
        "मल्टीपल स्क्लेरोसिस", "पार्किंसंस रोग", "अल्जाइमर",
        "गठिया", "ऑस्टियोआर्थराइटिस", "जोड़ प्रतिस्थापन",
        "अस्थमा उपचार", "सीओपीडी", "स्लीप एपनिया",
        "क्रोहन रोग", "यकृत सिरोसिस", "हेपेटाइटिस",
        "गुर्दे की बीमारी", "डायलिसिस", "गुर्दा प्रत्यारोपण",
        "गर्भावस्था जटिलताएं", "सिजेरियन", "बांझपन उपचार",
        "बाल टीकाकरण", "नवजात गहन देखभाल",
        "सेप्सिस", "आघात", "कार्डियक अरेस्ट",
        "कोविड-19 उपचार", "एंटीबायोटिक प्रतिरोध", "एचआईवी उपचार",
        "ऑटोइम्यून रोग", "एलर्जी उपचार",
        "मोतियाबिंद सर्जरी", "ग्लूकोमा उपचार", "बहरापन",
        "वृद्धावस्था देखभाल", "पुनर्वास", "निवारक चिकित्सा",
    ],
    # Additional languages with key medical terms
    "id": [
        "kedokteran estetika", "implan gigi", "penyakit jantung", "kanker",
        "diabetes", "hipertensi", "depresi", "asma", "penyakit ginjal",
        "kehamilan", "vaksinasi anak", "COVID-19", "HIV", "operasi",
    ],
    "vi": [
        "y học thẩm mỹ", "cấy ghép răng", "bệnh tim", "ung thư",
        "tiểu đường", "tăng huyết áp", "trầm cảm", "hen suyễn", "bệnh thận",
        "thai kỳ", "tiêm chủng trẻ em", "COVID-19", "HIV", "phẫu thuật",
    ],
    "th": [
        "เวชศาสตร์ความงาม", "รากฟันเทียม", "โรคหัวใจ", "มะเร็ง",
        "เบาหวาน", "ความดันโลหิตสูง", "ซึมเศร้า", "หอบหืด", "โรคไต",
        "การตั้งครรภ์", "วัคซีนเด็ก", "โควิด-19", "เอชไอวี", "การผ่าตัด",
    ],
    "fa": [
        "پزشکی زیبایی", "ایمپلنت دندان", "بیماری قلبی", "سرطان",
        "دیابت", "فشار خون بالا", "افسردگی", "آسم", "بیماری کلیه",
        "بارداری", "واکسیناسیون کودکان", "کووید-19", "اچ‌آی‌وی", "جراحی",
    ],
    "ur": [
        "جمالیاتی طب", "دانتوں کا امپلانٹ", "دل کی بیماری", "کینسر",
        "ذیابیطس", "ہائی بلڈ پریشر", "ڈپریشن", "دمہ", "گردے کی بیماری",
        "حمل", "بچوں کی ویکسینیشن", "کوویڈ-19", "ایچ آئی وی", "سرجری",
    ],
    "bn": [
        "নান্দনিক ওষুধ", "দাঁতের ইমপ্লান্ট", "হৃদরোগ", "ক্যান্সার",
        "ডায়াবেটিস", "উচ্চ রক্তচাপ", "বিষণ্নতা", "হাঁপানি", "কিডনি রোগ",
        "গর্ভাবস্থা", "শিশু টিকাদান", "কোভিড-19", "এইচআইভি", "অস্ত্রোপচার",
    ],
    "ta": [
        "அழகியல் மருத்துவம்", "பல் பொருத்துதல்", "இதய நோய்", "புற்றுநோய்",
        "நீரிழிவு", "உயர் இரத்த அழுத்தம்", "மனச்சோர்வு", "ஆஸ்துமா", "சிறுநீரக நோய்",
        "கர்ப்பம்", "குழந்தை தடுப்பூசி", "கோவிட்-19", "எச்ஐவி", "அறுவை சிகிச்சை",
    ],
    "te": [
        "సౌందర్య వైద్యం", "దంత అమర్పు", "గుండె వ్యాధి", "క్యాన్సర్",
        "మధుమేహం", "అధిక రక్తపోటు", "నిరాశ", "ఆస్తమా", "మూత్రపిండ వ్యాధి",
        "గర్భధారణ", "పిల్లల టీకాలు", "కోవిడ్-19", "హెచ్ఐవి", "శస్త్రచికిత్స",
    ],
    "mr": [
        "सौंदर्य औषध", "दंत रोपण", "हृदयरोग", "कर्करोग",
        "मधुमेह", "उच्च रक्तदाब", "नैराश्य", "दमा", "मूत्रपिंड रोग",
        "गर्भधारणा", "बाल लसीकरण", "कोविड-19", "एचआयव्ही", "शस्त्रक्रिया",
    ],
    "pa": [
        "ਸੁੰਦਰਤਾ ਦਵਾਈ", "ਦੰਦਾਂ ਦਾ ਇਮਪਲਾਂਟ", "ਦਿਲ ਦੀ ਬਿਮਾਰੀ", "ਕੈਂਸਰ",
        "ਸ਼ੂਗਰ", "ਹਾਈ ਬਲੱਡ ਪ੍ਰੈਸ਼ਰ", "ਡਿਪਰੈਸ਼ਨ", "ਦਮਾ", "ਗੁਰਦੇ ਦੀ ਬਿਮਾਰੀ",
        "ਗਰਭ ਅਵਸਥਾ", "ਬੱਚਿਆਂ ਦਾ ਟੀਕਾਕਰਨ", "ਕੋਵਿਡ-19", "ਐੱਚਆਈਵੀ", "ਸਰਜਰੀ",
    ],
    "sw": [
        "dawa ya uzuri", "upandikizaji meno", "ugonjwa wa moyo", "saratani",
        "kisukari", "shinikizo la damu", "huzuni", "pumu", "ugonjwa wa figo",
        "ujauzito", "chanjo za watoto", "COVID-19", "VVU", "upasuaji",
    ],
    "ha": [
        "likitancin kyau", "dasa hakori", "cutar zuciya", "kansa",
        "ciwon sukari", "hawan jini", "damuwa", "asma", "cutar koda",
        "ciki", "allurar rigakafi ga yara", "COVID-19", "HIV", "tiyata",
    ],
}


def search_pmc_multilang(query: str, language: str, retmax: int = 500) -> List[str]:
    """Search PubMed Central for papers in specific language."""
    lang_filter = LANGUAGE_CODES.get(language, "english")
    
    full_query = f'({query}) AND {lang_filter}[Language] AND "open access"[filter]'
    
    params = {
        "db": "pmc",
        "term": full_query,
        "retmax": retmax,
        "retmode": "json",
        "sort": "relevance",
    }
    
    try:
        r = requests.get(ESEARCH_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        id_list = data.get("esearchresult", {}).get("idlist", [])
        count = int(data.get("esearchresult", {}).get("count", 0))
        
        logger.info(f"  [{language}] Query '{query[:40]}...' found {count} papers, returning {len(id_list)}")
        return id_list
        
    except Exception as e:
        logger.error(f"  [{language}] Search error: {e}")
        return []


def fetch_pmc_metadata(pmc_ids: List[str]) -> List[Dict]:
    """Fetch metadata for PMC IDs."""
    if not pmc_ids:
        return []
    
    params = {
        "db": "pmc",
        "id": ",".join(pmc_ids),
        "retmode": "xml",
    }
    
    try:
        r = requests.get(EFETCH_URL, params=params, timeout=60)
        r.raise_for_status()
        
        root = ET.fromstring(r.content)
        articles = []
        
        for article in root.findall(".//article"):
            try:
                pmcid_elem = article.find(".//article-id[@pub-id-type='pmcid']")
                if pmcid_elem is None:
                    pmcid_elem = article.find(".//article-id[@pub-id-type='pmc']")
                
                if pmcid_elem is not None and pmcid_elem.text:
                    pmcid = pmcid_elem.text if pmcid_elem.text.startswith("PMC") else f"PMC{pmcid_elem.text}"
                else:
                    pmcid = None
                
                title_elem = article.find(".//article-title")
                title = "".join(title_elem.itertext()) if title_elem is not None else "Untitled"
                
                abstract_elem = article.find(".//abstract")
                abstract = ""
                if abstract_elem is not None:
                    abstract = " ".join("".join(p.itertext()) for p in abstract_elem.findall(".//p"))
                
                journal_elem = article.find(".//journal-title")
                journal = journal_elem.text if journal_elem is not None else ""
                
                year_elem = article.find(".//pub-date/year")
                year = year_elem.text if year_elem is not None else ""
                
                lang_elem = article.get("{http://www.w3.org/XML/1998/namespace}lang", "en")
                
                authors = []
                for contrib in article.findall(".//contrib[@contrib-type='author']"):
                    surname = contrib.find(".//surname")
                    given = contrib.find(".//given-names")
                    if surname is not None:
                        name = surname.text or ""
                        if given is not None and given.text:
                            name = f"{given.text} {name}"
                        authors.append(name)
                
                if pmcid and title:
                    articles.append({
                        "pmcid": pmcid,
                        "title": title[:500],
                        "abstract": abstract[:5000] if abstract else "",
                        "journal": journal[:200] if journal else "",
                        "year": year,
                        "authors": ", ".join(authors[:10]),
                        "language": lang_elem,
                    })
            except Exception as e:  # nosec B112
                continue
        
        return articles
        
    except Exception as e:
        logger.error(f"Fetch metadata error: {e}")
        return []


def ingest_paper(db, paper: Dict, specialty: str, language: str) -> bool:
    """Ingest a single paper into the database."""
    try:
        existing = db.execute(
            text("SELECT id FROM documents WHERE source_id = :sid"),
            {"sid": paper["pmcid"]}
        ).fetchone()
        
        if existing:
            return False
        
        year_int = None
        if paper.get("year"):
            try:
                year_int = int(paper["year"])
            except:  # nosec B110
                pass
        
        doc_id = db.execute(
            text("""
                INSERT INTO documents (source_id, title, abstract, journal, year, authors, specialty, language, document_type, domain, created_at)
                VALUES (:source_id, :title, :abstract, :journal, :year, :authors, :specialty, :language, 'pubmed_pmc', 'medicine', NOW())
                RETURNING id
            """),
            {
                "source_id": paper["pmcid"],
                "title": paper["title"],
                "abstract": paper.get("abstract", ""),
                "journal": paper.get("journal", ""),
                "year": year_int,
                "authors": paper.get("authors", ""),
                "specialty": specialty,
                "language": language,
            }
        ).scalar()
        
        if not doc_id:
            return False
        
        content = f"{paper['title']}\n\n{paper.get('abstract', '')}"
        if content.strip():
            chunks = chunk_text(content)
            for i, chunk in enumerate(chunks):
                try:
                    embedding = embed_text(chunk)
                    db.execute(
                        text("""
                            INSERT INTO chunks (document_id, chunk_index, text, embedding)
                            VALUES (:doc_id, :idx, :content, :emb)
                        """),
                        {
                            "doc_id": doc_id,
                            "idx": i,
                            "content": chunk,
                            "emb": embedding,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Chunk embed error: {e}")
        
        db.commit()
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Ingest error for {paper.get('pmcid', 'unknown')}: {e}")
        return False


def chunk_text(text: str, max_chars: int = 1500, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks."""
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunk = text[start:end]
        
        if end < len(text):
            last_period = chunk.rfind(".")
            last_newline = chunk.rfind("\n")
            break_point = max(last_period, last_newline)
            if break_point > max_chars // 2:
                chunk = chunk[:break_point + 1]
                end = start + break_point + 1
        
        chunks.append(chunk.strip())
        start = end - overlap
    
    return [c for c in chunks if c]


def run_multilingual_sync(max_per_query: int = 500, delay_between_queries: float = 0.35):
    """
    Run the multilingual publication sync - MAXIMUM COVERAGE MODE.
    
    Configured to download maximum publications across all 25 languages
    and all medical fields. Default max_per_query increased to 500.
    """
    logger.info("=" * 60)
    logger.info("AesthetiCite Multilingual Publication Sync - MAXIMUM COVERAGE")
    logger.info(f"Languages: {len(LANGUAGE_CODES)} | Max per query: {max_per_query}")
    logger.info("=" * 60)
    
    stats = {lang: {"queries": 0, "found": 0, "ingested": 0} for lang in LANGUAGE_CODES}
    total_ingested = 0
    
    with SessionLocal() as db:
        for lang_code, queries in MULTILINGUAL_QUERIES.items():
            lang_name = LANGUAGE_CODES[lang_code]
            logger.info(f"\n{'='*40}")
            logger.info(f"Processing {lang_name.upper()} ({lang_code}) - {len(queries)} queries")
            logger.info(f"{'='*40}")
            
            for query in queries:
                stats[lang_code]["queries"] += 1
                
                pmc_ids = search_pmc_multilang(query, lang_code, retmax=max_per_query)
                stats[lang_code]["found"] += len(pmc_ids)
                
                if pmc_ids:
                    batch_size = 100
                    for i in range(0, len(pmc_ids), batch_size):
                        batch = pmc_ids[i:i + batch_size]
                        papers = fetch_pmc_metadata(batch)
                        
                        for paper in papers:
                            specialty = determine_specialty(query)
                            if ingest_paper(db, paper, specialty, lang_code):
                                stats[lang_code]["ingested"] += 1
                                total_ingested += 1
                        
                        if i + batch_size < len(pmc_ids):
                            time.sleep(0.2)
                
                time.sleep(delay_between_queries)
            
            logger.info(f"  {lang_name}: {stats[lang_code]['ingested']} papers ingested")
    
    logger.info("\n" + "=" * 60)
    logger.info("MULTILINGUAL SYNC COMPLETE")
    logger.info("=" * 60)
    
    for lang_code, lang_stats in stats.items():
        logger.info(f"  {LANGUAGE_CODES[lang_code]:12} | Queries: {lang_stats['queries']:3} | Found: {lang_stats['found']:5} | Ingested: {lang_stats['ingested']:4}")
    
    logger.info(f"\nTOTAL PAPERS INGESTED: {total_ingested}")
    
    return stats


def determine_specialty(query: str) -> str:
    """Determine specialty based on query keywords - expanded for all medical fields."""
    query_lower = query.lower()
    
    # Aesthetic Medicine & Dermatology
    if any(k in query_lower for k in ["esthétique", "estética", "estetica", "ästhetisch", "filler", "botox", "toxin", "rejuvenation", "laser skin", "美容", "美学", "整形", "peeling", "liposuction", "rhinoplasty"]):
        return "aesthetic_medicine"
    elif any(k in query_lower for k in ["psoriasis", "dermat", "peau", "piel", "haut", "acne", "eczema", "skin cancer", "melanoma", "皮肤"]):
        return "dermatology"
    
    # Dental Medicine
    elif any(k in query_lower for k in ["dental", "dentaire", "dentario", "zahnimplantat", "orthodon", "periodon", "canal", "canalare", "tooth", "teeth", "molar", "牙", "歯", "dent"]):
        return "dental_medicine"
    
    # Cardiology & Cardiovascular
    elif any(k in query_lower for k in ["cardiac", "cardíaca", "cardiaque", "heart", "coeur", "corazón", "herz", "arrhythmia", "fibrillation", "infarct", "stroke", "hypertension", "心", "心臓", "심장"]):
        return "cardiology"
    
    # Oncology & Hematology
    elif any(k in query_lower for k in ["cancer", "cáncer", "krebs", "tumor", "oncol", "leukemia", "lymphoma", "chemotherapy", "radiation therapy", "癌", "がん", "암", "سرطان"]):
        return "oncology"
    
    # Endocrinology & Metabolism
    elif any(k in query_lower for k in ["diabetes", "diabète", "thyroid", "obesity", "metabolic", "adrenal", "hormone", "osteoporosis", "糖尿病", "甲状腺"]):
        return "endocrinology"
    
    # Psychiatry & Mental Health
    elif any(k in query_lower for k in ["depression", "dépression", "depresión", "antidepressant", "anxiety", "schizophrenia", "bipolar", "ptsd", "adhd", "insomnia", "psychiatric", "mental", "抑郁", "うつ"]):
        return "psychiatry"
    
    # Neurology
    elif any(k in query_lower for k in ["neurol", "parkinson", "alzheimer", "dementia", "epilepsy", "seizure", "migraine", "sclerosis", "neuropath", "脳", "神経", "뇌"]):
        return "neurology"
    
    # Orthopedics & Rheumatology
    elif any(k in query_lower for k in ["arthrit", "rheumat", "rhumatoïde", "osteoarth", "joint", "fracture", "spine", "orthoped", "fibromyalgia", "gout", "lupus", "関節", "관절"]):
        return "rheumatology"
    
    # Pulmonology & Respiratory
    elif any(k in query_lower for k in ["asthma", "copd", "pulmon", "respirat", "lung", "pneumon", "fibrosis", "apnea", "tuberculosis", "肺", "호흡"]):
        return "pulmonology"
    
    # Gastroenterology & Hepatology
    elif any(k in query_lower for k in ["gastro", "hepat", "liver", "crohn", "colitis", "bowel", "pancreat", "cirrhosis", "reflux", "celiac", "肝", "胃", "腸"]):
        return "gastroenterology"
    
    # Nephrology & Urology
    elif any(k in query_lower for k in ["kidney", "renal", "nephro", "dialysis", "urinary", "prostate", "bladder", "urolog", "腎", "신장"]):
        return "nephrology"
    
    # Obstetrics & Gynecology
    elif any(k in query_lower for k in ["pregnan", "obstet", "gynecol", "cesarean", "preeclampsia", "infertility", "menopause", "endometriosis", "contraception", "妊娠", "임신", "حمل"]):
        return "obstetrics_gynecology"
    
    # Pediatrics & Neonatology
    elif any(k in query_lower for k in ["pediatr", "neonat", "child", "infant", "vaccination", "vaccine", "developmental", "autism", "儿童", "小児", "아동"]):
        return "pediatrics"
    
    # Emergency & Critical Care
    elif any(k in query_lower for k in ["emergency", "critical", "intensive", "sepsis", "trauma", "resuscitation", "shock", "burn", "急诊", "救急"]):
        return "emergency_medicine"
    
    # Infectious Disease & Immunology
    elif any(k in query_lower for k in ["covid", "antibiotic", "antibiotique", "infection", "hiv", "aids", "malaria", "influenza", "autoimmune", "allergy", "immunol", "感染", "免疫"]):
        return "infectious_disease"
    
    # Ophthalmology & ENT
    elif any(k in query_lower for k in ["ophthalm", "eye", "cataract", "glaucoma", "macular", "hearing", "ear", "tinnitus", "sinus", "cochlear", "眼", "耳"]):
        return "ophthalmology_ent"
    
    # Surgery & Anesthesiology
    elif any(k in query_lower for k in ["surgery", "surgical", "anesthes", "postoperative", "transplant", "bariatric", "invasive", "外科", "수술"]):
        return "surgery"
    
    # Geriatrics & Rehabilitation
    elif any(k in query_lower for k in ["geriatr", "elderly", "frailty", "rehabilit", "physical therapy", "palliative", "老年", "재활"]):
        return "geriatrics"
    
    # Preventive Medicine & Public Health
    elif any(k in query_lower for k in ["preventive", "prevention", "screening", "public health", "epidemiol", "lifestyle", "tobacco", "cessation", "预防", "예방"]):
        return "preventive_medicine"
    
    else:
        return "general_medicine"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="AesthetiCite Multilingual Publication Sync - MAXIMUM COVERAGE",
        epilog="Downloads publications across 25 languages and all medical fields. Schedule: Daily at 02:00 UTC starting January 30, 2026."
    )
    parser.add_argument("--max-per-query", type=int, default=500, help="Max papers per query (default: 500 for maximum coverage)")
    parser.add_argument("--delay", type=float, default=0.35, help="Delay between queries in seconds (default: 0.35)")
    parser.add_argument("--languages", type=str, default="all", help="Comma-separated language codes or 'all' (default: all)")
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║     AesthetiCite Publication Sync - MAXIMUM COVERAGE MODE         ║
╠══════════════════════════════════════════════════════════════╣
║  Languages: {len(LANGUAGE_CODES):2} languages supported                          ║
║  Fields: All medical specialties                             ║
║  Max per query: {args.max_per_query:4} papers                                    ║
║  Schedule: Daily at 02:00 UTC                                ║
║  Start Date: January 30, 2026                                ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    run_multilingual_sync(
        max_per_query=args.max_per_query,
        delay_between_queries=args.delay
    )
