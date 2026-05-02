from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
SAMPLE_DIR = ROOT / "sample_folder"
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024


def load_env(path: Path = ROOT / ".env") -> None:
    # Tiny .env loader so this stays a one-file Python app. Good enough for dev.
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env()


# This is the product brain for now: known biomarkers, rough ranges, and plain
# English guidance. The AI layer below only rewrites the summary if a key exists.
BIOMARKERS = [
    {
        "key": "vitamin_d",
        "name": "Vitamin D",
        "aliases": ["vitamin d", "25-oh vitamin d", "25 hydroxy vitamin d", "25(oh)d"],
        "unit": "ng/mL",
        "low": 30,
        "high": 100,
        "optimal_low": 40,
        "optimal_high": 70,
        "category": "Vitamins",
        "tips_low": [
            "Get sensible morning sunlight exposure when possible.",
            "Add vitamin D rich foods like eggs, fortified dairy, mushrooms, or fatty fish.",
            "Ask a clinician whether supplementation is appropriate for your report and history.",
        ],
        "tips_high": [
            "Avoid extra supplementation until a clinician reviews your level.",
            "Check calcium and kidney-related markers with your doctor.",
        ],
        "praise": "Great vitamin D status. This supports bone, immune, and muscle health.",
    },
    {
        "key": "vitamin_b12",
        "name": "Vitamin B12",
        "aliases": ["vitamin b12", "b12", "cobalamin"],
        "unit": "pg/mL",
        "low": 200,
        "high": 900,
        "optimal_low": 400,
        "optimal_high": 800,
        "category": "Vitamins",
        "tips_low": [
            "Consider B12-rich foods such as eggs, dairy, fish, meat, or fortified foods.",
            "If vegetarian or vegan, discuss a B12 supplement plan with a clinician.",
            "If symptoms exist, ask about methylmalonic acid or homocysteine testing.",
        ],
        "tips_high": [
            "Review supplements and injections with a clinician.",
            "If not supplementing, ask your doctor whether follow-up testing is needed.",
        ],
        "praise": "B12 looks strong. That is helpful for red blood cells and nerve function.",
    },
    {
        "key": "ferritin",
        "name": "Ferritin",
        "aliases": ["ferritin"],
        "unit": "ng/mL",
        "low": 30,
        "high": 300,
        "optimal_low": 50,
        "optimal_high": 150,
        "category": "Iron",
        "tips_low": [
            "Pair iron-rich foods with vitamin C to improve absorption.",
            "Avoid tea or coffee right with high-iron meals.",
            "Discuss iron supplementation only after a clinician reviews CBC and iron studies.",
        ],
        "tips_high": [
            "Do not take iron supplements unless prescribed.",
            "Ask about inflammation, liver markers, and full iron studies.",
        ],
        "praise": "Ferritin is in a useful zone for iron storage.",
    },
    {
        "key": "hemoglobin",
        "name": "Hemoglobin",
        "aliases": ["hemoglobin", "haemoglobin", "hb"],
        "unit": "g/dL",
        "low": 12,
        "high": 17.5,
        "optimal_low": 13,
        "optimal_high": 16,
        "category": "Blood",
        "tips_low": [
            "Review iron, B12, folate, and bleeding history with a clinician.",
            "Include protein and micronutrient-dense foods consistently.",
        ],
        "tips_high": [
            "Hydration status, altitude, smoking, and sleep breathing can affect this.",
            "Share this with a clinician if it stays elevated.",
        ],
        "praise": "Hemoglobin looks steady, which is good for oxygen transport.",
    },
    {
        "key": "hba1c",
        "name": "HbA1c",
        "aliases": ["hba1c", "a1c", "glycated hemoglobin", "glycosylated hemoglobin"],
        "unit": "%",
        "low": 4.0,
        "high": 5.7,
        "optimal_low": 4.8,
        "optimal_high": 5.4,
        "category": "Metabolic",
        "tips_low": [
            "If you have symptoms of low blood sugar, discuss them with a clinician.",
        ],
        "tips_high": [
            "Build meals around protein, fiber, and minimally processed carbs.",
            "Add a 10-20 minute walk after carb-heavy meals.",
            "Prioritize sleep consistency and resistance training.",
        ],
        "praise": "Excellent glucose trend. Your long-term blood sugar marker looks healthy.",
    },
    {
        "key": "fasting_glucose",
        "name": "Fasting Glucose",
        "aliases": ["fasting glucose", "blood glucose fasting", "glucose fasting", "fasting blood sugar", "fbs"],
        "unit": "mg/dL",
        "low": 70,
        "high": 100,
        "optimal_low": 75,
        "optimal_high": 90,
        "category": "Metabolic",
        "tips_low": [
            "Do not ignore dizziness, shakiness, or fainting symptoms.",
            "Review medication timing and meal pattern with a clinician.",
        ],
        "tips_high": [
            "Reduce liquid sugar and refined snacks.",
            "Use protein-forward breakfasts and regular strength training.",
        ],
        "praise": "Fasting glucose is in a clean range.",
    },
    {
        "key": "tsh",
        "name": "TSH",
        "aliases": ["tsh", "thyroid stimulating hormone"],
        "unit": "mIU/L",
        "low": 0.4,
        "high": 4.0,
        "optimal_low": 0.8,
        "optimal_high": 2.5,
        "category": "Hormones",
        "tips_low": [
            "Ask about free T4, free T3, thyroid antibodies, symptoms, and medications.",
            "Do not change thyroid medication without medical guidance.",
        ],
        "tips_high": [
            "Review free T4, thyroid antibodies, iodine intake, sleep, and stress load.",
            "Ensure adequate selenium, zinc, and protein through food where possible.",
        ],
        "praise": "TSH is sitting in a comfortable thyroid signaling range.",
    },
    {
        "key": "testosterone",
        "name": "Testosterone",
        "aliases": ["testosterone", "total testosterone"],
        "unit": "ng/dL",
        "low": 300,
        "high": 1000,
        "optimal_low": 500,
        "optimal_high": 850,
        "category": "Hormones",
        "tips_low": [
            "Prioritize sleep, resistance training, adequate calories, and healthy fats.",
            "Ask about free testosterone, SHBG, LH, prolactin, and symptoms.",
        ],
        "tips_high": [
            "Review supplements, medications, and symptoms with a clinician.",
        ],
        "praise": "Testosterone is in a strong range for the general reference used here.",
    },
    {
        "key": "total_cholesterol",
        "name": "Total Cholesterol",
        "aliases": ["total cholesterol", "cholesterol total"],
        "unit": "mg/dL",
        "low": 120,
        "high": 200,
        "optimal_low": 140,
        "optimal_high": 180,
        "category": "Lipids",
        "tips_low": [
            "Very low values should be interpreted with overall nutrition and thyroid markers.",
        ],
        "tips_high": [
            "Increase soluble fiber from oats, beans, lentils, fruits, and vegetables.",
            "Review LDL, HDL, triglycerides, ApoB, blood pressure, and family history.",
        ],
        "praise": "Total cholesterol is within the general reference range.",
    },
    {
        "key": "hdl",
        "name": "HDL Cholesterol",
        "aliases": ["hdl cholesterol", "hdl-c", "hdl"],
        "unit": "mg/dL",
        "low": 40,
        "high": 100,
        "optimal_low": 50,
        "optimal_high": 80,
        "category": "Lipids",
        "tips_low": [
            "Add regular aerobic activity and resistance training.",
            "Favor unsaturated fats from nuts, olive oil, avocado, and fish.",
        ],
        "tips_high": [
            "Very high HDL is not automatically protective; interpret with ApoB and overall risk.",
        ],
        "praise": "HDL is in a helpful range.",
    },
    {
        "key": "ldl",
        "name": "LDL Cholesterol",
        "aliases": ["ldl cholesterol", "ldl-c", "ldl"],
        "unit": "mg/dL",
        "low": 40,
        "high": 100,
        "optimal_low": 50,
        "optimal_high": 90,
        "category": "Lipids",
        "tips_low": [
            "Interpret unusually low values with nutrition status, medication use, and symptoms.",
        ],
        "tips_high": [
            "Emphasize soluble fiber and replace saturated fat with unsaturated fats.",
            "Ask about ApoB or non-HDL cholesterol for a clearer risk picture.",
        ],
        "praise": "LDL is in a favorable general range.",
    },
    {
        "key": "triglycerides",
        "name": "Triglycerides",
        "aliases": ["triglycerides", "tg"],
        "unit": "mg/dL",
        "low": 30,
        "high": 150,
        "optimal_low": 50,
        "optimal_high": 100,
        "category": "Lipids",
        "tips_low": [
            "Low triglycerides can be normal; interpret with diet, weight trend, and symptoms.",
        ],
        "tips_high": [
            "Reduce alcohol, sugar, refined carbs, and late heavy meals.",
            "Improve activity after meals and consider omega-3 rich foods.",
        ],
        "praise": "Triglycerides look excellent for metabolic health.",
    },
    {
        "key": "crp",
        "name": "CRP",
        "aliases": ["crp", "c-reactive protein", "hs-crp", "hs crp"],
        "unit": "mg/L",
        "low": 0,
        "high": 3,
        "optimal_low": 0,
        "optimal_high": 1,
        "category": "Inflammation",
        "tips_low": [
            "Low CRP is usually a positive finding.",
        ],
        "tips_high": [
            "Recent infection, injury, poor sleep, dental issues, or inflammation can raise CRP.",
            "Retest when well and discuss persistent elevation with a clinician.",
        ],
        "praise": "CRP is low, a nice sign for systemic inflammation.",
    },
]


