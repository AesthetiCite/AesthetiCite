"""
AesthetiCite Publication Sync Agent

Automated agent that runs daily to:
1. Check for new publications from PubMed Central
2. Download and ingest new papers into the knowledge base
3. Track sync status and report metrics

Similar to OpenEvidence and Isaac OneHealth publication pipelines.
"""

import os
import sys
import time
import json
import logging
import requests
import defusedxml.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from sqlalchemy import text, update, table, column
from sqlalchemy.orm import Session

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
PMC_OA_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"

AESTHETIC_MEDICINE_QUERIES = [
    # Core filler topics
    '"dermal filler"[Title/Abstract] AND (complication OR adverse OR safety)',
    '"hyaluronic acid filler"[Title/Abstract]',
    '"hyaluronidase"[Title/Abstract] AND (filler OR injection)',
    '"calcium hydroxylapatite"[Title/Abstract] AND filler',
    '"poly-L-lactic acid"[Title/Abstract] AND (filler OR Sculptra)',
    '"polymethylmethacrylate"[Title/Abstract] AND filler',
    # Vascular complications
    '"vision loss"[Title/Abstract] AND (filler OR injection)',
    '"vascular occlusion"[Title/Abstract] AND (filler OR dermal)',
    '"retinal artery occlusion"[Title/Abstract] AND filler',
    '"skin necrosis"[Title/Abstract] AND (filler OR injection)',
    '"embolization"[Title/Abstract] AND (filler OR cosmetic)',
    # Botulinum toxin
    '"botulinum toxin"[Title/Abstract] AND aesthetic',
    '"botulinum toxin"[Title/Abstract] AND (wrinkle OR facial)',
    '"botox"[Title/Abstract] AND cosmetic',
    '"dysport"[Title/Abstract] AND aesthetic',
    # Facial rejuvenation
    '"facial rejuvenation"[Title/Abstract] AND (laser OR injectable)',
    '"facial anatomy"[Title/Abstract] AND (injection OR filler)',
    '"danger zones"[Title/Abstract] AND (face OR injection)',
    # Laser treatments
    '"laser resurfacing"[Title/Abstract]',
    '"fractional laser"[Title/Abstract] AND skin',
    '"CO2 laser"[Title/Abstract] AND (skin OR rejuvenation)',
    '"erbium laser"[Title/Abstract] AND skin',
    '"IPL"[Title/Abstract] AND (skin OR photofacial)',
    '"intense pulsed light"[Title/Abstract] AND aesthetic',
    '"Nd:YAG laser"[Title/Abstract] AND (skin OR vascular)',
    '"pulsed dye laser"[Title/Abstract]',
    '"picosecond laser"[Title/Abstract]',
    # Skin conditions & treatments
    '"chemical peel"[Title/Abstract] AND dermatology',
    '"melasma"[Title/Abstract] AND treatment',
    '"acne scar"[Title/Abstract] AND (laser OR treatment)',
    '"hyperpigmentation"[Title/Abstract] AND (laser OR treatment)',
    '"photoaging"[Title/Abstract] AND treatment',
    '"skin tightening"[Title/Abstract] AND (radiofrequency OR ultrasound)',
    # Microneedling & RF
    '"microneedling"[Title/Abstract]',
    '"radiofrequency microneedling"[Title/Abstract]',
    '"collagen induction"[Title/Abstract]',
    # PRP & regenerative
    '"platelet rich plasma"[Title/Abstract] AND aesthetic',
    '"PRP"[Title/Abstract] AND (skin OR hair OR rejuvenation)',
    '"stem cell"[Title/Abstract] AND aesthetic',
    '"exosome"[Title/Abstract] AND (skin OR aesthetic)',
    # Body contouring
    '"body contouring"[Title/Abstract] AND (cryolipolysis OR radiofrequency)',
    '"cryolipolysis"[Title/Abstract]',
    '"lipolysis"[Title/Abstract] AND (injection OR non-surgical)',
    '"deoxycholic acid"[Title/Abstract] AND (submental OR fat)',
    '"HIFU"[Title/Abstract] AND (skin OR body)',
    # Specific procedures
    '"lip augmentation"[Title/Abstract]',
    '"rhinoplasty"[Title/Abstract] AND (filler OR non-surgical)',
    '"tear trough"[Title/Abstract] AND (filler OR treatment)',
    '"nasolabial"[Title/Abstract] AND (filler OR treatment)',
    '"marionette lines"[Title/Abstract] AND filler',
    '"temple"[Title/Abstract] AND (filler OR augmentation)',
    '"jawline"[Title/Abstract] AND (filler OR contouring)',
    '"chin augmentation"[Title/Abstract] AND filler',
    # Complications
    '"biofilm"[Title/Abstract] AND (filler OR implant)',
    '"granuloma"[Title/Abstract] AND (filler OR cosmetic)',
    '"necrosis"[Title/Abstract] AND (filler OR injection)',
    '"Tyndall effect"[Title/Abstract]',
    '"filler migration"[Title/Abstract]',
    '"nodule"[Title/Abstract] AND (filler OR injectable)',
    # Safety & protocols
    '"Fitzpatrick"[Title/Abstract] AND (laser OR skin)',
    '"anesthesia"[Title/Abstract] AND (dermal OR aesthetic)',
    '"consent"[Title/Abstract] AND (aesthetic OR cosmetic)',
    '"patient satisfaction"[Title/Abstract] AND (aesthetic OR cosmetic)',
    # Hair restoration
    '"hair restoration"[Title/Abstract] AND (PRP OR laser)',
    '"alopecia"[Title/Abstract] AND (PRP OR treatment)',
    # Thread lifting
    '"thread lift"[Title/Abstract]',
    '"PDO thread"[Title/Abstract]',
    # Scar treatment
    '"keloid"[Title/Abstract] AND treatment',
    '"hypertrophic scar"[Title/Abstract] AND treatment',
    '"scar revision"[Title/Abstract] AND laser',
    # Vascular lesions
    '"telangiectasia"[Title/Abstract] AND (laser OR treatment)',
    '"rosacea"[Title/Abstract] AND (laser OR treatment)',
    '"port wine stain"[Title/Abstract] AND laser',
    # Pigmentation
    '"tattoo removal"[Title/Abstract] AND laser',
    '"nevus"[Title/Abstract] AND (laser OR removal)',
    # Combination treatments
    '"combination therapy"[Title/Abstract] AND (aesthetic OR cosmetic)',
    '"multimodal"[Title/Abstract] AND (rejuvenation OR aesthetic)',
]

# Dental Medicine comprehensive query list
DENTAL_MEDICINE_QUERIES = [
    # Implantology
    '"dental implant"[Title/Abstract] AND (placement OR survival OR failure)',
    '"osseointegration"[Title/Abstract] AND (implant OR dental)',
    '"peri-implantitis"[Title/Abstract] AND (treatment OR prevention)',
    '"implant abutment"[Title/Abstract]',
    '"immediate implant"[Title/Abstract] AND loading',
    '"bone augmentation"[Title/Abstract] AND (dental OR implant)',
    '"sinus lift"[Title/Abstract] AND dental',
    '"guided bone regeneration"[Title/Abstract]',
    '"alveolar ridge"[Title/Abstract] AND (preservation OR augmentation)',
    # Endodontics
    '"root canal"[Title/Abstract] AND (treatment OR therapy)',
    '"endodontic"[Title/Abstract] AND (retreatment OR infection)',
    '"apical periodontitis"[Title/Abstract]',
    '"pulpitis"[Title/Abstract] AND (diagnosis OR treatment)',
    '"rotary instrumentation"[Title/Abstract] AND endodontic',
    '"obturation"[Title/Abstract] AND (root canal OR endodontic)',
    '"apical surgery"[Title/Abstract] AND dental',
    '"vital pulp therapy"[Title/Abstract]',
    # Periodontics
    '"periodontal disease"[Title/Abstract] AND (treatment OR therapy)',
    '"periodontitis"[Title/Abstract] AND (management OR treatment)',
    '"gingivitis"[Title/Abstract] AND (treatment OR prevention)',
    '"scaling and root planing"[Title/Abstract]',
    '"periodontal regeneration"[Title/Abstract]',
    '"gum recession"[Title/Abstract] AND treatment',
    '"connective tissue graft"[Title/Abstract] AND periodontal',
    '"guided tissue regeneration"[Title/Abstract] AND dental',
    '"bone graft"[Title/Abstract] AND periodontal',
    # Prosthodontics
    '"dental crown"[Title/Abstract] AND (material OR longevity)',
    '"dental bridge"[Title/Abstract] AND (fixed OR partial)',
    '"complete denture"[Title/Abstract]',
    '"removable partial denture"[Title/Abstract]',
    '"CAD CAM"[Title/Abstract] AND dental',
    '"zirconia"[Title/Abstract] AND (crown OR restoration)',
    '"ceramic restoration"[Title/Abstract] AND dental',
    '"dental veneer"[Title/Abstract]',
    '"full mouth rehabilitation"[Title/Abstract]',
    # Orthodontics
    '"orthodontic treatment"[Title/Abstract] AND (outcome OR efficacy)',
    '"clear aligner"[Title/Abstract]',
    '"Invisalign"[Title/Abstract]',
    '"malocclusion"[Title/Abstract] AND (treatment OR correction)',
    '"bracket"[Title/Abstract] AND orthodontic',
    '"tooth movement"[Title/Abstract] AND orthodontic',
    '"retention"[Title/Abstract] AND orthodontic',
    '"orthognathic surgery"[Title/Abstract]',
    # Oral Surgery
    '"tooth extraction"[Title/Abstract] AND (complication OR technique)',
    '"wisdom tooth"[Title/Abstract] AND (removal OR impacted)',
    '"third molar"[Title/Abstract] AND (extraction OR surgery)',
    '"oral surgery"[Title/Abstract] AND (complication OR technique)',
    '"jaw surgery"[Title/Abstract]',
    '"TMJ"[Title/Abstract] AND (disorder OR treatment)',
    '"temporomandibular"[Title/Abstract] AND (dysfunction OR therapy)',
    '"osteonecrosis"[Title/Abstract] AND (jaw OR bisphosphonate)',
    # Restorative Dentistry
    '"dental composite"[Title/Abstract] AND (restoration OR filling)',
    '"dental amalgam"[Title/Abstract] AND (restoration OR safety)',
    '"glass ionomer"[Title/Abstract] AND dental',
    '"dental bonding"[Title/Abstract]',
    '"adhesive dentistry"[Title/Abstract]',
    '"secondary caries"[Title/Abstract]',
    '"minimal intervention"[Title/Abstract] AND dentistry',
    # Oral Medicine & Pathology
    '"oral cancer"[Title/Abstract] AND (diagnosis OR screening)',
    '"oral squamous cell carcinoma"[Title/Abstract]',
    '"oral lichen planus"[Title/Abstract]',
    '"oral mucosal"[Title/Abstract] AND (lesion OR disease)',
    '"xerostomia"[Title/Abstract] AND (treatment OR management)',
    '"burning mouth syndrome"[Title/Abstract]',
    '"oral candidiasis"[Title/Abstract]',
    # Pediatric Dentistry
    '"pediatric dentistry"[Title/Abstract]',
    '"primary teeth"[Title/Abstract] AND (treatment OR caries)',
    '"dental caries"[Title/Abstract] AND (children OR pediatric)',
    '"pulpotomy"[Title/Abstract] AND (primary OR pediatric)',
    '"space maintainer"[Title/Abstract]',
    '"fluoride"[Title/Abstract] AND (dental OR caries)',
    # Dental Materials
    '"dental cement"[Title/Abstract]',
    '"resin cement"[Title/Abstract] AND dental',
    '"dental alloy"[Title/Abstract]',
    '"biocompatibility"[Title/Abstract] AND dental',
    # Digital Dentistry
    '"digital dentistry"[Title/Abstract]',
    '"intraoral scanner"[Title/Abstract]',
    '"3D printing"[Title/Abstract] AND dental',
    '"digital impression"[Title/Abstract]',
    '"CBCT"[Title/Abstract] AND dental',
    # Pain & Sedation
    '"dental anesthesia"[Title/Abstract]',
    '"dental sedation"[Title/Abstract]',
    '"dental anxiety"[Title/Abstract] AND management',
    '"orofacial pain"[Title/Abstract]',
]

