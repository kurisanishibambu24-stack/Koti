#!/usr/bin/env python3
"""
JobBot - Complete All-in-One CLI & Web Application
Automated Job Aggregation, Truth-Aware ATS CV Tailoring, Scam Detection, and Application Dispatcher

NEW IN THIS VERSION
-------------------
1. Per-job CV choice: every job found asks you to pick "custom ats cv" (built by
   this program) or "own cv" (a file you upload yourself).
2. Unique per-job email letters, viewable and editable (CLI + web dashboard).
3. Throttled bulk sending: a configurable gap (default 10 seconds + jitter)
   between outgoing emails so Gmail does not flag/ban the account.
"""

import os
import sys
import re
import json
import time
import random
import shutil
import sqlite3
import argparse
import datetime
import tempfile
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import subprocess
import hashlib
import smtplib
import ssl
import platform
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

# Optional third-party imports with fallback handling
try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from flask import Flask, render_template_string, request, redirect, url_for, jsonify
except ImportError:
    Flask = None


# ==========================================
# PATHS & GLOBALS SETUP
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_DIR = os.path.join(BASE_DIR, "out")
CVS_DIR = os.path.join(OUT_DIR, "cvs")
ATTACHMENTS_DIR = os.path.join(DATA_DIR, "attachments")
OWN_CV_DIR = os.path.join(DATA_DIR, "own_cv")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

DB_PATH = os.path.join(DATA_DIR, "jobbot.db")
MASTER_CV_PATH = os.path.join(DATA_DIR, "master_cv.json")
CONFIG_PATH = os.path.join(CONFIG_DIR, "settings.json")
BLOCKLIST_PATH = os.path.join(DATA_DIR, "blocklist.txt")

# CV Engine Styling Constants
FONT = "Helvetica"
BODY = 10.5
LEAD = 5.6

# ------------------------------------------
# CV MODE CONSTANTS  (Change #1)
# ------------------------------------------
CV_MODE_CUSTOM = "custom"          # program builds a tailored ATS CV
CV_MODE_OWN = "own"                # user's own uploaded CV file is attached
CV_MODE_LABELS = {
    CV_MODE_CUSTOM: "custom ats cv",
    CV_MODE_OWN: "own cv",
    "": "(not chosen yet)",
}
OWN_CV_ALLOWED_SUFFIXES = (".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt")

# ------------------------------------------
# SEND THROTTLE CONSTANTS  (Change #3)
# Gmail account limits (as a guide):
#   * Free @gmail.com accounts: roughly 500 messages / rolling 24 hours
#   * Google Workspace accounts: roughly 2,000 messages / rolling 24 hours
# Sending many mails back-to-back with no pause is the fastest way to get
# rate-limited or locked out, so a gap of ~10 seconds (plus a little random
# jitter so the pattern is not perfectly robotic) is used by default.
# ------------------------------------------
DEFAULT_SEND_DELAY = 10            # seconds between two outgoing emails
DEFAULT_SEND_JITTER = 3            # extra random 0..N seconds on top of the delay
DEFAULT_MAX_PER_RUN = 100          # safety cap per single run
GMAIL_DAILY_SOFT_LIMIT = 500       # informational warning threshold

DEFAULT_SETTINGS = {
    "own_cv_path": "",
    "send_delay_seconds": DEFAULT_SEND_DELAY,
    "send_delay_jitter": DEFAULT_SEND_JITTER,
    "max_emails_per_run": DEFAULT_MAX_PER_RUN,
    "default_cv_mode": "",
}

# Regex & NLP Patterns
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
PHONE_RE = re.compile(r"(?:\+27|0)\s?(?:\d[\s-]?){8,9}\d")
DATE_RE = re.compile(
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*)?"
    r"(19|20)\d{2}\s*(?:-|to|until|\u2013)\s*"
    r"(present|current|now|((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"[a-z]*\s*)?(19|20)\d{2})",
    re.I,
)
YEARS_RE = re.compile(r"(\d{1,2})\+?\s*(?:years|yrs)\b", re.I)

SECTIONS = {
    "profile": r"(profile|summary|objective|about me|personal statement|career summary|professional summary)",
    "skills": r"(skills|competenc|strengths|proficienc|abilities|attributes)",
    "experience": r"(experience|employment|work history|career history|previous position)",
    "education": r"(education|qualification|academic|schooling)",
    "certs": r"(certificat|courses|training|licence|license|accreditation)",
    "references": r"(reference|referee)",
}

NAME_EXCLUDE_PHRASES = {
    "curriculum vitae", "resume", "résumé", "cv", "personal details",
    "contact details", "contact information", "biodata", "profile",
}

DUTY_VERB_STARTS = {
    "assisted", "handled", "managed", "responsible", "performed", "provided",
    "maintained", "organized", "organised", "processed", "served", "answered",
    "prepared", "checked", "cleaned", "packed", "loaded", "unloaded",
    "captured", "filed", "restocked", "supervised", "trained", "delivered",
    "monitored", "resolved", "operated", "conducted", "supported", "sold",
}

STOP = set(
    """
a an the and or but if then than that this these those with without within for
to of in on at by from as is are was were be been being it its their there here
we you your our will shall can may must should would could have has had do does
did not no yes all any each other more most such only own same so too very job
role position candidate company applicant successful required requirements
duties responsibilities please apply application work working experience ability
able strong good excellent must-have year years month months per day week team
environment based salary market related benefits opportunity
""".split()
)

SA_PHRASES = [
    "grade 12", "matric", "ncv level 4", "nqf level 4", "senior certificate",
    "code 8", "code 10", "code 14", "drivers licence", "driver's licence",
    "own transport", "forklift", "pdp", "first aid", "health and safety",
    "customer service", "stock control", "cash handling", "data capturing",
    "microsoft office", "ms excel", "ms word", "pastel", "sage", "sap",
    "call centre", "cold calling", "merchandising", "quality control",
    "picking and packing", "general worker", "security", "psira", "cleaning",
    "admin", "reception", "filing", "invoicing", "debtors", "creditors",
    "inventory", "warehouse", "retail", "sales", "cashier", "customer care",
]

QUALIFICATION_TERMS = [
    "grade 12", "matric", "ncv level 4", "nqf level 4", "senior certificate",
    "qualification", "certificate", "diploma", "degree",
]

LICENCE_TERMS = [
    "drivers licence", "driver's licence", "code 8", "code 10", "code 14",
    "pdp", "forklift licence", "forklift license", "psira",
]

# ==========================================
# PROVINCE FILTER: South African provinces mapped to their major
# cities/towns, so filtering by province also catches postings that only
# name a city rather than the province itself.
# ==========================================
PROVINCE_CITY_MAP = {
    "eastern cape": [
        "eastern cape", "gqeberha", "port elizabeth", "east london", "mthatha",
        "uitenhage", "kariega", "king williams town", "qonce", "grahamstown",
        "makhanda", "queenstown", "komani", "butterworth", "graaff-reinet",
        "jeffreys bay", "humansdorp", "cradock", "aliwal north", "stutterheim",
    ],
    "free state": [
        "free state", "bloemfontein", "mangaung", "welkom", "bethlehem",
        "sasolburg", "kroonstad", "parys", "phuthaditjhaba", "harrismith",
        "virginia", "odendaalsrus", "botshabelo", "bothaville", "ficksburg",
    ],
    "gauteng": [
        "gauteng", "johannesburg", "joburg", "pretoria", "tshwane", "soweto",
        "sandton", "midrand", "centurion", "kempton park", "benoni",
        "boksburg", "germiston", "roodepoort", "randburg", "vanderbijlpark",
        "vereeniging", "springs", "alberton", "krugersdorp", "brakpan",
        "edenvale", "randfontein", "carletonville", "tembisa",
    ],
    "kwazulu-natal": [
        "kwazulu-natal", "kwazulu natal", "kzn", "durban", "ethekwini",
        "pietermaritzburg", "richards bay", "newcastle", "pinetown",
        "umlazi", "ladysmith", "empangeni", "howick", "kokstad", "ballito",
        "margate", "port shepstone", "estcourt", "vryheid",
    ],
    "limpopo": [
        "limpopo", "polokwane", "tzaneen", "mokopane", "thohoyandou",
        "musina", "phalaborwa", "lephalale", "giyani", "bela-bela",
        "modimolle", "louis trichardt", "makhado",
    ],
    "mpumalanga": [
        "mpumalanga", "nelspruit", "mbombela", "witbank", "emalahleni",
        "secunda", "standerton", "ermelo", "middelburg", "barberton",
        "sabie", "white river", "hazyview", "piet retief",
    ],
    "north west": [
        "north west", "rustenburg", "klerksdorp", "mahikeng", "mafikeng",
        "potchefstroom", "brits", "vryburg", "lichtenburg", "zeerust",
        "christiana", "stilfontein", "orkney", "wolmaransstad", "koster",
        "ventersdorp", "taung",
    ],
    "northern cape": [
        "northern cape", "kimberley", "upington", "springbok", "kuruman",
        "de aar", "kathu", "colesberg", "calvinia", "postmasburg",
        "kakamas", "warrenton",
    ],
    "western cape": [
        "western cape", "cape town", "stellenbosch", "paarl", "george",
        "worcester", "mossel bay", "knysna", "hermanus", "oudtshoorn",
        "bellville", "parow", "somerset west", "malmesbury", "vredenburg",
        "saldanha", "swellendam", "beaufort west",
    ],
}

# ==========================================
# MANDATORY BASELINE REQUIREMENT FILTER
# Always-on filter (cannot be turned off): a fetched job must mention a
# minimum qualification (Grade 12 / Matric / NCV Level 4 or equivalent) OR
# a driver's licence (or equivalent), per user configuration.
# ==========================================
BASELINE_QUALIFICATION_TERMS = [
    "grade 12", "matric", "senior certificate", "ncv level 4", "nqf level 4",
    "national certificate vocational level 4", "national senior certificate",
]

BASELINE_LICENCE_TERMS = [
    "drivers licence", "driver's licence", "drivers license", "driver's license",
    "code 8", "code 10", "code 14", "code eb", "code c1", "pdp",
]

def passes_baseline_filter(text: str) -> bool:
    """Mandatory always-on filter. Returns True only if the job text mentions
    a minimum qualification (Grade 12/Matric/NCV Level 4 or equivalent) OR a
    driver's licence (or equivalent)."""
    low = text.lower()
    has_qualification = any(term in low for term in BASELINE_QUALIFICATION_TERMS)
    has_licence = any(term in low for term in BASELINE_LICENCE_TERMS)
    return has_qualification or has_licence

def prompt_for_province() -> str:
    """Interactive numbered menu forcing a province choice before fetch can run."""
    provinces = list(PROVINCE_CITY_MAP.keys())
    print("\nSelect a province to search for jobs in:")
    for i, prov in enumerate(provinces, 1):
        print(f"  [{i}] {prov.title()}")
    while True:
        choice = input(f"Enter number (1-{len(provinces)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(provinces):
            return provinces[int(choice) - 1]
        print("[!] Invalid selection, please try again.")

SKILL_TERMS = [
    "customer service", "customer care", "communication", "teamwork",
    "cash handling", "cashier", "sales", "stock control", "inventory",
    "data capturing", "microsoft office", "ms word", "ms excel", "excel",
    "filing", "administration", "admin", "reception", "cleaning",
    "merchandising", "quality control", "health and safety", "time management",
    "problem solving", "attention to detail", "picking and packing",
    "warehouse", "retail",
]

DUTY_TERMS = [
    "assist customers", "serve customers", "receive stock", "stock control",
    "pack stock", "pick orders", "pack orders", "load", "unload",
    "clean", "file documents", "capture data", "answer calls",
    "process payments", "handle cash", "maintain records", "merchandise",
    "check stock", "organize stock", "prepare orders",
]

PREFERRED_MARKERS = ["preferred", "advantage", "advantageous", "added advantage", "would be an advantage", "nice to have", "plus"]
REQUIRED_MARKERS = ["required", "must have", "must-have", "essential", "minimum requirement", "requirements", "you need", "applicants must"]

TRANSFER_MAP = {
    "customer service": ["customer", "customers", "assisted customers", "served customers", "client", "clients", "sales"],
    "cash handling": ["cash", "payments", "sales", "tuck shop", "cashier"],
    "stock control": ["stock", "supplies", "products", "merchandise", "inventory", "organized supplies", "maintained supplies"],
    "inventory": ["stock", "supplies", "products", "merchandise", "inventory"],
    "teamwork": ["team", "worked with colleagues", "assisted staff", "coworkers"],
    "communication": ["customers", "clients", "communication", "assisted", "explained", "answered questions"],
    "sales": ["sales", "sold", "cash", "purchases", "customers"],
    "cleaning": ["clean", "cleanliness", "maintained work area", "sanitation"],
    "administration": ["records", "filing", "documents", "data", "office", "admin"],
    "data capturing": ["records", "data", "documents", "computer", "excel"],
    "warehouse": ["stock", "inventory", "supplies", "packing", "orders"],
}

NEGATION_TERMS = {"no", "not", "without", "n/a", "none", "never", "excluding", "lacking", "lack", "isn't", "wasn't", "don't", "doesn't", "didn't"}
NEGATION_WINDOW = 4


def ensure_directories():
    for d in [CONFIG_DIR, DATA_DIR, OUT_DIR, CVS_DIR, ATTACHMENTS_DIR, OWN_CV_DIR, TEMPLATES_DIR]:
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(BLOCKLIST_PATH):
        with open(BLOCKLIST_PATH, "w", encoding="utf-8") as f:
            f.write("# Add blocklisted keywords or domains (one per line)\ntelegram\nwhatsapp only\npay for registration\n")
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=2)