def add_marker(
    key: str,
    name: str,
    aliases: list[str],
    unit: str,
    low: float,
    high: float,
    optimal_low: float,
    optimal_high: float,
    category: str,
    low_tips: list[str] | None = None,
    high_tips: list[str] | None = None,
    praise: str | None = None,
    about: str | None = None,
) -> None:
    BIOMARKERS.append(
        {
            "key": key,
            "name": name,
            "aliases": aliases,
            "unit": unit,
            "low": low,
            "high": high,
            "optimal_low": optimal_low,
            "optimal_high": optimal_high,
            "category": category,
            "tips_low": low_tips or [f"Review the low {name} result with a clinician in the context of symptoms and the rest of the report."],
            "tips_high": high_tips or [f"Review the high {name} result with a clinician and compare with previous reports if available."],
            "praise": praise or f"The {name} result looks healthy on this general reference.",
            "about": about or "",
        }
    )


for marker_args in [
    ("wbc", "WBC", ["wbc", "white blood cell count", "total leukocyte count", "tlc"], "10^3/uL", 4.0, 11.0, 5.0, 9.0, "Blood"),
    ("rbc", "RBC", ["rbc", "red blood cell count", "erythrocyte count"], "10^6/uL", 4.0, 5.9, 4.4, 5.4, "Blood"),
    ("hematocrit", "Hematocrit", ["hematocrit", "haematocrit", "hct", "pcv"], "%", 36, 52, 40, 48, "Blood"),
    ("platelets", "Platelets", ["platelets", "platelet count", "thrombocyte count"], "10^3/uL", 150, 450, 180, 350, "Blood"),
    ("mcv", "MCV", ["mcv", "mean corpuscular volume"], "fL", 80, 100, 84, 94, "Blood"),
    ("mch", "MCH", ["mch", "mean corpuscular hemoglobin"], "pg", 27, 33, 28, 32, "Blood"),
    ("mchc", "MCHC", ["mchc", "mean corpuscular hemoglobin concentration"], "g/dL", 32, 36, 33, 35, "Blood"),
    ("rdw", "RDW", ["rdw", "red cell distribution width", "rdw-cv"], "%", 11.5, 14.5, 12, 13.8, "Blood"),
    ("neutrophils", "Neutrophils", ["neutrophils", "neutrophil"], "%", 40, 75, 45, 68, "Blood"),
    ("lymphocytes", "Lymphocytes", ["lymphocytes", "lymphocyte"], "%", 20, 45, 25, 40, "Blood"),
    ("monocytes", "Monocytes", ["monocytes", "monocyte"], "%", 2, 10, 3, 8, "Blood"),
    ("eosinophils", "Eosinophils", ["eosinophils", "eosinophil"], "%", 0, 6, 1, 4, "Blood"),
    ("basophils", "Basophils", ["basophils", "basophil"], "%", 0, 2, 0, 1, "Blood"),
    ("alt", "ALT / SGPT", ["alt", "sgpt", "alanine aminotransferase"], "U/L", 7, 56, 10, 35, "Liver"),
    ("ast", "AST / SGOT", ["ast", "sgot", "aspartate aminotransferase"], "U/L", 8, 40, 12, 30, "Liver"),
    ("alp", "Alkaline Phosphatase", ["alkaline phosphatase", "alp"], "U/L", 44, 147, 50, 115, "Liver"),
    ("ggt", "GGT", ["ggt", "gamma gt", "gamma-glutamyl transferase"], "U/L", 5, 55, 8, 35, "Liver"),
    ("bilirubin", "Bilirubin", ["bilirubin total", "total bilirubin", "bilirubin"], "mg/dL", 0.1, 1.2, 0.2, 0.9, "Liver"),
    ("albumin", "Albumin", ["albumin"], "g/dL", 3.5, 5.5, 4.0, 5.0, "Liver"),
    ("total_protein", "Total Protein", ["total protein", "protein total"], "g/dL", 6.0, 8.3, 6.6, 7.8, "Liver"),
    ("creatinine", "Creatinine", ["creatinine", "serum creatinine"], "mg/dL", 0.6, 1.3, 0.7, 1.1, "Kidney"),
    ("bun", "BUN / Urea Nitrogen", ["bun", "blood urea nitrogen", "urea nitrogen"], "mg/dL", 7, 20, 9, 17, "Kidney"),
    ("urea", "Urea", ["urea", "blood urea"], "mg/dL", 15, 45, 20, 38, "Kidney"),
    ("egfr", "eGFR", ["egfr", "estimated gfr", "glomerular filtration rate"], "mL/min", 60, 130, 90, 120, "Kidney"),
    ("uric_acid", "Uric Acid", ["uric acid", "serum uric acid"], "mg/dL", 3.5, 7.2, 4.0, 6.2, "Kidney"),
    ("sodium", "Sodium", ["sodium", "na+"], "mmol/L", 135, 145, 137, 143, "Electrolytes"),
    ("potassium", "Potassium", ["potassium", "k+"], "mmol/L", 3.5, 5.1, 3.8, 4.8, "Electrolytes"),
    ("chloride", "Chloride", ["chloride", "cl-"], "mmol/L", 98, 107, 100, 105, "Electrolytes"),
    ("calcium", "Calcium", ["calcium", "serum calcium"], "mg/dL", 8.6, 10.2, 9.0, 9.8, "Electrolytes"),
    ("magnesium", "Magnesium", ["magnesium", "mg serum"], "mg/dL", 1.7, 2.4, 1.9, 2.3, "Electrolytes"),
    ("phosphorus", "Phosphorus", ["phosphorus", "phosphate"], "mg/dL", 2.5, 4.5, 3.0, 4.0, "Electrolytes"),
    ("free_t4", "Free T4", ["free t4", "ft4", "thyroxine free"], "ng/dL", 0.8, 1.8, 1.0, 1.5, "Hormones"),
    ("free_t3", "Free T3", ["free t3", "ft3", "triiodothyronine free"], "pg/mL", 2.3, 4.2, 2.8, 3.8, "Hormones"),
    ("estradiol", "Estradiol", ["estradiol", "e2"], "pg/mL", 10, 350, 20, 200, "Hormones"),
    ("prolactin", "Prolactin", ["prolactin"], "ng/mL", 3, 25, 5, 18, "Hormones"),
    ("cortisol", "Cortisol", ["cortisol"], "ug/dL", 5, 25, 8, 18, "Hormones"),
    ("insulin", "Fasting Insulin", ["fasting insulin", "insulin fasting", "insulin"], "uIU/mL", 2, 20, 3, 8, "Metabolic"),
    ("folate", "Folate", ["folate", "folic acid"], "ng/mL", 3, 20, 6, 15, "Vitamins"),
    ("serum_iron", "Serum Iron", ["serum iron", "iron serum"], "ug/dL", 60, 170, 80, 140, "Iron"),
    ("tibc", "TIBC", ["tibc", "total iron binding capacity"], "ug/dL", 250, 450, 280, 380, "Iron"),
    ("transferrin_saturation", "Transferrin Saturation", ["transferrin saturation", "tsat", "iron saturation"], "%", 20, 50, 25, 40, "Iron"),
]:
    add_marker(*marker_args)