# General Medicine comprehensive query list - All Specializations
GENERAL_MEDICINE_QUERIES = [
    # Cardiology
    '"heart failure"[Title/Abstract] AND (treatment OR management)',
    '"hypertension"[Title/Abstract] AND (guidelines OR therapy)',
    '"atrial fibrillation"[Title/Abstract] AND (management OR anticoagulation)',
    '"myocardial infarction"[Title/Abstract] AND (treatment OR STEMI)',
    '"coronary artery disease"[Title/Abstract] AND (therapy OR intervention)',
    '"cardiac arrhythmia"[Title/Abstract] AND treatment',
    '"valvular heart disease"[Title/Abstract]',
    '"lipid lowering"[Title/Abstract] AND (statin OR therapy)',
    '"pericarditis"[Title/Abstract] AND treatment',
    '"cardiomyopathy"[Title/Abstract] AND management',
    # Endocrinology
    '"diabetes mellitus"[Title/Abstract] AND (management OR treatment)',
    '"type 2 diabetes"[Title/Abstract] AND (therapy OR guidelines)',
    '"thyroid"[Title/Abstract] AND (disorder OR treatment)',
    '"hyperthyroidism"[Title/Abstract] AND management',
    '"hypothyroidism"[Title/Abstract] AND treatment',
    '"adrenal"[Title/Abstract] AND (insufficiency OR disorder)',
    '"osteoporosis"[Title/Abstract] AND (treatment OR prevention)',
    '"metabolic syndrome"[Title/Abstract]',
    '"pituitary"[Title/Abstract] AND (adenoma OR disorder)',
    '"Cushing syndrome"[Title/Abstract] AND treatment',
    # Gastroenterology
    '"GERD"[Title/Abstract] AND (treatment OR management)',
    '"inflammatory bowel disease"[Title/Abstract]',
    '"Crohn disease"[Title/Abstract] AND treatment',
    '"ulcerative colitis"[Title/Abstract] AND therapy',
    '"cirrhosis"[Title/Abstract] AND (management OR complication)',
    '"hepatitis"[Title/Abstract] AND (treatment OR chronic)',
    '"pancreatitis"[Title/Abstract] AND management',
    '"colorectal cancer"[Title/Abstract] AND (screening OR treatment)',
    '"irritable bowel syndrome"[Title/Abstract] AND treatment',
    '"celiac disease"[Title/Abstract] AND management',
    '"peptic ulcer"[Title/Abstract] AND treatment',
    '"gallbladder"[Title/Abstract] AND (cholecystitis OR surgery)',
    # Pulmonology
    '"COPD"[Title/Abstract] AND (management OR exacerbation)',
    '"asthma"[Title/Abstract] AND (treatment OR guidelines)',
    '"pneumonia"[Title/Abstract] AND (treatment OR community-acquired)',
    '"pulmonary embolism"[Title/Abstract] AND (diagnosis OR treatment)',
    '"interstitial lung disease"[Title/Abstract]',
    '"sleep apnea"[Title/Abstract] AND (treatment OR CPAP)',
    '"pulmonary fibrosis"[Title/Abstract]',
    '"bronchiectasis"[Title/Abstract] AND treatment',
    '"pleural effusion"[Title/Abstract] AND management',
    # Nephrology
    '"chronic kidney disease"[Title/Abstract] AND management',
    '"acute kidney injury"[Title/Abstract] AND treatment',
    '"dialysis"[Title/Abstract] AND (hemodialysis OR peritoneal)',
    '"kidney transplant"[Title/Abstract]',
    '"glomerulonephritis"[Title/Abstract]',
    '"nephrotic syndrome"[Title/Abstract]',
    '"polycystic kidney"[Title/Abstract]',
    '"renal artery stenosis"[Title/Abstract]',
    # Rheumatology
    '"rheumatoid arthritis"[Title/Abstract] AND (treatment OR biologic)',
    '"osteoarthritis"[Title/Abstract] AND (management OR therapy)',
    '"systemic lupus erythematosus"[Title/Abstract]',
    '"gout"[Title/Abstract] AND (treatment OR management)',
    '"ankylosing spondylitis"[Title/Abstract]',
    '"psoriatic arthritis"[Title/Abstract]',
    '"fibromyalgia"[Title/Abstract] AND treatment',
    '"scleroderma"[Title/Abstract] AND treatment',
    '"vasculitis"[Title/Abstract] AND management',
    '"Sjogren syndrome"[Title/Abstract]',
    # Neurology
    '"stroke"[Title/Abstract] AND (treatment OR prevention)',
    '"epilepsy"[Title/Abstract] AND (treatment OR seizure)',
    '"Parkinson disease"[Title/Abstract] AND therapy',
    '"multiple sclerosis"[Title/Abstract] AND treatment',
    '"migraine"[Title/Abstract] AND (prophylaxis OR treatment)',
    '"Alzheimer disease"[Title/Abstract] AND management',
    '"dementia"[Title/Abstract] AND treatment',
    '"neuropathy"[Title/Abstract] AND (peripheral OR treatment)',
    '"amyotrophic lateral sclerosis"[Title/Abstract]',
    '"myasthenia gravis"[Title/Abstract] AND treatment',
    '"meningitis"[Title/Abstract] AND treatment',
    '"encephalitis"[Title/Abstract] AND management',
    '"trigeminal neuralgia"[Title/Abstract]',
    # Hematology/Oncology
    '"anemia"[Title/Abstract] AND (treatment OR iron)',
    '"lymphoma"[Title/Abstract] AND treatment',
    '"leukemia"[Title/Abstract] AND therapy',
    '"breast cancer"[Title/Abstract] AND (treatment OR screening)',
    '"lung cancer"[Title/Abstract] AND (treatment OR immunotherapy)',
    '"prostate cancer"[Title/Abstract] AND management',
    '"anticoagulation"[Title/Abstract] AND (therapy OR reversal)',
    '"thrombocytopenia"[Title/Abstract]',
    '"multiple myeloma"[Title/Abstract] AND treatment',
    '"melanoma"[Title/Abstract] AND (immunotherapy OR treatment)',
    '"ovarian cancer"[Title/Abstract] AND treatment',
    '"pancreatic cancer"[Title/Abstract] AND therapy',
    '"thyroid cancer"[Title/Abstract] AND management',
    '"gastric cancer"[Title/Abstract] AND treatment',
    '"esophageal cancer"[Title/Abstract] AND therapy',
    '"bladder cancer"[Title/Abstract] AND treatment',
    '"renal cell carcinoma"[Title/Abstract] AND therapy',
    '"testicular cancer"[Title/Abstract] AND treatment',
    '"sarcoma"[Title/Abstract] AND therapy',
    '"brain tumor"[Title/Abstract] AND (glioma OR treatment)',
    '"hemophilia"[Title/Abstract] AND treatment',
    '"sickle cell"[Title/Abstract] AND management',
    '"deep vein thrombosis"[Title/Abstract] AND treatment',
    # Infectious Disease
    '"sepsis"[Title/Abstract] AND (management OR bundle)',
    '"antibiotic resistance"[Title/Abstract]',
    '"urinary tract infection"[Title/Abstract] AND treatment',
    '"cellulitis"[Title/Abstract] AND treatment',
    '"HIV"[Title/Abstract] AND (treatment OR antiretroviral)',
    '"tuberculosis"[Title/Abstract] AND therapy',
    '"COVID-19"[Title/Abstract] AND (treatment OR management)',
    '"influenza"[Title/Abstract] AND (treatment OR vaccination)',
    '"osteomyelitis"[Title/Abstract] AND treatment',
    '"endocarditis"[Title/Abstract] AND (infective OR treatment)',
    '"meningococcal"[Title/Abstract] AND infection',
    '"fungal infection"[Title/Abstract] AND treatment',
    '"parasitic infection"[Title/Abstract] AND therapy',
    '"Lyme disease"[Title/Abstract] AND treatment',
    '"herpes zoster"[Title/Abstract] AND management',
    # Psychiatry
    '"depression"[Title/Abstract] AND (treatment OR antidepressant)',
    '"anxiety disorder"[Title/Abstract] AND therapy',
    '"bipolar disorder"[Title/Abstract] AND treatment',
    '"schizophrenia"[Title/Abstract] AND (treatment OR antipsychotic)',
    '"PTSD"[Title/Abstract] AND treatment',
    '"substance use disorder"[Title/Abstract]',
    '"insomnia"[Title/Abstract] AND treatment',
    '"obsessive compulsive"[Title/Abstract] AND treatment',
    '"eating disorder"[Title/Abstract] AND (anorexia OR bulimia)',
    '"ADHD"[Title/Abstract] AND (adult OR treatment)',
    '"personality disorder"[Title/Abstract] AND therapy',
    # Dermatology
    '"psoriasis"[Title/Abstract] AND (treatment OR biologic)',
    '"atopic dermatitis"[Title/Abstract] AND (management OR therapy)',
    '"eczema"[Title/Abstract] AND treatment',
    '"acne vulgaris"[Title/Abstract] AND (treatment OR therapy)',
    '"skin cancer"[Title/Abstract] AND (basal OR squamous)',
    '"urticaria"[Title/Abstract] AND treatment',
    '"contact dermatitis"[Title/Abstract] AND management',
    '"pemphigus"[Title/Abstract] AND treatment',
    '"pemphigoid"[Title/Abstract] AND therapy',
    '"vitiligo"[Title/Abstract] AND treatment',
    '"alopecia areata"[Title/Abstract] AND therapy',
    '"seborrheic dermatitis"[Title/Abstract]',
    '"fungal skin infection"[Title/Abstract] AND treatment',
    '"warts"[Title/Abstract] AND (HPV OR treatment)',
    '"herpes simplex"[Title/Abstract] AND skin',
    '"drug eruption"[Title/Abstract] AND cutaneous',
    '"Stevens-Johnson"[Title/Abstract] AND syndrome',
    '"erythema multiforme"[Title/Abstract]',
    '"hidradenitis suppurativa"[Title/Abstract]',
    # Orthopedics / Traumatology
    '"fracture"[Title/Abstract] AND (treatment OR fixation)',
    '"hip fracture"[Title/Abstract] AND (surgery OR management)',
    '"vertebral fracture"[Title/Abstract] AND treatment',
    '"spine fracture"[Title/Abstract] AND management',
    '"ankle fracture"[Title/Abstract] AND treatment',
    '"wrist fracture"[Title/Abstract] AND (distal radius OR management)',
    '"shoulder injury"[Title/Abstract] AND treatment',
    '"rotator cuff"[Title/Abstract] AND (tear OR repair)',
    '"ACL injury"[Title/Abstract] AND (reconstruction OR treatment)',
    '"meniscus"[Title/Abstract] AND (tear OR surgery)',
    '"carpal tunnel"[Title/Abstract] AND (syndrome OR surgery)',
    '"herniated disc"[Title/Abstract] AND treatment',
    '"spinal stenosis"[Title/Abstract] AND management',
    '"scoliosis"[Title/Abstract] AND (treatment OR surgery)',
    '"total hip replacement"[Title/Abstract]',
    '"total knee replacement"[Title/Abstract]',
    '"joint replacement"[Title/Abstract] AND (outcome OR complication)',
    '"arthroscopy"[Title/Abstract] AND (knee OR shoulder)',
    '"tendon injury"[Title/Abstract] AND (repair OR treatment)',
    '"Achilles tendon"[Title/Abstract] AND (rupture OR repair)',
    '"ligament injury"[Title/Abstract] AND treatment',
    '"sports injury"[Title/Abstract] AND management',
    '"bone healing"[Title/Abstract] AND (fracture OR union)',
    '"osteomyelitis"[Title/Abstract] AND (orthopedic OR treatment)',
    '"compartment syndrome"[Title/Abstract]',
    '"polytrauma"[Title/Abstract] AND management',
    '"pelvic fracture"[Title/Abstract] AND treatment',
    '"spinal cord injury"[Title/Abstract] AND (rehabilitation OR management)',
    # Urology
    '"benign prostatic hyperplasia"[Title/Abstract] AND treatment',
    '"prostatitis"[Title/Abstract] AND management',
    '"erectile dysfunction"[Title/Abstract] AND (treatment OR therapy)',
    '"kidney stone"[Title/Abstract] AND (treatment OR lithotripsy)',
    '"urinary incontinence"[Title/Abstract] AND treatment',
    '"overactive bladder"[Title/Abstract] AND therapy',
    '"urethral stricture"[Title/Abstract] AND treatment',
    '"hydronephrosis"[Title/Abstract] AND management',
    '"varicocele"[Title/Abstract] AND treatment',
    '"testicular torsion"[Title/Abstract]',
    '"epididymitis"[Title/Abstract] AND treatment',
    '"urologic oncology"[Title/Abstract]',
    # Gynecology / Obstetrics
    '"endometriosis"[Title/Abstract] AND (treatment OR management)',
    '"uterine fibroid"[Title/Abstract] AND treatment',
    '"polycystic ovary"[Title/Abstract] AND (syndrome OR treatment)',
    '"menopause"[Title/Abstract] AND (hormone OR therapy)',
    '"cervical cancer"[Title/Abstract] AND (screening OR treatment)',
    '"endometrial cancer"[Title/Abstract] AND management',
    '"pelvic organ prolapse"[Title/Abstract] AND treatment',
    '"vulvovaginal"[Title/Abstract] AND (infection OR treatment)',
    '"preeclampsia"[Title/Abstract] AND management',
    '"gestational diabetes"[Title/Abstract] AND treatment',
    '"ectopic pregnancy"[Title/Abstract] AND management',
    '"placenta previa"[Title/Abstract]',
    '"cesarean section"[Title/Abstract] AND (indication OR outcome)',
    '"postpartum hemorrhage"[Title/Abstract] AND treatment',
    '"infertility"[Title/Abstract] AND (female OR treatment)',
    '"IVF"[Title/Abstract] AND (outcome OR success)',
    '"contraception"[Title/Abstract] AND (method OR efficacy)',
    # Ophthalmology
    '"cataract"[Title/Abstract] AND (surgery OR treatment)',
    '"glaucoma"[Title/Abstract] AND (treatment OR therapy)',
    '"macular degeneration"[Title/Abstract] AND treatment',
    '"diabetic retinopathy"[Title/Abstract] AND management',
    '"retinal detachment"[Title/Abstract] AND surgery',
    '"uveitis"[Title/Abstract] AND treatment',
    '"dry eye"[Title/Abstract] AND (disease OR treatment)',
    '"keratitis"[Title/Abstract] AND treatment',
    '"corneal transplant"[Title/Abstract]',
    '"refractive surgery"[Title/Abstract] AND (LASIK OR outcome)',
    '"strabismus"[Title/Abstract] AND treatment',
    '"optic neuritis"[Title/Abstract]',
    # Otolaryngology (ENT)
    '"hearing loss"[Title/Abstract] AND (sensorineural OR treatment)',
    '"cochlear implant"[Title/Abstract]',
    '"tinnitus"[Title/Abstract] AND treatment',
    '"vertigo"[Title/Abstract] AND (vestibular OR management)',
    '"Meniere disease"[Title/Abstract]',
    '"sinusitis"[Title/Abstract] AND (chronic OR treatment)',
    '"nasal polyp"[Title/Abstract] AND treatment',
    '"sleep apnea"[Title/Abstract] AND (surgery OR ENT)',
    '"tonsillitis"[Title/Abstract] AND (treatment OR tonsillectomy)',
    '"laryngeal cancer"[Title/Abstract] AND treatment',
    '"thyroid nodule"[Title/Abstract] AND management',
    '"parotid tumor"[Title/Abstract]',
    '"vocal cord"[Title/Abstract] AND (paralysis OR nodule)',
    '"epistaxis"[Title/Abstract] AND management',
    '"otitis media"[Title/Abstract] AND treatment',
    # Pediatrics
    '"pediatric"[Title/Abstract] AND (fever OR management)',
    '"childhood asthma"[Title/Abstract] AND treatment',
    '"pediatric obesity"[Title/Abstract] AND intervention',
    '"neonatal"[Title/Abstract] AND (jaundice OR sepsis)',
    '"bronchiolitis"[Title/Abstract] AND treatment',
    '"pediatric pneumonia"[Title/Abstract]',
    '"congenital heart disease"[Title/Abstract]',
    '"pediatric epilepsy"[Title/Abstract]',
    '"autism spectrum"[Title/Abstract] AND (disorder OR therapy)',
    '"developmental delay"[Title/Abstract] AND assessment',
    '"failure to thrive"[Title/Abstract]',
    '"pediatric diabetes"[Title/Abstract]',
    '"kawasaki disease"[Title/Abstract]',
    '"pediatric fracture"[Title/Abstract] AND treatment',
    # Allergy / Immunology
    '"anaphylaxis"[Title/Abstract] AND (treatment OR management)',
    '"food allergy"[Title/Abstract] AND therapy',
    '"drug allergy"[Title/Abstract] AND management',
    '"allergic rhinitis"[Title/Abstract] AND treatment',
    '"immunodeficiency"[Title/Abstract] AND (primary OR treatment)',
    '"autoimmune disease"[Title/Abstract] AND therapy',
    '"immunotherapy"[Title/Abstract] AND (allergy OR cancer)',
    # Vascular Surgery
    '"aortic aneurysm"[Title/Abstract] AND (repair OR treatment)',
    '"peripheral artery disease"[Title/Abstract] AND treatment',
    '"carotid stenosis"[Title/Abstract] AND (surgery OR stent)',
    '"varicose veins"[Title/Abstract] AND treatment',
    '"venous insufficiency"[Title/Abstract] AND management',
    '"arteriovenous malformation"[Title/Abstract]',
    '"limb ischemia"[Title/Abstract] AND treatment',
    '"endovascular"[Title/Abstract] AND (repair OR treatment)',
    # Plastic Surgery / Reconstructive
    '"breast reconstruction"[Title/Abstract] AND surgery',
    '"cleft lip"[Title/Abstract] AND (palate OR repair)',
    '"burn injury"[Title/Abstract] AND (treatment OR reconstruction)',
    '"skin graft"[Title/Abstract] AND surgery',
    '"flap surgery"[Title/Abstract] AND reconstruction',
    '"hand surgery"[Title/Abstract] AND reconstruction',
    '"facial reconstruction"[Title/Abstract]',
    # Emergency Medicine
    '"acute abdomen"[Title/Abstract] AND (diagnosis OR management)',
    '"trauma"[Title/Abstract] AND (management OR resuscitation)',
    '"shock"[Title/Abstract] AND (septic OR treatment)',
    '"cardiac arrest"[Title/Abstract] AND (resuscitation OR CPR)',
    '"poisoning"[Title/Abstract] AND (treatment OR overdose)',
    '"burn management"[Title/Abstract] AND emergency',
    '"head injury"[Title/Abstract] AND (mild OR management)',
    '"thoracic trauma"[Title/Abstract]',
    '"abdominal trauma"[Title/Abstract] AND management',
    # Primary Care / Preventive Medicine
    '"vaccination"[Title/Abstract] AND (adult OR schedule)',
    '"health screening"[Title/Abstract] AND guidelines',
    '"preventive care"[Title/Abstract]',
    '"chronic disease management"[Title/Abstract]',
    '"polypharmacy"[Title/Abstract] AND elderly',
    '"smoking cessation"[Title/Abstract] AND intervention',
    '"obesity management"[Title/Abstract] AND primary care',
    # Pain Management
    '"chronic pain"[Title/Abstract] AND management',
    '"opioid"[Title/Abstract] AND (prescribing OR stewardship)',
    '"neuropathic pain"[Title/Abstract] AND treatment',
    '"palliative care"[Title/Abstract]',
    '"interventional pain"[Title/Abstract] AND management',
    '"spinal cord stimulation"[Title/Abstract]',
    # Geriatrics
    '"geriatric"[Title/Abstract] AND (syndrome OR assessment)',
    '"falls"[Title/Abstract] AND (prevention OR elderly)',
    '"frailty"[Title/Abstract] AND management',
    '"delirium"[Title/Abstract] AND (elderly OR treatment)',
    '"nursing home"[Title/Abstract] AND (care OR quality)',
    '"end of life"[Title/Abstract] AND care',
    # Sports Medicine
    '"sports medicine"[Title/Abstract] AND treatment',
    '"concussion"[Title/Abstract] AND (sport OR management)',
    '"exercise-induced"[Title/Abstract] AND (asthma OR injury)',
    '"overuse injury"[Title/Abstract] AND treatment',
    '"muscle strain"[Title/Abstract] AND treatment',
    '"athletic injury"[Title/Abstract] AND rehabilitation',
    # Physical Medicine / Rehabilitation
    '"rehabilitation"[Title/Abstract] AND (stroke OR injury)',
    '"physical therapy"[Title/Abstract] AND outcome',
    '"occupational therapy"[Title/Abstract] AND intervention',
    '"prosthetics"[Title/Abstract] AND (limb OR rehabilitation)',
    '"spasticity"[Title/Abstract] AND treatment',
    '"wheelchair"[Title/Abstract] AND assessment',
    # Nuclear Medicine / Radiology
    '"PET scan"[Title/Abstract] AND (diagnosis OR oncology)',
    '"CT scan"[Title/Abstract] AND (diagnosis OR protocol)',
    '"MRI"[Title/Abstract] AND (diagnostic OR imaging)',
    '"ultrasound"[Title/Abstract] AND (diagnosis OR guided)',
    '"interventional radiology"[Title/Abstract] AND treatment',
    '"radiation therapy"[Title/Abstract] AND cancer',
    # Genetics / Genomics
    '"genetic testing"[Title/Abstract] AND (cancer OR disease)',
    '"hereditary"[Title/Abstract] AND (cancer OR syndrome)',
    '"pharmacogenomics"[Title/Abstract]',
    '"gene therapy"[Title/Abstract] AND treatment',
    '"CRISPR"[Title/Abstract] AND therapy',
    '"rare disease"[Title/Abstract] AND (diagnosis OR treatment)',
]

