import html
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import storage

URL = "https://nether.wowhead.com/tooltip/spell/{}?dataEnv=1&locale=0"


def _text(tip):
    # the first table is name, range and cast time; the description follows
    parts = tip.split("</table>", 1)
    body = parts[1] if len(parts) > 1 else parts[0]
    body = re.sub(r"<br\s*/?>|</?(td|tr|div|table)[^>]*>", "\n", body)
    body = html.unescape(re.sub(r"<[^>]+>", "", body))
    body = "\n".join(line.strip() for line in body.split("\n") if not line.strip().startswith("Requires"))
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _fetch(spell_id):
    req = urllib.request.Request(URL.format(spell_id), headers={"User-Agent": "Mozilla/5.0 RaidReview"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=15))
    except Exception:
        return ""
    return _text(r.get("tooltip", ""))[:600]


def describe(name_ids, progress=lambda done, total: None):
    """name_ids maps an ability name to candidate spell IDs, best first. Returns {name: {"id", "d"}}."""
    cache = storage.load_tips()
    missing = sorted({i for ids in name_ids.values() for i in ids[:4] if str(i) not in cache})
    with ThreadPoolExecutor(4) as ex:
        for n, (i, text) in enumerate(zip(missing, ex.map(_fetch, missing))):
            cache[str(i)] = text
            if n % 20 == 0:
                progress(n, len(missing))
    storage.save_tips(cache)
    out = {}
    for name, ids in name_ids.items():
        for i in ids[:4]:
            if cache.get(str(i)):
                out[name] = {"id": i, "d": cache[str(i)]}
                break
    return out
