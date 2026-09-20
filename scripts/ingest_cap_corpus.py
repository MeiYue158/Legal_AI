"""
Phase 1 — pull a small, open (no-login) sample of real case law from
static.case.law (Harvard Caselaw Access Project, CC0) and load it into the
corpus_cases table.

Reporter chosen: Delaware Chancery Reports ("del-ch") — Delaware Chancery is
the leading US corporate-law court, which thematically fits the existing
contract-analysis modules. Easy to swap: change REPORTER/VOLUMES below.

This is a PILOT run — only a couple of volumes (~a few hundred cases, a few
MB) are pulled, not the whole reporter. Re-run with more VOLUMES once the
pilot is reviewed.

Usage:
    venv/bin/python -m scripts.ingest_cap_corpus
"""

import io
import json
import logging
import os
import zipfile

import requests

from app.db.connection import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPORTER = "del-ch"
VOLUMES = [42, 43]  # pilot: 2 volumes only, ~a few hundred cases total
RAW_DIR = os.path.join("data", "corpus_raw", REPORTER)
BASE_URL = f"https://static.case.law/{REPORTER}"


def download_volume(volume: int) -> bytes:
    os.makedirs(RAW_DIR, exist_ok=True)
    cache_path = os.path.join(RAW_DIR, f"{volume}.zip")
    if os.path.exists(cache_path):
        logger.info(f"Using cached {cache_path}")
        with open(cache_path, "rb") as f:
            return f.read()

    url = f"{BASE_URL}/{volume}.zip"
    logger.info(f"Downloading {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    with open(cache_path, "wb") as f:
        f.write(resp.content)
    return resp.content


def parse_case(raw: dict) -> dict:
    casebody = raw.get("casebody", {})
    opinions = casebody.get("opinions", [])
    opinion_text = "\n\n".join(op.get("text", "") for op in opinions)
    head_matter = casebody.get("head_matter", "")
    full_text = (head_matter + "\n\n" + opinion_text).strip()

    citations = raw.get("citations", [])
    citation = citations[0]["cite"] if citations else None

    court = raw.get("court", {}) or {}

    return {
        "case_id": f"cap-{REPORTER}-{raw['id']}",
        "jurisdiction": (raw.get("jurisdiction") or {}).get("name"),
        "court": court.get("name"),
        "case_name": raw.get("name_abbreviation") or raw.get("name"),
        "citation": citation,
        "decision_date": raw.get("decision_date"),
        "case_text": full_text,
        "source_file": f"{REPORTER}/{raw['id']}",
    }


def ingest_volume(volume: int) -> int:
    content = download_volume(volume)
    count = 0
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        json_names = [n for n in zf.namelist() if n.startswith("json/") and n.endswith(".json")]
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                for name in json_names:
                    with zf.open(name) as f:
                        raw = json.load(f)
                    case = parse_case(raw)
                    if not case["case_text"] or len(case["case_text"]) < 200:
                        continue  # skip empty/near-empty opinions
                    cur.execute(
                        """
                        INSERT INTO corpus_cases
                            (case_id, jurisdiction, court, case_name, citation,
                             decision_date, case_text, source_file)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (case_id) DO NOTHING
                        """,
                        (
                            case["case_id"], case["jurisdiction"], case["court"],
                            case["case_name"], case["citation"], case["decision_date"],
                            case["case_text"], case["source_file"],
                        ),
                    )
                    count += cur.rowcount
            conn.commit()
        finally:
            conn.close()
    return count


def main():
    total = 0
    for vol in VOLUMES:
        n = ingest_volume(vol)
        logger.info(f"Volume {vol}: inserted {n} new cases")
        total += n
    print(f"✅ Ingested {total} cases from {REPORTER} volumes {VOLUMES} into corpus_cases")


if __name__ == "__main__":
    main()