# HIGH-VOLUME QUERIES - Broad terms to maximize paper count
HIGH_VOLUME_QUERIES = [
    # Mega broad medical terms (10K-100K+ papers each)
    '"clinical trial"[Title/Abstract]',
    '"randomized controlled"[Title/Abstract]',
    '"meta-analysis"[Title/Abstract]',
    '"systematic review"[Title/Abstract]',
    '"cohort study"[Title/Abstract]',
    '"case-control"[Title/Abstract]',
    '"retrospective study"[Title/Abstract]',
    '"prospective study"[Title/Abstract]',
    '"treatment outcome"[Title/Abstract]',
    '"patient outcome"[Title/Abstract]',
    '"drug therapy"[Title/Abstract]',
    '"surgical treatment"[Title/Abstract]',
    '"diagnostic accuracy"[Title/Abstract]',
    '"prognosis"[Title/Abstract]',
    '"mortality"[Title/Abstract]',
    '"survival"[Title/Abstract]',
    '"efficacy"[Title/Abstract]',
    '"safety"[Title/Abstract]',
    '"adverse events"[Title/Abstract]',
    '"side effects"[Title/Abstract]',
    # Major disease categories
    '"cancer"[Title/Abstract] AND treatment',
    '"cardiovascular"[Title/Abstract] AND disease',
    '"infectious disease"[Title/Abstract]',
    '"autoimmune"[Title/Abstract]',
    '"inflammation"[Title/Abstract]',
    '"metabolic"[Title/Abstract] AND disease',
    '"neurological"[Title/Abstract]',
    '"psychiatric"[Title/Abstract]',
    '"respiratory"[Title/Abstract]',
    '"gastrointestinal"[Title/Abstract]',
    '"renal"[Title/Abstract]',
    '"hepatic"[Title/Abstract]',
    '"endocrine"[Title/Abstract]',
    '"hematologic"[Title/Abstract]',
    '"musculoskeletal"[Title/Abstract]',
    '"dermatologic"[Title/Abstract]',
    '"ophthalmologic"[Title/Abstract]',
    '"pediatric"[Title/Abstract]',
    '"geriatric"[Title/Abstract]',
    '"obstetric"[Title/Abstract]',
    # Drug classes
    '"antibiotic"[Title/Abstract]',
    '"antiviral"[Title/Abstract]',
    '"antifungal"[Title/Abstract]',
    '"analgesic"[Title/Abstract]',
    '"anti-inflammatory"[Title/Abstract]',
    '"immunotherapy"[Title/Abstract]',
    '"chemotherapy"[Title/Abstract]',
    '"targeted therapy"[Title/Abstract]',
    '"biologic therapy"[Title/Abstract]',
    '"hormone therapy"[Title/Abstract]',
    # Procedures
    '"surgery"[Title/Abstract] AND outcome',
    '"minimally invasive"[Title/Abstract]',
    '"laparoscopic"[Title/Abstract]',
    '"endoscopic"[Title/Abstract]',
    '"robotic surgery"[Title/Abstract]',
    '"transplantation"[Title/Abstract]',
    '"radiation therapy"[Title/Abstract]',
    '"interventional"[Title/Abstract]',
    # Diagnostics
    '"imaging"[Title/Abstract] AND diagnosis',
    '"MRI"[Title/Abstract]',
    '"CT scan"[Title/Abstract]',
    '"ultrasound"[Title/Abstract] AND diagnosis',
    '"PET scan"[Title/Abstract]',
    '"biopsy"[Title/Abstract]',
    '"biomarker"[Title/Abstract]',
    '"screening"[Title/Abstract]',
    # Guidelines & Evidence
    '"guideline"[Title/Abstract]',
    '"recommendation"[Title/Abstract]',
    '"consensus"[Title/Abstract]',
    '"evidence-based"[Title/Abstract]',
    '"best practice"[Title/Abstract]',
    '"standard of care"[Title/Abstract]',
]

