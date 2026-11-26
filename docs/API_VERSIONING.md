# API versioning and change guidance

RegEngine has routes under both `/api/v1/` and `/v1/`; use the exact path and
contract for the endpoint rather than assuming either prefix applies to every
route. Router existence in source is not proof that it is enabled in a target
environment. Check [`server/router_policy.py`](../server/router_policy.py),
[`server/main.py`](../server/main.py), and the [router audit](engineering/ROUTER_SURFACE.md).
The [OpenAPI documentation](openapi/README.md) describes the generated API
artifacts and their limitations.

## Compatibility guidance

Treat removal or renaming of endpoints or fields, new required inputs, type or
authorization changes, and changed error behavior as potentially breaking.
Adding a response enum value can also break clients that exhaustively match values.
Before a breaking change, document the affected operation, migration path,
client impact, and rollout and notification plan; update the relevant tests and
[CHANGELOG.md](../CHANGELOG.md). Do not assume that versioning alone makes a
change safe.

Earlier versions of this page described automatic version, deprecation, Sunset,
and SDK headers, fixed notice periods and email notifications as existing
behavior. Those guarantees are not established by the current source review.
A deprecation schedule or response headers must be implemented and announced for
the specific change before clients rely on them.

The [Python SDK](../regengine/README.md) is source-installable and not currently
published to PyPI. Its individual methods have different route availability;
check the SDK documentation and the target environment before depending on one.