BIOMARKER_ABOUT = {
    "vitamin_d": "Vitamin D supports bones, muscles, immune function, and mood. Low levels are common when sunlight exposure or intake is limited.",
    "vitamin_b12": "Vitamin B12 helps make red blood cells and keeps nerves working well. It is especially important for vegetarian and vegan diets.",
    "ferritin": "Ferritin reflects stored iron. It helps show whether your body has enough iron reserve beyond what is visible in hemoglobin.",
    "hemoglobin": "Hemoglobin is the oxygen-carrying protein inside red blood cells. It is a key marker for anemia and oxygen delivery.",
    "hba1c": "HbA1c estimates your average blood sugar over roughly the last 2 to 3 months.",
    "fasting_glucose": "Fasting glucose shows blood sugar after not eating. It is a snapshot of glucose control at that moment.",
    "tsh": "TSH is a brain signal that tells the thyroid how hard to work. It helps screen thyroid function.",
    "testosterone": "Testosterone is a sex hormone involved in energy, libido, muscle, mood, and reproductive function.",
    "total_cholesterol": "Total cholesterol is the combined cholesterol carried in different blood particles. It is useful, but LDL, HDL, and triglycerides explain more.",
    "hdl": "HDL is often called good cholesterol because it participates in cholesterol transport and cleanup.",
    "ldl": "LDL carries cholesterol into tissues. Higher LDL can raise cardiovascular risk, especially with other risk factors.",
    "triglycerides": "Triglycerides are blood fats that often rise with excess sugar, alcohol, refined carbs, or insulin resistance.",
    "crp": "CRP is an inflammation marker. It can rise from infection, injury, chronic inflammation, dental issues, or hard training.",
    "wbc": "WBC counts immune cells that help fight infection and respond to inflammation.",
    "rbc": "RBC counts red blood cells, which carry oxygen through the body.",
    "hematocrit": "Hematocrit is the percentage of your blood volume made up of red blood cells. It helps assess hydration, anemia, and oxygen-carrying capacity.",
    "platelets": "Platelets help blood clot and repair vessel injury. They can change with inflammation, infection, or bone marrow activity.",
    "mcv": "MCV is the average size of red blood cells. It can point toward iron, B12, or folate patterns.",
    "mch": "MCH is the average amount of hemoglobin inside each red blood cell.",
    "mchc": "MCHC shows how concentrated hemoglobin is inside red blood cells.",
    "rdw": "RDW shows how varied red blood cell sizes are. Higher variation can appear with nutrient deficiencies or recovery from anemia.",
    "neutrophils": "Neutrophils are immune cells that respond strongly to bacterial infection, inflammation, stress, and injury.",
    "lymphocytes": "Lymphocytes are immune cells involved in viral defense and long-term immune memory.",
    "monocytes": "Monocytes are immune cleanup cells that respond to inflammation and help repair tissue.",
    "eosinophils": "Eosinophils are immune cells linked with allergies, asthma, eczema, and parasite responses.",
    "basophils": "Basophils are rare immune cells involved in allergic and inflammatory responses.",
    "alt": "ALT is a liver enzyme. It can rise when liver cells are irritated or injured.",
    "ast": "AST is an enzyme found in liver and muscle. It can rise with liver stress, muscle injury, or hard exercise.",
    "alp": "Alkaline phosphatase can reflect bile duct, liver, or bone activity depending on the rest of the report.",
    "ggt": "GGT is a liver and bile duct enzyme that can rise with alcohol use, fatty liver, medications, or bile flow issues.",
    "bilirubin": "Bilirubin comes from normal red blood cell breakdown and is processed by the liver.",
    "albumin": "Albumin is a major blood protein made by the liver. It reflects protein status, inflammation, liver function, and fluid balance.",
    "total_protein": "Total protein combines albumin and globulins, giving a broad view of blood protein status.",
    "creatinine": "Creatinine is a waste product from muscle metabolism used to estimate kidney filtration.",
    "bun": "BUN reflects urea nitrogen from protein breakdown and kidney handling. Hydration and protein intake affect it.",
    "urea": "Urea is a protein-breakdown waste product cleared by the kidneys.",
    "egfr": "eGFR estimates how well the kidneys filter blood. Higher is generally better until very high values need context.",
    "uric_acid": "Uric acid is a waste product from purine metabolism. Higher levels can relate to gout risk and metabolic health.",
    "sodium": "Sodium is a key electrolyte for fluid balance, blood pressure, nerves, and muscles.",
    "potassium": "Potassium supports heart rhythm, nerve signals, and muscle contraction.",
    "chloride": "Chloride helps maintain fluid balance and acid-base balance.",
    "calcium": "Calcium supports bones, muscles, nerves, and heart rhythm.",
    "magnesium": "Magnesium supports muscle, nerve, glucose, blood pressure, and energy metabolism.",
    "phosphorus": "Phosphorus supports bones, energy production, and cell function.",
    "free_t4": "Free T4 is a thyroid hormone available in the blood. It helps show thyroid output.",
    "free_t3": "Free T3 is an active thyroid hormone that influences energy, temperature, and metabolism.",
    "estradiol": "Estradiol is an estrogen hormone involved in reproductive health, bones, mood, and cardiovascular function.",
    "prolactin": "Prolactin is a pituitary hormone involved in lactation and reproductive hormone signaling.",
    "cortisol": "Cortisol is a stress hormone that affects energy, inflammation, blood sugar, and sleep-wake rhythm.",
    "insulin": "Fasting insulin shows how much insulin your body needs to keep fasting glucose controlled.",
    "folate": "Folate supports DNA production, red blood cells, pregnancy health, and methylation pathways.",
    "serum_iron": "Serum iron is the amount of circulating iron in blood at that moment. It changes more day to day than ferritin.",
    "tibc": "TIBC estimates how much iron-binding capacity is available in the blood.",
    "transferrin_saturation": "Transferrin saturation shows the percentage of iron transport capacity currently filled with iron.",
}


