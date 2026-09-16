# Recall Reconstruction Fixture

A small, fully synthetic scenario for one question: **when a recall names a lot, can RegEngine show where every case went, and say plainly what it cannot show?**

All names, GLNs, SSCCs, lot codes, and documents are invented (see `../SYNTHETIC.md`). Identifiers carry valid GS1 check digits so they exercise the real validators.

## The scenario

One product, two lots, six pallets, four custodians:

| Party | GLN | Records it holds |
|---|---|---|
| Harborline Foods Plant (manufacturer) | 0861000110003 | lots, pallet build, outbound shipping |
| Northgate Distribution Center (DC, ERP-fed) | 0861000220009 | receiving, repack, outbound shipping |
| Bluewater Logistics (3PL) | 0861000330005 | receiving, repack, outbound shipping |
| Cascade Market DC / Summit Foods Warehouse (destinations) | 0861000440001 / 0861000550007 | receiving |

Lot **HLF-215A** is the implicated lot (190 cases). **HLF-215B** (140 cases) travels alongside it.

| Pallet (SSCC) | Built at | Contents | What happens to it |
|---|---|---|---|
| …0010 (P1) | MFG | A 60 | MFG → DC → 3PL → Cascade |
| …0027 (P2) | MFG | A 60 | same; Cascade counts 58 |
| …0034 (P3) | MFG | A 40 + B 20 (mixed) | split at DC into P7 and P8 |
| …0041 (P4) | MFG | B 60 | DC receipt keyed without a BOL; corrected by the recall coordinator with reason and evidence |
| …0058 (P5) | MFG | B 60 | MFG → DC → 3PL → Summit |
| …0065 (P6) | MFG | A 30 | relabelled at DC as P9 (identifier change) |
| …0072 (P7) / …0089 (P8) | DC | A 40 / B 20 | consolidated at the 3PL into P10 |
| …0096 (P9) | DC | A 30 | 3PL → Cascade |
| …0102 (P10) | 3PL | A 40 + B 20 (mixed) | 3PL → Summit |

Answer key (`answer_key.json`): HLF-215A reaches Cascade (150 cases: P1, P2, P9) and Summit (40 cases: P10).

## Files

One CSV per record source. Every row is kept with its file, row number, and file hash, so every conclusion in the output points back to a record.

- `mfg_lots.csv`, `mfg_pallet_contents.csv`, `mfg_shipping.csv` — manufacturer WMS
- `dc_receiving.csv`, `dc_repack.csv`, `dc_shipping.csv` — DC ERP
- `3pl_receiving.csv`, `3pl_repack.csv`, `3pl_shipping.csv` — 3PL WMS
- `destination_receiving.csv` — destination WMS
- `manual_corrections.csv` — attested corrections (author, reason, evidence required)
- `sync_manifest.json` — per-file hash and per-source last successful synchronization time
- `retained/dc_erp/` — the DC ERP snapshot RegEngine holds, taken before the DC's outbound shipments
- `answer_key.json` — ground truth plus the expected outcome of each case

## The three runs

```bash
python3 scripts/run_recall_fixture.py --case all --output-dir /tmp/regengine-recall-fixture
```

| Case | What changes | What the worksheet must say |
|---|---|---|
| `complete` | nothing | every row `linked` or `no_link_established`; totals match the answer key; the 2-case shortfall on P2 is reported |
| `missing_3pl_contents` | `3pl_repack.csv` withheld | P10, P7, P8 become `unresolved`; the exact record needed is named (type, custodian, GLN, time window, candidate input pallets); HLF-215A at Summit is *not* reported as zero |
| `erp_unavailable` | DC ERP unreachable; only `retained/dc_erp/` used | the package states the last successful sync time; DC receiving and repacks reproduce exactly; every movement after the cutoff is `unresolved` with the missing shipping record named |

## Reading the worksheet

Each row is one (pallet, lot) at its last recorded location, with exactly one label:

- `linked` — an unbroken evidence chain connects this quantity to the implicated lot.
- `no_link_established` — the chain is complete within the reviewed evidence and no record on it names the implicated lot. This is **not** a statement that product is safe.
- `unresolved` — a required record is missing, conflicting, or was unavailable. Treat as potentially implicated until the named record is obtained.

Flags `co_palletized_with_implicated_lot` and `lineage_includes_implicated_lot` mark rows a practitioner will want to look at even when the label is `no_link_established`.

Excluding product from a recall is a practitioner decision. The engine never makes it.
