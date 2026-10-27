#!/usr/bin/env python3
"""SearchAI demo server 压测 — 基线/并发/错误路径"""
import json, statistics, time, concurrent.futures, requests

BASE = "http://127.0.0.1:8918"
S = requests.Session()
results = []

def bench(name, fn, n=10):
    ts = []
    ok = 0
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            code = fn()
            if 200 <= code < 300: ok += 1
        except Exception:
            code = -1
        ts.append((time.perf_counter() - t0) * 1000)
    p = sorted(ts)
    results.append((name, ok, n, statistics.median(p), p[int(len(p)*0.95)-1 if n>1 else 0]))
    print(f"{name:36s} {ok}/{n}  median={results[-1][3]:7.1f}ms  p95={results[-1][4]:7.1f}ms")

def h(): return S.get(BASE+"/health").status_code
def models(): return S.get(BASE+"/v1/models").status_code
def acct(): return S.post(BASE+"/v1/account").status_code
def hist(): return S.post(BASE+"/v1/search/ai/history", json={"page":1}).status_code
def bad_json():
    r = S.post(BASE+"/v1/search/ai", data="notjson", headers={"Content-Type":"application/json"})
    return r.status_code if r.status_code == 400 else -1
def no_prompt():
    r = S.post(BASE+"/v1/search/ai", json={})
    return r.status_code if r.status_code == 400 else -1
def bad_task():
    r = S.post(BASE+"/v1/search/ai/task", json={"searchId":"99999999999999999999"})
    return r.status_code  # 502 expected = 上游错误正确映射
def nf(): return S.get(BASE+"/nope").status_code if S.get(BASE+"/nope").status_code==404 else -1

print("== 基线 ==")
bench("GET /health", h, 20)
bench("GET /v1/models", models, 10)
bench("POST /v1/account (上游)", acct, 5)
bench("POST /v1/search/ai/history (上游)", hist, 5)

print("== 错误路径 ==")
bench("400 invalid json", bad_json, 3)
bench("400 no prompt", no_prompt, 3)
bench("502 bad searchId (上游映射)", bad_task, 3)
bench("404 not found", nf, 3)

print("== 端到端 (真实搜索, 并发x3) ==")
def e2e(i):
    r = S.post(BASE+"/v1/search/ai", json={"prompt": f"What is the career history of person {i}?"}, timeout=300)
    j = r.json()
    return r.status_code if (r.status_code==200 and j.get("status")=="SUCCESS" and j.get("answer")) else -1
t0=time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(3) as ex:
    codes = list(ex.map(e2e, range(3)))
el = time.perf_counter()-t0
print(f"e2e search x3 并发: {codes}  wall={el:.1f}s  全部SUCCESS={'YES' if all(c==200 for c in codes) else 'NO'}")

print("== 并发 x10 health ==")
with concurrent.futures.ThreadPoolExecutor(10) as ex:
    cs = list(ex.map(lambda _: h(), range(10)))
print("health x10:", cs)