NEJM_QUERIES = [
    '"N Engl J Med"[Journal] AND "dermal filler"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "botulinum toxin"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "aesthetic"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "cosmetic"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "skin"[Title/Abstract] AND treatment',
    '"N Engl J Med"[Journal] AND "laser"[Title/Abstract] AND therapy',
    '"N Engl J Med"[Journal] AND "melanoma"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "psoriasis"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "atopic dermatitis"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "immunotherapy"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "cancer"[Title/Abstract] AND treatment',
    '"N Engl J Med"[Journal] AND "cardiovascular"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "diabetes"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "hypertension"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "heart failure"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "stroke"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "sepsis"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "antibiotic"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "vaccine"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "COVID-19"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "obesity"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "GLP-1"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "semaglutide"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "clinical trial"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "randomized"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "guideline"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "surgery"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "transplant"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "arthritis"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "asthma"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "COPD"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "kidney"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "liver"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "lung cancer"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "breast cancer"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "prostate cancer"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "colorectal"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "leukemia"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "lymphoma"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "multiple sclerosis"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "Parkinson"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "Alzheimer"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "epilepsy"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "pain"[Title/Abstract] AND management',
    '"N Engl J Med"[Journal] AND "opioid"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "infection"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "HIV"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "hepatitis"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "gene therapy"[Title/Abstract]',
    '"N Engl J Med"[Journal] AND "CRISPR"[Title/Abstract]',
]

