# RegEngine Sample Data — E2E Ingestion Test

These CSV files simulate a real multi-supplier romaine lettuce supply chain.
Import them via **Dashboard → Data Import → CSV Upload** in order:

1. `01_harvesting.csv` — Salinas Valley Farms harvests 3 lots
2. `02_cooling.csv` — Same-day cooling (one event missing cooling_date — will trigger rule failure)
3. `03_initial_packing.csv` — FreshCut Processing packs into retail units
4. `04_shipping.csv` — Ships to 2 retailers
5. `05_receiving.csv` — MegaMart and Premier Grocery receive shipments
6. `06_transformation.csv` — Metro Processing transforms into salad mix

After import, visit:
- **Dashboard → Compliance** — score should reflect KDE gaps
- **Dashboard → Audit Log** — all events in tamper-evident chain
- **Dashboard → Recall Report** — readiness assessment based on real data
