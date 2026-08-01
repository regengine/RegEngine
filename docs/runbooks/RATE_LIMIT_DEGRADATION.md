# Rate-limit degradation — failure modes, the knob, and the math

Decision record for #2699 (2026-08-01). The silent-failure sweep found
that the rate limiter's in-memory fallback on Redis failure **degrades**
the control (effective budget ≈ per-process budget × workers × replicas)
rather than removing it. Making a Redis blip an ingestion outage is an
availability trade-off, so the behavior is now **visible, bounded, and
operator-controllable** — defaulting to availability (`degrade`).

## The knob

| Env var | Values | Default | Governs |
| --- | --- | --- | --- |
| `RATE_LIMIT_FAIL_MODE` | `degrade` \| `closed` | `degrade` | Request-path rate limits: `shared/tenant_rate_limiting.py` (`_RedisBucket`, `TenantRateLimitMiddleware`, `consume_tenant_rate_limit` — ingestion RBAC, webhook, portal-link, supplier-token buckets) and `shared/rate_limit.py` `BruteForceLimiter` reads |
| `IDEMPOTENCY_FAIL_MODE` | `degrade` \| `closed` | `degrade` | `shared/idempotency.py` cache-READ errors (degrade = re-execute; duplicates still blocked by the v072 `UNIQUE (tenant_id, idempotency_key)` index) |
| `RATE_LIMIT_FALLBACK_DIVISOR` | int ≥ 1 | `WEB_CONCURRENCY`, else 1 | Per-process budget divisor while degraded (see math) |
| `CIRCUIT_BREAKER_ALLOW_MEMORY_FALLBACK` | `1` | unset | Escape hatch: allow the old silent memory-store substitution when `CIRCUIT_BREAKER_BACKEND=redis` init fails (default now fails startup) |

A **present but unrecognized** `RATE_LIMIT_FAIL_MODE` value fails closed
(`closed`) with a once-per-value error log — the operator intended a
mode; a typo must not silently weaken the control (#2662 shape).

## Behavior per mode

### `degrade` (default — preserves availability)

On a Redis error the per-process in-memory bucket keeps limiting, and:

* **Structured warning on every fallback activation** (healthy→degraded
  transition, not per request): `rate_limit_backend_unavailable` with
  `fail_mode`, `fallback`, `fallback_divisor`. Recovery logs
  `rate_limit_backend_recovered`.
* **Metric**: `rate_limit_fallback_activations_total{surface="tenant"}`
  increments once per activation. **Alert on any increase in prod.**
* **Response header**: `X-RateLimit-Degraded: 1` on responses served
  while degraded (TenantRateLimitMiddleware); `rate_limiter_degraded()`
  is exported for health payloads.
* **Tightened budget** (see math below).
* `BruteForceLimiter` (admin master key / login / MFA lockout) falls back
  to its per-process counter with the same per-activation warning
  (`brute_force_limiter_backend_unavailable`) — never silently.

### `closed` (hard guarantee, availability trade-off)

Redis uncertainty → **503 + `Retry-After: 30`** (the
`supplier_portal.py` #2700 pattern):

* `_RedisBucket.is_allowed` raises `RateLimitBackendUnavailable`
  (an `HTTPException`), which FastAPI converts to 503 at route level;
  `TenantRateLimitMiddleware` converts it explicitly (exceptions inside
  `BaseHTTPMiddleware` bypass FastAPI's handlers).
* `BruteForceLimiter.is_limited` treats Redis uncertainty as **limited**
  (deny) — a Redis blip cannot reset a lockout. Failures are still
  recorded in the per-process counter in both modes.
* `IDEMPOTENCY_FAIL_MODE=closed`: cache-read error → 503 + Retry-After
  instead of re-executing the request.

## The budget math under N workers

Redis healthy: one shared bucket → fleet budget = `limit` per window.

Redis down, `degrade` mode: every process falls back to its own empty
bucket, so the fleet budget becomes

```
effective_budget ≈ (limit ÷ RATE_LIMIT_FALLBACK_DIVISOR) × workers_per_replica × replicas
```

With the default divisor = `WEB_CONCURRENCY` (gunicorn workers per
replica, prod default 4) and a single replica, the fallback budget per
process is `limit ÷ 4`, so the fleet budget stays ≈ `limit`. Running R
replicas? Set `RATE_LIMIT_FALLBACK_DIVISOR = workers × replicas` to claw
the fleet budget back to ≈ `limit` (at the cost of stricter per-process
limits and unlucky-routing 429s — sticky load balancing softens this).
The divisor never lowers a per-process limit below 1.

`BruteForceLimiter` fallback is NOT divided: dividing a lockout
threshold (e.g. 5 failures) by workers would lock legitimate users out
after 1 mistake. Its degrade multiplies the attacker budget by worker
count — the documented-intentional trade-off from the inventory; use
`closed` mode if that is unacceptable.

## What to alert on

| Signal | Meaning |
| --- | --- |
| `rate_limit_fallback_activations_total` increase | limiter degraded to per-process |
| `rate_limit_backend_unavailable` / `brute_force_limiter_backend_unavailable` warn logs | same, with error detail |
| `X-RateLimit-Degraded: 1` on responses | live confirmation from the edge |
| `rate_limit_redis_not_configured` warn at boot | limiter was NEVER Redis-backed (config gap, not a blip) |
| `circuit_breaker_redis_init_failed` + boot failure | explicit redis circuit-store misconfigured |
| `stripe_subscription_state_corrupt` error | corrupt reorder-guard state; the update was refused — repair the mapping |

## Entitlement gates are fail-closed regardless

The subscription/entitlement gate (`subscription_gate.py`, and the
supplier-portal gate fixed in #2700) **already fails closed** — Redis
uncertainty or an open circuit returns 503, a missing/inactive
subscription returns 402, per the README contract. It does **not** read
`RATE_LIMIT_FAIL_MODE`; the only bypass remains
`SUBSCRIPTION_GATE_FAIL_OPEN` (default off, CRITICAL-logged per
request). Nothing in this change touches that contract, and the
regression tests assert it.

## Related fixes shipped with this runbook (#2699)

* Sticky `_redis_failed` in `stripe_billing/rate_limiting.py` and
  `sandbox/rate_limiting.py`: now retries Redis after a 30s cooldown and
  logs the fallback at WARNING (was DEBUG — invisible in prod).
* `circuit_breaker_store.get_store()`: explicitly configured
  `CIRCUIT_BREAKER_BACKEND=redis` that fails init now raises instead of
  silently substituting per-replica memory state (escape hatch above).
* Stripe webhook reorder guard: corrupt stored `last_event_created`
  refuses the update with an error log instead of assuming `0` (which
  let a stale `active` overwrite `canceled`).

## Deferred (still open under #2699's area)

* `services/ingestion/app/authz.py` module-level auth-failure dict: never
  migrated to `BruteForceLimiter` (#1392 did the admin key); needs its
  own migration PR.
* slowapi decorators (e.g. the 1/day GDPR export limit) still bind to
  whatever storage existed at import; a readiness check asserting
  Redis-backed rate limiting in prod remains open.
* Public sandbox share limit dict (unbounded growth, low).
