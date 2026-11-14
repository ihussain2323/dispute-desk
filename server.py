"""Local HTTP interface for a turn-based voice dispute agent."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit
import wave

from audio import transcribe
from intake import Conflict, advance, case, connection, initialize, start

ROOT = Path(__file__).resolve().parent
MAX_UPLOAD = 1_000_000


class Handler(BaseHTTPRequestHandler):
    def send(self, status, data, mime):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers()
        self.wfile.write(data)

    def respond(self, status, obj):
        self.send(status, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        path = self.path
        pages = {"/":("index.html","text/html; charset=utf-8"),"/app.js":("app.js","text/javascript"),
                 "/style.css":("style.css","text/css")}
        if path in pages:
            filename, mime = pages[path]
            self.send(200,(ROOT/"static"/filename).read_bytes(),mime)
            return
        match = re.fullmatch(r"/cases/(DSP-[A-F0-9]{12})", path)
        if match:
            try:
                self.respond(200,case(self.server.db,match[1]))
            except KeyError:
                self.respond(404,{"error":"Case not found"})
            return
        match = re.fullmatch(r"/calls/([a-f0-9]{32})/speech/(\d{1,5})", path)
        if match:
            with connection(self.server.db) as db:
                if int(match[2]) == 0:
                    from intake import OPENING
                    row = db.execute("SELECT ? FROM calls WHERE id=?", (OPENING,match[1])).fetchone()
                else:
                    row = db.execute("SELECT reply FROM turns WHERE call_id=? AND seq=?", (match[1],int(match[2]))).fetchone()
            if not row:
                self.respond(404,{"error":"Prompt not found"})
                return
            prompt = row[0] if int(match[2]) == 0 else json.loads(row[0])["prompt"]
            try:
                with tempfile.TemporaryDirectory() as folder:
                    output = Path(folder)/"reply.wav"
                    subprocess.run([self.server.flite,"-voice","rms","-t",prompt,"-o",str(output)],
                                   check=True,capture_output=True,timeout=20)
                    self.send(200,output.read_bytes(),"audio/wav")
            except (OSError,subprocess.SubprocessError):
                self.respond(503,{"error":"Speech synthesis unavailable"})
            return
        self.respond(404,{"error":"Not found"})

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            self.respond(403,{"error":"Cross-origin writes are disabled"})
            return
        if self.path == "/calls":
            self.respond(201,start(self.server.db))
            return
        match = re.fullmatch(r"/calls/([a-f0-9]{32})/turns",self.path)
        if not match:
            self.respond(404,{"error":"Unknown path"})
            return
        try:
            if self.headers.get_content_type()!="audio/wav":
                raise ValueError("Send a WAV audio turn")
            length = int(self.headers.get("Content-Length",0))
            if not 44 <= length <= MAX_UPLOAD:
                raise ValueError("Recording exceeds size limits or is empty")
            seq = int(self.headers.get("X-Sequence",""))
            key = self.headers.get("Idempotency-Key","")
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",key):
                raise ValueError("Supply a valid turn ID")
            data = self.rfile.read(length)
            words = transcribe(data,self.server.cli,self.server.model)
            self.respond(200,advance(self.server.db,match[1],seq,key,words))
        except Conflict as exc:
            self.respond(409,{"error":str(exc)})
        except (ValueError,EOFError,wave.Error) as exc:
            self.respond(422,{"error":str(exc)})
        except KeyError:
            self.respond(404,{"error":"Unknown call"})
        except (OSError,subprocess.SubprocessError):
            self.respond(503,{"error":"Recognition unavailable. Check the configured CLI and model."})


def make_server(port, db, cli, model, flite, bind="127.0.0.1"):
    initialize(db)
    server = ThreadingHTTPServer((bind,port),Handler)
    server.db, server.cli, server.model, server.flite = db, cli, model, flite
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--bind",default="127.0.0.1")
    parser.add_argument("--db",default="disputes.sqlite")
    args = parser.parse_args()
    with make_server(args.port,args.db,os.environ.get("WHISPER_CLI","whisper-cli"),
                     os.environ.get("WHISPER_MODEL","ggml-tiny.en.bin"),os.environ.get("FLITE","flite"), args.bind) as service:
        print(f"Dispute Desk at http://127.0.0.1:{service.server_port}",flush=True)
        service.serve_forever()
