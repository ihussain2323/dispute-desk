"""Serve local voice intake and its browser client with FastAPI."""
import argparse
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import wave

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
import uvicorn

from audio import SpeechEngine
from intake import OPENING, Conflict, advance, case, connection, initialize, start

STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD = 1_000_000


def create_app(db, models, voice):
    @asynccontextmanager
    async def lifespan(app):
        initialize(db)
        app.state.speech = SpeechEngine(models, voice)
        yield

    app = FastAPI(title="Dispute Desk", lifespan=lifespan)

    @app.middleware("http")
    async def local_requests(request, call_next):
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"error": "Cross-origin writes are disabled"}, status_code=403)
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        return response

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"error": str(exc.args[0])}, status_code=404)

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=409)

    @app.post("/calls", status_code=201)
    def begin():
        return start(db)

    @app.get("/cases/{case_id}")
    def read_case(case_id: str):
        return case(db, case_id)

    @app.get("/calls/{call_id}/speech/{seq}")
    def say(call_id: str, seq: int):
        with connection(db) as conn:
            if seq == 0:
                row = conn.execute("SELECT ? FROM calls WHERE id=?", (OPENING, call_id)).fetchone()
            else:
                row = conn.execute("SELECT reply FROM turns WHERE call_id=? AND seq=?", (call_id, seq)).fetchone()
        if not row:
            raise KeyError("Prompt not found")
        prompt = row[0] if seq == 0 else json.loads(row[0])["prompt"]
        return Response(app.state.speech.synthesize(prompt), media_type="audio/wav")

    @app.post("/calls/{call_id}/turns")
    async def turn(call_id: str, request: Request,
                   x_sequence: int = Header(ge=0),
                   idempotency_key: str = Header(pattern=r"^[a-zA-Z0-9_-]{1,64}$")):
        if request.headers.get("content-type", "").split(";")[0] != "audio/wav":
            return JSONResponse({"error": "Send a WAV audio turn"}, status_code=415)
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_UPLOAD:
                return JSONResponse({"error": "Recording is too long"}, status_code=413)
            data.extend(chunk)
        try:
            text = await run_in_threadpool(app.state.speech.transcribe, data)
        except (ValueError, EOFError, wave.Error) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return await run_in_threadpool(advance, db, call_id, x_sequence, idempotency_key, text)

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="browser")
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--db", default="disputes.sqlite")
    args = parser.parse_args()
    app = create_app(args.db, Path(os.getenv("MODEL_DIR", "models")), int(os.getenv("AGENT_SPEAKER", "5")))
    uvicorn.run(app, host=args.bind, port=args.port)
