# Data provenance and licences



One row per dataset. `DATA.md` requires this as a pitch slide; `DEMO.md` says

the panel will ask "where did your training data come from". Keep it current.



Scope decision (2026-09-06): **Indian government documents only.** MIDV-2020/

500/2019, MIDV-Holo, SIDTD, IDNet, DocXPand, DocTamper and FindIt are all

European or Chinese documents and are **not used**. Six document types remain

in scope, Visa included.



---



## Document datasets — held locally (`SIH/SIH/`)



| Directory | Source | Licence | Images | Classes | Status |

|---|---|---|---|---|---|

| `Aadhar dataset/` | `jizo/aadhar-card-entity-detection` (Roboflow Universe) | CC BY 4.0 | 2,646 labelled | 5, originally unnamed integers — mapped, see its `CLASSES.md` | **Usable** |

| `Aadhar dataset/Dataset 2` | unknown | unknown | 1,000 (100 cards × front/back × 5 augmentations) | none — **no labels** | Reference only |

| `PAN dataset/` | `panocr/ocr-qaxqg` v5 | CC BY 4.0 | 1,726 labelled | 4: dob, father, name, pan | **Usable** |

| `VoterID dataset/` | `voterid/voterid-duejn` v1 | CC BY 4.0 | 1,274 labelled | 17 | **Usable**, 5 classes dropped |

| `Passport dataset/Passport Validation` | `name-address-mykad-number-gender/passport-validation-ci5do` v2 | CC BY 4.0 | 620 | 1: MRZ | **Usable** |

| `Passport dataset/passport` | `name-address-mykad-number-gender/passport-xwnm3` v2 | CC BY 4.0 | 256 | 1: passport (document-level) | Segmentation only |

| `Passport dataset/PassportAreaNames` | `passport-4nsxp/passportareanames-wkpad` v3 | CC BY 4.0 | 40 | 1: generic `field_name` | **Unusable** — too small, no field identity |

| `Passport dataset/_archive_raw` | unknown | unknown | 15 | none (CSV index only) | Synthetic passport renders — see note |

| `Face dataset/` | LFW deepfunneled | LFW terms, research use | 13,233 / 5,749 identities | pairs CSVs | Threshold **sanity check only** — LFW is live-to-live, wrong domain for doc-vs-live (D11) |



### Notes



- **`PAN dataset/` and `VoterID dataset/` were swapped** on arrival — each held

  the other's data. Corrected 2026-09-06.

- **`_archive_raw`** is a set of synthetic non-Indian passport renders (UAE and

  others) with full VIZ, ghost portrait, guilloche and an MRZ strip. The MRZ is

  **cosmetic, not ICAO-compliant** — dates are `DDMMYYYY` and there are no

  per-field check digits, so it fails our own parser by construction. Value is

  as a reference for what a good synthetic render looks like, and as a negative

  test for the MRZ parser. Not ground truth.

- Provenance for `Dataset 2` and `_archive_raw` is **unrecorded** and needs an

  origin before either appears in a deck.



## Generated data — `data/generator/` (2026-09-07)

The answer to "where did your training data come from?" for everything below.

| What | Source | Licence | Notes |
|---|---|---|---|
| Document images and labels | `data/generator/`, this repository | ours | Six templates, rendered programmatically. Labels are a by-product of drawing, so every field is annotated by construction. |
| Identities | Faker `en_IN` + `modules/validation/checksums.py` | MIT (Faker) | Every number is *constructed* valid under the same function Layer A validates it with - not sampled and hoped over. |
| Portraits | SFHQ small-sample (`data/raw/face/sfhq/`) | **CC0** | StyleGAN / diffusion output. No real person, so no consent question and no PII. |
| Fonts | Noto Sans, Noto Sans Devanagari, Noto Sans Mono | **OFL-1.1** | `scripts/fetch_fonts.py`. See `data/templates/fonts/PROVENANCE.md`. |
| Signatures on generated documents | `issuer/`, our own Ed25519 reference issuer | ours | Never a government key (D1). The console renders the `disclosure` string so a reference verification cannot be mistaken for a government one. |
| Forgeries and masks | `data/tools/mutate.py` | ours | Five families, ground-truth mask on every one. Measured in `data/TAMPERING.md`. |