SIMPLE_ABOUT = {
    "vitamin_d": "Helps bones, muscles, mood, and immunity. Low levels are common when sunlight is low.",
    "vitamin_b12": "Helps nerves and red blood cells. Low B12 can affect energy and tingling/numbness.",
    "ferritin": "Shows your stored iron. Think of it as the backup iron tank.",
    "hemoglobin": "The oxygen carrier in red blood cells. Low values can point toward anemia.",
    "hba1c": "Your average blood sugar picture over the last 2 to 3 months.",
    "fasting_glucose": "Your blood sugar after fasting. It is a quick snapshot, not the whole movie.",
    "tsh": "A signal from the brain telling the thyroid how hard to work.",
    "testosterone": "A hormone tied to libido, energy, muscle, mood, and reproductive health.",
    "hdl": "The cleanup-style cholesterol marker. Higher is usually better within reason.",
    "ldl": "The cholesterol marker doctors watch closely for heart risk.",
    "triglycerides": "Blood fats that often rise with sugar, alcohol, refined carbs, or insulin resistance.",
    "crp": "A general inflammation marker. It can rise after infection, injury, poor sleep, or chronic inflammation.",
    "wbc": "Your immune-cell count. It moves with infection, inflammation, stress, and recovery.",
    "rbc": "Your red blood cell count. These cells carry oxygen around the body.",
    "hematocrit": "How much of your blood is made of red blood cells. It changes with hydration and anemia.",
    "platelets": "Small blood cells that help clotting and repair.",
    "mcv": "Average red blood cell size. It can hint at iron, B12, or folate issues.",
    "mch": "How much hemoglobin is inside each red blood cell.",
    "mchc": "How concentrated hemoglobin is inside red blood cells.",
    "rdw": "How uneven your red blood cell sizes are. More uneven can suggest nutrient issues.",
    "neutrophils": "Fast-response immune cells, often higher with bacterial infection or stress.",
    "lymphocytes": "Immune cells used for viruses and immune memory.",
    "monocytes": "Cleanup immune cells that rise with inflammation and tissue repair.",
    "eosinophils": "Immune cells linked with allergies, asthma, eczema, and parasites.",
    "basophils": "Rare immune cells involved in allergy-type reactions.",
    "alt": "A liver enzyme. Higher values can mean liver cells are irritated.",
    "ast": "An enzyme from liver and muscle. Hard workouts can also move it.",
    "creatinine": "A kidney-filtering marker based partly on muscle waste.",
    "egfr": "An estimate of kidney filtration. Higher is usually better, with context.",
    "sodium": "A key salt for fluid balance, nerves, and blood pressure.",
    "potassium": "Important for heart rhythm, nerves, and muscles.",
    "free_t4": "A thyroid hormone level. It helps show thyroid output.",
    "free_t3": "An active thyroid hormone tied to energy and metabolism.",
    "insulin": "Shows how much insulin your body needs while fasting.",
}


