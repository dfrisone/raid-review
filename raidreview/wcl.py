import base64
import json
import time
import urllib.error
import urllib.request

TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
API_URL = "https://www.warcraftlogs.com/api/v2/client"


class WclError(Exception):
    pass


class Client:
    def __init__(self, client_id, secret):
        self.client_id = client_id
        self.secret = secret
        self._token = None
        self._expires = 0

    def _fetch_token(self):
        auth = base64.b64encode(f"{self.client_id}:{self.secret}".encode()).decode()
        req = urllib.request.Request(TOKEN_URL, data=b"grant_type=client_credentials",
                                     headers={"Authorization": "Basic " + auth,
                                              "Content-Type": "application/x-www-form-urlencoded"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as e:
            if e.code in (400, 401):
                raise WclError("Warcraft Logs rejected the client ID or secret.") from e
            raise
        self._token = r["access_token"]
        self._expires = time.time() + r.get("expires_in", 3600) - 60

    def gql(self, query, variables=None):
        if not self._token or time.time() > self._expires:
            self._fetch_token()
        req = urllib.request.Request(API_URL, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                     headers={"Authorization": "Bearer " + self._token, "Content-Type": "application/json"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=120))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise WclError("Warcraft Logs rate limit reached. It resets within the hour.") from e
            raise
        if r.get("errors"):
            msg = r["errors"][0].get("message", "unknown error")
            if "permission" in msg.lower() or "private" in msg.lower():
                msg = "This report is private. Only public and unlisted reports can be reviewed."
            raise WclError(msg)
        return r["data"]

    def check(self):
        return self.gql("{ rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn } }")["rateLimitData"]