JAMA_QUERIES = [
    '"JAMA"[Journal] AND "dermal filler"[Title/Abstract]',
    '"JAMA"[Journal] AND "botulinum toxin"[Title/Abstract]',
    '"JAMA"[Journal] AND "aesthetic"[Title/Abstract]',
    '"JAMA"[Journal] AND "cosmetic surgery"[Title/Abstract]',
    '"JAMA"[Journal] AND "skin cancer"[Title/Abstract]',
    '"JAMA"[Journal] AND "melanoma"[Title/Abstract]',
    '"JAMA"[Journal] AND "cancer"[Title/Abstract] AND treatment',
    '"JAMA"[Journal] AND "cardiovascular"[Title/Abstract]',
    '"JAMA"[Journal] AND "diabetes"[Title/Abstract]',
    '"JAMA"[Journal] AND "hypertension"[Title/Abstract]',
    '"JAMA"[Journal] AND "stroke"[Title/Abstract]',
    '"JAMA"[Journal] AND "obesity"[Title/Abstract]',
    '"JAMA"[Journal] AND "clinical trial"[Title/Abstract]',
    '"JAMA"[Journal] AND "guideline"[Title/Abstract]',
    '"JAMA"[Journal] AND "screening"[Title/Abstract]',
    '"JAMA"[Journal] AND "prevention"[Title/Abstract]',
    '"JAMA"[Journal] AND "surgery"[Title/Abstract]',
    '"JAMA"[Journal] AND "antibiotic"[Title/Abstract]',
    '"JAMA"[Journal] AND "vaccine"[Title/Abstract]',
    '"JAMA"[Journal] AND "COVID-19"[Title/Abstract]',
    '"JAMA Dermatol"[Journal]',
    '"JAMA Surg"[Journal]',
    '"JAMA Oncol"[Journal]',
    '"JAMA Cardiol"[Journal]',
    '"JAMA Neurol"[Journal]',
    '"JAMA Intern Med"[Journal]',
    '"JAMA Pediatr"[Journal]',
    '"JAMA Ophthalmol"[Journal]',
    '"JAMA Otolaryngol Head Neck Surg"[Journal]',
    '"JAMA Psychiatry"[Journal]',
    '"JAMA Netw Open"[Journal] AND aesthetic',
    '"JAMA Netw Open"[Journal] AND dermatology',
    '"JAMA Netw Open"[Journal] AND cancer',
    '"JAMA Netw Open"[Journal] AND cardiovascular',
    '"JAMA Netw Open"[Journal] AND diabetes',
    '"JAMA Facial Plast Surg"[Journal]',
    '"JAMA Dermatol"[Journal] AND laser',
    '"JAMA Dermatol"[Journal] AND filler',
    '"JAMA Dermatol"[Journal] AND botulinum',
    '"JAMA Dermatol"[Journal] AND psoriasis',
    '"JAMA Dermatol"[Journal] AND atopic dermatitis',
    '"JAMA Dermatol"[Journal] AND melanoma',
    '"JAMA Dermatol"[Journal] AND acne',
    '"JAMA Surg"[Journal] AND plastic',
    '"JAMA Surg"[Journal] AND reconstruction',
    '"JAMA Surg"[Journal] AND minimally invasive',
]