def biomarker_about(key: str, name: str, category: str) -> str:
    if key in SIMPLE_ABOUT:
        return SIMPLE_ABOUT[key]
    if key in BIOMARKER_ABOUT:
        return BIOMARKER_ABOUT[key]
    return f"{name} belongs to the {category.lower()} section. Read it with nearby markers and your lab range."


for marker in BIOMARKERS:
    marker["about"] = marker.get("about") or biomarker_about(marker["key"], marker["name"], marker["category"])


def read_upload(headers: dict[str, str], body: bytes) -> tuple[str, str | None]:
    content_type = headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return body.decode("utf-8", errors="replace"), None

    boundary_match = re.search(r"boundary=(.+)", content_type)
    if not boundary_match:
        return "", "Upload was missing a multipart boundary."

    boundary = ("--" + boundary_match.group(1).strip().strip('"')).encode()
    report_text = ""
    file_note = None

    for raw_part in body.split(boundary):
        if not raw_part or raw_part in (b"--\r\n", b"--"):
            continue
        head, sep, content = raw_part.partition(b"\r\n\r\n")
        if not sep:
            continue
        disposition = head.decode("utf-8", errors="replace")
        content = content.rstrip(b"\r\n-")
        name_match = re.search(r'name="([^"]+)"', disposition)
        field_name = name_match.group(1) if name_match else ""
        if field_name == "report_text":
            report_text += "\n" + content.decode("utf-8", errors="replace")
        elif field_name == "report_file" and content:
            filename_match = re.search(r'filename="([^"]*)"', disposition)
            filename = filename_match.group(1).lower() if filename_match else ""
            if filename.endswith((".txt", ".csv", ".tsv")):
                report_text += "\n" + content.decode("utf-8", errors="replace")
            elif filename.endswith(".pdf"):
                pdf_text, pdf_error = extract_pdf_text(content)
                if pdf_text.strip():
                    report_text += "\n" + pdf_text
                else:
                    file_note = pdf_error or "Could not read text from this PDF. If it is a scanned image, OCR is needed."
            else:
                file_note = "This app can read PDF, TXT, CSV, and pasted text. Paste the report text if this file is image-based."

    return report_text.strip(), file_note


