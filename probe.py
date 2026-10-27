#!/usr/bin/env python3
# SearchAI (com.xjprhinox.searchai) 上游协议 PoC — 从 jadx 还原
# 协议: POST JSON {"vs": base64(nonce12||AES-GCM-CT(json, key))} + headers {n, overSeaFlag, va, sea, timeZone}
import base64, json, os, time, uuid, requests

BASE = "https://appss.airy365.com"
BODY_KEY = b"FkdCTuwMcrHyO2LK"   # Configuration.BODY_KEY
HEADER_KEY = b"GQmj8ePOKHn0VN2c" # Configuration.HEADER_KEY
APP_NAME = "10175611458440310241"

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    def gcm(key, plaintext):
        nonce = os.urandom(12)
        ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ct).decode()
except ImportError:
    from Crypto.Cipher import AES
    def gcm(key, plaintext):
        nonce = os.urandom(12)
        c = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=16)
        ct, tag = c.encrypt_and_digest(plaintext.encode())
        return base64.b64encode(nonce + ct + tag).decode()

UUID = str(uuid.uuid4()).replace("-", "") + str(int(time.time()*1000))
ACCOUNT = {"accountId": "", "token": ""}

def enc_body(obj):
    obj = dict(obj)
    obj.setdefault("language", "en")
    obj.setdefault("accountId", ACCOUNT["accountId"])
    obj.setdefault("timestamp", str(int(time.time()*1000)))
    return {"vs": gcm(BODY_KEY, json.dumps(obj, separators=(",", ":")))}

def enc_header():
    h = {"deviceType": "ANDROID", "version": "1.0.1", "deviceModel": "Pixel 6",
         "uuid": UUID, "brand": "Google", "channel": "google", "appName": APP_NAME,
         "lang": "en", "region": "US", "androidId": UUID[:16], "systemVersion": "13"}
    return {"n": APP_NAME, "overSeaFlag": "YES", "sea": "YES",
            "va": gcm(HEADER_KEY, json.dumps(h, separators=(",", ":"))),
            "timeZone": "Asia/Shanghai", "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "okhttp/4.12.0"}

def post(path, obj, timeout=30):
    r = requests.post(BASE + path, json=enc_body(obj), headers=enc_header(), timeout=timeout)
    try: return r.status_code, r.json()
    except Exception: return r.status_code, r.text[:300]

def x(resp):
    """解 response.result (vs 加密可选, XResult格式)"""
    if not isinstance(resp, dict): return resp
    if resp.get("result") and isinstance(resp["result"], str) and len(resp["result"]) > 40:
        try:
            raw = base64.b64decode(resp["result"])
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            pt = AESGCM(BODY_KEY).decrypt(raw[:12], raw[12:], None)
            resp["_decrypted"] = json.loads(pt)
        except Exception as e:
            resp["_decrypt_err"] = str(e)
    return resp

if __name__ == "__main__":
    print("== 1. getAccountInfo (未登录) ==")
    print(*post("/app/account/getAccountInfo", {}), sep="\n")
    print("\n== 2. quickLogin (伪造 token) ==")
    print(*post("/app/account/quickLogin", {"token": "fake-token-123"}), sep="\n")
    print("\n== 3. /search/ai/create/task ==")
    print(*post("/search/ai/create/task", {"birthDate": "01-01-1990", "location": "NYC",
        "professionalBackground": "engineer", "searchTitle": "Who is John Doe?"}), sep="\n")
    print("\n== 4. /search/ai/get/history/page/list ==")
    print(*post("/search/ai/get/history/page/list", {"requestPage": 1, "pageSize": 30}), sep="\n")
    print("\n== 5. 错误 key 对照 (错误 BODY_KEY) ==")
    import copy
    bad = enc_body({"language": "en", "timestamp": str(int(time.time()*1000))})
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12); ct = AESGCM(b"AAAAAAAAAAAAAAAA").encrypt(nonce, b"{}", None)
    r = requests.post(BASE + "/search/ai/create/task", json={"vs": base64.b64encode(nonce+ct).decode()},
                      headers=enc_header(), timeout=20)
    print(r.status_code, r.text[:200])
