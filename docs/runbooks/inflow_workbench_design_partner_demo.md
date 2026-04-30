# Inflow Workbench Design-Partner Demo

Purpose: a 3-4 minute Loom that shows RegEngine turning messy supplier data into explainable readiness, remediation work, and protected evidence handoff.

## Setup

- Open the verified staging app at `/tools/inflow-lab`.
- Use the built-in scenario `Missing shipping destination`.
- Keep the dashboard tabs ready in a second browser tab: `/dashboard/compliance` and `/dashboard/suppliers`.
- Keep the supplier portal tab ready if the buyer asks how external partners submit data.

## Talk Track

1. Start with the problem.
   "Most FSMA 204 teams do not start with clean APIs. They start with supplier CSVs, screenshots, spreadsheets, EDI extracts, and partial shipment records."

2. Load the messy supplier feed.
   Show the Inflow Lab scenario library, choose `Missing shipping destination`, and load it into Data Feeder.

3. Run preflight.
   Click evaluate. Call out the readiness score, blocked/warning states, and the exact failed KDEs. Use this line:
   "Inflow prepares the data before it becomes permanent evidence."

4. Open the fix queue.
   Show the generated task for the missing shipping destination and any blocking rule reasons.
   "The product does not stop at pass/fail. It creates operational work with owner, severity, impact, and replay path."

5. Show the commit gate.
   Move through simulation/preflight/staging/production evidence language.
   "Simulation and preflight are safe. Production evidence requires authentication, persistence, provenance, and no unresolved fixes."

6. Save the run and switch to dashboards.
   Open `/dashboard/compliance` and point to `Inflow Workbench` readiness. Then open `/dashboard/suppliers` and show the same readiness signal beside supplier management.

7. Close with the system-of-record point.
   "The Engine proves whether records are complete and trustworthy. Inflow is now the operational front door that gets supplier data into that shape."

## Strongest Before/After

- Before: a supplier CSV with a shipment that cannot support FDA export.
- After: exact missing KDE, fix queue item, blocked commit gate, unified readiness score, and a path to replay corrected records.

## One-Liner

Inflow prepares the data. The Engine proves it.