def analyze_sample_report() -> tuple[dict, int]:
    pdfs = sorted(SAMPLE_DIR.glob("*.pdf"))
    if not pdfs:
        return {"error": "No sample PDF found in sample_folder/."}, 404

    sample_pdf = pdfs[0]
    pdf_text, pdf_error = extract_pdf_text(sample_pdf.read_bytes())
    if not pdf_text.strip():
        return {"error": pdf_error or f"Could not read text from {sample_pdf.name}."}, 500

    result = analyze_report(pdf_text, f"Loaded sample PDF: {sample_pdf.name}")
    result["sample_file"] = sample_pdf.name
    return result, 200


def extract_pdf_text(content: bytes) -> tuple[str, str | None]:
    # pdftotext handles normal lab PDFs well. Scanned PDFs are just pictures;
    # those need OCR, not wishful thinking.
    with tempfile.NamedTemporaryFile(suffix=".pdf") as source:
        source.write(content)
        source.flush()
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", source.name, "-"],
                check=False,
                capture_output=True,
                text=True,
                timeout=12,
            )
        except FileNotFoundError:
            return "", "PDF extraction requires the `pdftotext` command to be installed."
        except subprocess.TimeoutExpired:
            return "", "PDF extraction took too long. Try a smaller report or paste the text."

    if result.returncode != 0:
        message = result.stderr.strip() or "Could not extract text from this PDF."
        return "", message
    return result.stdout, None


