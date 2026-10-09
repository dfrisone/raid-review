import json
import sys
import urllib.request
import webbrowser

from .server import serve

PORT = 8765


def already_running():
    try:
        return json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/ping", timeout=1)).get("app") == "raidreview"
    except Exception:
        return False


def main():
    url = f"http://127.0.0.1:{PORT}/"
    if already_running():
        webbrowser.open(url)
        return
    try:
        httpd = serve(PORT)
    except OSError:
        httpd = serve(0)
        url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"Raid Review is running at {url}")
    print("Close this window to quit.")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
