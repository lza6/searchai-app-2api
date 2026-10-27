#!/usr/bin/env python3
"""SearchAI demo server — 上游透传 + OpenAI 风格接口. 端口 8918."""
import base64, json, os, sys, time, uuid, threading, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

BASE = "https://appss.airy365.com"
BODY_KEY = b"FkdCTuwMcrHyO2LK"
HEADER_KEY = b"GQmj8ePOKHn0VN2c"
APP_NAME = "10175611458440310241"
DEMO_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.html")

SESSION = {"uuid": str(uuid.uuid4()).replace("-", "") + str(int(time.time() * 1000)),
           "accountId": "", "lock": threading.Lock()}
STATS = {"req": 0, "up_err": 0, "t0": time.time()}
GATE = threading.Semaphore(4)  # 全局并发闸, 防上游限流

def gcm_enc(key, plaintext: str) -> str:
    nonce = os.urandom(12)
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, plaintext.encode(), None)).decode()

def gcm_dec(key, b64: str):
    raw = base64.b64decode(b64)
    return AESGCM(key).decrypt(raw[:12], raw[12:], None).decode()

def headers() -> dict:
    h = {"deviceType": "ANDROID", "version": "1.0.1", "deviceModel": "Pixel 6",
         "uuid": SESSION["uuid"], "brand": "Google", "channel": "google",
         "appName": APP_NAME, "lang": "en", "region": "US",
         "androidId": SESSION["uuid"][:16], "systemVersion": "13"}
    return {"n": APP_NAME, "overSeaFlag": "YES", "sea": "YES",
            "va": gcm_enc(HEADER_KEY, json.dumps(h, separators=(",", ":"))),
            "timeZone": "Asia/Shanghai", "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "okhttp/4.12.0"}

def up_post(path: str, obj: dict, timeout=60):
    with SESSION["lock"]:
        if not SESSION["accountId"]:
            # 注意: getAccountInfo body 不能带 accountId, 账号由 header va 的 uuid 决定
            body = {"vs": gcm_enc(BODY_KEY, json.dumps({"language": "en", "timestamp": str(int(time.time()*1000))}))}
            r = requests.post(BASE + "/app/account/getAccountInfo", json=body, headers=headers(), timeout=30)
            SESSION["accountId"] = r.json()["result"]["dataId"]
    obj = dict(obj)
    obj.setdefault("language", "en")
    obj.setdefault("timestamp", str(int(time.time() * 1000)))
    if not path.endswith("getAccountInfo"):
        obj.setdefault("accountId", SESSION["accountId"])
    body = {"vs": gcm_enc(BODY_KEY, json.dumps(obj, separators=(",", ":")))}
    with GATE:
        r = requests.post(BASE + path, json=body, headers=headers(), timeout=timeout)
    STATS["req"] += 1
    try:
        return r.status_code, r.json()
    except Exception:
        STATS["up_err"] += 1
        return r.status_code, {"success": False, "errorMsg": r.text[:200]}

def decrypt_result(resp: dict):
    res = resp.get("result")
    if isinstance(res, str) and len(res) > 40:
        try:
            resp["result"] = json.loads(gcm_dec(BODY_KEY, res))
        except Exception:
            pass
    return resp

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % a))

    def _send(self, code, obj, raw=None):
        data = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8" if raw is None else "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/demo"):
            with open(DEMO_HTML, "rb") as f:
                return self._send(200, None, raw=f.read())
        if self.path == "/health":
            return self._send(200, {"status": "ok", "uptime_s": round(time.time()-STATS["t0"],1), "upstream_reqs": STATS["req"]})
        if self.path == "/stats":
            return self._send(200, STATS)
        if self.path == "/v1/models":
            return self._send(200, {"object": "list", "data": [{"id": "searchai-deepsearch", "object": "model"}]})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "invalid json"})

        if self.path == "/v1/search/ai":
            prompt = payload.get("prompt") or payload.get("searchTitle")
            if not prompt:
                return self._send(400, {"error": "prompt required"})
            birth = payload.get("birthDate", ""); loc = payload.get("location", "")
            prof = payload.get("professionalBackground", "")
            code, r = up_post("/search/ai/create/task",
                              {"birthDate": birth, "location": loc, "professionalBackground": prof, "searchTitle": prompt})
            if code != 200 or not r.get("success"):
                return self._send(502, {"error": "upstream create failed", "upstream": r})
            sid = r["result"]["searchId"]
            for _ in range(40):
                time.sleep(4)
                code, q = up_post("/search/ai/query/task", {"searchId": sid})
                res = (q.get("result") or {}) if q.get("success") else {}
                if res.get("status") in ("SUCCESS", "FAIL"):
                    break
            return self._send(200, {"searchId": sid, "status": res.get("status", "TIMEOUT"),
                                    "title": prompt, "answer": res.get("answer", [])})

        if self.path == "/v1/search/ai/task":
            sid = payload.get("searchId")
            if not sid:
                return self._send(400, {"error": "searchId required"})
            code, q = up_post("/search/ai/query/task", {"searchId": sid})
            return self._send(200 if q.get("success") else 502, q)

        if self.path == "/v1/search/ai/history":
            code, q = up_post("/search/ai/get/history/page/list",
                              {"requestPage": payload.get("page", 1), "pageSize": payload.get("pageSize", 30)})
            return self._send(200 if q.get("success") else 502, q)

        if self.path == "/v1/account":
            code, q = up_post("/app/account/getAccountInfo", {})
            return self._send(200 if q.get("success") else 502, q)

        if self.path.startswith("/proxy/"):  # 原生路径透传: /proxy/search/ai/...
            code, q = up_post(self.path[len("/proxy"):], payload)
            return self._send(200, decrypt_result(q))

        self._send(404, {"error": "not found"})

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8918
    print(f"SearchAI demo server on http://0.0.0.0:{port}  (upstream {BASE})")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
