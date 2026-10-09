import json
import sys
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import review, storage
from .wcl import Client, WclError

STATIC = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent)) / "raidreview" / "static"
if not STATIC.exists():
    STATIC = Path(__file__).parent / "static"

jobs = {}
_client = None


def client():
    global _client
    cfg = storage.load_config()
    if not cfg.get("clientId"):
        raise WclError("Add your Warcraft Logs API client first.")
    if not _client or _client.client_id != cfg["clientId"] or _client.secret != cfg["secret"]:
        _client = Client(cfg["clientId"], cfg["secret"])
    return _client


def with_avoid(r):
    saved = storage.load_config().get("avoid", {}).get(str(r["meta"]["encounter"]))
    if saved is not None:
        r["avoid"] = saved
    return r


def run_job(job_id, code, encounter, difficulty, mode):
    job = jobs[job_id]

    def progress(stage, done, total):
        job.update(stage=stage, done=done, total=total)

    try:
        r = review.build(client(), code, encounter, difficulty, mode, progress)
        key = storage.review_key(code, encounter, difficulty, mode)
        storage.save_review(key, r)
        job.update(key=key, finished=True)
    except (WclError, ValueError) as e:
        job.update(error=str(e), finished=True)
    except Exception as e:
        traceback.print_exc()
        job.update(error=f"Something went wrong: {e}", finished=True)


def export_html(r):
    page = (STATIC / "app.html").read_text(encoding="utf-8")
    data = json.dumps(r, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return page.replace("<!--EMBED-->", f"<script>window.EMBEDDED = {data};</script>", 1)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, status=200, ctype="application/json", headers=()):
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def allowed(self, write=False):
        # websites open in the same browser can reach localhost; a custom header forces a CORS preflight they cannot pass
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        return not write or self.headers.get("X-Raid-Review") == "1"

    def do_GET(self):
        if not self.allowed():
            return self.send({"error": "Forbidden."}, 403)
        path = self.path.partition("?")[0]
        if path == "/":
            return self.send((STATIC / "app.html").read_text(encoding="utf-8"), ctype="text/html")
        if path == "/api/ping":
            return self.send({"app": "raidreview"})
        if path == "/api/state":
            cfg = storage.load_config()
            return self.send({"configured": bool(cfg.get("clientId")), "clientId": cfg.get("clientId", ""),
                              "reviews": storage.list_reviews(), "avoid": cfg.get("avoid", {}), "defaults": review.AVOID_DEFAULTS})
        if path.startswith("/api/job/"):
            job = jobs.get(path.rsplit("/", 1)[1])
            return self.send(job or {"error": "Unknown job.", "finished": True})
        if path.startswith("/api/review/"):
            r = storage.load_review(path.rsplit("/", 1)[1])
            return self.send(with_avoid(r)) if r else self.send({"error": "Review not found."}, 404)
        if path.startswith("/api/export/"):
            key = path.rsplit("/", 1)[1]
            r = storage.load_review(key)
            if not r:
                return self.send({"error": "Review not found."}, 404)
            m = r["meta"]
            name = f'{m["boss"]} {m["difficultyName"]} {m["mode"]} {key.split("_")[0]}.html'.replace(" ", "-")
            return self.send(export_html(with_avoid(r)), ctype="text/html",
                             headers=[("Content-Disposition", f'attachment; filename="{name}"')])
        self.send({"error": "Not found."}, 404)

    def do_POST(self):
        if not self.allowed(write=True):
            return self.send({"error": "Forbidden."}, 403)
        try:
            b = self.body()
            if self.path == "/api/credentials":
                c = Client(b["clientId"].strip(), b["secret"].strip())
                c.check()
                cfg = storage.load_config()
                cfg.update(clientId=c.client_id, secret=c.secret)
                storage.save_config(cfg)
                return self.send({"ok": True})
            if self.path == "/api/report":
                code, boss, diff, mode = review.parse_report(b["link"])
                ov = review.overview(client(), code)
                ov["pick"] = {"encounter": boss, "difficulty": diff, "mode": mode}
                return self.send(ov)
            if self.path == "/api/review":
                key = storage.review_key(b["code"], b["encounter"], b["difficulty"], b["mode"])
                if not b.get("refresh") and storage.load_review(key):
                    return self.send({"key": key})
                job_id = uuid.uuid4().hex
                jobs[job_id] = {"stage": "Starting", "done": 0, "total": 1, "finished": False}
                threading.Thread(target=run_job, args=(job_id, b["code"], int(b["encounter"]), int(b["difficulty"]), b["mode"]),
                                 daemon=True).start()
                return self.send({"job": job_id})
            if self.path == "/api/avoid":
                cfg = storage.load_config()
                cfg.setdefault("avoid", {})[str(b["encounter"])] = b["list"]
                storage.save_config(cfg)
                return self.send({"ok": True})
        except (WclError, ValueError, KeyError) as e:
            return self.send({"error": str(e)}, 400)
        self.send({"error": "Not found."}, 404)

    def do_DELETE(self):
        if not self.allowed(write=True):
            return self.send({"error": "Forbidden."}, 403)
        if self.path.startswith("/api/review/"):
            storage.delete_review(self.path.rsplit("/", 1)[1])
            return self.send({"ok": True})
        self.send({"error": "Not found."}, 404)


def serve(port):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
