"""Local ASGI reproduction of BE-010; no sockets or real backend are used."""

import pytest
from fastapi import FastAPI, Request, UploadFile
from fastapi.testclient import TestClient
from shared.request_safety import RequestSizeLimitMiddleware, RequestTimeoutMiddleware
from starlette.responses import JSONResponse, StreamingResponse


@pytest.fixture
def body_client():
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=8)
    app.state.handled = False

    @app.post("/consume")
    async def consume(request: Request):
        app.state.handled = True
        return {"bytes_read": len(await request.body())}

    @app.post("/parse")
    async def parse(payload: dict):
        app.state.handled = True
        return payload

    @app.post("/ignore")
    async def ignore():
        app.state.handled = True
        return {"ok": True}

    @app.post("/respond-stream")
    async def respond_stream(request: Request):
        body = await request.body()

        async def chunks():
            yield body[:4]
            yield body[4:]

        return StreamingResponse(chunks())

    with TestClient(app) as client:
        yield client


def test_declared_oversized_body_rejected(body_client):
    assert body_client.post("/consume", content=b"123456789").status_code == 413


def test_body_at_limit_accepted(body_client):
    response = body_client.post("/consume", content=b"12345678")
    assert response.status_code == 200
    assert response.json() == {"bytes_read": 8}


def test_streamed_body_is_limited_without_content_length(body_client):
    response = body_client.post("/consume", content=iter([b"12345", b"67890"]))
    if "content-length" in response.request.headers:
        pytest.fail("Fixture unexpectedly added Content-Length; chunked-body repro is invalid")
    assert response.status_code == 413, response.text
    assert body_client.app.state.handled is False


@pytest.mark.parametrize("path", ["/consume", "/parse", "/ignore"])
@pytest.mark.parametrize("declared_length", ["-1", "0", "1", "8"])
def test_deceptive_content_length_rejected_before_handler(body_client, path, declared_length):
    """BE-010: parsers and handlers must never see an oversized request."""
    response = body_client.post(
        path,
        content=b'{"x":123}',
        headers={"Content-Length": declared_length, "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"
    assert body_client.app.state.handled is False


def test_valid_json_body_replayed_to_parser(body_client):
    response = body_client.post("/parse", content=b'{"x":1}', headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    assert response.json() == {"x": 1}


def test_negative_content_length_preserves_existing_acceptance_under_limit(body_client):
    response = body_client.post("/consume", content=b"1234", headers={"Content-Length": "-1"})
    assert response.status_code == 200
    assert response.json() == {"bytes_read": 4}


def test_accepted_body_can_produce_streaming_response(body_client):
    response = body_client.post("/respond-stream", content=iter([b"1234", b"5678"]))
    assert response.status_code == 200
    assert response.content == b"12345678"


def test_accepted_multipart_upload_preserved():
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=1024)

    @app.post("/upload")
    async def upload(file: UploadFile):
        return {"filename": file.filename, "content": (await file.read()).decode()}

    with TestClient(app) as client:
        response = client.post("/upload", files={"file": ("test.txt", b"12345678", "text/plain")})
    assert response.status_code == 200
    assert response.json() == {"filename": "test.txt", "content": "12345678"}


def _http_scope(headers=(), path="/consume"):
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "method": "POST",
        "path": path,
        "query_string": b"",
        "headers": list(headers),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("declared_length", [None, b"0", b"8"])
async def test_actual_asgi_chunks_stop_at_limit_before_dispatch(declared_length):
    """TestClient may combine chunks; assert real receive-message boundaries."""
    received = []
    sent = []
    messages = iter(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"6789", "more_body": True},
        ]
    )

    async def receive():
        message = next(messages)  # No third receive is allowed after the limit.
        received.append(message)
        return message

    async def send(message):
        sent.append(message)

    async def handler(scope, receive, send):
        pytest.fail("Oversized request reached the handler")

    headers = [] if declared_length is None else [(b"content-length", declared_length)]
    await RequestSizeLimitMiddleware(handler, max_bytes=8)(_http_scope(headers), receive, send)
    assert len(received) == 2
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [[b""], [b"1234", b"", b"5678"]])
async def test_actual_asgi_chunks_replayed_exactly(chunks):
    sent = []
    messages = iter(
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    )

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def handler(scope, receive, send):
        request = Request(scope, receive)
        assert await request.body() == b"".join(chunks)
        await JSONResponse({"ok": True})(scope, receive, send)

    await RequestSizeLimitMiddleware(handler, max_bytes=8)(_http_scope(), receive, send)
    assert sent[0]["status"] == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("content_length, status", [(b"9", 413), (b"invalid", 400)])
async def test_invalid_or_oversized_header_rejected_without_receiving(content_length, status):
    sent = []

    async def receive():
        pytest.fail("Rejected header must not wait for the request body")

    async def send(message):
        sent.append(message)

    async def handler(scope, receive, send):
        pytest.fail("Rejected header reached the handler")

    await RequestSizeLimitMiddleware(handler, max_bytes=8)(
        _http_scope([(b"content-length", content_length)]), receive, send
    )
    assert sent[0]["status"] == status


@pytest.mark.asyncio
async def test_disconnected_upload_never_reaches_handler():
    messages = iter(
        [
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.disconnect"},
        ]
    )

    async def receive():
        return next(messages)

    async def send(message):
        pytest.fail("Disconnected upload must not produce a response")

    async def handler(scope, receive, send):
        pytest.fail("Incomplete upload reached the handler")

    await RequestSizeLimitMiddleware(handler, max_bytes=8)(_http_scope(), receive, send)


@pytest.mark.asyncio
async def test_incomplete_upload_remains_subject_to_request_timeout():
    import asyncio

    sent = []

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

    async def handler(scope, receive, send):
        pytest.fail("Incomplete upload reached the handler")

    app = RequestTimeoutMiddleware(
        RequestSizeLimitMiddleware(handler, max_bytes=8), timeout_seconds=0.01
    )
    await asyncio.wait_for(app(_http_scope(), receive, send), timeout=1)
    assert sent[0]["status"] == 504


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [{"type": "websocket"}, _http_scope(path="/health")])
async def test_non_http_and_exempt_requests_pass_through_without_reading(scope):
    handled = []

    async def receive():
        pytest.fail("Passthrough must not read a body")

    async def send(message):
        pass

    async def handler(inner_scope, inner_receive, inner_send):
        assert (inner_scope, inner_receive, inner_send) == (scope, receive, send)
        handled.append(True)

    await RequestSizeLimitMiddleware(handler, max_bytes=8)(scope, receive, send)
    assert handled == [True]
