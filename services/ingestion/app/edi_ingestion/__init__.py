__all__ = ["router", "EDIIngestResponse"]


def __getattr__(name: str):
    if name == "router":
        from .routes import router

        return router
    if name == "EDIIngestResponse":
        from .models import EDIIngestResponse

        return EDIIngestResponse
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