# ==========================================
# SETTINGS HELPERS
# ==========================================
def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                settings.update(loaded)
    except Exception:
        pass
    return settings

def save_settings(settings: dict) -> None:
    ensure_directories()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


# ==========================================
# DATABASE INIT + MIGRATION
# ==========================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _table_columns(cursor, table: str) -> set:
    try:
        return {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()

def migrate_db():
    """Adds the new columns (cv_mode, email_subject, email_body, email_edited)
    to databases that were created by an older version of JobBot."""
    conn = get_db()
    c = conn.cursor()
    job_cols = _table_columns(c, "jobs")
    for name, ddl in [
        ("cv_mode", "TEXT DEFAULT ''"),
        ("email_subject", "TEXT DEFAULT ''"),
        ("email_body", "TEXT DEFAULT ''"),
        ("email_edited", "INTEGER DEFAULT 0"),
    ]:
        if name not in job_cols:
            try:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}")
            except Exception:
                pass
    app_cols = _table_columns(c, "applications")
    for name, ddl in [
        ("cv_mode", "TEXT DEFAULT ''"),
        ("email_subject", "TEXT DEFAULT ''"),
        ("email_body", "TEXT DEFAULT ''"),
    ]:
        if name not in app_cols:
            try:
                c.execute(f"ALTER TABLE applications ADD COLUMN {name} {ddl}")
            except Exception:
                pass
    conn.commit()
    conn.close()

def init_db():
    ensure_directories()
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            url TEXT UNIQUE,
            name TEXT,
            active INTEGER DEFAULT 1,
            last_fetched TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            uid TEXT PRIMARY KEY,
            source_id TEXT,
            title TEXT,
            company TEXT,
            location TEXT,
            url TEXT,
            description TEXT,
            contact_email TEXT,
            match_score INTEGER DEFAULT 0,
            scam_score INTEGER DEFAULT 0,
            selected INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new',
            created_at TEXT,
            cv_mode TEXT DEFAULT '',
            email_subject TEXT DEFAULT '',
            email_body TEXT DEFAULT '',
            email_edited INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_uid TEXT,
            company TEXT,
            title TEXT,
            contact_email TEXT,
            cv_path TEXT,
            sent_at TEXT,
            status TEXT,
            cv_mode TEXT DEFAULT '',
            email_subject TEXT DEFAULT '',
            email_body TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()
    migrate_db()


# ==========================================
# CVBOT TAILORING ENGINE & CV PARSER
# ==========================================
def _from_pdf(path: Path) -> str:
    if not PdfReader:
        raise ImportError("pypdf is required to read PDF files. Install via: pip install pypdf")
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)

def _from_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        w_p = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
        w_t = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
        root = ET.fromstring(z.read("word/document.xml"))
        lines = []
        for para in root.iter(w_p):
            lines.append("".join(t.text or "" for t in para.iter(w_t)))
    return "\n".join(lines)

