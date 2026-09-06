"""Hand-written signal fixtures — the frozen contract made concrete.

These are how the console gets built before any model exists
(context/GETTING-STARTED.md §3 and §6). One file per DEMO.md scene. The mock
transport replays them at the real latency budget, so the UI cannot tell the
difference from the backend.

These should become the shared `tests/fixtures/signals_*.json` the Python side
scores against — same bytes, one source of truth.

Run: python scripts/build_fixtures.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "fixtures"


def sig(sid, module, tier, verdict, confidence, trust, hard_fail, anchor,
        evidence, region=None, ms=0):
    return {
        "id": sid, "module": module, "tier": tier, "verdict": verdict,
        "confidence": confidence, "trust_class": trust, "hard_fail": hard_fail,
        "anchor": anchor, "evidence": evidence, "region": region,
        "latency_ms": ms,
    }


# --------------------------------------------------------------- Scene 1
GREEN = {
    "meta": {
        "scene": "1 — the clean pass",
        "doc_type": "passport", "canvas": [1654, 1170],
        "note": "Genuine synthetic passport. Five MRZ check digits verify.",
    },
    "signals": [
        sig("extraction.quality.blur", "extraction", 1, "pass", 1.0, "arithmetic", False,
            "document", "Image sharpness 412, above the 180 threshold", None, 60),
        sig("extraction.doctype.confidence", "extraction", 1, "pass", 0.97, "probabilistic", False,
            "document", "Identified as passport, confidence 97%", None, 15),
        sig("validation.signature.valid", "validation", 1, "pass", 1.0, "cryptographic", True,
            "document", "Ed25519 signature verifies against trusted issuer SIH-REF-01", None, 4),
        sig("validation.signature.issuer_trusted", "validation", 1, "pass", 1.0, "cryptographic", False,
            "document", "Issuer SIH-REF-01 is present in the trust anchor store", None, 1),
        sig("validation.mrz.checkdigit.document_number", "validation", 1, "pass", 1.0, "arithmetic", False,
            "field:id_number", "MRZ document number check digit 3 is correct",
            [90, 900, 1564, 1050], 2),
        sig("validation.mrz.checkdigit.dob", "validation", 1, "pass", 1.0, "arithmetic", False,
            "field:dob", "MRZ date of birth check digit 7 is correct",
            [90, 900, 1564, 1050], 2),
        sig("validation.mrz.checkdigit.expiry", "validation", 1, "pass", 1.0, "arithmetic", False,
            "field:expiry_date", "MRZ expiry check digit 4 is correct",
            [90, 900, 1564, 1050], 2),
        sig("validation.mrz.checkdigit.optional", "validation", 1, "pass", 1.0, "arithmetic", False,
            "field:secondary_id", "MRZ optional data check digit 0 is correct",
            [90, 900, 1564, 1050], 1),
        sig("validation.mrz.checkdigit.composite", "validation", 1, "pass", 1.0, "arithmetic", True,
            "document", "MRZ composite check digit 8 is correct",
            [90, 900, 1564, 1050], 2),
        sig("validation.vizmrz.dob_mismatch", "validation", 1, "pass", 1.0, "arithmetic", False,
            "field:dob", "MRZ date of birth 1991-08-04 matches printed 1991-08-04",
            [600, 470, 950, 525], 1),
        sig("validation.vizmrz.name_mismatch", "validation", 1, "pass", 1.0, "arithmetic", False,
            "field:name", "MRZ name MUHAMAD SABRI matches printed MUHAMAD SABRI",
            [600, 360, 1250, 415], 1),
        sig("validation.crossfield.date_order", "validation", 1, "pass", 1.0, "arithmetic", False,
            "document", "Issued 2021-07-18, before expiry 2031-07-17", None, 1),
        sig("validation.expiry.expired", "validation", 1, "pass", 1.0, "arithmetic", True,
            "field:expiry_date", "Expires 2031-07-17, valid for another 5 years 10 months",
            [600, 580, 950, 635], 1),
        sig("validation.watchlist.hit", "validation", 1, "pass", 1.0, "arithmetic", True,
            "document", "No match in the OFAC SDN or UN Consolidated list", None, 7),
        sig("tamper.physical.ocrb_conformance", "tamper", 1, "pass", 0.88, "probabilistic", False,
            "field:mrz", "MRZ glyphs conform to OCR-B within tolerance",
            [90, 900, 1564, 1050], 44),
        sig("tamper.physical.guilloche_break", "tamper", 1, "pass", 0.81, "probabilistic", False,
            "document", "Guilloche line-work runs continuously across the data page", None, 52),
        sig("tamper.physical.ghost_missing", "tamper", 1, "pass", 0.90, "probabilistic", False,
            "field:ghost_photo", "Ghost portrait present and consistent with the primary photo",
            [1300, 560, 1480, 800], 31),
        sig("tamper.physical.layout_geometry", "tamper", 1, "pass", 0.86, "probabilistic", False,
            "document", "Field positions fall within 1.2 mm of the TD3 reference layout", None, 18),
        sig("tamper.digital.exif_software", "tamper", 1, "not_applicable", 1.0, "arithmetic", False,
            "document", "Scanner input, so file metadata checks do not apply", None, 0),
        sig("face.doc.detected", "face", 1, "pass", 0.99, "probabilistic", False,
            "field:person_photo", "Face located in the document photo",
            [110, 300, 480, 800], 96),
        sig("face.live.detected", "face", 1, "pass", 0.99, "probabilistic", False,
            "document", "Face located in the live camera frame", None, 88),
        sig("face.liveness.passive", "face", 1, "pass", 0.94, "probabilistic", False,
            "document", "Passive liveness 0.94, consistent with a live subject", None, 74),
        sig("face.match.cosine", "face", 1, "pass", 0.83, "probabilistic", False,
            "field:person_photo",
            "Document and live face match at cosine 0.61, against a 0.32 threshold",
            [110, 300, 480, 800], 62),
    ],
    "findings": [
        {"anchor": "document", "severity": 0.0, "trust_class": "cryptographic",
         "headline": "Signature verifies against a trusted issuer", "region": None},
        {"anchor": "document", "severity": 0.0, "trust_class": "arithmetic",
         "headline": "All five MRZ check digits are correct",
         "region": [90, 900, 1564, 1050]},
    ],
    "verdict": {
        "band": "GREEN", "score": 0.04, "coverage": 0.96,
        "disclosure": "Signature verified against our reference issuer, for demonstration. We hold no government keys.",
    },
    "face": {"cosine": 0.61, "threshold": 0.32},
    "fields": [
        {"name": "name", "value": "MUHAMAD SABRI", "source": "mrz", "confidence": 1.0,
         "state": "pass", "region": [600, 360, 1250, 415]},
        {"name": "dob", "value": "1991-08-04", "source": "mrz", "confidence": 1.0,
         "state": "pass", "region": [600, 470, 950, 525]},
        {"name": "id_number", "value": "E1009353", "source": "mrz", "confidence": 1.0,
         "state": "pass", "region": [600, 250, 1000, 300]},
        {"name": "nationality", "value": "IND", "source": "mrz", "confidence": 1.0,
         "state": "pass", "region": [1020, 360, 1330, 415]},
        {"name": "expiry_date", "value": "2031-07-17", "source": "mrz", "confidence": 1.0,
         "state": "pass", "region": [600, 580, 950, 635]},
    ],
}

# --------------------------------------------------------------- Scene 2
RED = {
    "meta": {
        "scene": "2 — the tamper",
        "doc_type": "passport", "canvas": [1654, 1170],
        "note": "The printed date of birth was altered. The MRZ was left alone.",
    },
    "signals": [
        sig("extraction.quality.blur", "extraction", 1, "pass", 1.0, "arithmetic", False,
            "document", "Image sharpness 388, above the 180 threshold", None, 60),
        sig("extraction.doctype.confidence", "extraction", 1, "pass", 0.96, "probabilistic", False,
            "document", "Identified as passport, confidence 96%", None, 15),
        sig("validation.signature.valid", "validation", 1, "pass", 1.0, "cryptographic", True,
            "document", "Ed25519 signature verifies against trusted issuer SIH-REF-01", None, 4),
        sig("validation.mrz.checkdigit.composite", "validation", 1, "pass", 1.0, "arithmetic", True,
            "document", "MRZ composite check digit 8 is correct",
            [90, 900, 1564, 1050], 2),
        sig("validation.mrz.checkdigit.dob", "validation", 1, "pass", 1.0, "arithmetic", False,
            "field:dob", "MRZ date of birth check digit 7 is correct",
            [90, 900, 1564, 1050], 2),
        sig("validation.vizmrz.dob_mismatch", "validation", 1, "fail", 1.0, "arithmetic", True,
            "field:dob",
            "MRZ date of birth 1991-03-04 does not match printed 1991-08-04",
            [600, 470, 950, 525], 1),
        sig("validation.crossfield.date_order", "validation", 1, "pass", 1.0, "arithmetic", False,
            "document", "Issued 2021-07-18, before expiry 2031-07-17", None, 1),
        sig("validation.expiry.expired", "validation", 1, "pass", 1.0, "arithmetic", True,
            "field:expiry_date", "Expires 2031-07-17, valid for another 5 years 10 months",
            [600, 580, 950, 635], 1),
        sig("validation.watchlist.hit", "validation", 1, "pass", 1.0, "arithmetic", True,
            "document", "No match in the OFAC SDN or UN Consolidated list", None, 7),
        sig("tamper.physical.ocrb_conformance", "tamper", 1, "fail", 0.74, "probabilistic", False,
            "field:dob", "Printed date of birth glyphs deviate from the typeface used elsewhere on the page",
            [600, 470, 950, 525], 44),
        sig("tamper.physical.halftone", "tamper", 1, "fail", 0.66, "probabilistic", False,
            "field:dob", "The print halftone screen breaks inside the date of birth field",
            [600, 470, 950, 525], 38),
        sig("tamper.digital.copy_move", "tamper", 2, "fail", 0.58, "probabilistic", False,
            "field:dob", "A pixel block beside the date of birth duplicates another region of the page",
            [600, 470, 950, 525], 420),
        sig("tamper.physical.guilloche_break", "tamper", 1, "pass", 0.79, "probabilistic", False,
            "document", "Guilloche line-work runs continuously across the data page", None, 52),
        sig("tamper.physical.layout_geometry", "tamper", 1, "pass", 0.84, "probabilistic", False,
            "document", "Field positions fall within 1.4 mm of the TD3 reference layout", None, 18),
        sig("face.doc.detected", "face", 1, "pass", 0.99, "probabilistic", False,
            "field:person_photo", "Face located in the document photo",
            [110, 300, 480, 800], 96),
        sig("face.liveness.passive", "face", 1, "pass", 0.91, "probabilistic", False,
            "document", "Passive liveness 0.91, consistent with a live subject", None, 74),
        sig("face.match.cosine", "face", 1, "pass", 0.80, "probabilistic", False,
            "field:person_photo",
            "Document and live face match at cosine 0.58, against a 0.32 threshold",
            [110, 300, 480, 800], 62),
    ],
    "findings": [
        {"anchor": "field:dob", "severity": 1.0, "trust_class": "arithmetic",
         "headline": "Printed date of birth conflicts with the machine-readable zone",
         "region": [600, 470, 950, 525]},
        {"anchor": "document", "severity": 0.0, "trust_class": "cryptographic",
         "headline": "Signature verifies against a trusted issuer", "region": None},
    ],
    "verdict": {
        "band": "RED", "score": 1.0, "coverage": 0.94,
        "disclosure": "Signature verified against our reference issuer, for demonstration. We hold no government keys.",
    },
    "face": {"cosine": 0.58, "threshold": 0.32},
    "fields": [
        {"name": "name", "value": "MUHAMAD SABRI", "source": "mrz", "confidence": 1.0,
         "state": "pass", "region": [600, 360, 1250, 415]},
        {"name": "dob", "value": "1991-08-04", "source": "ocr", "confidence": 0.93,
         "state": "fail", "region": [600, 470, 950, 525]},
        {"name": "id_number", "value": "E1009353", "source": "mrz", "confidence": 1.0,
         "state": "pass", "region": [600, 250, 1000, 300]},
        {"name": "nationality", "value": "IND", "source": "mrz", "confidence": 1.0,
         "state": "pass", "region": [1020, 360, 1330, 415]},
        {"name": "expiry_date", "value": "2031-07-17", "source": "mrz", "confidence": 1.0,
         "state": "pass", "region": [600, 580, 950, 635]},
    ],
}

# --------------------------------------------------------------- Scene 5
AMBER = {
    "meta": {
        "scene": "5 — the honest failure",
        "doc_type": "passport", "canvas": [1654, 1170],
        "note": "The machine-readable zone is too blurred to read. Coverage falls below the floor.",
    },
    "signals": [
        sig("extraction.quality.blur", "extraction", 1, "fail", 0.71, "probabilistic", False,
            "document", "Image sharpness 96, below the 180 threshold for a document capture",
            None, 60),
        sig("extraction.quality.resolution", "extraction", 1, "pass", 1.0, "arithmetic", False,
            "document", "1654 by 2339 pixels, 246 dpi at TD3 size", None, 3),
        sig("extraction.doctype.confidence", "extraction", 1, "pass", 0.88, "probabilistic", False,
            "document", "Identified as passport, confidence 88%", None, 15),
        sig("validation.signature.valid", "validation", 1, "inconclusive", 0.0, "unverified", True,
            "document", "No signature payload found, so this document has no cryptographic anchor",
            None, 3),
        sig("validation.mrz.checkdigit.composite", "validation", 1, "inconclusive", 0.0, "arithmetic", True,
            "document", "The machine-readable zone could not be read",
            [90, 900, 1564, 1050], 2),
        sig("validation.mrz.checkdigit.dob", "validation", 1, "inconclusive", 0.0, "arithmetic", False,
            "field:dob", "The machine-readable zone could not be read",
            [90, 900, 1564, 1050], 1),
        sig("validation.vizmrz.dob_mismatch", "validation", 1, "inconclusive", 0.0, "arithmetic", False,
            "field:dob",
            "Cannot compare printed and machine-readable date of birth while the zone is unreadable",
            [600, 470, 950, 525], 1),
        sig("validation.expiry.expired", "validation", 1, "pass", 1.0, "arithmetic", True,
            "field:expiry_date", "Expires 2029-03-28, valid for another 3 years 6 months",
            [600, 580, 950, 635], 1),
        sig("validation.watchlist.hit", "validation", 1, "pass", 1.0, "arithmetic", True,
            "document", "No match in the OFAC SDN or UN Consolidated list", None, 7),
        sig("tamper.physical.ocrb_conformance", "tamper", 1, "inconclusive", 0.0, "probabilistic", False,
            "field:mrz", "Too blurred to assess OCR-B conformance",
            [90, 900, 1564, 1050], 44),
        sig("tamper.physical.guilloche_break", "tamper", 1, "inconclusive", 0.0, "probabilistic", False,
            "document", "Too blurred to trace guilloche continuity", None, 52),
        sig("tamper.digital.exif_software", "tamper", 1, "not_applicable", 1.0, "arithmetic", False,
            "document", "Scanner input, so file metadata checks do not apply", None, 0),
        sig("face.doc.quality", "face", 1, "fail", 0.68, "probabilistic", False,
            "field:person_photo",
            "Document photo is below the quality gate. Ask for a higher-resolution capture of the document, not a new selfie.",
            [110, 300, 480, 800], 40),
        sig("face.match.cosine", "face", 1, "inconclusive", 0.0, "probabilistic", False,
            "field:person_photo", "Document photo is too soft to embed reliably",
            [110, 300, 480, 800], 62),
    ],
    "findings": [
        {"anchor": "document", "severity": 0.42, "trust_class": "probabilistic",
         "headline": "The capture is too soft to read the machine-readable zone", "region": None},
    ],
    "verdict": {"band": "AMBER", "score": 0.11, "coverage": 0.38, "disclosure": None},
    "face": {"cosine": None, "threshold": 0.32},
    "fields": [
        {"name": "name", "value": "SHAH RUKH", "source": "ocr", "confidence": 0.62,
         "state": "inconclusive", "region": [600, 360, 1250, 415]},
        {"name": "dob", "value": "1988-0?-14", "source": "ocr", "confidence": 0.41,
         "state": "inconclusive", "region": [600, 470, 950, 525]},
        {"name": "expiry_date", "value": "2029-03-28", "source": "ocr", "confidence": 0.87,
         "state": "pass", "region": [600, 580, 950, 635]},
    ],
}

# --------------------------------------------------------------- Scene 3
CROSSDOC = {
    "meta": {
        "scene": "3 — cross-document trust propagation",
        "doc_type": "pan", "canvas": [1400, 900],
        "note": "A signed Aadhaar presented earlier in this session gives 1996. This PAN prints 1998.",
        "session_documents": [
            {"doc_type": "aadhaar", "signed": True, "label": "Aadhaar",
             "band": "GREEN", "anchors": ["name", "dob"]},
            {"doc_type": "pan", "canvas": [1400, 900], "signed": False, "label": "PAN",
             "band": "RED", "anchors": ["name", "dob"]},
        ],
        "propagation": [
            {"field": "name", "from": "aadhaar", "to": "pan", "agrees": True,
             "from_value": "PRADEEP KESHAV GHARAT", "to_value": "PRADEEP KESHAV GHARAT"},
            {"field": "dob", "from": "aadhaar", "to": "pan", "agrees": False,
             "from_value": "1996-11-02", "to_value": "1998-11-02"},
        ],
    },
    "signals": [
        sig("extraction.quality.blur", "extraction", 1, "pass", 1.0, "arithmetic", False,
            "document", "Image sharpness 356, above the 180 threshold", None, 60),
        sig("extraction.doctype.confidence", "extraction", 1, "pass", 0.95, "probabilistic", False,
            "document", "Identified as a PAN card, confidence 95%", None, 15),
        sig("validation.signature.valid", "validation", 1, "not_applicable", 1.0, "unverified", True,
            "document", "A PAN card carries no signature payload, so it has no cryptographic anchor of its own",
            None, 2),
        sig("validation.format.pan.id_number", "validation", 1, "pass", 1.0, "arithmetic", False,
            "field:id_number", "PAN check character F is correct for ABLPG7040",
            [110, 640, 620, 700], 1),
        sig("validation.mrz.checkdigit.composite", "validation", 1, "not_applicable", 1.0, "arithmetic", True,
            "document", "A PAN card has no machine-readable zone", None, 0),
        sig("validation.crossdoc.dob_mismatch", "validation", 1, "fail", 1.0, "cryptographic", True,
            "field:dob",
            "The signed Aadhaar payload gives date of birth 1996-11-02; this PAN prints 1998-11-02",
            [110, 480, 560, 535], 3),
        sig("validation.crossdoc.name_mismatch", "validation", 1, "pass", 1.0, "cryptographic", False,
            "field:name",
            "The signed Aadhaar payload name PRADEEP KESHAV GHARAT matches this PAN",
            [110, 300, 800, 355], 2),
        sig("validation.watchlist.hit", "validation", 1, "pass", 1.0, "arithmetic", True,
            "document", "No match in the OFAC SDN or UN Consolidated list", None, 7),
        sig("tamper.physical.layout_geometry", "tamper", 1, "pass", 0.83, "probabilistic", False,
            "document", "Field positions fall within 1.8 mm of the PAN reference layout", None, 18),
        sig("tamper.physical.ocrb_conformance", "tamper", 1, "fail", 0.44, "probabilistic", False,
            "field:dob",
            "Printed date of birth glyph weight differs slightly from the rest of the line",
            [110, 480, 560, 535], 44),
        sig("face.doc.detected", "face", 1, "pass", 0.98, "probabilistic", False,
            "field:person_photo", "Face located in the document photo",
            [1080, 300, 1330, 620], 96),
        sig("face.liveness.passive", "face", 1, "pass", 0.93, "probabilistic", False,
            "document", "Passive liveness 0.93, consistent with a live subject", None, 74),
        sig("face.match.cosine", "face", 1, "pass", 0.77, "probabilistic", False,
            "field:person_photo",
            "Document and live face match at cosine 0.54, against a 0.32 threshold",
            [1080, 300, 1330, 620], 62),
    ],
    "findings": [
        {"anchor": "field:dob", "severity": 1.0, "trust_class": "cryptographic",
         "headline": "Date of birth contradicts a signed document in this session",
         "region": [110, 480, 560, 535]},
        {"anchor": "field:name", "severity": 0.0, "trust_class": "cryptographic",
         "headline": "Name is confirmed by the signed Aadhaar payload",
         "region": [110, 300, 800, 355]},
    ],
    "verdict": {
        "band": "RED", "score": 1.0, "coverage": 0.91,
        "disclosure": "Signature verified against our reference issuer, for demonstration. We hold no government keys. The trust anchor store is keyed by issuer, and the verification code is unchanged for a real one.",
    },
    "face": {"cosine": 0.54, "threshold": 0.32},
    "fields": [
        {"name": "name", "value": "PRADEEP KESHAV GHARAT", "source": "ocr", "confidence": 0.96,
         "state": "pass", "region": [110, 300, 800, 355]},
        {"name": "father_name", "value": "KESHAV NARAYAN GHARAT", "source": "ocr", "confidence": 0.94,
         "state": "pass", "region": [110, 390, 800, 445]},
        {"name": "dob", "value": "1998-11-02", "source": "ocr", "confidence": 0.95,
         "state": "fail", "region": [110, 480, 560, 535]},
        {"name": "id_number", "value": "ABLPG7040F", "source": "ocr", "confidence": 0.97,
         "state": "pass", "region": [110, 640, 620, 700]},
    ],
}


def attach_supporting(doc):
    """A finding carries every signal that shares its anchor. Fusion does this
    server-side; the fixtures mirror the result so the console sees real shapes."""
    for f in doc["findings"]:
        f["supporting"] = [s for s in doc["signals"] if s["anchor"] == f["anchor"]]
    return doc


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, doc in [
        ("signals_green", GREEN),
        ("signals_red_hardfail", RED),
        ("signals_amber_coverage", AMBER),
        ("signals_crossdoc_mismatch", CROSSDOC),
    ]:
        attach_supporting(doc)
        (OUT / f"{name}.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
        v = doc["verdict"]
        print(f"{name+'.json':34} {len(doc['signals']):2} signals  "
              f"{len(doc['findings'])} findings  {v['band']:5} "
              f"score {v['score']:.2f} coverage {v['coverage']:.2f}")