**No real government document was used to build any of this.** The templates are
drawn from the published layouts, not traced from a specimen scan, and the State
Emblem is deliberately a stand-in mark - the real one is protected under the
State Emblem of India (Prohibition of Improper Use) Act.

### Stated limitations of the generated set

- **Portraits are not age- or sex-matched to the identity.** SFHQ ships no
  metadata and we deploy no age model, so a card can carry a face that does not
  match its printed date of birth or gender. It is consistent *across* one
  person's documents, which is what Layer D and the face module actually need.
  Fixing it properly means a build-time pass with an age/gender model over the
  1,450 faces, cached to disk - about fifty lines, and worth doing before any
  demo card is printed.
- **The barcode is not a real symbology.** Bars are derived from the value so
  the class has instances to locate; nothing decodes them, and nothing claims to.
- **The MRZ is set in Noto Sans Mono, not OCR-B**, which is licensed. Glyph
  height uniformity - what `tamper.physical.ocrb_conformance` measures - is
  identical; typeface identity is not tested and could not be.
- **No print-and-rescan pass yet.** `DATA.md` is right that a model trained only
  on clean renders falls apart on a real scanner. These are clean renders.

## Reference data — downloaded 2026-09-06 (`data/raw/reference/`)



| File | Source | Licence | Size | Content |

|---|---|---|---|---|

| `watchlist/sdn.csv` | OFAC SDN, `sanctionslistservice.ofac.treas.gov` | Public government data | 5.7 MB | ~11k entries, 170 India-linked |

| `watchlist/alt.csv` | OFAC alternate names | Public | 1.1 MB | 20,145 aliases |

| `watchlist/add.csv` | OFAC addresses | Public | 1.7 MB | — |

| `watchlist/sdn_advanced.xml` | OFAC enhanced | Public | 63.7 MB | 5,982 birthdates, 1,692 passport numbers |

| `watchlist/un_consolidated.xml` | UN Security Council, `scsanctions.un.org` | Public | 2.2 MB | 736 individuals, generated 2026-09-05 |

| `iso3166/country-codes.csv` | `datasets/country-codes` (GitHub) | Public domain | 134 KB | 249 countries, alpha-2/alpha-3. Layer B needs the ICAO supplementary codes on top (`D` for Germany, GBR subtypes) - those are in Doc 9303, not ISO. |



Enough to build Layer E now: lookup by document number *and* by name+DOB, with

real alias and transliteration variants.




## Roboflow Universe - pulled 2026-09-06 (`data/raw/`)

Pulled with `data/tools/pull_roboflow.py` using a private workspace key in
`.env` (`ROBOFLOW_API_KEY`, gitignored). All CC BY 4.0 unless noted.

| Directory | Project | Images | Boxes | Use |
|---|---|---|---|---|
| `aadhaar/aadhaar-card-1-ebbdz` | `monika-ztd2k/...` v4 | 938 | 6,291 | qr_code, person_photo, logo, secondary_id |
| `aadhaar/aadhaar-card-annotation` | `mitesh-workspace/...` v1 | 754 | 2,182 | name, dob, id_number |
| `aadhaar/back-aadhaar-card` | `mitesh-workspace/...` v1 | 584 | 585 | father_name |
| `aadhaar/id-bdbwr` | `project-epimx/...` v2 | 93 | 413 | emblem, logo, blank template, `fake` label |
| `dl/my-first-project-fypmb` | `license-plate-detection-ov9nk/...` v2 | 49 | 444 | **only Indian DL field set**; blood_group, expiry |
| `dl/indian-driving-licence-reader-rlxel` | `jaspreetsingh/...` v1 | 40 | 120 | DL name/dob/number |
| `pan/pan-card-entity-extraction` | `cardamage-fvhwg/...` v1 | 2,082 | 8,295 | PAN fields |
| `passport/passport-exe8g` | `misha-88lag/...` v1 | 328 | 4,460 | passport VIZ (templates, non-Indian) |
| `passport/passport-sscsb` | `bms-ur6hn/...` v1 | 341 | 4,082 | passport VIZ (USA) |
| `passport/passport-ppwp8` | `arvind-kumar-wjygd/...` v1 | 25 | 320 | **only Indian passport VIZ**; only `signature` |
| `passport/passport-page-mrz-detection` | `phiphi-20ww6/...` v1 | 119 | 237 | mrz |
| `passport/bangladeshi-passport-fields` | `at-in/...` v2 | 200 | 27 | **images only** - see rejects |
| `visa/visa-o0eyd` | `omkar-padave-vjltn/...` v1 (Public Domain) | 50 | 1,202 | only visa annotations found |
| `doctype/identity-card-classifier` | `mahrprojects/...` v4 | 221 | 221 | document-type routing |
| `doctype/identity-card-segmentation` | `ip2-kbjz5/...` v2 | 267 | 267 | quad warp / segmentation |
| `tamper/tampering-detection-0muly` | `tampering-detection/...` v1 | 600 | 604 | Module 3 - class list needs an audit |

