# Compliance Service

The compliance service powers checklist evaluation and FSMA 204 domain logic. Dependencies are managed via `requirements.txt` and installed in the service Docker image.

## Key Python Dependencies
- `fastapi` for the HTTP API.
- `uvicorn` for the ASGI server.
- `pydantic` for request/response models.
- `pyyaml` for loading compliance definitions.
- `structlog` for structured logging.
- `prometheus-client` for metrics exposition.
- `validators==0.22.0` for GLN, FDA registration, and location identifier validation helpers.
