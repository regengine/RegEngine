# RegEngine architecture documentation

These pages describe the checked-in FSMA-first application and its configured
release surface. Source review is not evidence of a successful live deployment,
customer use, regulatory approval, or compliance.

- [Architecture overview](ARCHITECTURE.md): data flow, routing and trust boundaries.
- [C4 context](c4-context.md): actors and external dependencies.
- [C4 containers](c4-containers.md): frontend, consolidated backend and stores.
- [C4 components](c4-components.md): key code paths in the backend.
- [Consolidation](CONSOLIDATION.md): current build wiring and legacy scaffolding.
- [Decisions](decisions/): architecture decision records, each with its own date and scope.

The release-approved route set is maintained in
[`server/router_policy.py`](../../server/router_policy.py), with mount points in
[`server/main.py`](../../server/main.py). A route existing in source does not
establish that it is enabled or deployed.