### Rejected and deleted - do not re-add

| Project | Why |
|---|---|
| `fil-9zpqb/voter-01` (146) | Every image is an **Albion Online screenshot**. Shipped 477 boxes labelled `voter`; the box audit looked perfectly healthy. |
| `bekaarbhai/voter-card-detection` (38) | Bangladeshi electoral roll pages, not Indian EPIC cards. |
| `info-ukkiy/pan-ypwo1` (1,027) | Pre-cropped 416x416 field images, one box covering ~99% of the frame. A classification set wearing a detection label. |
| `at-in/bangladeshi-passport-fields` labels | Advertises 200 images x 33 classes, ships **27 boxes on one image**. Images kept as generator reference; labels unused. |
| `university-of-greenwich-xo9z4/driving-licence-text-detection` | Owner never generated a version, so there is no export endpoint. Needs a manual browser download. |

### Roboflow's YOLO export is not trustworthy

For `monika-ztd2k/aadhaar-card-1-ebbdz` v4 the **yolov11 export is corrupt** -
box heights collapse to ~0.000 and centres shift - while the **COCO export of
the same version is pixel-correct**. `pull_roboflow.py` therefore always
requests COCO and converts to YOLO locally. Check every new pull with
`data/tools/draw_boxes.py`.

### Real-document caution

Several of these sets (`aadhaar-card-annotation`, `back-aadhaar-card`,
`id-bdbwr`, `passport-ppwp8`) contain what appear to be **real Aadhaar cards
and real Indian passports** with legible numbers. `data/raw/` is gitignored so
nothing is committed, but CLAUDE.md rule #4 says no real government document
in any dataset. Training on them is an explicit owner decision, not a default.

## Synthetic faces - `data/raw/face/sfhq/` (2026-09-06)

| Source | Licence | Held | Use |
|---|---|---|---|
| SFHQ (Synthetic Faces High Quality), David Beniaguev, via `bitmind/SyntheticFacesHQ` | **CC0 Public Domain** | 750 of 493,398 (small-sample zips) | Face pool for the document generator |

StyleGAN2 / Stable Diffusion output - no real person, no privacy or licence
encumbrance. Replaces the 2,000 MIDV faces lost when the European datasets went
out of scope. `python data/tools/pull_faces.py` fetches more.

## Outstanding - needs a human



| Item | Why blocked |

|---|---|

| **ICAO Doc 9303** parts 1–12 | `icao.int` sits behind a Cloudflare JS challenge; returns 403 to any scripted fetch. Needs a browser. Parts 3 and 4 are the ones that matter (check digits, TD3 layout). |

| **Roboflow Universe exports** | Export needs a private API key. The publishable key (`rf_…`) is rejected by the export API, and the MCP export link 404s at storage. |

| ~~**ISO 3166-1**~~ | **Closed 2026-09-08 — not blocked, and pycountry declined.** See §pycountry below. |

| **Official Indian specimens** | PRADO (Indian passport), UIDAI sample Aadhaar/PVC, ITD PAN, ECI EPIC, Parivahan DL. Manual collection; the template base for the generator. |

---

## pycountry — asked for, declined (2026-09-08)

`pip install pycountry` succeeded (26.2.16, 8.0 MB wheel) and imports with
every socket monkeypatched, so it is offline-safe. It was still declined and
uninstalled. Three reasons, in order of weight.