def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u2018\u2019]", "'", text)
    text = re.sub(r"[\u201c\u201d]", '"', text)
    text = re.sub(r"[\u2013\u2014]", "-", text)
    text = re.sub(r"[\u2022\u25cf\u25aa\u00b7]", "- ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(ln.strip() for ln in text.split("\n")).strip()

def extract_text(path: str | Path) -> str:
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        raw = _from_pdf(path)
    elif suffix == ".docx":
        raw = _from_docx(path)
    elif suffix in (".txt", ".md"):
        raw = path.read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
    out = _clean(raw)
    if len(out) < 80:
        raise ValueError("Almost no text found. The document may be scanned or image-based.")
    return out

def _is_heading(line: str) -> str | None:
    stripped = line.strip().rstrip(":").strip()
    if not stripped or len(stripped) > 55 or stripped.endswith("."):
        return None
    low = stripped.lower()
    for key, pattern in SECTIONS.items():
        if re.fullmatch(rf"[^a-z]*{pattern}[a-z ]*", low):
            return key
    return None

def _split_sections(text: str) -> dict[str, list[str]]:
    out = {"_header": []}
    current = "_header"
    for line in text.split("\n"):
        heading = _is_heading(line)
        if heading:
            current = heading
            out.setdefault(current, [])
        else:
            out.setdefault(current, []).append(line)
    return {k: [ln for ln in v if ln.strip()] for k, v in out.items()}

def _contact(header: list[str], full: str) -> dict:
    email_match = EMAIL_RE.search(full)
    phone_match = PHONE_RE.search(full)
    name = ""
    for line in header[:8]:
        candidate = line.strip()
        words = candidate.split()
        if candidate.lower() in NAME_EXCLUDE_PHRASES:
            continue
        if 1 < len(words) <= 4 and not any(c.isdigit() for c in candidate) and "@" not in candidate:
            name = candidate.title()
            break
    location = ""
    for line in header[:12]:
        if re.search(r"(gauteng|north west|limpopo|mpumalanga|free state|kwazulu|eastern cape|western cape|northern cape|johannesburg|pretoria|rustenburg|mahikeng|klerksdorp|potchefstroom|durban|cape town|parow)", line, re.I):
            location = line.strip(" ,|-")
            break
    return {
        "name": name or "YOUR NAME",
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
        "location": location,
    }

def _bulletise(lines: list[str]) -> list[str]:
    items = []
    for line in lines:
        line = re.sub(r"^[-*\u2022\d.)\s]+", "", line).strip()
        if line:
            items.append(line)
    return items

def _looks_like_role_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith(("-", "*", "\u2022")):
        return False
    if DATE_RE.search(stripped):
        return True
    if len(stripped) >= 90 or stripped.endswith("."):
        return False
    if re.search(r"\bat\s+[A-Z]", stripped):
        return True
    if "," in stripped and len(stripped.split()) <= 8:
        first_word = stripped.split()[0].strip(".,").lower()
        if first_word not in DUTY_VERB_STARTS:
            return True
    return False

def _experience(lines: list[str]) -> list[dict]:
    roles = []
    current = None
    for line in lines:
        if _looks_like_role_header(line):
            stripped = line.strip()
            if current and not current["bullets"] and DATE_RE.search(stripped) and not DATE_RE.search(current["header"]):
                current["header"] = f"{current['header']} ({stripped})"
                continue
            if current:
                roles.append(current)
            current = {"header": stripped, "bullets": [], "skills_demonstrated": []}
        elif current:
            cleaned = re.sub(r"^[-*\u2022\s]+", "", line).strip()
            if cleaned:
                current["bullets"].append(cleaned)
    if current:
        roles.append(current)
    return roles

def _infer_demonstrated_skills(bullets: list[str]) -> list[str]:
    text = " ".join(bullets).lower()
    found = []
    for skill, evidence_terms in TRANSFER_MAP.items():
        for term in evidence_terms:
            if term in text and not _is_negated(text, term):
                found.append(skill)
                break
    return sorted(set(found))

def _infer_years_experience(text: str) -> int | None:
    matches = [int(m.group(1)) for m in YEARS_RE.finditer(text)]
    return max(matches) if matches else None

def _dedupe_preserve_case(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if not item:
            continue
        cleaned = str(item).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out

def parse_cv(text: str) -> dict:
    sec = _split_sections(text)
    skills_raw = " , ".join(sec.get("skills", []))
    skills = _dedupe_preserve_case([s.strip(" .;") for s in re.split(r"[,;|]|\s{2,}", skills_raw) if 2 < len(s.strip()) < 60])[:40]
    experience = _experience(sec.get("experience", []))
    for role in experience:
        role["skills_demonstrated"] = _infer_demonstrated_skills(role.get("bullets", []))
    return {
        "contact": _contact(sec.get("_header", []), text),
        "profile": " ".join(sec.get("profile", []))[:1000],
        "skills": skills,
        "experience": experience,
        "education": _bulletise(sec.get("education", [])),
        "certifications": _bulletise(sec.get("certs", [])),
        "references": _bulletise(sec.get("references", [])) or ["Available on request"],
        "years_experience": _infer_years_experience(text),
    }

def normalize_master_cv(data: dict) -> dict:
    if "contact" not in data or not isinstance(data.get("contact"), dict):
        data["contact"] = {
            "name": data.get("full_name") or data.get("name") or "YOUR NAME",
            "email": data.get("email") or "",
            "phone": data.get("phone") or "",
            "location": data.get("location") or "",
        }
    if not data.get("profile") and data.get("summary"):
        data["profile"] = data["summary"]
    if data.get("certifications") is None:
        data["certifications"] = data.get("certs") or []
    if not data.get("references"):
        data["references"] = ["Available on request"]
    if data.get("experience"):
        normalized_exp = []
        for exp in data["experience"]:
            if isinstance(exp, dict):
                header = exp.get("header") or f"{exp.get('role', '')} | {exp.get('company', '')}".strip(" |")
                bullets = exp.get("bullets") or exp.get("duties") or []
                if isinstance(bullets, str):
                    bullets = [bullets]
                normalized_exp.append({
                    "header": header,
                    "bullets": bullets,
                    "skills_demonstrated": exp.get("skills_demonstrated") or _infer_demonstrated_skills(bullets),
                })
        data["experience"] = normalized_exp
    return data


# ==========================================
# ANALYSIS & MATCHING ENGINE
# ==========================================
def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z+#./'-]{2,}", text.lower()) if w not in STOP]

def _extract_known_terms(job_text: str, term_list: list[str]) -> list[str]:
    low = job_text.lower()
    return [term for term in term_list if term in low]

def job_keywords(job_text: str, top: int = 35) -> list[str]:
    low = job_text.lower()
    found = [p for p in SA_PHRASES if p in low]
    found_words = {w for phrase in found for w in phrase.split()}
    counts = Counter(_tokens(job_text))
    singles = [w for w, _ in counts.most_common(80) if w not in found_words]
    result = []
    for item in found + singles:
        if item not in result:
            result.append(item)
    return result[:top]

def analyze_job(job_text: str) -> dict:
    low = job_text.lower()
    qualifications = _extract_known_terms(low, QUALIFICATION_TERMS)
    licences = _extract_known_terms(low, LICENCE_TERMS)
    skills = _extract_known_terms(low, SKILL_TERMS)
    duties = _extract_known_terms(low, DUTY_TERMS)
    preferred = any(marker in low for marker in PREFERRED_MARKERS)
    required = any(marker in low for marker in REQUIRED_MARKERS)
    unique = lambda items: list(dict.fromkeys(items))
    return {
        "qualifications": unique(qualifications),
        "licences": unique(licences),
        "skills": unique(skills),
        "duties": unique(duties),
        "preferred_markers_present": preferred,
        "required_markers_present": required,
        "keywords": job_keywords(job_text),
    }

def _cv_blob(master: dict) -> str:
    parts = [
        master.get("profile") or "",
        " ".join(master.get("skills") or []),
        " ".join(master.get("education") or []),
        " ".join(master.get("certifications") or []),
    ]
    for role in (master.get("experience") or []):
        if isinstance(role, dict):
            parts.append(role.get("header") or "")
            parts.extend(role.get("bullets") or [])
            parts.extend(role.get("skills_demonstrated") or [])
    return " ".join(parts).lower()

def _is_negated(text: str, term: str) -> bool:
    low_text = text.lower()
    low_term = term.lower()
    occurrences = [m.start() for m in re.finditer(re.escape(low_term), low_text)]
    if not occurrences:
        return False
    for idx in occurrences:
        prefix = low_text[max(0, idx - 40):idx]
        prefix_words = re.findall(r"[a-z']+", prefix)
        if not any(w in NEGATION_TERMS for w in prefix_words[-NEGATION_WINDOW:]):
            return False
    return True

def _direct_match(term: str, master: dict) -> bool:
    blob = _cv_blob(master)
    return term.lower() in blob and not _is_negated(blob, term)

def _transfer_match(term: str, master: dict) -> list[str]:
    target = term.lower()
    evidence = []
    aliases = TRANSFER_MAP.get(target, [])
    for role in (master.get("experience") or []):
        if isinstance(role, dict):
            role_text = " ".join([role.get("header") or ""] + (role.get("bullets") or []) + (role.get("skills_demonstrated") or [])).lower()
            for alias in aliases:
                if alias.lower() in role_text and not _is_negated(role_text, alias):
                    evidence.append(role.get("header") or "Experience")
                    break
    return evidence

def classify_requirement(term: str, master: dict) -> dict:
    if _direct_match(term, master):
        return {"term": term, "status": "direct", "evidence": ["Exact/explicit evidence found in master CV."]}
    evidence = _transfer_match(term, master)
    if evidence:
        return {"term": term, "status": "transferable", "evidence": evidence}
    return {"term": term, "status": "missing", "evidence": []}

def build_match_report(master: dict, analysis: dict) -> dict:
    all_terms = list(dict.fromkeys(analysis["qualifications"] + analysis["licences"] + analysis["skills"] + analysis["duties"] + analysis["keywords"]))
    requirements = [classify_requirement(term, master) for term in all_terms]
    direct = [x["term"] for x in requirements if x["status"] == "direct"]
    transferable = [x["term"] for x in requirements if x["status"] == "transferable"]
    missing = [x["term"] for x in requirements if x["status"] == "missing"]
    coverage = round(100 * (len(direct) + len(transferable)) / max(len(requirements), 1))
    return {
        "requirements": requirements,
        "direct": direct,
        "transferable": transferable,
        "missing": missing,
        "keyword_coverage_percent": coverage,
    }


# ==========================================
# TRUTH-AWARE TAILORING & PDF RENDERER
# ==========================================
def _score(text: str, keywords: list[str]) -> int:
    low = text.lower()
    score = 0
    for keyword in keywords:
        if keyword.lower() in low:
            score += 2 if " " in keyword else 1
    return score

def _relevant_skills(master: dict, analysis: dict) -> list[str]:
    keywords = analysis.get("keywords") or []
    skills = master.get("skills") or []
    ranked = sorted(skills, key=lambda s: _score(str(s), keywords), reverse=True)
    return _dedupe_preserve_case(ranked)[:16]

def _relevant_bullets(role: dict, analysis: dict) -> list[str]:
    keywords = analysis.get("keywords") or []
    bullets = role.get("bullets") or []
    skills_dem = role.get("skills_demonstrated") or []
    ranked = sorted(bullets, key=lambda b: _score(str(b) + " " + " ".join(skills_dem), keywords), reverse=True)
    return ranked[:6]

def _summary(master: dict, job: dict, match: dict) -> str:
    direct = (match.get("direct") or [])[:4]
    transferable = (match.get("transferable") or [])[:3]
    pieces = []
    prof = master.get("profile")
    if prof:
        pieces.append(str(prof).strip())
    if direct:
        pieces.append("Relevant strengths include " + ", ".join(direct) + ".")
    if transferable:
        pieces.append("Transferable strengths include " + ", ".join(transferable) + ".")
    if not pieces:
        pieces.append(f"Motivated candidate seeking to contribute to the {job.get('title', 'position')} role.")
    summary = " ".join(pieces)
    return re.sub(r"\s+", " ", summary).strip()[:900]

def tailor(master: dict, job: dict) -> dict:
    master = normalize_master_cv(master)
    analysis = analyze_job(f"{job.get('title', '')} {job.get('company') or ''} {job.get('description') or ''}")
    match = build_match_report(master, analysis)
    roles = []
    for role in (master.get("experience") or []):
        if isinstance(role, dict):
            bullets = _relevant_bullets(role, analysis)
            roles.append({
                "header": role.get("header") or "",
                "bullets": bullets,
                "relevance": _score((role.get("header") or "") + " " + " ".join(bullets), analysis["keywords"]),
            })
    roles.sort(key=lambda r: r["relevance"], reverse=True)
    return {
        "contact": master.get("contact") or {},
        "target_title": job.get("title", ""),
        "target_company": job.get("company") or "",
        "profile": _summary(master, job, match),
        "skills": _relevant_skills(master, analysis),
        "experience": roles,
        "education": master.get("education") or [],
        "certifications": master.get("certifications") or [],
        "references": master.get("references") or ["Available on request"],
        "_analysis": analysis,
        "_match": match,
    }

def _safe(text: str) -> str:
    text = str(text)
    text = (
        text.replace("\u2022", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u00a0", " ")
    )
    out_chars = []
    for ch in text:
        try:
            ch.encode("latin-1")
            out_chars.append(ch)
        except UnicodeEncodeError:
            decomposed = unicodedata.normalize("NFKD", ch)
            ascii_ch = decomposed.encode("ascii", "ignore").decode("ascii")
            out_chars.append(ascii_ch)
    return re.sub(r"\s+", " ", "".join(out_chars)).strip()

if FPDF:
    class ATSCv(FPDF):
        def header(self):
            pass
        def footer(self):
            pass

def _section(pdf, title: str) -> None:
    pdf.ln(2.5)
    pdf.set_font(FONT, "B", 11)
    pdf.cell(0, 6, _safe(title.upper()), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(120, 120, 120)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(1.5)
    pdf.set_font(FONT, "", BODY)

def render_pdf(cv: dict, out_path: str | Path) -> Path | None:
    if not FPDF:
        print("[!] Warning: fpdf2 is not installed. Install via: pip install fpdf2")
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = ATSCv(format="A4", unit="mm")
    pdf.set_auto_page_break(True, margin=14)
    pdf.set_margins(16, 14, 16)
    c = cv.get("contact") or {}
    name = c.get("name") or "Applicant"
    pdf.set_title(f"{name} - CV - {cv.get('target_title', '')}")
    pdf.set_author(name)
    pdf.set_creator("JobBot CV Engine")
    pdf.add_page()
    pdf.set_font(FONT, "B", 17)
    pdf.cell(0, 9, _safe(name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "", 9.5)
    contact_line = " | ".join(x for x in (c.get("phone"), c.get("email"), c.get("location")) if x)
    if contact_line:
        pdf.multi_cell(0, 5, _safe(contact_line))
    if cv.get("target_title"):
        pdf.ln(1)
        pdf.set_font(FONT, "B", 11)
        pdf.multi_cell(0, 5.5, _safe(f"Application for: {cv['target_title']}"))
    if cv.get("profile"):
        _section(pdf, "Professional Summary")
        pdf.multi_cell(0, LEAD, _safe(cv["profile"]))
    if cv.get("skills"):
        _section(pdf, "Key Skills")
        for skill in cv["skills"]:
            pdf.multi_cell(0, LEAD, _safe(f"- {skill}"))
    if cv.get("experience"):
        _section(pdf, "Work Experience")
        for role in cv["experience"]:
            if role.get("header"):
                pdf.set_font(FONT, "B", BODY)
                pdf.multi_cell(0, LEAD, _safe(role["header"]))
            pdf.set_font(FONT, "", BODY)
            for bullet in role.get("bullets") or []:
                pdf.multi_cell(0, LEAD, _safe(f"- {bullet}"))
            pdf.ln(1.2)
    for title, key in (("Education", "education"), ("Certifications and Licences", "certifications"), ("References", "references")):
        if cv.get(key):
            _section(pdf, title)
            for item in cv[key]:
                pdf.multi_cell(0, LEAD, _safe(f"- {item}"))
    pdf.output(str(out_path))
    return out_path

def ats_preview(path: Path) -> str:
    if not PdfReader:
        return "(Install `pypdf` to preview extractable text)"
    text = "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    return text.strip() or "(NO TEXT FOUND - this PDF would be invisible to an ATS)"

def validate_ats(path: Path, cv: dict | None = None) -> dict:
    if not PdfReader:
        return {"status": "UNCHECKED", "passed": 0, "total": 0, "reason": "pypdf not installed"}
    if Path(path).suffix.lower() != ".pdf":
        return {"status": "UNCHECKED", "passed": 0, "total": 0, "reason": "not a PDF file"}
    reader = PdfReader(str(path))
    raw_text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    lower = raw_text.lower()
    name = cv.get("contact", {}).get("name", "") if cv and isinstance(cv.get("contact"), dict) else ""
    checks = {
        "text_extractable": bool(raw_text),
        "name_present": bool(name and name.lower() in lower) if name else bool(raw_text),
        "email_present": bool(EMAIL_RE.search(raw_text)),
        "phone_present": bool(PHONE_RE.search(raw_text)),
        "summary_heading": "professional summary" in lower,
        "skills_heading": "key skills" in lower,
        "experience_heading": "work experience" in lower,
        "education_heading": "education" in lower,
        "reasonable_page_count": 1 <= len(reader.pages) <= 3,
    }
    passed = sum(checks.values())
    total = len(checks)
    return {
        "checks": checks,
        "passed": passed,
        "total": total,
        "status": "PASS" if passed == total else "REVIEW",
        "page_count": len(reader.pages),
        "extractable_characters": len(raw_text),
    }

def open_pdf(path: Path) -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", str(path)], check=True)
            return
        if system == "Windows":
            os.startfile(str(path))
            return
        try:
            subprocess.run(["termux-open", str(path)], check=True)
            return
        except FileNotFoundError:
            pass
        subprocess.run(["xdg-open", str(path)], check=True)
    except Exception:
        print(f"Could not open automatically. Open manually:\n{Path(path).resolve()}")


# ==========================================
# SCAM & MATCH SCORE HEURISTICS
# ==========================================
def calculate_scam_score(text, company=""):
    score = 0
    t = text.lower()
    if os.path.exists(BLOCKLIST_PATH):
        with open(BLOCKLIST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().lower()
                if line and not line.startswith("#") and line in t:
                    score += 40
    scam_keywords = ["telegram", "whatsapp only", "registration fee", "wire transfer", "crypto", "no experience $500/day"]
    for kw in scam_keywords:
        if kw in t:
            score += 25
    if not company or company.lower() in ["unknown", "n/a", ""]:
        score += 15
    return min(score, 100)

def calculate_match_score(text, keywords=None):
    if not keywords:
        keywords = ["customer service", "admin", "office", "tourism", "assistant", "receptionist", "clerk"]
    score = 30
    t = text.lower()
    for kw in keywords:
        if kw.lower() in t:
            score += 10
    return min(score, 100)

def extract_email(text):
    match = EMAIL_RE.search(text)
    return match.group(0) if match else ""


# ==========================================
# OWN CV HANDLING  (Change #1)
# ==========================================
def get_own_cv_path() -> Path | None:
    """Returns the path of the user's own uploaded CV, if one is available."""
    settings = load_settings()
    configured = (settings.get("own_cv_path") or "").strip()
    if configured:
        p = Path(configured).expanduser()
        if p.exists() and p.is_file():
            return p
    if os.path.isdir(OWN_CV_DIR):
        candidates = [
            Path(OWN_CV_DIR) / f
            for f in os.listdir(OWN_CV_DIR)
            if Path(f).suffix.lower() in OWN_CV_ALLOWED_SUFFIXES
        ]
        if candidates:
            return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    return None

def set_own_cv_path(path: Path) -> None:
    settings = load_settings()
    settings["own_cv_path"] = str(path)
    save_settings(settings)

def store_own_cv(src: str | Path) -> Path:
    """Copies the user's own CV into data/own_cv/ and registers it in settings."""
    ensure_directories()
    src = Path(src).expanduser()
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")
    if src.suffix.lower() not in OWN_CV_ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported CV file type '{src.suffix}'. Allowed: {', '.join(OWN_CV_ALLOWED_SUFFIXES)}")
    dest = Path(OWN_CV_DIR) / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    set_own_cv_path(dest)
    return dest

def normalise_cv_mode(value: str) -> str | None:
    """Accepts loose user input like 'own cv', 'custom ats cv', '1', '2'."""
    if value is None:
        return None
    v = str(value).strip().lower().replace("-", " ").replace("_", " ")
    v = re.sub(r"\s+", " ", v)
    if v in {"1", "custom", "custom ats cv", "custom ats", "ats", "custom cv", "tailored"}:
        return CV_MODE_CUSTOM
    if v in {"2", "own", "own cv", "my cv", "mine", "upload", "uploaded"}:
        return CV_MODE_OWN
    return None

def set_job_cv_mode(uid: str, mode: str, select: bool = True) -> bool:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT uid FROM jobs WHERE uid = ?", (uid,))
    if not c.fetchone():
        conn.close()
        return False
    if select:
        c.execute("UPDATE jobs SET cv_mode = ?, selected = 1 WHERE uid = ?", (mode, uid))
    else:
        c.execute("UPDATE jobs SET cv_mode = ? WHERE uid = ?", (mode, uid))
    conn.commit()
    conn.close()
    return True

def prompt_cv_mode(job_row, index: int | None = None, total: int | None = None) -> str | None:
    """Per-job CV chooser menu: custom ats cv vs own cv."""
    header = ""
    if index and total:
        header = f"\n----- Job {index} of {total} -----"
    else:
        header = "\n-----------------------------"
    print(header)
    print(f"Title    : {job_row['title']}")
    print(f"Company  : {job_row['company'] or 'Unknown'}")
    print(f"Location : {job_row['location'] or '-'}")
    print(f"Contact  : {job_row['contact_email'] or '(no email found)'}")
    print(f"Match    : {job_row['match_score']}%   Scam risk: {job_row['scam_score']}%")
    if job_row["url"]:
        print(f"Link     : {job_row['url']}")
    print("\nWhich CV should be sent for this job?")
    print("  [1] custom ats cv   (built and tailored for this job by JobBot)")
    print("  [2] own cv          (attach the CV file you uploaded yourself)")
    print("  [3] skip            (decide later, job left unselected)")
    print("  [q] stop choosing")
    while True:
        choice = input("Choose 1 / 2 / 3 / q: ").strip().lower()
        if choice in {"1", "custom", "custom ats cv"}:
            return CV_MODE_CUSTOM
        if choice in {"2", "own", "own cv"}:
            return CV_MODE_OWN
        if choice in {"3", "skip", ""}:
            return None
        if choice in {"q", "quit", "stop"}:
            return "__STOP__"
        print("[!] Invalid choice. Type 1 for custom ats cv, 2 for own cv, 3 to skip, q to stop.")

def run_cv_mode_chooser(uids: list[str] | None = None, only_undecided: bool = True) -> None:
    """Walks through every job (or the given UIDs) asking for custom ats cv / own cv."""
    if not sys.stdin.isatty():
        print("[*] Not an interactive terminal - skipping the CV choice prompts.")
        print("    Use: jobbot cv-mode <uid> \"custom ats cv\"  |  jobbot cv-mode <uid> \"own cv\"")
        return
    conn = get_db()
    c = conn.cursor()
    if uids:
        placeholders = ",".join("?" for _ in uids)
        c.execute(f"SELECT * FROM jobs WHERE uid IN ({placeholders}) ORDER BY match_score DESC", uids)
    elif only_undecided:
        c.execute("SELECT * FROM jobs WHERE cv_mode IS NULL OR cv_mode = '' ORDER BY match_score DESC")
    else:
        c.execute("SELECT * FROM jobs ORDER BY match_score DESC")
    jobs = c.fetchall()
    conn.close()

    if not jobs:
        print("[*] No jobs are waiting for a CV choice.")
        return

    own_cv = get_own_cv_path()
    print("\n" + "=" * 72)
    print(f"[*] CV CHOICE REQUIRED FOR {len(jobs)} JOB(S)")
    print("    For every job you must pick: \"custom ats cv\" or \"own cv\".")
    if own_cv:
        print(f"    Your uploaded own CV: {own_cv}")
    else:
        print("    No own CV uploaded yet - use: jobbot cv-upload <file>")
    print("=" * 72)

    chosen_custom = chosen_own = skipped = 0
    for i, job in enumerate(jobs, 1):
        mode = prompt_cv_mode(job, i, len(jobs))
        if mode == "__STOP__":
            print("[*] Stopped choosing. Remaining jobs left undecided.")
            break
        if mode is None:
            skipped += 1
            continue
        if mode == CV_MODE_OWN and not own_cv:
            print("    [!] No own CV file is uploaded yet. Run `jobbot cv-upload <file>` before sending.")
        set_job_cv_mode(job["uid"], mode, select=True)
        ensure_job_email(job["uid"], overwrite=False, quiet=True)
        print(f"    [+] {job['uid']} -> {CV_MODE_LABELS[mode]} (selected for dispatch, email draft ready)")
        if mode == CV_MODE_CUSTOM:
            chosen_custom += 1
        else:
            chosen_own += 1

    print(f"\n[+] Choices saved: {chosen_custom} custom ats cv, {chosen_own} own cv, {skipped} skipped.")
    print("    Review or edit the generated emails with: jobbot email-list / email-show <uid> / email-edit <uid>")


# ==========================================
# UNIQUE PER-JOB EMAIL GENERATION  (Change #2)
# ==========================================
EMAIL_GREETINGS_NAMED = [
    "Dear Hiring Team at {company},",
    "Good day {company} Recruitment Team,",
    "Dear {company} Hiring Manager,",
    "Good day {company} Team,",
    "Dear Recruitment Team at {company},",
]

EMAIL_GREETINGS_GENERIC = [
    "Good day,",
    "Dear Hiring Manager,",
    "Dear Recruitment Team,",
    "Good day Hiring Team,",
]

EMAIL_OPENERS = [
    "I would like to apply for the {title} position{where}.",
    "Please accept this email as my application for the {title} vacancy{where}.",
    "I am writing to apply for the advertised {title} role{where}.",
    "I came across your {title} vacancy{where} and would like to submit my application.",
    "I am very interested in the {title} opportunity{where} and would like to be considered.",
]

EMAIL_CLOSERS = [
    "I would welcome the opportunity to discuss how I can contribute to your team, and I am available for an interview at your convenience.",
    "I would appreciate the chance to discuss my application further and can attend an interview whenever it suits you.",
    "Thank you for taking the time to consider my application. I am ready to start as soon as required and can attend an interview at short notice.",
    "I would be grateful for the opportunity of an interview to show how my background fits this role.",
    "Thank you for reviewing my application. I am available for an interview and can provide references on request.",
]

EMAIL_SUBJECTS = [
    "Application for {title} - {name}",
    "{title} Vacancy - Application from {name}",
    "Application: {title}{loc_suffix} - {name}",
    "CV for the {title} Position - {name}",
    "{name} - Application for {title}{loc_suffix}",
]

EMAIL_SIGNOFFS = ["Kind regards", "Sincerely", "Best regards", "Yours faithfully", "Warm regards"]


def _variant_index(seed: str, options: int, salt: str = "") -> int:
    digest = hashlib.md5((str(seed) + "|" + salt).encode("utf-8")).hexdigest()
    return int(digest, 16) % max(options, 1)

def _company_is_known(company: str) -> bool:
    return bool(company) and company.strip().lower() not in {
        "unknown", "n/a", "none", "", "company", "extracted company", "direct import",
    }

def _pretty_terms(terms: list[str], limit: int = 4) -> str:
    cleaned = []
    for t in terms[:limit]:
        t = str(t).strip()
        if not t:
            continue
        cleaned.append(t if len(t) > 3 else t.upper())
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return ", ".join(cleaned[:-1]) + " and " + cleaned[-1]

def generate_email_for_job(job: dict, master_cv: dict, cv_mode: str = CV_MODE_CUSTOM) -> tuple[str, str]:
    """Builds a UNIQUE subject + body per job.

    Uniqueness comes from three places:
      * the job's own UID picks different greeting/opener/closing variants,
      * the wording quotes this job's title, company, location and reference link,
      * the matched requirements are pulled from the truth-aware match report,
        so only real (direct) evidence is claimed, and transferable experience
        is described honestly as transferable.
    """
    master = normalize_master_cv(dict(master_cv or {}))
    contact = master.get("contact") or {}
    name = contact.get("name") or "Applicant"
    phone = contact.get("phone") or ""
    email = contact.get("email") or ""
    home_loc = contact.get("location") or ""

    uid = job.get("uid") or hashlib.md5(json.dumps(job, default=str, sort_keys=True).encode()).hexdigest()[:12]
    title = (job.get("title") or "the advertised position").strip()
    company = (job.get("company") or "").strip()
    location = (job.get("location") or "").strip()
    url = (job.get("url") or "").strip()
    description = job.get("description") or ""

    analysis = analyze_job(f"{title} {company} {description}")
    match = build_match_report(master, analysis)

    direct = match.get("direct") or []
    transferable = match.get("transferable") or []

    baseline_quals = [t for t in direct if t in BASELINE_QUALIFICATION_TERMS or t in QUALIFICATION_TERMS]
    baseline_licences = [t for t in direct if t in BASELINE_LICENCE_TERMS or t in LICENCE_TERMS]
    direct_skills = [t for t in direct if t in SKILL_TERMS or t in DUTY_TERMS]
    transfer_skills = [t for t in transferable if t in SKILL_TERMS or t in DUTY_TERMS] or transferable

    known_company = _company_is_known(company)
    where = f" in {location}" if location else ""

    # ---- Subject ----
    subj_template = EMAIL_SUBJECTS[_variant_index(uid, len(EMAIL_SUBJECTS), "subject")]
    loc_suffix = f" ({location})" if location else ""
    subject = subj_template.format(title=title, name=name, loc_suffix=loc_suffix)
    subject = re.sub(r"\s+", " ", subject).strip()[:180]

    # ---- Greeting ----
    if known_company:
        greeting = EMAIL_GREETINGS_NAMED[_variant_index(uid, len(EMAIL_GREETINGS_NAMED), "greet")].format(company=company)
    else:
        greeting = EMAIL_GREETINGS_GENERIC[_variant_index(uid, len(EMAIL_GREETINGS_GENERIC), "greet")]

    paragraphs = []

    # ---- Opening paragraph ----
    opener = EMAIL_OPENERS[_variant_index(uid, len(EMAIL_OPENERS), "open")].format(title=title, where=where)
    if known_company:
        opener += f" I believe my background is a good fit for what {company} is looking for."
    paragraphs.append(opener)

    # ---- Requirements paragraph (truth-aware) ----
    req_bits = []
    if baseline_quals:
        req_bits.append(f"I meet the stated minimum qualification requirement ({_pretty_terms(baseline_quals, 3)})")
    if baseline_licences:
        req_bits.append(f"I hold the required {_pretty_terms(baseline_licences, 3)}")
    if direct_skills:
        req_bits.append(f"I have hands-on experience in {_pretty_terms(direct_skills, 4)}")
    if req_bits:
        paragraphs.append("Regarding the requirements listed in the advert: " + "; ".join(req_bits) + ".")

    if transfer_skills:
        paragraphs.append(
            "In addition, my previous work has given me closely related experience that transfers directly to "
            f"{_pretty_terms(transfer_skills, 3)}, and I am a quick learner in areas that are new to me."
        )

    # ---- Personal / profile paragraph ----
    profile = (master.get("profile") or "").strip()
    if profile:
        trimmed = re.sub(r"\s+", " ", profile)[:320].strip()
        if trimmed and not trimmed.endswith((".", "!", "?")):
            trimmed += "."
        paragraphs.append(trimmed)

    # ---- Location / availability line ----
    if location and home_loc:
        paragraphs.append(f"I am currently based in {home_loc} and am available to work in {location}.")
    elif location:
        paragraphs.append(f"I am available to work in {location}.")

    # ---- Attachment paragraph (depends on the per-job CV choice) ----
    if cv_mode == CV_MODE_OWN:
        paragraphs.append("My CV is attached to this email for your consideration.")
    else:
        paragraphs.append(
            f"Attached is my CV, which I have set out specifically for the {title} role so that the relevant "
            "qualifications, skills and duties are easy to find."
        )

    # ---- Reference line ----
    if url:
        paragraphs.append(f"Advert reference: {url}")

    # ---- Closing ----
    paragraphs.append(EMAIL_CLOSERS[_variant_index(uid, len(EMAIL_CLOSERS), "close")])

    signoff = EMAIL_SIGNOFFS[_variant_index(uid, len(EMAIL_SIGNOFFS), "sign")]
    signature_lines = [signoff + ",", name]
    if phone:
        signature_lines.append(phone)
    if email:
        signature_lines.append(email)
    if home_loc:
        signature_lines.append(home_loc)

    body = greeting + "\n\n" + "\n\n".join(paragraphs) + "\n\n" + "\n".join(signature_lines) + "\n"
    return subject, body

def ensure_job_email(uid: str, overwrite: bool = False, quiet: bool = False) -> tuple[str, str] | None:
    """Makes sure a job has an email draft stored. Never overwrites a draft the
    user has edited by hand unless overwrite=True."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE uid = ?", (uid,))
    job = c.fetchone()
    if not job:
        conn.close()
        if not quiet:
            print(f"[!] Job {uid} not found.")
        return None

    has_draft = bool((job["email_body"] or "").strip())
    edited = bool(job["email_edited"])
    if has_draft and not overwrite:
        conn.close()
        return job["email_subject"] or "", job["email_body"] or ""
    if edited and not overwrite:
        conn.close()
        return job["email_subject"] or "", job["email_body"] or ""

    if not os.path.exists(MASTER_CV_PATH):
        conn.close()
        if not quiet:
            print("[!] Master CV not found - run `jobbot cv-import <file>` (or `jobbot cv-upload <file>`) first.")
        return None
    with open(MASTER_CV_PATH, "r", encoding="utf-8") as f:
        master_cv = json.load(f)

    job_dict = {k: job[k] for k in job.keys()}
    mode = job["cv_mode"] or CV_MODE_CUSTOM
    subject, body = generate_email_for_job(job_dict, master_cv, mode)
    c.execute("UPDATE jobs SET email_subject = ?, email_body = ?, email_edited = 0 WHERE uid = ?", (subject, body, uid))
    conn.commit()
    conn.close()
    if not quiet:
        print(f"[+] Email draft generated for {uid}.")
    return subject, body

def save_job_email(uid: str, subject: str, body: str, mark_edited: bool = True) -> bool:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT uid FROM jobs WHERE uid = ?", (uid,))
    if not c.fetchone():
        conn.close()
        return False
    c.execute(
        "UPDATE jobs SET email_subject = ?, email_body = ?, email_edited = ? WHERE uid = ?",
        (subject, body, 1 if mark_edited else 0, uid),
    )
    conn.commit()
    conn.close()
    return True

def _read_multiline(prompt: str) -> str:
    print(prompt)
    print("(Type a single line containing only  END  to finish, or press Ctrl-D / Ctrl-Z.)")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip() + "\n"

def _edit_in_editor(subject: str, body: str) -> tuple[str, str] | None:
    """Opens the draft in $EDITOR. First line is the subject, rest is the body."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        for candidate in ("nano", "vi", "notepad"):
            if shutil.which(candidate):
                editor = candidate
                break
    if not editor:
        print("[!] No text editor found. Set the EDITOR environment variable, or use --subject/--body.")
        return None
    content = (
        "SUBJECT: " + (subject or "") + "\n"
        "# ^ Keep the SUBJECT line first. Everything below the blank line is the email body.\n\n"
        + (body or "")
    )
    tmp = Path(tempfile.gettempdir()) / f"jobbot_email_{int(time.time())}.txt"
    tmp.write_text(content, encoding="utf-8")
    try:
        subprocess.run([editor, str(tmp)], check=False)
        edited = tmp.read_text(encoding="utf-8")
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass
    new_subject = subject
    body_lines = []
    for line in edited.split("\n"):
        if line.strip().startswith("#"):
            continue
        if line.upper().startswith("SUBJECT:") and new_subject == subject:
            new_subject = line.split(":", 1)[1].strip()
            continue
        body_lines.append(line)
    return new_subject, "\n".join(body_lines).strip() + "\n"


# ==========================================
# COMMAND HANDLERS
# ==========================================
def do_cv_import(args):
    path = args.file
    if not os.path.exists(path):
        print(f"[!] File not found: {path}")
        return
    try:
        text = extract_text(path)
        data = parse_cv(text)
        with open(MASTER_CV_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[+] Master CV imported at: {MASTER_CV_PATH}")
        print(f"    Name:        {data['contact']['name']}")
        print(f"    Email:       {data['contact']['email'] or '(not found)'}")
        print(f"    Phone:       {data['contact']['phone'] or '(not found)'}")
        print(f"    Skills:      {len(data['skills'])}")
        print(f"    Roles:       {len(data['experience'])}")
        print(f"    Education:   {len(data['education'])}")
        print(f"    Certs:       {len(data['certifications'])}")
    except Exception as e:
        print(f"[!] Import failed: {e}")

def do_cv_upload(args):
    """Registers the user's OWN CV file, used whenever a job is set to 'own cv'."""
    try:
        dest = store_own_cv(args.file)
        print(f"[+] Own CV registered: {dest}")
        print("    Jobs set to \"own cv\" will have this exact file attached, unchanged.")
    except Exception as e:
        print(f"[!] Upload failed: {e}")
        return
    # Convenience: if no master CV exists yet, parse the uploaded CV so that
    # email letters (name, phone, skills, evidence) can still be generated.
    if not os.path.exists(MASTER_CV_PATH):
        try:
            text = extract_text(dest)
            data = parse_cv(text)
            with open(MASTER_CV_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[+] Also parsed it into a master CV profile ({MASTER_CV_PATH}) for email personalisation.")
        except Exception as e:
            print(f"[*] Could not auto-parse it into a master CV ({e}). Run `jobbot cv-import <file>` if you want tailored emails.")

def do_cv_own(args):
    own = get_own_cv_path()
    if own:
        size = own.stat().st_size // 1024
        print(f"[*] Own CV currently in use: {own} ({size} KB)")
    else:
        print("[*] No own CV uploaded yet. Add one with: jobbot cv-upload <file>")

def do_cv_mode(args):
    mode = normalise_cv_mode(args.mode)
    if mode is None:
        print("[!] Unrecognised mode. Use \"custom ats cv\" (or custom) or \"own cv\" (or own).")
        return
    if mode == CV_MODE_OWN and not get_own_cv_path():
        print("[!] Warning: no own CV file uploaded yet. Run `jobbot cv-upload <file>` before dispatch.")
    if set_job_cv_mode(args.uid, mode, select=not args.no_select):
        print(f"[+] Job {args.uid} will use: {CV_MODE_LABELS[mode]}")
        ensure_job_email(args.uid, overwrite=False, quiet=True)
    else:
        print(f"[!] Job {args.uid} not found.")

def do_choose(args):
    run_cv_mode_chooser(uids=args.uid or None, only_undecided=not args.all)

def do_cv_list(args):
    if not os.path.exists(CVS_DIR):
        print("[!] No CVs directory found.")
        return
    files = sorted([f for f in os.listdir(CVS_DIR) if f.endswith(".pdf")], key=lambda x: os.path.getmtime(os.path.join(CVS_DIR, x)), reverse=True)
    if not files:
        print("[*] No tailored CV PDFs generated yet in out/cvs/")
        return
    print("\n--- Tailored Generated CVs ---")
    for i, fname in enumerate(files, 1):
        fpath = Path(CVS_DIR) / fname
        json_path = fpath.with_suffix(".json")
        note = ""
        if json_path.exists():
            try:
                meta = json.loads(json_path.read_text(encoding="utf-8"))
                cov = meta.get("keyword_coverage_percent", "?")
                comp = meta.get("company", "")
                note = f" [{cov}% coverage | {comp}]"
            except Exception:
                pass
        size = fpath.stat().st_size // 1024
        print(f"[{i}] {fname} ({size} KB){note}")

def do_cv_view(args):
    files = sorted([f for f in os.listdir(CVS_DIR) if f.endswith(".pdf")], key=lambda x: os.path.getmtime(os.path.join(CVS_DIR, x)), reverse=True) if os.path.exists(CVS_DIR) else []
    if not files or args.n > len(files) or args.n < 1:
        print(f"[!] Invalid index: {args.n}. Check `jobbot cv-list`.")
        return
    target = Path(CVS_DIR) / files[args.n - 1]
    print(f"[*] Opening {target.name}...")
    open_pdf(target)

def do_cv_preview(args):
    files = sorted([f for f in os.listdir(CVS_DIR) if f.endswith(".pdf")], key=lambda x: os.path.getmtime(os.path.join(CVS_DIR, x)), reverse=True) if os.path.exists(CVS_DIR) else []
    if not files or args.n > len(files) or args.n < 1:
        print(f"[!] Invalid index: {args.n}.")
        return
    target = Path(CVS_DIR) / files[args.n - 1]
    print(f"\n--- Preview: {target.name} ---")
    print(ats_preview(target))
    print("\n--- ATS Validation Checks ---")
    ats = validate_ats(target)
    print(f"Status: {ats['status']} ({ats['passed']}/{ats['total']} passed, {ats.get('page_count', 0)} page(s))")

def do_src(args):
    conn = get_db()
    c = conn.cursor()
    action = args.action
    if action == "list":
        c.execute("SELECT * FROM sources")
        rows = c.fetchall()
        print("\n--- Registered Job Sources ---")
        for r in rows:
            status = "ON" if r["active"] else "OFF"
            print(f"[{r['id']}] {r['name']} ({status})\n    URL: {r['url']}")
    elif action == "add":
        if not args.target:
            print("[!] Please supply a URL to add.")
            return
        sid = "src_" + hashlib.md5(args.target.encode()).hexdigest()[:8]
        c.execute("INSERT OR REPLACE INTO sources (id, url, name, active) VALUES (?, ?, ?, 1)", (sid, args.target, args.target))
        conn.commit()
        print(f"[+] Added source: {sid}")
    elif action in ["on", "off"]:
        val = 1 if action == "on" else 0
        c.execute("UPDATE sources SET active = ? WHERE id = ?", (val, args.target))
        conn.commit()
        print(f"[+] Set source {args.target} status to {action.upper()}")
    elif action == "test":
        print(f"[*] Testing connection to: {args.target}")
        try:
            req = urllib.request.Request(args.target, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f"[+] Status Code: {resp.status}")
        except Exception as e:
            print(f"[!] Connection failed: {e}")
    conn.close()

def do_fetch(args):
    # --- 1. MANDATORY PROVINCE SELECTION ---
    # Fetch cannot proceed until a valid South African province is chosen.
    # If an invalid or empty value was passed on the command line, the user
    # is forced into the interactive menu instead.
    province_input = (args.province or "").strip().lower()
    if province_input not in PROVINCE_CITY_MAP:
        if province_input:
            print(f"[!] '{args.province}' is not a recognised South African province.")
        province_input = prompt_for_province()

    province_terms = PROVINCE_CITY_MAP[province_input]
    keyword_filters = [k.strip().lower() for k in args.keywords.split(",") if k.strip()]

    print("\n" + "=" * 72)
    print(f"[*] PROVINCE FILTER (selected): {province_input.title()}")
    other_terms = [t.title() for t in province_terms if t != province_input]
    print(f"    Also matching cities/towns: {', '.join(other_terms)}")
    print("[*] BASELINE FILTER (always on, cannot be disabled):")
    print("    Job must mention Grade 12 / Matric / NCV Level 4 (or equivalent)")
    print("    OR a Driver's Licence (Code 8/10/14, PDP, or equivalent).")
    if keyword_filters:
        print(f"[*] Extra keyword filter: {', '.join(keyword_filters)}")
    print("=" * 72)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM sources WHERE active = 1")
    sources = c.fetchall()

    added = 0
    skipped_location = 0
    skipped_baseline = 0
    skipped_keyword = 0
    skipped_duplicate = 0
    new_uids = []

    for s in sources:
        try:
            req = urllib.request.Request(s["url"], headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                root = ET.fromstring(data)
                for item in root.findall(".//item"):
                    title = item.findtext("title", "Untitled Job")
                    link = item.findtext("link", "")
                    desc = item.findtext("description", "")
                    combined = f"{title} {desc}".lower()

                    # Province + city filter
                    if not any(term in combined for term in province_terms):
                        skipped_location += 1
                        continue

                    # Mandatory baseline requirement filter (always on)
                    if not passes_baseline_filter(combined):
                        skipped_baseline += 1
                        continue

                    # Optional extra keyword filter
                    if keyword_filters and not any(kw in combined for kw in keyword_filters):
                        skipped_keyword += 1
                        continue

                    uid = hashlib.md5((title + link).encode()).hexdigest()[:12]
                    scam = calculate_scam_score(title + " " + desc)
                    match = calculate_match_score(title + " " + desc)
                    email = extract_email(desc)
                    c.execute("""
                        INSERT OR IGNORE INTO jobs 
                        (uid, source_id, title, company, location, url, description, contact_email, match_score, scam_score, created_at, cv_mode, email_subject, email_body, email_edited)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', 0)
                    """, (uid, s["id"], title, "Unknown", province_input.title(), link, desc, email, match, scam, datetime.datetime.now().isoformat()))
                    if c.rowcount:
                        added += 1
                        new_uids.append(uid)
                    else:
                        skipped_duplicate += 1
        except Exception as e:
            print(f"[!] Could not parse feed {s['name']}: {e}")
    conn.commit()
    conn.close()

    print(f"\n[+] Fetch complete for {province_input.title()}.")
    print(f"    Added:                              {added}")
    print(f"    Skipped (outside selected province): {skipped_location}")
    print(f"    Skipped (failed baseline filter):    {skipped_baseline}")
    print(f"    Skipped (keyword mismatch):          {skipped_keyword}")
    print(f"    Skipped (duplicate):                 {skipped_duplicate}")

    # --- 2. PER-JOB CV CHOICE: "custom ats cv" or "own cv" ---
    if added and not args.no_choose:
        run_cv_mode_chooser(uids=new_uids, only_undecided=False)
    elif added:
        print("\n[*] CV choice skipped (--no-choose). Run `jobbot choose` to pick custom ats cv / own cv per job.")

def do_import_url(args):
    url = args.url
    print(f"[*] Scraping job posting from: {url}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "Imported Job Posting"
            clean_text = re.sub(r'<[^>]+>', ' ', html)
            uid = hashlib.md5(url.encode()).hexdigest()[:12]
            scam = calculate_scam_score(clean_text)
            match = calculate_match_score(clean_text)
            email = extract_email(clean_text)
            conn = get_db()
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO jobs 
                (uid, source_id, title, company, location, url, description, contact_email, match_score, scam_score, created_at, cv_mode, email_subject, email_body, email_edited)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', 0)
            """, (uid, "manual_url", title, "Extracted Company", "Cape Town", url, clean_text[:2000], email, match, scam, datetime.datetime.now().isoformat()))
            conn.commit()
            conn.close()
            print(f"[+] Successfully imported job listing. UID: {uid}")
            if not args.no_choose:
                run_cv_mode_chooser(uids=[uid], only_undecided=False)
    except Exception as e:
        print(f"[!] Import failed: {e}")

def do_import_text(args):
    if not os.path.exists(args.file):
        print(f"[!] File not found: {args.file}")
        return
    with open(args.file, "r", encoding="utf-8") as f:
        text = f.read()
    uid = hashlib.md5(text.encode()).hexdigest()[:12]
    scam = calculate_scam_score(text, args.company)
    match = calculate_match_score(text)
    email = extract_email(text)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT uid FROM jobs WHERE uid = ?", (uid,))
    exists = c.fetchone() is not None
    if exists and not args.force:
        print(f"[!] A job with identical text already exists (UID: {uid}). Use --force to overwrite.")
        conn.close()
        return
    c.execute("""
        INSERT OR REPLACE INTO jobs 
        (uid, source_id, title, company, location, url, description, contact_email, match_score, scam_score, created_at, cv_mode, email_subject, email_body, email_edited)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', 0)
    """, (uid, "manual_text", args.title, args.company or "Direct Import", args.location or "Parow, Cape Town", args.url, text, email, match, scam, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"[{'+' if not exists else '+ (overwritten)'}] Successfully imported raw job text. UID: {uid}")
    if not args.no_choose:
        run_cv_mode_chooser(uids=[uid], only_undecided=False)

def do_summary(args):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT uid, title, company, location, match_score, scam_score, selected, contact_email, cv_mode, email_body, email_edited FROM jobs ORDER BY match_score DESC")
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("[*] No job listings found. Run `jobbot fetch` or `jobbot import-text` first.")
        return
    print("\n" + "=" * 118)
    print("Note: jobs added via `jobbot fetch` already passed the mandatory baseline filter")
    print("(Grade 12/Matric/NCV Level 4 or equivalent, OR Driver's Licence or equivalent).")
    print("Manually imported jobs (import-url/import-text) are not subject to this filter.")
    print("CV column: 'custom ats cv' = built by JobBot, 'own cv' = your uploaded file.")
    print("=" * 118)
    print(f"{'UID':<14}{'SEL':<5}{'MATCH%':<8}{'SCAM%':<7}{'CV CHOICE':<16}{'EMAIL':<12}{'LOCATION':<15}{'TITLE & COMPANY':<40}")
    print("=" * 118)
    for r in rows:
        sel = "[X]" if r["selected"] else "[ ]"
        company_name = r['company'] or "Unknown"
        title_comp = f"{r['title'][:22]} ({company_name[:14]})"
        location = (r['location'] or "")[:14]
        mode_label = CV_MODE_LABELS.get(r["cv_mode"] or "", "(not chosen)")
        if (r["email_body"] or "").strip():
            email_state = "edited" if r["email_edited"] else "draft"
        else:
            email_state = "-"
        print(f"{r['uid']:<14}{sel:<5}{r['match_score']:<8}{r['scam_score']:<7}{mode_label:<16}{email_state:<12}{location:<15}{title_comp:<40}")
    print("=" * 118)
    print("Pick CVs per job : jobbot choose            View/edit an email : jobbot email-show <uid> / email-edit <uid>")

def do_toggle(args):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT selected FROM jobs WHERE uid = ?", (args.uid,))
    row = c.fetchone()
    if not row:
        print(f"[!] Job with UID {args.uid} not found.")
        conn.close()
        return
    new_val = 0 if row["selected"] else 1
    c.execute("UPDATE jobs SET selected = ? WHERE uid = ?", (new_val, args.uid))
    conn.commit()
    conn.close()
    status = "SELECTED" if new_val else "UNSELECTED"
    print(f"[+] Job {args.uid} is now {status}.")

def do_email_list(args):
    conn = get_db()
    c = conn.cursor()
    if args.selected:
        c.execute("SELECT * FROM jobs WHERE selected = 1 ORDER BY match_score DESC")
    else:
        c.execute("SELECT * FROM jobs ORDER BY match_score DESC")
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("[*] No jobs found.")
        return
    print("\n--- Per-Job Email Drafts ---")
    for r in rows:
        state = "EDITED BY YOU" if r["email_edited"] else ("auto-draft" if (r["email_body"] or "").strip() else "not generated")
        mode_label = CV_MODE_LABELS.get(r["cv_mode"] or "", "(not chosen)")
        print(f"\n[{r['uid']}] {r['title']} @ {r['company'] or 'Unknown'}")
        print(f"    CV choice : {mode_label}")
        print(f"    To        : {r['contact_email'] or '(no email found)'}")
        print(f"    Subject   : {r['email_subject'] or '(none yet)'}")
        print(f"    Status    : {state}")
    print("\nView full text: jobbot email-show <uid>    Edit: jobbot email-edit <uid>    Regenerate: jobbot email-regen <uid>")

def do_email_show(args):
    result = ensure_job_email(args.uid, overwrite=False, quiet=True)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE uid = ?", (args.uid,))
    job = c.fetchone()
    conn.close()
    if not job:
        print(f"[!] Job {args.uid} not found.")
        return
    if not (job["email_body"] or "").strip():
        print("[!] No email draft available. Import a master CV first (`jobbot cv-import <file>`), then run `jobbot email-regen`.")
        return
    mode_label = CV_MODE_LABELS.get(job["cv_mode"] or "", "(not chosen)")
    print("\n" + "=" * 72)
    print(f"JOB      : {job['title']} @ {job['company'] or 'Unknown'}  [{job['uid']}]")
    print(f"CV CHOICE: {mode_label}")
    print(f"TO       : {job['contact_email'] or '(no email found)'}")
    print(f"SUBJECT  : {job['email_subject']}")
    print(f"STATE    : {'edited by you' if job['email_edited'] else 'auto-generated draft'}")
    print("=" * 72)
    print(job["email_body"])
    print("=" * 72)
    print("Not happy with it? Edit with: jobbot email-edit " + args.uid)

def do_email_edit(args):
    ensure_job_email(args.uid, overwrite=False, quiet=True)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE uid = ?", (args.uid,))
    job = c.fetchone()
    conn.close()
    if not job:
        print(f"[!] Job {args.uid} not found.")
        return

    subject = job["email_subject"] or ""
    body = job["email_body"] or ""

    # Mode A: values supplied directly on the command line
    if args.subject or args.body or args.body_file:
        new_subject = args.subject if args.subject else subject
        if args.body_file:
            p = Path(args.body_file).expanduser()
            if not p.exists():
                print(f"[!] Body file not found: {p}")
                return
            new_body = p.read_text(encoding="utf-8")
        elif args.body:
            new_body = args.body.replace("\\n", "\n")
        else:
            new_body = body
        save_job_email(args.uid, new_subject.strip(), new_body, mark_edited=True)
        print(f"[+] Email for {args.uid} updated.")
        return

    # Mode B: external editor
    if args.editor:
        edited = _edit_in_editor(subject, body)
        if not edited:
            return
        new_subject, new_body = edited
        save_job_email(args.uid, new_subject.strip(), new_body, mark_edited=True)
        print(f"[+] Email for {args.uid} updated from editor.")
        return

    # Mode C: interactive inline editing
    print("\n--- Current email ---")
    print(f"Subject: {subject}")
    print("-" * 60)
    print(body)
    print("-" * 60)
    if not sys.stdin.isatty():
        print("[!] Not an interactive terminal. Use --subject/--body/--body-file or --editor.")
        return
    new_subject = input(f"\nNew subject (Enter to keep current): ").strip() or subject
    change_body = input("Rewrite the body as well? (y/N): ").strip().lower() == "y"
    new_body = _read_multiline("\nType the new email body:") if change_body else body
    save_job_email(args.uid, new_subject, new_body, mark_edited=True)
    print(f"[+] Email for {args.uid} saved. Preview it with: jobbot email-show {args.uid}")

def do_email_regen(args):
    conn = get_db()
    c = conn.cursor()
    if args.all:
        c.execute("SELECT uid, email_edited FROM jobs")
    elif args.selected:
        c.execute("SELECT uid, email_edited FROM jobs WHERE selected = 1")
    else:
        c.execute("SELECT uid, email_edited FROM jobs WHERE uid = ?", (args.uid or "",))
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("[!] Nothing to regenerate. Give a UID, or use --selected / --all.")
        return
    regenerated = protected = 0
    for row in rows:
        if row["email_edited"] and not args.force:
            protected += 1
            continue
        if ensure_job_email(row["uid"], overwrite=True, quiet=True):
            regenerated += 1
    print(f"[+] Regenerated {regenerated} email draft(s).")
    if protected:
        print(f"[*] Left {protected} hand-edited email(s) untouched (use --force to overwrite them too).")

def _build_attachment(job, master_cv, mode: str) -> tuple[Path | None, dict | None]:
    """Returns (attachment_path, audit_report). Honours the per-job CV choice."""
    company_name = job["company"] or "Company"
    if mode == CV_MODE_OWN:
        own = get_own_cv_path()
        if not own:
            print("    [!] This job is set to \"own cv\" but no own CV file is uploaded.")
            print("        Fix with: jobbot cv-upload <file>   (or switch it: jobbot cv-mode <uid> \"custom ats cv\")")
            return None, None
        print(f"    [+] Using your own CV: {own.name}")
        return own, {
            "title": job["title"],
            "company": job["company"] or "",
            "cv_mode": CV_MODE_LABELS[CV_MODE_OWN],
            "attachment": str(own),
        }

    job_info = {
        "title": job["title"],
        "company": job["company"] or "",
        "location": job["location"] or "",
        "description": job["description"] or "",
    }
    tailored_cv = tailor(master_cv, job_info)
    analysis = tailored_cv.pop("_analysis")
    match = tailored_cv.pop("_match")

    company_clean = re.sub(r'[^a-zA-Z0-9]', '_', company_name)
    pdf_filename = f"CV_{job['uid']}_{company_clean}.pdf"
    pdf_path = Path(CVS_DIR) / pdf_filename
    render_pdf(tailored_cv, pdf_path)
    print(f"    [+] Generated custom ATS PDF: {pdf_path}")
    print(f"    [*] Evidence / Keyword Coverage: {match['keyword_coverage_percent']}%")

    report = {
        "title": job["title"],
        "company": job["company"] or "",
        "cv_mode": CV_MODE_LABELS[CV_MODE_CUSTOM],
        "keyword_coverage_percent": match["keyword_coverage_percent"],
        "direct_matches": match["direct"],
        "transferable_matches": match["transferable"],
        "missing": match["missing"],
        "ats_validation": validate_ats(pdf_path, tailored_cv),
    }
    pdf_path.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return pdf_path, report

def _attach_file(msg: MIMEMultipart, path: Path) -> None:
    with open(path, "rb") as f:
        part = MIMEApplication(f.read(), Name=path.name)
    part["Content-Disposition"] = f'attachment; filename="{path.name}"'
    msg.attach(part)

def do_send(args):
    settings = load_settings()
    delay = getattr(args, "delay", None)
    if delay is None:
        delay = settings.get("send_delay_seconds", DEFAULT_SEND_DELAY)
    try:
        delay = max(0, int(delay))
    except Exception:
        delay = DEFAULT_SEND_DELAY
    jitter = getattr(args, "jitter", None)
    if jitter is None:
        jitter = settings.get("send_delay_jitter", DEFAULT_SEND_JITTER)
    try:
        jitter = max(0, int(jitter))
    except Exception:
        jitter = DEFAULT_SEND_JITTER
    max_per_run = getattr(args, "max_per_run", None)
    if max_per_run is None:
        max_per_run = settings.get("max_emails_per_run", DEFAULT_MAX_PER_RUN)
    try:
        max_per_run = max(1, int(max_per_run))
    except Exception:
        max_per_run = DEFAULT_MAX_PER_RUN
    auto_yes = getattr(args, "yes", False)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE selected = 1")
    selected_jobs = c.fetchall()

    if not selected_jobs:
        print("[!] No jobs selected for dispatch. Toggle jobs using `jobbot toggle <uid>` or via web.")
        conn.close()
        return

    if not os.path.exists(MASTER_CV_PATH):
        print("[!] Master CV not found. Run `jobbot cv-import <file>` first.")
        conn.close()
        return

    with open(MASTER_CV_PATH, "r", encoding="utf-8") as f:
        master_cv = json.load(f)

    print(f"\n[*] Preparing to process {len(selected_jobs)} selected job applications...")
    print("[*] THROTTLE (anti-ban): " + (
        f"waiting {delay}s (+0-{jitter}s random) between each email; max {max_per_run} emails this run."
        if delay else f"delay disabled (!); max {max_per_run} emails this run."))
    print("    Gmail guideline: about 500 messages per 24h on free accounts, about 2,000 on Workspace.")
    if delay == 0:
        print("    [!] Sending with no gap greatly increases the risk of Gmail throttling or locking the account.")

    sent_count = 0
    for job in selected_jobs:
        company_name = job['company'] or "Company"
        mode = job["cv_mode"] or ""
        if not mode:
            if sys.stdin.isatty() and not auto_yes:
                print(f"\n[?] No CV choice recorded for '{job['title']}' @ {company_name}.")
                chosen = prompt_cv_mode(job)
                if chosen in (None, "__STOP__"):
                    print("    [*] Skipped - no CV choice made.")
                    continue
                mode = chosen
                set_job_cv_mode(job["uid"], mode, select=True)
            else:
                mode = CV_MODE_CUSTOM
                set_job_cv_mode(job["uid"], mode, select=True)
                print(f"\n[*] '{job['title']}' had no CV choice - defaulting to {CV_MODE_LABELS[CV_MODE_CUSTOM]}.")

        print(f"\n--> Preparing application for: {job['title']} at {company_name}")
        print(f"    CV choice: {CV_MODE_LABELS.get(mode, mode)}")

        attachment_path, report = _build_attachment(job, master_cv, mode)
        if attachment_path is None:
            c.execute("UPDATE jobs SET status = 'Blocked (no own CV file)' WHERE uid = ?", (job["uid"],))
            continue

        # Per-job email: use the stored (possibly hand-edited) draft, else make one.
        c.execute("SELECT email_subject, email_body, email_edited FROM jobs WHERE uid = ?", (job["uid"],))
        row = c.fetchone()
        subject = (row["email_subject"] or "").strip()
        body = (row["email_body"] or "").strip()
        if not body:
            job_dict = {k: job[k] for k in job.keys()}
            subject, body = generate_email_for_job(job_dict, master_cv, mode)
            c.execute("UPDATE jobs SET email_subject = ?, email_body = ?, email_edited = 0 WHERE uid = ?",
                      (subject, body, job["uid"]))
            conn.commit()
            print("    [+] Unique email letter generated for this job.")
        else:
            print(f"    [+] Using stored email ({'your edited version' if row['email_edited'] else 'auto-draft'}).")

        recipient_email = job["contact_email"]
        if not recipient_email:
            print(f"    [!] Skipping automated email dispatch for {job['uid']}: No contact email address found.")
            c.execute("UPDATE jobs SET status = 'CV Ready (No Email)' WHERE uid = ?", (job["uid"],))
            continue

        if not auto_yes:
            print("\n    ----- EMAIL PREVIEW -----")
            print(f"    To     : {recipient_email}")
            print(f"    Subject: {subject}")
            print("    " + "-" * 40)
            for line in body.split("\n"):
                print("    " + line)
            print("    " + "-" * 40)
            confirm = input(f"    [?] Send this email to {recipient_email}? (y = send / e = edit first / N = skip): ").strip().lower()
            if confirm == "e":
                do_email_edit(argparse.Namespace(uid=job["uid"], subject="", body="", body_file="", editor=False))
                c.execute("SELECT email_subject, email_body FROM jobs WHERE uid = ?", (job["uid"],))
                row = c.fetchone()
                subject = (row["email_subject"] or "").strip()
                body = (row["email_body"] or "").strip()
                confirm = input(f"    [?] Send the updated email to {recipient_email}? (y/N): ").strip().lower()
            if confirm != "y":
                print("    [*] Dispatch skipped by user.")
                continue

        # SMTP Dispatch
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 465))
        sender_email = os.environ.get("SMTP_USER", master_cv.get("contact", {}).get("email"))
        sender_password = os.environ.get("SMTP_PASS", "")

        if not sender_password:
            print("    [!] SMTP credentials not configured in environment (SMTP_USER, SMTP_PASS).")
            print("    [*] Application recorded locally in database.")
            c.execute("UPDATE jobs SET status = 'CV Tailored Ready' WHERE uid = ?", (job["uid"],))
            c.execute("""INSERT INTO applications (job_uid, company, title, contact_email, cv_path, sent_at, status, cv_mode, email_subject, email_body)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (job["uid"], company_name, job["title"], recipient_email, str(attachment_path),
                       datetime.datetime.now().isoformat(), "Prepared", CV_MODE_LABELS.get(mode, mode), subject, body))
            conn.commit()
            continue

        if sent_count >= max_per_run:
            print(f"    [!] Per-run cap of {max_per_run} emails reached - stopping here to protect the account.")
            print("        Run `jobbot send` again later (or raise --max-per-run) to continue.")
            break

        # --- Throttle: wait before every email except the first one ---
        if sent_count > 0 and delay > 0:
            wait = delay + (random.randint(0, jitter) if jitter else 0)
            print(f"    [*] Anti-ban pause: waiting {wait}s before the next send...")
            time.sleep(wait)

        try:
            msg = MIMEMultipart()
            msg["From"] = sender_email
            msg["To"] = recipient_email
            msg["Subject"] = subject or f"Application for {job['title']}"
            msg.attach(MIMEText(body, "plain", "utf-8"))
            _attach_file(msg, Path(attachment_path))

            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, recipient_email, msg.as_string())

            sent_count += 1
            print(f"    [+] Email {sent_count} successfully sent to {recipient_email}")
            c.execute("UPDATE jobs SET status = 'Applied' WHERE uid = ?", (job["uid"],))
            c.execute("""INSERT INTO applications (job_uid, company, title, contact_email, cv_path, sent_at, status, cv_mode, email_subject, email_body)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (job["uid"], company_name, job["title"], recipient_email, str(attachment_path),
                       datetime.datetime.now().isoformat(), "Sent", CV_MODE_LABELS.get(mode, mode), subject, body))
            conn.commit()
        except Exception as e:
            print(f"    [!] Email dispatch error: {e}")
            c.execute("UPDATE jobs SET status = 'Send Failed' WHERE uid = ?", (job["uid"],))
            conn.commit()

    # Daily volume awareness
    try:
        today = datetime.date.today().isoformat()
        c.execute("SELECT COUNT(*) FROM applications WHERE status = 'Sent' AND sent_at LIKE ?", (today + "%",))
        today_total = c.fetchone()[0]
    except Exception:
        today_total = sent_count

    conn.commit()
    conn.close()

    print(f"\n[+] Dispatch run finished. Emails sent this run: {sent_count}")
    print(f"    Emails sent today (recorded): {today_total}")
    if today_total >= GMAIL_DAILY_SOFT_LIMIT * 0.8:
        print(f"    [!] You are close to the ~{GMAIL_DAILY_SOFT_LIMIT}/day guideline for free Gmail accounts. Consider pausing until tomorrow.")

def do_block(args):
    with open(BLOCKLIST_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n{args.name.strip()}")
    print(f"[+] Added '{args.name}' to blocklist file: {BLOCKLIST_PATH}")

def do_history(args):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM applications ORDER BY id DESC LIMIT ?", (args.n,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("[*] No application history recorded yet.")
        return
    print("\n--- Dispatch Application History ---")
    for r in rows:
        keys = r.keys()
        mode = r["cv_mode"] if "cv_mode" in keys and r["cv_mode"] else "-"
        print(f"[{r['id']}] {r['sent_at'][:16]} | {r['title']} @ {r['company']} ({r['contact_email']}) -> {r['status']} | CV: {mode}")

def do_config(args):
    settings = load_settings()
    if args.key:
        if args.value is None:
            print(f"{args.key} = {settings.get(args.key)}")
            return
        value = args.value
        if args.key in {"send_delay_seconds", "send_delay_jitter", "max_emails_per_run"}:
            try:
                value = int(value)
            except ValueError:
                print("[!] That setting needs a whole number.")
                return
        settings[args.key] = value
        save_settings(settings)
        print(f"[+] {args.key} = {value}")
        return
    print("\n--- JobBot Settings (config/settings.json) ---")
    for k, v in settings.items():
        print(f"  {k} = {v}")
    print("\nChange one with: jobbot config send_delay_seconds 10")


# ==========================================
# WEB DASHBOARD
# ==========================================
def build_flask_app():
    """Build and return the JobBot Flask app WITHOUT running it.
    Used both by the CLI 'web' command and by the Android mobile entrypoint
    (main.py), which starts this in a background thread and shows it inside
    a native WebView instead of a desktop browser."""
    if not Flask:
        print("[!] Flask is not installed. Run: pip install flask")
        return None

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>JobBot Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            :root {
                --bg: #0b1220; --bg-soft: #0f1b30; --card: #142238; --card-border: #1f3358;
                --accent: #3b82f6; --accent-dark: #1d4ed8; --accent-soft: #1e3a8a;
                --text: #e6edf7; --text-dim: #93a4c3; --danger: #ef4444; --warn: #f59e0b; --ok: #22c55e;
            }
            * { box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; background: linear-gradient(180deg, var(--bg) 0%, var(--bg-soft) 100%); color: var(--text); min-height: 100vh; }
            h1 { color: var(--text); font-weight: 700; letter-spacing: -0.02em; display:flex; align-items:center; gap:10px; margin-bottom: 4px; }
            h3 { color: var(--text); margin-bottom: 4px; }
            a { color: var(--accent); }
            .card { background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; padding: 16px; margin-bottom: 14px; box-shadow: 0 4px 14px rgba(0,0,0,0.25); }
            .btn { background: var(--accent); color: white; padding: 9px 16px; border: none; border-radius: 8px; text-decoration: none; cursor: pointer; display:inline-block; margin: 3px 4px 3px 0; font-size: 14px; font-weight: 600; transition: background 0.15s ease; }
            .btn:hover { background: var(--accent-dark); }
            .btn-danger { background: var(--danger); }
            .btn-blue { background: var(--accent-dark); }
            .btn-grey { background: #2b3b57; color: var(--text-dim); }
            .btn-outline { background: transparent; color: var(--text-dim); border: 1px solid var(--card-border); }
            .badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; background: #1f2f4a; color: var(--text-dim); margin: 2px 4px 2px 0; }
            .badge-scam { background: rgba(239,68,68,0.15); color: #f87171; }
            .badge-match { background: rgba(34,197,94,0.15); color: #4ade80; }
            .badge-cv { background: rgba(59,130,246,0.18); color: #93c5fd; }
            .badge-warn { background: rgba(245,158,11,0.15); color: #fbbf24; }
            .note { background: rgba(59,130,246,0.08); border: 1px solid var(--accent-soft); padding: 12px 16px; border-radius: 10px; font-size: 14px; color: var(--text-dim); }
            textarea { width: 100%; min-height: 340px; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px; padding: 10px; background: var(--bg-soft); color: var(--text); border: 1px solid var(--card-border); border-radius: 8px; }
            input[type=text] { width: 100%; padding: 9px; font-size: 14px; background: var(--bg-soft); color: var(--text); border: 1px solid var(--card-border); border-radius: 8px; }
            code { background: rgba(59,130,246,0.12); color: #93c5fd; padding: 1px 5px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>💙 JobBot Dashboard</h1>
        <p class="note">
            <strong>Active filters on `fetch`:</strong> Baseline requirement filter is always on
            (Grade 12 / Matric / NCV Level 4 or equivalent, OR Driver's Licence or equivalent).
            Province filter is chosen each time you run <code>jobbot fetch</code>.<br>
            <strong>Sending throttle:</strong> {{ delay }}s (+0-{{ jitter }}s random) between emails, max {{ max_per_run }} per run.<br>
            <strong>Own CV file:</strong> {{ own_cv or 'none uploaded yet' }} &nbsp; <a href="/own-cv">upload / change</a>
        </p>
        <p>
            <a href="/send" class="btn">Process &amp; Dispatch Selected Jobs</a>
            <a href="/own-cv" class="btn btn-grey">Upload Own CV</a>
        </p>
        <div>
            {% for job in jobs %}
            <div class="card">
                <h3>{{ job.title }} - <small style="color:var(--text-dim);">{{ job.company or 'Unknown' }}</small></h3>
                <p style="color:var(--text-dim);"><strong style="color:var(--text);">Location:</strong> {{ job.location }} | <strong style="color:var(--text);">Contact:</strong> {{ job.contact_email or 'N/A' }}</p>
                <p>
                    <span class="badge badge-match">Match: {{ job.match_score }}%</span>
                    <span class="badge badge-scam">Scam Risk: {{ job.scam_score }}%</span>
                    <span class="badge">Status: {{ job.status }}</span>
                    {% if job.cv_mode == 'custom' %}
                        <span class="badge badge-cv">CV: custom ats cv</span>
                    {% elif job.cv_mode == 'own' %}
                        <span class="badge badge-cv">CV: own cv</span>
                    {% else %}
                        <span class="badge badge-warn">CV: not chosen yet</span>
                    {% endif %}
                    {% if job.email_edited %}<span class="badge badge-cv">Email: edited by you</span>
                    {% elif job.email_body %}<span class="badge">Email: auto-draft</span>
                    {% else %}<span class="badge badge-warn">Email: none yet</span>{% endif %}
                </p>
                <p><strong>Choose the CV for this job:</strong><br>
                    <a href="/mode/{{ job.uid }}/custom" class="btn {% if job.cv_mode != 'custom' %}btn-outline{% endif %}">custom ats cv</a>
                    <a href="/mode/{{ job.uid }}/own" class="btn {% if job.cv_mode != 'own' %}btn-outline{% endif %}">own cv</a>
                </p>
                <p>
                    <a href="/email/{{ job.uid }}" class="btn btn-blue">View / Edit Email</a>
                    <a href="/regen/{{ job.uid }}" class="btn btn-grey">Regenerate Email</a>
                    <a href="/toggle/{{ job.uid }}" class="btn {% if job.selected %}btn-danger{% endif %}">
                        {% if job.selected %}Unselect{% else %}Select for Dispatch{% endif %}
                    </a>
                </p>
            </div>
            {% endfor %}
        </div>
    </body>
    </html>
    """

    EMAIL_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Email - {{ job.title }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            :root {
                --bg: #0b1220; --bg-soft: #0f1b30; --card: #142238; --card-border: #1f3358;
                --accent: #3b82f6; --accent-dark: #1d4ed8; --text: #e6edf7; --text-dim: #93a4c3;
            }
            * { box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; background: linear-gradient(180deg, var(--bg) 0%, var(--bg-soft) 100%); color: var(--text); min-height: 100vh; }
            .card { background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px; box-shadow: 0 4px 14px rgba(0,0,0,0.25); }
            .btn { background: var(--accent); color: white; padding: 9px 16px; border: none; border-radius: 8px; text-decoration: none; cursor: pointer; display:inline-block; font-size: 14px; font-weight: 600; }
            .btn:hover { background: var(--accent-dark); }
            .btn-grey { background: #2b3b57; color: var(--text-dim); }
            textarea { width: 100%; min-height: 380px; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px; padding: 10px; background: var(--bg-soft); color: var(--text); border: 1px solid var(--card-border); border-radius: 8px; }
            input[type=text] { width: 100%; padding: 9px; font-size: 14px; background: var(--bg-soft); color: var(--text); border: 1px solid var(--card-border); border-radius: 8px; }
            label { font-weight: 600; display:block; margin-top: 14px; color: var(--text-dim); }
            small { color: var(--text-dim); }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>{{ job.title }} <small>@ {{ job.company or 'Unknown' }}</small></h2>
            <p style="color:var(--text-dim);"><strong style="color:var(--text);">To:</strong> {{ job.contact_email or '(no contact email found)' }}<br>
               <strong style="color:var(--text);">CV that will be attached:</strong> {{ mode_label }}<br>
               <strong style="color:var(--text);">Draft state:</strong> {{ 'edited by you' if job.email_edited else 'auto-generated' }}</p>
            <form method="post">
                <label for="subject">Subject</label>
                <input type="text" id="subject" name="subject" value="{{ job.email_subject or '' }}">
                <label for="body">Email body</label>
                <textarea id="body" name="body">{{ job.email_body or '' }}</textarea>
                <p>
                    <button type="submit" class="btn">Save Email</button>
                    <a href="/regen/{{ job.uid }}" class="btn btn-grey">Discard &amp; Regenerate</a>
                    <a href="/" class="btn btn-grey">Back to Dashboard</a>
                </p>
            </form>
        </div>
    </body>
    </html>
    """

    OWN_CV_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Upload Own CV</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            :root {
                --bg: #0b1220; --bg-soft: #0f1b30; --card: #142238; --card-border: #1f3358;
                --accent: #3b82f6; --accent-dark: #1d4ed8; --text: #e6edf7; --text-dim: #93a4c3;
            }
            * { box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; background: linear-gradient(180deg, var(--bg) 0%, var(--bg-soft) 100%); color: var(--text); min-height: 100vh; }
            .card { background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; padding: 20px; box-shadow: 0 4px 14px rgba(0,0,0,0.25); }
            .btn { background: var(--accent); color: white; padding: 9px 16px; border: none; border-radius: 8px; text-decoration: none; cursor: pointer; display:inline-block; font-size: 14px; font-weight: 600; }
            .btn:hover { background: var(--accent-dark); }
            .btn-grey { background: #2b3b57; color: var(--text-dim); }
            input[type=file] { color: var(--text-dim); }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Your own CV</h2>
            <p style="color:var(--text-dim);">Current file: <strong style="color:var(--text);">{{ own_cv or 'none uploaded yet' }}</strong></p>
            <p>{{ message }}</p>
            <form method="post" enctype="multipart/form-data">
                <input type="file" name="cvfile" accept=".pdf,.docx,.doc,.txt,.rtf,.odt">
                <p><button type="submit" class="btn">Upload</button>
                   <a href="/" class="btn btn-grey">Back to Dashboard</a></p>
            </form>
            <p style="font-size:13px;color:var(--text-dim);">Any job set to <strong style="color:var(--text);">own cv</strong> gets this exact file attached, untouched.
            Jobs set to <strong style="color:var(--text);">custom ats cv</strong> get a freshly tailored, ATS-friendly PDF built from your master CV.</p>
        </div>
    </body>
    </html>
    """

    @app.route("/")
    def index():
        settings = load_settings()
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM jobs ORDER BY match_score DESC")
        jobs = c.fetchall()
        conn.close()
        own = get_own_cv_path()
        return render_template_string(
            HTML_TEMPLATE,
            jobs=jobs,
            own_cv=str(own) if own else "",
            delay=settings.get("send_delay_seconds", DEFAULT_SEND_DELAY),
            jitter=settings.get("send_delay_jitter", DEFAULT_SEND_JITTER),
            max_per_run=settings.get("max_emails_per_run", DEFAULT_MAX_PER_RUN),
        )

    @app.route("/toggle/<uid>")
    def toggle_web(uid):
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE jobs SET selected = CASE WHEN selected=1 THEN 0 ELSE 1 END WHERE uid = ?", (uid,))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    @app.route("/mode/<uid>/<mode>")
    def mode_web(uid, mode):
        normalised = normalise_cv_mode(mode)
        if normalised:
            set_job_cv_mode(uid, normalised, select=True)
            ensure_job_email(uid, overwrite=False, quiet=True)
        return redirect(url_for("index"))

    @app.route("/email/<uid>", methods=["GET", "POST"])
    def email_web(uid):
        if request.method == "POST":
            save_job_email(uid, request.form.get("subject", "").strip(), request.form.get("body", ""), mark_edited=True)
            return redirect(url_for("index"))
        ensure_job_email(uid, overwrite=False, quiet=True)
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM jobs WHERE uid = ?", (uid,))
        job = c.fetchone()
        conn.close()
        if not job:
            return redirect(url_for("index"))
        return render_template_string(EMAIL_TEMPLATE, job=job, mode_label=CV_MODE_LABELS.get(job["cv_mode"] or "", "(not chosen yet)"))

    @app.route("/regen/<uid>")
    def regen_web(uid):
        ensure_job_email(uid, overwrite=True, quiet=True)
        return redirect(url_for("index"))

    @app.route("/own-cv", methods=["GET", "POST"])
    def own_cv_web():
        message = ""
        if request.method == "POST":
            file = request.files.get("cvfile")
            if not file or not file.filename:
                message = "No file selected."
            else:
                suffix = Path(file.filename).suffix.lower()
                if suffix not in OWN_CV_ALLOWED_SUFFIXES:
                    message = f"Unsupported file type '{suffix}'."
                else:
                    ensure_directories()
                    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(file.filename))
                    dest = Path(OWN_CV_DIR) / safe_name
                    file.save(str(dest))
                    set_own_cv_path(dest)
                    message = f"Uploaded and set as your own CV: {dest.name}"
        own = get_own_cv_path()
        return render_template_string(OWN_CV_TEMPLATE, own_cv=str(own) if own else "", message=message)

    @app.route("/send")
    def send_web():
        settings = load_settings()
        do_send(argparse.Namespace(
            yes=True,
            delay=settings.get("send_delay_seconds", DEFAULT_SEND_DELAY),
            jitter=settings.get("send_delay_jitter", DEFAULT_SEND_JITTER),
            max_per_run=settings.get("max_emails_per_run", DEFAULT_MAX_PER_RUN),
        ))
        return redirect(url_for("index"))

    return app


def do_web(args):
    app = build_flask_app()
    if app is None:
        return
    print(f"[*] Starting JobBot Web UI on http://127.0.0.1:{args.port}")
    print("[*] Per job you can pick \"custom ats cv\" or \"own cv\", and view/edit the email before sending.")
    app.run(host="0.0.0.0", port=args.port, debug=False)


# ==========================================
# CLI MAIN ENTRY POINT
# ==========================================
def main():
    init_db()

    ap = argparse.ArgumentParser(prog="jobbot", description="JobBot: Automated Application & CV Tailoring Tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # cv-import (master CV used for tailoring + email personalisation)
    p = sub.add_parser("cv-import", help="Import/parse your CV into the master profile used for tailoring.")
    p.add_argument("file")
    p.set_defaults(func=do_cv_import)

    # cv-upload (your OWN cv file, attached as-is when a job is set to "own cv")
    p = sub.add_parser("cv-upload", help="Upload your own CV file, attached unchanged for jobs set to \"own cv\".")
    p.add_argument("file")
    p.set_defaults(func=do_cv_upload)

    # cv-own (show which own CV is registered)
    p = sub.add_parser("cv-own", help="Show the own CV file currently registered.")
    p.set_defaults(func=do_cv_own)

    # cv-mode (set custom ats cv / own cv for one job)
    p = sub.add_parser("cv-mode", help="Set a job's CV choice: \"custom ats cv\" or \"own cv\".")
    p.add_argument("uid")
    p.add_argument("mode", help='"custom ats cv" (or custom/1) | "own cv" (or own/2)')
    p.add_argument("--no-select", action="store_true", help="Set the CV choice without selecting the job for dispatch.")
    p.set_defaults(func=do_cv_mode)

    # choose (walk every job and pick custom ats cv / own cv)
    p = sub.add_parser("choose", help="Go job by job and choose \"custom ats cv\" or \"own cv\" for each.")
    p.add_argument("uid", nargs="*", help="Optional specific job UIDs.")
    p.add_argument("--all", action="store_true", help="Ask again for every job, including ones already decided.")
    p.set_defaults(func=do_choose)

    # cv-list
    p = sub.add_parser("cv-list")
    p.set_defaults(func=do_cv_list)

    # cv-view
    p = sub.add_parser("cv-view")
    p.add_argument("n", type=int)
    p.set_defaults(func=do_cv_view)

    # cv-preview
    p = sub.add_parser("cv-preview")
    p.add_argument("n", type=int)
    p.set_defaults(func=do_cv_preview)

    # src
    p = sub.add_parser("src")
    p.add_argument("action", choices=["list", "add", "on", "off", "test"])
    p.add_argument("target", nargs="?", default="")
    p.set_defaults(func=do_src)

    # fetch
    p = sub.add_parser("fetch", description="Fetch jobs. Requires a South African province selection; if omitted or invalid, you'll be prompted with a menu. A baseline requirement filter (Grade 12/Matric/NCV4 or equivalent, OR Driver's Licence or equivalent) is always applied and cannot be disabled. After fetching, every job found asks you to choose \"custom ats cv\" or \"own cv\".")
    p.add_argument("--province", default="", help="South African province to search in (e.g. 'North West'). If omitted, you'll be prompted to choose from a menu.")
    p.add_argument("--keywords", default="", help="Optional comma-separated extra keywords to further narrow results.")
    p.add_argument("--no-choose", action="store_true", help="Skip the per-job custom ats cv / own cv prompts after fetching.")
    p.set_defaults(func=do_fetch)

    # import-url
    p = sub.add_parser("import-url")
    p.add_argument("url")
    p.add_argument("--no-choose", action="store_true")
    p.set_defaults(func=do_import_url)

    # import-text
    p = sub.add_parser("import-text")
    p.add_argument("file")
    p.add_argument("--title", required=True)
    p.add_argument("--company", default="")
    p.add_argument("--location", default="")
    p.add_argument("--url", default="")
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-choose", action="store_true")
    p.set_defaults(func=do_import_text)

    # summary
    p = sub.add_parser("summary")
    p.set_defaults(func=do_summary)

    # toggle
    p = sub.add_parser("toggle")
    p.add_argument("uid")
    p.set_defaults(func=do_toggle)

    # email-list
    p = sub.add_parser("email-list", help="List the per-job email drafts.")
    p.add_argument("--selected", action="store_true", help="Only jobs selected for dispatch.")
    p.set_defaults(func=do_email_list)

    # email-show
    p = sub.add_parser("email-show", help="View the full email that will be sent for a job.")
    p.add_argument("uid")
    p.set_defaults(func=do_email_show)

    # email-edit
    p = sub.add_parser("email-edit", help="Change the email for a job if you're not happy with the generated one.")
    p.add_argument("uid")
    p.add_argument("--subject", default="", help="New subject line.")
    p.add_argument("--body", default="", help="New body text (use \\n for line breaks).")
    p.add_argument("--body-file", default="", help="Read the new body from a text file.")
    p.add_argument("--editor", action="store_true", help="Open the draft in $EDITOR.")
    p.set_defaults(func=do_email_edit)

    # email-regen
    p = sub.add_parser("email-regen", help="Regenerate a unique auto email for a job / selection / all jobs.")
    p.add_argument("uid", nargs="?", default="")
    p.add_argument("--selected", action="store_true")
    p.add_argument("--all", action="store_true")
    p.add_argument("--force", action="store_true", help="Also overwrite emails you edited by hand.")
    p.set_defaults(func=do_email_regen)

    # send
    p = sub.add_parser("send", help="Dispatch selected applications, throttled to avoid Gmail bans.")
    p.add_argument("--yes", "-y", action="store_true", help="Do not ask for confirmation per email.")
    p.add_argument("--delay", type=int, default=None, help=f"Seconds to wait between emails (default {DEFAULT_SEND_DELAY}). Use 0 only if you know the risk.")
    p.add_argument("--jitter", type=int, default=None, help=f"Extra random 0-N seconds added to the delay (default {DEFAULT_SEND_JITTER}).")
    p.add_argument("--max-per-run", type=int, default=None, help=f"Maximum emails to send in this run (default {DEFAULT_MAX_PER_RUN}).")
    p.set_defaults(func=do_send)

    # block
    p = sub.add_parser("block")
    p.add_argument("name")
    p.set_defaults(func=do_block)

    # history
    p = sub.add_parser("history")
    p.add_argument("-n", type=int, default=50)
    p.set_defaults(func=do_history)

    # config
    p = sub.add_parser("config", help="View or change settings such as send_delay_seconds.")
    p.add_argument("key", nargs="?", default="")
    p.add_argument("value", nargs="?", default=None)
    p.set_defaults(func=do_config)

    # web
    p = sub.add_parser("web")
    p.add_argument("--port", type=int, default=5000)
    p.set_defaults(func=do_web)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