AESTHETIC_JOURNALS_QUERIES = [
    # Dermatologic Surgery
    '"Dermatol Surg"[Journal] AND filler',
    '"Dermatol Surg"[Journal] AND botulinum',
    '"Dermatol Surg"[Journal] AND laser',
    '"Dermatol Surg"[Journal] AND rejuvenation',
    '"Dermatol Surg"[Journal] AND complication',
    '"Dermatol Surg"[Journal] AND cosmetic',
    '"Dermatol Surg"[Journal] AND scar',
    '"Dermatol Surg"[Journal] AND microneedling',
    '"Dermatol Surg"[Journal] AND peel',
    '"Dermatol Surg"[Journal] AND body contouring',
    # Aesthetic Surgery Journal
    '"Aesthet Surg J"[Journal] AND filler',
    '"Aesthet Surg J"[Journal] AND injectable',
    '"Aesthet Surg J"[Journal] AND botulinum',
    '"Aesthet Surg J"[Journal] AND rhinoplasty',
    '"Aesthet Surg J"[Journal] AND facelift',
    '"Aesthet Surg J"[Journal] AND laser',
    '"Aesthet Surg J"[Journal] AND complication',
    '"Aesthet Surg J"[Journal] AND safety',
    '"Aesthet Surg J"[Journal] AND rejuvenation',
    '"Aesthet Surg J"[Journal] AND body',
    '"Aesthet Surg J"[Journal] AND breast',
    '"Aesthet Surg J"[Journal] AND liposuction',
    # Journal of Cosmetic Dermatology
    '"J Cosmet Dermatol"[Journal] AND filler',
    '"J Cosmet Dermatol"[Journal] AND botulinum',
    '"J Cosmet Dermatol"[Journal] AND laser',
    '"J Cosmet Dermatol"[Journal] AND PRP',
    '"J Cosmet Dermatol"[Journal] AND rejuvenation',
    '"J Cosmet Dermatol"[Journal] AND microneedling',
    '"J Cosmet Dermatol"[Journal] AND scar',
    '"J Cosmet Dermatol"[Journal] AND hyperpigmentation',
    '"J Cosmet Dermatol"[Journal] AND melasma',
    '"J Cosmet Dermatol"[Journal] AND hair',
    # Plastic and Reconstructive Surgery
    '"Plast Reconstr Surg"[Journal] AND filler',
    '"Plast Reconstr Surg"[Journal] AND injectable',
    '"Plast Reconstr Surg"[Journal] AND botulinum',
    '"Plast Reconstr Surg"[Journal] AND aesthetic',
    '"Plast Reconstr Surg"[Journal] AND facelift',
    '"Plast Reconstr Surg"[Journal] AND complication',
    '"Plast Reconstr Surg"[Journal] AND fat graft',
    '"Plast Reconstr Surg"[Journal] AND rhinoplasty',
    '"Plast Reconstr Surg"[Journal] AND breast augmentation',
    '"Plast Reconstr Surg"[Journal] AND body contouring',
    # JAAD - Journal of the American Academy of Dermatology
    '"J Am Acad Dermatol"[Journal] AND filler',
    '"J Am Acad Dermatol"[Journal] AND botulinum',
    '"J Am Acad Dermatol"[Journal] AND laser',
    '"J Am Acad Dermatol"[Journal] AND cosmetic',
    '"J Am Acad Dermatol"[Journal] AND acne',
    '"J Am Acad Dermatol"[Journal] AND melasma',
    '"J Am Acad Dermatol"[Journal] AND psoriasis',
    '"J Am Acad Dermatol"[Journal] AND atopic dermatitis',
    '"J Am Acad Dermatol"[Journal] AND skin cancer',
    '"J Am Acad Dermatol"[Journal] AND guideline',
    # Lasers in Surgery and Medicine
    '"Lasers Surg Med"[Journal] AND skin',
    '"Lasers Surg Med"[Journal] AND rejuvenation',
    '"Lasers Surg Med"[Journal] AND scar',
    '"Lasers Surg Med"[Journal] AND pigment',
    '"Lasers Surg Med"[Journal] AND vascular',
    '"Lasers Surg Med"[Journal] AND fractional',
    '"Lasers Surg Med"[Journal] AND tattoo',
    '"Lasers Surg Med"[Journal] AND hair removal',
    # Aesthetic Plastic Surgery
    '"Aesthetic Plast Surg"[Journal] AND filler',
    '"Aesthetic Plast Surg"[Journal] AND injectable',
    '"Aesthetic Plast Surg"[Journal] AND botulinum',
    '"Aesthetic Plast Surg"[Journal] AND facelift',
    '"Aesthetic Plast Surg"[Journal] AND rhinoplasty',
    '"Aesthetic Plast Surg"[Journal] AND complication',
    '"Aesthetic Plast Surg"[Journal] AND liposuction',
    '"Aesthetic Plast Surg"[Journal] AND breast',
    # Journal of Cutaneous and Aesthetic Surgery
    '"J Cutan Aesthet Surg"[Journal] AND filler',
    '"J Cutan Aesthet Surg"[Journal] AND laser',
    '"J Cutan Aesthet Surg"[Journal] AND scar',
    '"J Cutan Aesthet Surg"[Journal] AND PRP',
    '"J Cutan Aesthet Surg"[Journal] AND rejuvenation',
    # Clinical Cosmetic and Investigational Dermatology
    '"Clin Cosmet Investig Dermatol"[Journal] AND filler',
    '"Clin Cosmet Investig Dermatol"[Journal] AND laser',
    '"Clin Cosmet Investig Dermatol"[Journal] AND botulinum',
    '"Clin Cosmet Investig Dermatol"[Journal] AND skin',
    '"Clin Cosmet Investig Dermatol"[Journal] AND rejuvenation',
    # Journal of Drugs in Dermatology
    '"J Drugs Dermatol"[Journal] AND filler',
    '"J Drugs Dermatol"[Journal] AND botulinum',
    '"J Drugs Dermatol"[Journal] AND laser',
    '"J Drugs Dermatol"[Journal] AND cosmetic',
    '"J Drugs Dermatol"[Journal] AND acne',
    '"J Drugs Dermatol"[Journal] AND antiaging',
    # Dermatologic Therapy
    '"Dermatol Ther"[Journal] AND filler',
    '"Dermatol Ther"[Journal] AND laser',
    '"Dermatol Ther"[Journal] AND cosmetic',
    '"Dermatol Ther"[Journal] AND melasma',
    '"Dermatol Ther"[Journal] AND scar',
    # British Journal of Dermatology
    '"Br J Dermatol"[Journal] AND laser',
    '"Br J Dermatol"[Journal] AND cosmetic',
    '"Br J Dermatol"[Journal] AND filler',
    '"Br J Dermatol"[Journal] AND psoriasis AND treatment',
    '"Br J Dermatol"[Journal] AND atopic dermatitis AND treatment',
    # Archives of Dermatological Research
    '"Arch Dermatol Res"[Journal] AND aesthetic',
    '"Arch Dermatol Res"[Journal] AND laser',
    '"Arch Dermatol Res"[Journal] AND skin aging',
    # Journal of Cosmetic and Laser Therapy
    '"J Cosmet Laser Ther"[Journal] AND filler',
    '"J Cosmet Laser Ther"[Journal] AND laser',
    '"J Cosmet Laser Ther"[Journal] AND rejuvenation',
    '"J Cosmet Laser Ther"[Journal] AND IPL',
    '"J Cosmet Laser Ther"[Journal] AND scar',
    # International Journal of Dermatology
    '"Int J Dermatol"[Journal] AND filler',
    '"Int J Dermatol"[Journal] AND laser',
    '"Int J Dermatol"[Journal] AND cosmetic',
    '"Int J Dermatol"[Journal] AND melasma',
    # Skin Research and Technology
    '"Skin Res Technol"[Journal] AND laser',
    '"Skin Res Technol"[Journal] AND rejuvenation',
    '"Skin Res Technol"[Journal] AND filler',
    '"Skin Res Technol"[Journal] AND skin aging',
    # Annals of Plastic Surgery
    '"Ann Plast Surg"[Journal] AND filler',
    '"Ann Plast Surg"[Journal] AND injectable',
    '"Ann Plast Surg"[Journal] AND aesthetic',
    '"Ann Plast Surg"[Journal] AND facelift',
    '"Ann Plast Surg"[Journal] AND fat graft',
    # Facial Plastic Surgery & Aesthetic Medicine
    '"Facial Plast Surg Aesthet Med"[Journal] AND filler',
    '"Facial Plast Surg Aesthet Med"[Journal] AND botulinum',
    '"Facial Plast Surg Aesthet Med"[Journal] AND rhinoplasty',
    '"Facial Plast Surg Aesthet Med"[Journal] AND rejuvenation',
    '"Facial Plast Surg Aesthet Med"[Journal] AND complication',
    # Journal of Plastic Reconstructive and Aesthetic Surgery
    '"J Plast Reconstr Aesthet Surg"[Journal] AND filler',
    '"J Plast Reconstr Aesthet Surg"[Journal] AND injectable',
    '"J Plast Reconstr Aesthet Surg"[Journal] AND aesthetic',
    '"J Plast Reconstr Aesthet Surg"[Journal] AND facelift',
    '"J Plast Reconstr Aesthet Surg"[Journal] AND complication',
]

NCCN_QUERIES = [
    '"NCCN"[Title/Abstract] AND guideline',
    '"NCCN"[Title/Abstract] AND recommendation',
    '"NCCN"[Title/Abstract] AND treatment',
    '"NCCN"[Title/Abstract] AND cancer',
    '"NCCN"[Title/Abstract] AND melanoma',
    '"NCCN"[Title/Abstract] AND breast cancer',
    '"NCCN"[Title/Abstract] AND lung cancer',
    '"NCCN"[Title/Abstract] AND colorectal',
    '"NCCN"[Title/Abstract] AND prostate',
    '"NCCN"[Title/Abstract] AND lymphoma',
    '"NCCN"[Title/Abstract] AND leukemia',
    '"NCCN"[Title/Abstract] AND pancreatic',
    '"NCCN"[Title/Abstract] AND ovarian',
    '"NCCN"[Title/Abstract] AND head neck',
    '"NCCN"[Title/Abstract] AND thyroid cancer',
    '"NCCN"[Title/Abstract] AND bladder',
    '"NCCN"[Title/Abstract] AND renal cell',
    '"NCCN"[Title/Abstract] AND sarcoma',
    '"NCCN"[Title/Abstract] AND myeloma',
    '"NCCN"[Title/Abstract] AND antiemesis',
    '"NCCN"[Title/Abstract] AND supportive care',
    '"NCCN"[Title/Abstract] AND survivorship',
    '"NCCN"[Title/Abstract] AND screening',
    '"NCCN"[Title/Abstract] AND genetic testing',
    '"NCCN"[Title/Abstract] AND immunotherapy',
    '"National Comprehensive Cancer Network"[Title/Abstract]',
    '"NCCN Clinical Practice Guidelines"[Title/Abstract]',
    '"NCCN"[Title/Abstract] AND evidence block',
    '"NCCN"[Title/Abstract] AND risk stratification',
    '"NCCN"[Title/Abstract] AND staging',
]

# Combined query dictionary by domain
DOMAIN_QUERIES = {
    "aesthetic_medicine": AESTHETIC_MEDICINE_QUERIES,
    "dental_medicine": DENTAL_MEDICINE_QUERIES,
    "general_medicine": GENERAL_MEDICINE_QUERIES,
    "high_volume": HIGH_VOLUME_QUERIES,
    "nejm": NEJM_QUERIES,
    "jama": JAMA_QUERIES,
    "nccn": NCCN_QUERIES,
    "aesthetic_journals": AESTHETIC_JOURNALS_QUERIES,
}


