# Catalysis Writing Lexicon (v1)

*Purpose:* Reference vocabulary for writing MTA / CO₂→aromatic / zeolite catalysis manuscripts in
the field's idiomatic English register. **Read this before drafting any prose**; prefer phrasings
listed here. If a needed term isn't here, ask before inventing — many "synonyms" from general
English are wrong in catalysis register (e.g. "impaired" is not used; use "compromised" /
"diminished" / "deteriorated" / "deactivated").

*Last updated:* 2026-05-06 (v1, hand-seeded)
*To extend:* run `scripts/analysis/mine_lexicon.py` (planned) over corpus and review candidates.

---

## 0. Anti-patterns — DO NOT USE

These trigger "non-native / non-catalysis" reading. Replace as shown.

| Avoid | Use instead |
|---|---|
| impaired | compromised / diminished / deteriorated / suppressed / hampered |
| broken (catalyst) | deactivated / fouled / coked / poisoned / sintered |
| dies / dead (catalyst) | deactivates / spent |
| good selectivity | high selectivity / pronounced selectivity toward X |
| bad / poor (vague) | low / inferior / limited |
| very stable | remarkably stable / retained over N h on stream / no detectable deactivation over N h |
| many / a lot of | abundant / numerous / a wide range of / a high density of |
| make X better | enhance / improve / promote / boost / facilitate X |
| things / stuff | species / components / parameters / factors |
| got / get (results) | obtained / yielded / afforded |
| nowadays | currently / to date / in recent years |
| interesting | noteworthy / striking / unexpected |
| novel (overused) | (drop unless truly first-of-kind) |
| big / small (numeric) | high / low / large / modest |
| do / done (experiments) | perform / conduct / carry out |
| use / used (repetitive) | employ / utilize / apply (rotate, but don't overuse "utilize") |
| huge | substantial / pronounced / marked / order-of-magnitude |
| basically / essentially (informal) | (drop or use "predominantly") |
| rises/raises monotonically (simple trend) | **increases** (drop "monotonically" unless the monotonic property itself is the point) |
| acts on / affects / influences (vague verb) | be specific: inhibits / promotes / suppresses / poisons / blocks / displaces / sequesters / mediates / propagates / shifts equilibrium toward |
| each [catalyst] shows a [trend] | put the metric as subject: "[metric] decreases for all [N] catalysts" / "[metric] declines across the series" |
| X function rather than Y sites (asymmetric contrast) | use parallel structure: "the acid function rather than the metal function" / "Cu sites rather than acid sites" — match noun type on both sides |

**Hedging — keep it but right-sized:**
- weak: "may suggest", "could indicate"
- mid: "suggests", "indicates", "is consistent with"
- strong: "demonstrates", "establishes", "confirms"

---

## 1. Catalyst description

### Synthesis verbs
synthesize, prepare, fabricate, construct, assemble; dope, decorate, anchor, immobilize,
encapsulate, disperse, deposit, impregnate, exchange (ion-exchange), graft, functionalize,
modify, post-treat, dealuminate, desilicate, calcine, reduce, passivate, regenerate.

### Structural / morphological adjectives
hierarchical, mesoporous, microporous, well-defined, monodisperse, uniformly dispersed,
atomically dispersed, isolated, single-atom, sub-nanometer, well-faceted, crystalline,
amorphous, defect-rich, defect-free, intergrown, hollow, core–shell, yolk–shell.

### Acidity / sites (MTA/zeolite-specific)
- Brønsted acid sites (BAS); Lewis acid sites (LAS)
- framework Al; extra-framework Al (EFAl)
- acid density (μmol·g⁻¹); acid strength; total acidity; acid site distribution
- proximity / pairing of Al sites; Al siting
- silanol nests; defect sites
- "balanced BAS/LAS ratio"; "moderate acidity"; "tunable acid strength"

### Composition / structure
bimetallic, multimetallic, supported, encapsulated, alloyed, segregated;
"X supported on Y" / "X/Y", "X-modified Y", "X-promoted Y";
"with a Si/Al ratio of N" / "of Si/Al = N".

### Templates
- "[Cat] was synthesized via [route] using [precursor] as the [Y] source."
- "The [Cat] catalyst, with a Si/Al ratio of N and BET surface area of M m²·g⁻¹, ..."
- "[Metal] species were atomically dispersed on [support], as evidenced by [HAADF-STEM / EXAFS]."

---

## 2. Performance reporting

### Verbs (preferred)
exhibit, display, deliver, achieve, attain, afford, sustain, maintain, retain, reach.

### Adjectives (rank-ordered, weakest → strongest; use sparingly)
appreciable < notable < high < pronounced < remarkable < exceptional < outstanding < unprecedented.

Use "unprecedented" only if truly first-reported; reviewers push back on overclaim.

### Metrics — write the unit
- conversion (%) — "methanol conversion of N%"
- selectivity (%) — "selectivity toward [product] of N%" or "[product] selectivity of N%"
- yield (%) — "[product] yield of N%"
- productivity / space-time yield (STY) — "g_product · g_cat⁻¹ · h⁻¹"
- TOF (turnover frequency) — "h⁻¹" or "s⁻¹"
- TON (turnover number) — dimensionless
- aromatic yield, BTX yield, p-xylene selectivity, p/o ratio
- WHSV (h⁻¹), GHSV (h⁻¹), contact time

### Stability phrasing
- "stable for N h on stream"
- "no detectable deactivation was observed over N h"
- "[X]% of the initial activity was retained after N h"
- "the catalyst could be regenerated by [calcination in air at T °C] with [near-complete] recovery of activity over N cycles"

### Templates
- "[Cat] exhibited a [metric] of [value] under [conditions: T, P, WHSV]."
- "Under optimized conditions ([T] °C, [P] bar, WHSV = [X] h⁻¹), [Cat] afforded [N]% selectivity toward [product] at [M]% conversion."
- "[Cat] delivered an aromatic yield of [N]% and remained stable over [t] h on stream."
- "Compared with [reference], [Cat] showed an [N]-fold enhancement in [metric]."

---

## 3. Mechanism & active site

### Verbs
facilitate, promote, suppress, hinder, inhibit, mediate, govern, dictate, dominate,
accelerate, retard, activate, deactivate, propagate, terminate, regenerate.

### Mechanism vocabulary (MTA / MTH-specific)
- elementary step; rate-determining step (RDS); transition state; intermediate
- methylation; hydride transfer; β-scission; oligomerization; cyclization; aromatization;
  dehydrogenation; cracking; alkylation; isomerization
- dual-cycle mechanism: olefin-based cycle / aromatic-based cycle (alkene cycle / aromatic cycle)
- hydrocarbon pool (HCP); polymethylbenzenes (polyMBs); heptamethylbenzenium cation (heptaMB⁺)
- shape selectivity: reactant / product / transition-state shape selectivity
- confinement effect; pore confinement; diffusion limitation; molecular traffic
- coke / coke deposition; carbonaceous deposits; soft coke / hard coke; graphitic coke
- Mars–van Krevelen, Eley–Rideal, Langmuir–Hinshelwood (general)

### Cooperative / multifunctional language
synergistic, cooperative, bifunctional, tandem, relay, cascade.

### Causal / attributional connectors
- attributed to / ascribed to / arises from / originates from / stems from / reflects
- consistent with / in agreement with / in line with / supports the notion that
- evidences / indicates / suggests / implies
- "X plays a pivotal / decisive / key role in Y"
- "X is responsible for Y"
- "the enhanced [Y] is rationalized by [Z]"

### Templates
- "[Reaction] proceeds via [pathway], with [intermediate] as the key [species]."
- "The [observed enhancement] is attributed to [factor], which [mechanism]."
- "DFT calculations revealed that [step] is the rate-determining step, with an activation energy of [N] kJ·mol⁻¹."
- "The [olefin-based / aromatic-based] cycle dominates over [Cat], as evidenced by [12C/13C tracing / product distribution]."

---

## 4. Comparison & framing

### Comparative phrasing
- comparable to / on par with / in line with
- exceeds / outperforms / surpasses / is superior to
- in stark contrast to / by contrast / unlike [X]
- "an [N]-fold enhancement" / "an order-of-magnitude improvement"
- "[N]× higher than that of [reference]"
- benchmark / state-of-the-art (spell out at first use) / reported value

### Framing the contribution
- "to the best of our knowledge, this is the first report of [...]"
- "our [Cat] outperforms previously reported [class] catalysts under comparable conditions"
- "this represents a [N]-fold improvement over [reference]"

### Anti-pattern
- "many studies show" → "extensive prior work has demonstrated" / "previous studies have shown"
- "in the past few years many people have studied" → "[topic] has attracted considerable interest in recent years"

---

## 5. Motivation / introduction openers

- "[Topic / reaction] has attracted considerable / growing interest as a [route to / strategy for / pathway toward] [Y]."
- "[Reaction] represents a promising route for [Y], owing to [reason]."
- "Despite considerable progress, [challenge] remains a long-standing challenge owing to [Y]."
- "However, [issue] is hampered / constrained / limited by [Y]."
- "Achieving [target] therefore represents a key / outstanding / long-standing goal in [field]."
- "Tailoring [X] to balance [Y and Z] is critical for [outcome]."
- "Among the various [X], [class] has emerged as a particularly attractive candidate due to [Y]."

---

## 6. Discussion & attribution

### Hedge calibration
- weak: "may", "could", "tentatively"
- mid: "suggests", "indicates", "is consistent with", "likely"
- strong: "demonstrates", "establishes", "confirms"

### Attribution chain (use in Discussion)
- "[observation] is attributed to [factor]"
- "[factor] arises from [structural feature]"
- "[structural feature] is corroborated by [characterization]"

### Linking observations to mechanism
- "in agreement with / consistent with previous reports on [...]"
- "this observation supports the notion that [...]"
- "taken together, these results indicate that [...]"
- "we therefore propose that [...]"
- "to rationalize [observation], we performed [DFT / in situ / operando] [characterization], which revealed [...]"

### Limitations / caveats (if needed)
- "we note that [...]"
- "it should be emphasized that [...]"
- "the present work does not resolve [X]; further [in situ / operando] studies will be required to [...]"

---

## 7. Domain-specific shorthand & nomenclature

Use the standard abbreviation, spelled out at first use.

| Abbrev | Full |
|---|---|
| MTH | methanol-to-hydrocarbons |
| MTA | methanol-to-aromatics |
| MTO | methanol-to-olefins |
| MTP | methanol-to-propylene |
| MTG | methanol-to-gasoline |
| BTX | benzene, toluene, xylenes |
| pX / oX / mX | para- / ortho- / meta-xylene |
| BAS / LAS | Brønsted / Lewis acid sites |
| EFAl | extra-framework aluminium |
| HCP | hydrocarbon pool |
| polyMBs | polymethylbenzenes |
| WHSV / GHSV | weight / gas hourly space velocity |
| TOS | time-on-stream |
| STY | space-time yield |
| TOF / TON | turnover frequency / number |
| HAADF-STEM | high-angle annular dark-field STEM |
| EXAFS / XANES | extended X-ray absorption fine structure / X-ray absorption near-edge structure |
| ²⁹Si / ²⁷Al MAS NMR | (always italicize MAS in journals that require it) |
| TPD / TPR | temperature-programmed desorption / reduction |
| NH₃-TPD, Py-IR | ammonia TPD, pyridine IR (acidity probes) |

### Reaction product nomenclature
- "C₂–C₄ olefins / light olefins"
- "C₅⁺ hydrocarbons"
- "aromatics / BTX / heavy aromatics (C₉⁺)"
- "p-xylene selectivity within xylenes" vs "p-xylene selectivity within total products" — **always specify the basis**

---

## 8. Style notes

- **Tense**: methods past (synthesized, characterized); results past (exhibited, achieved);
  general truths / accepted mechanism present (proceeds, is governed by); discussion mixes past
  observations with present interpretation.
- **Voice**: passive is acceptable and idiomatic in catalysis. Don't over-correct to active.
- **Numbers**: spell out one through nine in prose; use digits with units always.
- **"Catalyst" naming**: introduce a short-hand like "[Metal]/[Support]" or "x%[Metal]@[Support]"
  on first use; keep consistent.
- **First-person plural** ("we") is normal and expected in the field.
- **British vs American spelling**: pick one (most journals: AmE — "aluminum", "behavior";
  but some still want BrE — "aluminium", "behaviour"). Match the target journal.

---

## 9. Quick-lookup index (for "I want to say X")

| I want to say... | Try... |
|---|---|
| The catalyst worked well | exhibited high activity / delivered [metric] of [value] |
| It got worse over time | underwent gradual deactivation / [metric] declined from N to M over t h |
| It didn't break down | remained stable / no detectable deactivation was observed |
| There were a lot of acid sites | a high density of BAS / abundant Brønsted acid sites |
| Because of the structure | owing to the [hierarchical pore structure / confined geometry / ...] |
| This shows that... | This [demonstrates / suggests / indicates] that... (calibrate hedge) |
| Compared to before | compared with [reference] / relative to [reference] |
| New / first | (sparingly) "represents the first report of" / "to the best of our knowledge" |
| Surprising | (sparingly) "noteworthy" / "unexpectedly" / "strikingly" |
| Important role | "plays a pivotal / decisive / key role in" |
| Caused by | "attributed to / ascribed to / originates from / stems from" |

---

## Notes on confidence (v1)

- Sections 1–4, 7: high confidence — these are field-standard.
- Sections 5, 6: medium — register fits but exact phrasings vary by journal house style.
- Anti-patterns table (§0): explicitly tagged as patterns Claude has used wrongly in the past
  (e.g., "impaired"). Extend as new mis-uses are caught.

**Extension plan**: `scripts/analysis/mine_lexicon.py` will (a) tokenize evidence_units by section,
(b) extract high-frequency catalysis-specific verbs/adjectives via spaCy + filtering,
(c) propose candidate additions for review.
