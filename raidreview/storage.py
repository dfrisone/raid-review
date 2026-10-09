import json
import os
from pathlib import Path


def app_dir():
    d = Path(os.environ.get("RAIDREVIEW_HOME") or Path(os.environ.get("APPDATA", Path.home())) / "RaidReview")
    (d / "reviews").mkdir(parents=True, exist_ok=True)
    return d


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _write(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_config():
    return _read(app_dir() / "config.json", {})


def save_config(cfg):
    _write(app_dir() / "config.json", cfg)


def load_tips():
    return _read(app_dir() / "tips.json", {})


def save_tips(tips):
    _write(app_dir() / "tips.json", tips)


def review_key(code, encounter, difficulty, mode):
    return f"{code}_{encounter}_{difficulty}_{mode}"


def review_path(key):
    if not key.replace("_", "").isalnum():
        raise ValueError("bad review key")
    return app_dir() / "reviews" / f"{key}.json"


def save_review(key, review):
    _write(review_path(key), review)
    _write(review_path(key).with_suffix(".summary"), {"key": key, "meta": review["meta"], "summary": review["summary"]})


def load_review(key):
    return _read(review_path(key), None)


def delete_review(key):
    review_path(key).unlink(missing_ok=True)
    review_path(key).with_suffix(".summary").unlink(missing_ok=True)


def list_reviews():
    out = [_read(p, None) for p in (app_dir() / "reviews").glob("*.summary")]
    return sorted([r for r in out if r], key=lambda r: r["meta"]["date"], reverse=True)