def ensure_sync_tables():
    """Create sync tracking tables if they don't exist."""
    ddl = """
    CREATE TABLE IF NOT EXISTS publication_syncs (
        id SERIAL PRIMARY KEY,
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        completed_at TIMESTAMPTZ,
        status TEXT NOT NULL DEFAULT 'running',
        papers_found INTEGER DEFAULT 0,
        papers_downloaded INTEGER DEFAULT 0,
        papers_ingested INTEGER DEFAULT 0,
        papers_skipped INTEGER DEFAULT 0,
        error_message TEXT,
        date_range_start DATE,
        date_range_end DATE
    );
    
    CREATE INDEX IF NOT EXISTS idx_syncs_started_at ON publication_syncs(started_at DESC);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))


def get_last_sync_date(db: Session) -> Optional[datetime]:
    """Get the date of the last successful sync."""
    row = db.execute(text("""
        SELECT date_range_end FROM publication_syncs
        WHERE status = 'completed'
        ORDER BY completed_at DESC
        LIMIT 1
    """)).fetchone()
    return row[0] if row else None


def create_sync_record(db: Session, date_start: datetime, date_end: datetime) -> int:
    """Create a new sync record and return its ID."""
    result = db.execute(text("""
        INSERT INTO publication_syncs (date_range_start, date_range_end, status)
        VALUES (:start, :end, 'running')
        RETURNING id
    """), {"start": date_start.date() if hasattr(date_start, 'date') and callable(date_start.date) else date_start, 
           "end": date_end.date() if hasattr(date_end, 'date') and callable(date_end.date) else date_end})
    db.commit()
    row = result.fetchone()
    return row[0] if row else 0


_ALLOWED_SYNC_COLUMNS = frozenset({
    "completed_at", "status", "papers_found", "papers_downloaded",
    "papers_ingested", "papers_skipped", "error_message",
    "date_range_start", "date_range_end",
})


_publication_syncs_table = table(
    "publication_syncs",
    column("id"),
    *[column(c) for c in _ALLOWED_SYNC_COLUMNS],
)


def update_sync_record(db: Session, sync_id: int, **kwargs):
    """Update sync record with progress."""
    invalid = kwargs.keys() - _ALLOWED_SYNC_COLUMNS
    if invalid:
        raise ValueError(f"Invalid column(s) for publication_syncs update: {invalid}")
    stmt = (
        update(_publication_syncs_table)
        .where(_publication_syncs_table.c.id == sync_id)
        .values(**kwargs)
    )
    db.execute(stmt)
    db.commit()


def search_pubmed(query: str, date_from: str, date_to: str, retmax: int = 500) -> list:
    """Search PubMed (not PMC) for papers — returns PMIDs. Covers all indexed abstracts."""
    params = {
        "db": "pubmed",
        "term": f'{query} AND ("{date_from}"[PDAT] : "{date_to}"[PDAT])',
        "retmax": retmax,
        "retmode": "json",
        "sort": "pub_date",
    }
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    try:
        resp = requests.get(ESEARCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        logger.warning(f"PubMed search failed: {e}")
        return []


def fetch_pubmed_abstract(pmid: str) -> Optional[dict]:
    """Fetch article metadata + abstract from PubMed by PMID."""
    try:
        params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
        api_key = os.environ.get("NCBI_API_KEY")
        if api_key:
            params["api_key"] = api_key
        resp = requests.get(EFETCH_URL, params=params, timeout=30)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        article = root.find(".//PubmedArticle")
        if article is None:
            return None

        medline = article.find(".//MedlineCitation")
        if medline is None:
            return None

        art = medline.find("Article")
        if art is None:
            return None

        title_el = art.find("ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""

        abstract_parts = []
        abstract_el = art.find("Abstract")
        if abstract_el is not None:
            for at in abstract_el.findall("AbstractText"):
                label = at.get("Label", "")
                txt = "".join(at.itertext()).strip()
                if label:
                    abstract_parts.append(f"{label}: {txt}")
                else:
                    abstract_parts.append(txt)
        abstract = "\n".join(abstract_parts)

        journal_el = art.find(".//Journal/Title")
        journal = journal_el.text.strip() if journal_el is not None and journal_el.text else ""

        year = None
        year_el = art.find(".//Journal/JournalIssue/PubDate/Year")
        if year_el is None:
            year_el = art.find(".//ArticleDate/Year")
        if year_el is not None and year_el.text and year_el.text.strip().isdigit():
            year = int(year_el.text.strip())
        else:
            medline_date_el = art.find(".//Journal/JournalIssue/PubDate/MedlineDate")
            if medline_date_el is not None and medline_date_el.text:
                import re as _re
                m = _re.search(r'((?:19|20)\d{2})', medline_date_el.text)
                if m:
                    year = int(m.group(1))

        authors = []
        for author in art.findall(".//AuthorList/Author"):
            lname = author.find("LastName")
            fname = author.find("ForeName")
            if lname is not None and lname.text:
                name = lname.text
                if fname is not None and fname.text:
                    name = f"{fname.text} {name}"
                authors.append(name)
        author_str = ", ".join(authors[:5])
        if len(authors) > 5:
            author_str += " et al."

        doi_el = None
        for eid in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if eid.get("IdType") == "doi":
                doi_el = eid
                break
        doi = doi_el.text.strip() if doi_el is not None and doi_el.text else ""

        return {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "year": year,
            "journal": journal,
            "authors": author_str,
            "doi": doi,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch PMID {pmid}: {e}")
        return None



def ingest_pubmed_paper(db: Session, paper: dict, domain: str = "general_medicine") -> bool:
    """Ingest a PubMed abstract-only paper into the database.
    Skips if richer full-text chunks already exist for this paper."""
    try:
        source_id = f"PMID_{paper['pmid']}"
        title = paper["title"][:500] if paper.get("title") else "Untitled"
        year = paper.get("year")
        journal = paper.get("journal", "")[:200]
        authors = paper.get("authors", "")[:300]
        doi = paper.get("doi", "")

        content = f"{title}\n\n{paper.get('abstract', '')}"
        content = content.strip()

        if len(content) < 100:
            logger.debug(f"Skipping PMID {paper['pmid']}: content too short")
            return False

        url = ""
        if doi:
            url = f"https://doi.org/{doi}"
        else:
            url = f"https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/"

        result = db.execute(text("""
            INSERT INTO documents (source_id, title, authors, year, organization_or_journal, domain, document_type, status, url)
            VALUES (:sid, :title, :authors, :year, :journal, :domain, 'journal_article', 'active', :url)
            ON CONFLICT (source_id) DO UPDATE SET
                title = EXCLUDED.title,
                authors = EXCLUDED.authors,
                year = EXCLUDED.year,
                organization_or_journal = EXCLUDED.organization_or_journal,
                domain = EXCLUDED.domain,
                url = EXCLUDED.url,
                updated_at = now()
            RETURNING id
        """), {
            "sid": source_id,
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "domain": domain,
            "url": url,
        })
        doc_id = result.scalar_one()

        existing_chunks = db.execute(text(
            "SELECT COUNT(*), COALESCE(MAX(length(text)),0) FROM chunks WHERE document_id = :doc_id"
        ), {"doc_id": doc_id}).fetchone()
        existing_count = existing_chunks[0] if existing_chunks else 0
        existing_max_len = existing_chunks[1] if existing_chunks else 0

        if existing_count > 0 and existing_max_len > len(content):
            db.commit()
            return True

        chunk_text_content = content[:8000]
        embedding_list = embed_text(chunk_text_content)
        if not embedding_list:
            return False

        db.execute(text("DELETE FROM chunks WHERE document_id = :doc_id"), {"doc_id": doc_id})

        db.execute(text("""
            INSERT INTO chunks (document_id, chunk_index, text, page_or_section, evidence_level, embedding)
            VALUES (:doc_id, 0, :text, 'abstract', NULL, :emb)
        """), {
            "doc_id": doc_id,
            "text": chunk_text_content,
            "emb": str(embedding_list),
        })

        db.commit()
        return True

    except Exception as e:
        logger.error(f"Failed to ingest PMID {paper.get('pmid')}: {e}")
        db.rollback()
        return False


def run_journal_sync(journals: list = None, years_back: int = 10, max_per_query: int = 500) -> dict:
    """
    Targeted sync for specific high-impact journals (NEJM, JAMA, NCCN).
    Searches PubMed for abstracts (not just PMC open-access).
    """
    ensure_sync_tables()
    db = SessionLocal()

    if journals is None:
        journals = ["nejm", "jama", "nccn"]

    journal_domain_map = {
        "nejm": "general_medicine",
        "jama": "general_medicine",
        "nccn": "general_medicine",
        "aesthetic_journals": "aesthetic_medicine",
    }

    try:
        date_end = datetime.now()
        date_start = date_end - timedelta(days=years_back * 365)
        sync_id = create_sync_record(db, date_start, date_end)

        date_from = date_start.strftime("%Y/%m/%d")
        date_to = date_end.strftime("%Y/%m/%d")

        logger.info(f"Journal sync #{sync_id}: {journals}, {date_start.strftime('%Y-%m-%d')} to {date_end.strftime('%Y-%m-%d')}")

        total_found = 0
        total_ingested = 0
        total_skipped = 0
        journal_stats = {}
        global_seen_pmids = set()

        for journal_key in journals:
            queries = DOMAIN_QUERIES.get(journal_key, [])
            if not queries:
                logger.warning(f"No queries for journal: {journal_key}")
                continue

            domain = journal_domain_map.get(journal_key, "general_medicine")
            all_pmids = set()

            logger.info(f"[{journal_key}] Searching {len(queries)} queries...")
            for query in queries:
                time.sleep(0.35)
                pmids = search_pubmed(query, date_from, date_to, retmax=max_per_query)
                all_pmids.update(pmids)
                if pmids:
                    logger.info(f"[{journal_key}] +{len(pmids)} PMIDs: {query[:60]}...")

            all_pmids -= global_seen_pmids
            global_seen_pmids.update(all_pmids)
            logger.info(f"[{journal_key}] Total unique PMIDs (after global dedup): {len(all_pmids)}")
            total_found += len(all_pmids)

            ingested = 0
            skipped = 0

            for pmid in all_pmids:
                source_id = f"PMID_{pmid}"
                if paper_exists(db, source_id):
                    skipped += 1
                    continue

                time.sleep(0.15)
                paper = fetch_pubmed_abstract(pmid)
                if paper and ingest_pubmed_paper(db, paper, domain=domain):
                    ingested += 1
                    if ingested % 50 == 0:
                        logger.info(f"[{journal_key}] Ingested {ingested} papers so far...")

            total_ingested += ingested
            total_skipped += skipped
            journal_stats[journal_key] = {"found": len(all_pmids), "ingested": ingested, "skipped": skipped}
            logger.info(f"[{journal_key}] Done: {ingested} ingested, {skipped} skipped")

        update_sync_record(
            db, sync_id,
            status="completed",
            completed_at=datetime.now(),
            papers_found=total_found,
            papers_downloaded=total_ingested,
            papers_ingested=total_ingested,
            papers_skipped=total_skipped,
        )

        result = {
            "sync_id": sync_id,
            "status": "completed",
            "journals": journals,
            "date_range": f"{date_start.strftime('%Y-%m-%d')} to {date_end.strftime('%Y-%m-%d')}",
            "total_found": total_found,
            "total_ingested": total_ingested,
            "total_skipped": total_skipped,
            "journal_stats": journal_stats,
        }
        logger.info(f"Journal sync completed: {result}")
        return result

    except Exception as e:
        logger.error(f"Journal sync failed: {e}")
        if 'sync_id' in locals():
            update_sync_record(db, sync_id, status="failed", error_message=str(e))
        raise
    finally:
        db.close()


def search_pmc(query: str, date_from: str, date_to: str, retmax: int = 100) -> list:
    """Search PubMed Central for papers matching query in date range."""
    params = {
        "db": "pmc",
        "term": f'{query} AND ("{date_from}"[PDAT] : "{date_to}"[PDAT])',
        "retmax": retmax,
        "retmode": "json",
        "sort": "pub_date",
    }
    # Add API key if available (allows 10 req/sec instead of 3)
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    try:
        resp = requests.get(ESEARCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        logger.warning(f"Search failed for query: {e}")
        return []


def fetch_paper_metadata(pmc_id: str) -> Optional[dict]:
    """Fetch paper metadata from PMC."""
    try:
        params = {"db": "pmc", "id": pmc_id, "retmode": "xml"}
        # Add API key if available (allows 10 req/sec instead of 3)
        api_key = os.environ.get("NCBI_API_KEY")
        if api_key:
            params["api_key"] = api_key
        resp = requests.get(EFETCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        
        root = ET.fromstring(resp.content)
        article = root.find(".//article")
        if article is None:
            return None
        
        front = article.find(".//front")
        if front is None:
            return None
        
        title_el = front.find(".//article-title")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""
        
        abstract_el = front.find(".//abstract")
        abstract = "".join(abstract_el.itertext()).strip() if abstract_el is not None else ""
        
        year_el = front.find(".//pub-date/year")
        year = int(year_el.text) if year_el is not None and year_el.text else None
        
        journal_el = front.find(".//journal-title")
        journal = journal_el.text.strip() if journal_el is not None and journal_el.text else ""
        
        body = article.find(".//body")
        body_text = "".join(body.itertext()).strip() if body is not None else ""
        
        return {
            "pmc_id": f"PMC{pmc_id}",
            "title": title,
            "abstract": abstract,
            "year": year,
            "journal": journal,
            "full_text": body_text,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch PMC{pmc_id}: {e}")
        return None


def paper_exists(db: Session, source_id: str) -> bool:
    """Check if paper already exists in database."""
    result = db.execute(
        text("SELECT 1 FROM documents WHERE source_id = :sid LIMIT 1"),
        {"sid": source_id}
    ).fetchone()
    return result is not None


def ingest_paper(db: Session, paper: dict, domain: str = "aesthetic_medicine") -> bool:
    """Ingest a paper into the database."""
    try:
        source_id = paper["pmc_id"]
        title = paper["title"][:500] if paper["title"] else "Untitled"
        year = paper.get("year")
        journal = paper.get("journal", "")[:200]
        
        content = f"{title}\n\n{paper.get('abstract', '')}\n\n{paper.get('full_text', '')}"
        content = content.strip()
        
        if len(content) < 200:
            logger.debug(f"Skipping {source_id}: content too short")
            return False
        
        # Insert document and get the document ID
        result = db.execute(text("""
            INSERT INTO documents (source_id, title, year, organization_or_journal, domain, document_type, status)
            VALUES (:sid, :title, :year, :journal, :domain, 'review', 'active')
            ON CONFLICT (source_id) DO UPDATE SET
                title = EXCLUDED.title,
                year = EXCLUDED.year,
                organization_or_journal = EXCLUDED.organization_or_journal,
                domain = EXCLUDED.domain,
                updated_at = now()
            RETURNING id
        """), {
            "sid": source_id,
            "title": title,
            "year": year,
            "journal": journal,
            "domain": domain,
        })
        doc_id = result.scalar_one()
        
        chunk_text = content[:8000]
        
        embedding_list = embed_text(chunk_text)
        if not embedding_list:
            return False
        
        # Delete existing chunks for this document
        db.execute(text("DELETE FROM chunks WHERE document_id = :doc_id"), {"doc_id": doc_id})
        
        # Insert chunk using document_id and str(embedding)
        db.execute(text("""
            INSERT INTO chunks (document_id, chunk_index, text, page_or_section, evidence_level, embedding)
            VALUES (:doc_id, 0, :text, 'p1-c0', NULL, :emb)
        """), {
            "doc_id": doc_id,
            "text": chunk_text,
            "emb": str(embedding_list),
        })
        
        db.commit()
        return True
        
    except Exception as e:
        logger.error(f"Failed to ingest {paper.get('pmc_id')}: {e}")
        db.rollback()
        return False


def run_sync(days_back: int = 7, max_papers_per_query: int = 20, domains: Optional[list] = None) -> dict:
    """
    Run the publication sync agent.
    
    Args:
        days_back: How many days back to search (default 7 for weekly sync)
        max_papers_per_query: Max papers to fetch per query
        domains: List of domains to sync (default: all domains)
    
    Returns:
        dict with sync statistics
    """
    ensure_sync_tables()
    db = SessionLocal()
    
    # Default to all domains
    if domains is None:
        domains = list(DOMAIN_QUERIES.keys())
    
    try:
        date_end = datetime.now()
        last_sync = get_last_sync_date(db)
        
        if last_sync:
            if hasattr(last_sync, 'date'):
                date_start = datetime.combine(last_sync, datetime.min.time()) if isinstance(last_sync, type(date_end.date())) else last_sync
            else:
                date_start = last_sync
            logger.info(f"Continuing from last sync: {date_start.strftime('%Y-%m-%d')}")
        else:
            date_start = date_end - timedelta(days=days_back)
            logger.info(f"First sync, searching last {days_back} days")
        
        sync_id = create_sync_record(db, date_start, date_end)
        logger.info(f"Started sync #{sync_id}: {date_start.strftime('%Y-%m-%d')} to {date_end.strftime('%Y-%m-%d')}")
        logger.info(f"Syncing domains: {', '.join(domains)}")
        
        date_from = date_start.strftime("%Y/%m/%d")
        date_to = date_end.strftime("%Y/%m/%d")
        
        # Track papers per domain
        domain_papers = {domain: set() for domain in domains}
        total_found = 0
        
        for domain in domains:
            queries = DOMAIN_QUERIES.get(domain, [])
            logger.info(f"Processing {domain}: {len(queries)} queries")
            
            for query in queries:
                time.sleep(0.5)
                ids = search_pmc(query, date_from, date_to, retmax=max_papers_per_query)
                domain_papers[domain].update(ids)
                if ids:
                    logger.info(f"[{domain}] Found {len(ids)} papers: {query[:50]}...")
            
            logger.info(f"[{domain}] Total unique papers: {len(domain_papers[domain])}")
            total_found += len(domain_papers[domain])
        
        update_sync_record(db, sync_id, papers_found=total_found)
        logger.info(f"Total papers found across all domains: {total_found}")
        
        downloaded = 0
        ingested = 0
        skipped = 0
        domain_stats = {domain: {"ingested": 0, "skipped": 0} for domain in domains}
        
        for domain in domains:
            for pmc_id in domain_papers[domain]:
                source_id = f"PMC{pmc_id}"
                
                if paper_exists(db, source_id):
                    skipped += 1
                    domain_stats[domain]["skipped"] += 1
                    continue
                
                time.sleep(0.3)
                paper = fetch_paper_metadata(pmc_id)
                
                if paper:
                    downloaded += 1
                    if ingest_paper(db, paper, domain=domain):
                        ingested += 1
                        domain_stats[domain]["ingested"] += 1
                        logger.info(f"[{domain}] Ingested: {paper['title'][:60]}...")
        
        update_sync_record(
            db, sync_id,
            status="completed",
            completed_at=datetime.now(),
            papers_downloaded=downloaded,
            papers_ingested=ingested,
            papers_skipped=skipped
        )
        
        result = {
            "sync_id": sync_id,
            "status": "completed",
            "date_range": f"{date_start.strftime('%Y-%m-%d')} to {date_end.strftime('%Y-%m-%d')}",
            "domains_synced": domains,
            "papers_found": total_found,
            "papers_downloaded": downloaded,
            "papers_ingested": ingested,
            "papers_skipped": skipped,
            "domain_stats": domain_stats,
        }
        
        logger.info(f"Sync completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        if 'sync_id' in locals():
            update_sync_record(db, sync_id, status="failed", error_message=str(e))
        raise
    finally:
        db.close()


def get_sync_status(db: Session, limit: int = 10) -> list:
    """Get recent sync history."""
    rows = db.execute(text("""
        SELECT id, started_at, completed_at, status, papers_found, 
               papers_downloaded, papers_ingested, papers_skipped, error_message
        FROM publication_syncs
        ORDER BY started_at DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().fetchall()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AesthetiCite Publication Sync Agent")
    parser.add_argument("--days", type=int, default=7, help="Days back to search")
    parser.add_argument("--max-per-query", type=int, default=20, help="Max papers per query")
    args = parser.parse_args()
    
    result = run_sync(days_back=args.days, max_papers_per_query=args.max_per_query)
    print(json.dumps(result, indent=2, default=str))