**1. The data is already here.** Layer B does not carry a hardcoded list.
`modules/extraction/normalize.py:country_codes()` reads
`data/raw/reference/iso3166/country-codes.csv` — the 134 KB public-domain file
already recorded in the Reference data table above — and merges 16 ICAO
supplementary codes. On this machine it resolves **265 codes**, `IND`
included. There is nothing to fix in the list.

**2. pycountry is a strict subset.** It carries the same 249 ISO alpha-3 codes
and **none** of the ICAO supplementary ones. Checked, not assumed:

```
pycountry.countries.get(alpha_3=c) for c in ("D","GBD","XXA","XXX","RKS","UNO")
  -> None, None, None, None, None, None
```

Those are exactly the codes a Layer B driven only by ISO would use to fail a
genuine German or stateless-person travel document. `ICAO_EXTRA` stays
hand-maintained against Doc 9303 either way, so pycountry would replace the
easy half of the problem with an 8 MB dependency and leave the hard half
untouched.

**3. It would land in the wrong file.** `is_country_code()` lives in
`modules/extraction/normalize.py`, not `layer_b.py`. Duplicating a country
lookup inside Layer B to avoid touching the shared function is how the same
list ends up maintained in two places.

### The real defect this turned up — one for whoever owns the ignore files

`country_codes()` degrades **silently** when the CSV is absent, and the CSV is
absent everywhere except a developer's working copy:

```
with CSV:    265 codes, is_country_code("IND") -> True
without CSV:  16 codes, is_country_code("IND") -> False
```

`data/raw/` is excluded by both `.gitignore` (line 7) and `.dockerignore`. So
in **the shipping container and in any fresh clone**, a genuine Indian passport
whose MRZ yields `nationality=IND` — and the MRZ path reads today, without the
field detector, per `context/PROGRESS.md` — produces:

> `validation.format.passport.nationality` → **fail**
> "Nationality IND is not a recognised ISO 3166 or ICAO code"

Not a hard fail on the passport profile, so it will not detain anyone, but it
is a `fail` on a genuine document in Scene 1 of the demo, and
`docker compose up` is on the 24-hour checklist. Two candidate fixes:

| Fix | Cost |
|---|---|
| Un-ignore that one file in `.gitignore` and `.dockerignore` | 134 KB, no dependency, two lines |
| Add pycountry to `requirements.txt` and rewrite `country_codes()` | 8.0 MB, a new dependency, and still needs `ICAO_EXTRA` |

The first one is obviously right. Both files are outside this agent's scope,
so it is written down rather than done. Worth a test that asserts
`is_country_code("IND")` in an environment where `data/raw/` does not exist —
that is what would have caught it.

---

## Clean container build — attempted 2026-09-08, could not run

`context/DEMO.md`'s 24-hour checklist and ROADMAP Phase 5 both require
`docker compose down -v && docker compose up` from clean. **Not attempted on
this machine: there is no Docker CLI on it.**

```
$ docker version
bash: docker: command not found

PS> docker version
docker : The term 'docker' is not recognized as the name of a cmdlet,
function, script file, or operable program.
```

Docker Desktop is *installed* — `C:\Program Files\Docker\Docker\resources\bin\`
holds `docker.exe`, `docker-compose.exe` and the rest — but that directory is
not on `PATH` in either shell, and the Desktop engine was not running. Adding
the directory to `PATH` would only get as far as the daemon.

So the Phase 5 clean-build gate is **still open**, and it has to be run on the
actual demo box rather than here anyway — that is the point of the gate. Two
things to expect when someone does run it:

1. The pip layer needs the network. This machine has an intermittent DNS
   outage; the build box needs a working resolver or a warm pip cache.
2. `GET /health` should report `field_detector_22cls` **missing** and the rest
   loaded. That is a supported state, not a crash — `Dockerfile` says so and
   the rehearsal record in `context/DEMO.md` records the same health output.

---

## The licence slide

`docs/PROVENANCE-SLIDE.md` — the slide `context/DEMO.md` asks for on the day,
built from this file. Seven projected slides plus a non-projected appendix.
The two answers worth rehearsing are on slides 3 and 6: the only
non-commercial term we actually hold is **LFW's research-use restriction**
(DocXPand-25k and `passportdetection-rgnih` are in `context/DATA.md` but were
scoped out on 2026-09-06 and were never pulled), and the field-detector
training corpus contains third-party-published real Indian cards, which we
volunteer rather than wait to be asked about.

