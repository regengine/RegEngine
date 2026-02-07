# Schema Evolution Policy

## 1. Compliance Standard
All schemas must maintain **BACKWARD** compatibility mode in Confluent Schema Registry. This ensures that consumers using new schema versions can process data written with old schema versions.

## 2. Evolution Rules

### ✅ Allowed Changes
*   **Adding Fields**: Must have a valid `default` value (e.g., `null` or a constant).
*   **Removing Fields**: Specify as optional (`["null", "type"]`) before removing, then remove from producer first.
*   **Renaming Fields**: Use `aliases` to support old field names.
*   **Widening Types**: `int` -> `long`, `float` -> `double`.

### ❌ Prohibited Changes (Breaking)
*   Adding mandatory fields (no default).
*   Removing mandatory fields.
*   Changing enum symbols (renaming/removing).
*   Narrowing types (`long` -> `int`).

## 3. Deployment Procedure
1.  **Validate**: Run `schema-registry-cli check` against compatibility mode.
2.  **Register**: Push new schema to registry (auto-versioned).
3.  **Update Consumers**: Deploy consumers compatible with new schema.
4.  **Update Producers**: Deploy producers using new schema.