def parse_number(raw: str) -> float | None:
    cleaned = raw.replace(",", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    return float(match.group(0)) if match else None


def normalize_unit(unit: str, default: str) -> str:
    unit = unit.strip().replace("μ", "u")
    return unit or default


def find_marker(text: str, marker: dict) -> dict | None:
    # Reports are messy: some are "LDL 112", some are table rows, some are
    # mangled PDF text. Try line-by-line first before searching the whole blob.
    match = find_marker_match(text, marker)
    if not match:
        return None

    value = parse_number(match["value"])
    if value is None:
        return None

    unit = normalize_unit(match.get("unit") or marker["unit"], marker["unit"])
    return {
        "key": marker["key"],
        "name": marker["name"],
        "value": value,
        "unit": unit,
        "category": marker["category"],
        "range": {"low": marker["low"], "high": marker["high"]},
        "optimal": {"low": marker["optimal_low"], "high": marker["optimal_high"]},
        "status": classify(value, marker),
        "score": score(value, marker),
        "about": marker["about"],
        "tips": tips(value, marker),
        "message": message(value, marker),
    }


def find_marker_match(text: str, marker: dict) -> dict | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        match = find_marker_match_in_text(line, marker)
        if match:
            return match
    return find_marker_match_in_text(text, marker)


def find_marker_match_in_text(text: str, marker: dict) -> dict | None:
    for alias in sorted(marker["aliases"], key=len, reverse=True):
        alias_pattern = alias_to_pattern(alias)
        alias_match = re.search(alias_pattern, text, re.IGNORECASE)
        if not alias_match:
            continue

        tail = text[alias_match.end() : alias_match.end() + 120]
        lead = text[max(0, alias_match.start() - 80) : alias_match.start()]
        value_match = find_value_after_alias(tail) or find_value_before_alias(lead)
        if value_match:
            return value_match
    return None


def alias_to_pattern(alias: str) -> str:
    escaped = re.escape(alias)
    escaped = escaped.replace(r"\ ", r"[\s_/\-]+")
    start = r"(?<![A-Za-z0-9])" if alias[0].isalnum() else ""
    end = r"(?![A-Za-z0-9])" if alias[-1].isalnum() else ""
    return start + escaped + end


def find_value_after_alias(text: str) -> dict | None:
    cleaned = re.sub(r"(reference|normal|range|units?|method|male|female)\b.*", "", text, flags=re.IGNORECASE)
    pattern = re.compile(
        r"(?:result|value|level|observed value)?[\s:=-]{0,20}"
        r"([<>]?\s*\d[\d,]*(?:\.\d+)?)"
        r"\s*([a-zA-Z/%^\.]+(?:/[a-zA-Z]+)?)?",
        re.IGNORECASE,
    )
    match = pattern.search(cleaned)
    if not match:
        return None
    return {"value": match.group(1), "unit": match.group(2)}


def find_value_before_alias(text: str) -> dict | None:
    matches = list(
        re.finditer(
            r"([<>]?\s*\d[\d,]*(?:\.\d+)?)\s*([a-zA-Z/%^\.]+(?:/[a-zA-Z]+)?)?\s*$",
            text.strip(),
            re.IGNORECASE,
        )
    )
    if not matches:
        return None
    match = matches[-1]
    return {"value": match.group(1), "unit": match.group(2)}


def classify(value: float, marker: dict) -> str:
    if value < marker["low"]:
        return "low"
    if value > marker["high"]:
        return "high"
    if marker["optimal_low"] <= value <= marker["optimal_high"]:
        return "great"
    return "ok"


def score(value: float, marker: dict) -> int:
    low = marker["low"]
    high = marker["high"]
    opt_low = marker["optimal_low"]
    opt_high = marker["optimal_high"]
    if opt_low <= value <= opt_high:
        return 96
    if low <= value <= high:
        edge = min(abs(value - opt_low), abs(value - opt_high))
        span = max((high - low) / 2, 1)
        return max(72, min(90, round(90 - edge / span * 18)))
    distance = low - value if value < low else value - high
    span = max(high - low, 1)
    return max(35, round(70 - distance / span * 45))


def tips(value: float, marker: dict) -> list[str]:
    if value < marker["low"]:
        return marker["tips_low"]
    if value > marker["high"]:
        return marker["tips_high"]
    if marker["optimal_low"] <= value <= marker["optimal_high"]:
        return [marker["praise"]]
    if value < marker["optimal_low"]:
        return [marker["praise"].replace("Great", "Good"), *marker["tips_low"][:2]]
    return [marker["praise"].replace("Great", "Good"), *marker["tips_high"][:2]]


def message(value: float, marker: dict) -> str:
    status = classify(value, marker)
    if status == "great":
        return marker["praise"]
    if status == "ok":
        return f"{marker['name']} is inside the broad reference range, with room to optimize."
    if status == "low":
        return f"{marker['name']} appears below the general reference range."
    return f"{marker['name']} appears above the general reference range."


def analyze_report(text: str, note: str | None = None) -> dict:
    # Main analyzer. No black box here: parse values, compare to our ranges,
    # group the results, then optionally ask AI to write a nicer summary.
    markers = [found for marker in BIOMARKERS if (found := find_marker(text, marker))]
    markers = sorted(markers, key=lambda item: (item["category"], status_rank(item["status"]), item["name"]))
    status_counts = {name: sum(1 for item in markers if item["status"] == name) for name in ["great", "ok", "low", "high"]}
    average = round(sum(item["score"] for item in markers) / len(markers)) if markers else 0
    focus = [item for item in markers if item["status"] in ("low", "high")]
    wins = [item for item in markers if item["status"] == "great"]
    categories = build_categories(markers)

    if not text.strip():
        summary = "Paste or upload readable report text to get a biomarker review."
    elif not markers:
        summary = "I could not recognize common biomarkers in the text. If this is a scanned PDF, OCR is needed before analysis."
    elif focus:
        summary = f"Found {len(markers)} biomarkers across {len(categories)} sections. Score {average}/100 is {score_label(average)}. {len(focus)} need attention and {len(wins)} look excellent."
    else:
        summary = f"Found {len(markers)} biomarkers across {len(categories)} sections. Score {average}/100 is {score_label(average)} with no obvious out-of-range values."

    ai_summary = generate_ai_summary(markers, summary)

    return {
        "id": str(uuid.uuid4())[:8],
        "score": average,
        "summary": summary,
        "ai_summary": ai_summary,
        "ai_enabled": bool(os.environ.get("OPENAI_API_KEY")),
        "markers": markers,
        "categories": categories,
        "focus": focus[:6],
        "wins": wins[:6],
        "counts": status_counts,
        "note": note,
        "disclaimer": "Educational only. Reference ranges vary by lab, sex, age, pregnancy status, medications, and medical history. Do not use this as a diagnosis.",
    }


def status_rank(status: str) -> int:
    return {"high": 0, "low": 1, "ok": 2, "great": 3}.get(status, 4)


def score_label(score_value: int) -> str:
    if score_value >= 90:
        return "excellent"
    if score_value >= 80:
        return "good"
    if score_value >= 70:
        return "fair"
    if score_value:
        return "worth reviewing"
    return "not available yet"


def build_categories(markers: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for marker in markers:
        grouped.setdefault(marker["category"], []).append(marker)

    categories = []
    for name, items in grouped.items():
        category_score = round(sum(item["score"] for item in items) / len(items))
        focus_count = sum(1 for item in items if item["status"] in ("low", "high"))
        categories.append(
            {
                "name": name,
                "score": category_score,
                "label": score_label(category_score),
                "focus_count": focus_count,
                "markers": items,
            }
        )
    return sorted(categories, key=lambda item: (item["focus_count"] == 0, -item["focus_count"], item["name"]))


def generate_ai_summary(markers: list[dict], fallback: str) -> str | None:
    # Optional polish layer. If OPENAI_API_KEY is missing or the API fails, the
    # app still works with the rule-based summary.
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not markers:
        return None

    model = os.environ.get("OPENAI_MODEL", "gpt-5")
    compact_markers = [
        {
            "name": item["name"],
            "value": item["value"],
            "unit": item["unit"],
            "status": item["status"],
            "message": item["message"],
            "tips": item["tips"][:2],
        }
        for item in markers
    ]
    prompt = (
        "Write a warm, concise blood report summary for a consumer wellness app. "
        "Do not diagnose. Praise strong values, mention focus areas, and suggest safe lifestyle next steps. "
        "Keep it under 90 words.\n\n"
        + json.dumps({"fallback_summary": fallback, "markers": compact_markers})
    )
    payload = json.dumps(
        {
            "model": model,
            "input": prompt,
            "max_output_tokens": 220,
        }
    ).encode("utf-8")
    request = Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    for output in data.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return content["text"].strip()
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self.serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        static_path = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR.resolve() in static_path.parents and static_path.exists():
            content_type = "text/plain"
            if static_path.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif static_path.suffix == ".js":
                content_type = "application/javascript; charset=utf-8"
            self.serve_file(static_path, content_type)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/sample":
            result, status = analyze_sample_report()
            self.send_json(result, status)
            return

        if path != "/api/analyze":
            self.send_error(404)
            return

        length = int(self.headers.get("content-length", "0"))
        if length > MAX_UPLOAD_BYTES:
            upload_mb = MAX_UPLOAD_BYTES // 1024 // 1024
            self.send_json({"error": f"Upload is too large. Keep it under {upload_mb} MB."}, 413)
            return

        body = self.rfile.read(length)
        headers = {key.lower(): value for key, value in self.headers.items()}
        report_text, note = read_upload(headers, body)
        self.send_json(analyze_report(report_text, note))

    def serve_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, data: dict, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"BioAI running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
