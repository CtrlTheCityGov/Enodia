"""AthensGov Sandbox client.

Real mode: calls https://athensgov.cityofathens.gr/sandbox with X-API-Key.
Mock mode (no SANDBOX_KEY): same method signatures, fake in-memory data,
so the team can build before the key arrives. Mock data is clearly fictional.

Endpoints used (from the sandbox OpenAPI spec):
  GET  /v1/search?q=                 -> answer {text, sources[{title,url}]}, results[]
  GET  /v1/registry/services?q=      -> 570 real municipal services (static copy)
  GET  /v1/registry/services/{id}    -> documents, cost, where/when, FAQ
  GET  /v1/pois?category=&lat=&lng=&radius_km=
  GET  /v1/requests?lat=&lng=&radius_km=&category=&status=&mine=
  POST /v1/requests                  -> {category,title,address,description,lat,lng,district}
  GET  /v1/requests/{id}
  PATCH /v1/requests/{id}            -> {status, note}
  POST /v1/requests/{id}/upvote
  GET  /v1/me                         (persona via X-Persona header)
"""
from __future__ import annotations

import itertools
import time
from datetime import datetime, timezone

import httpx

from . import config
from .geo import haversine_km

CATEGORIES = [
    "pothole", "streetlight", "garbage", "bulky_waste", "graffiti", "tree", "sidewalk",
    "abandoned_vehicle", "noise", "stray_animals", "water_leak", "other",
]
STATUSES = ["submitted", "received", "in_progress", "resolved", "rejected"]


class SandboxError(Exception):
    pass


class _Cache:
    """Tiny TTL cache so polling screens don't burn the 100 req/min limit."""

    def __init__(self):
        self._d = {}

    def get(self, key):
        v = self._d.get(key)
        if v and v[0] > time.time():
            return v[1]
        return None

    def set(self, key, value, ttl):
        self._d[key] = (time.time() + ttl, value)

    def clear(self):
        self._d.clear()


class Sandbox:
    def __init__(self, base_url=None, key=None, persona=None, mock=None):
        self.base = (base_url or config.SANDBOX_URL).rstrip("/")
        self.key = key if key is not None else config.SANDBOX_KEY
        self.persona = persona or config.PERSONA
        self.mock = config.MOCK if mock is None else mock
        self.cache = _Cache()
        if self.mock:
            self._m = _MockData()
        else:
            self.http = httpx.Client(
                base_url=self.base,
                headers={"X-API-Key": self.key, "X-Persona": self.persona, "Accept-Language": "el"},
                timeout=15,
            )

    # ---------- low level ----------
    def _req(self, method, path, ttl=0, **kw):
        key = (method, path, repr(sorted((kw.get("params") or {}).items())))
        if method == "GET" and ttl:
            hit = self.cache.get(key)
            if hit is not None:
                return hit
        for attempt in range(2):
            r = self.http.request(method, path, **kw)
            if r.status_code == 429 and attempt == 0:
                time.sleep(min(float(r.headers.get("Retry-After", "2")), 5))
                continue
            break
        if r.status_code >= 400:
            try:
                err = r.json().get("error", {})
            except Exception:
                err = {"message": r.text[:200]}
            raise SandboxError(f"{r.status_code} {err.get('code', '')}: {err.get('message', '')}")
        data = r.json() if r.content else {}
        if method == "GET" and ttl:
            self.cache.set(key, data, ttl)
        if method != "GET":
            self.cache.clear()  # writes invalidate cached lists
        return data

    # ---------- public API ----------
    def whoami(self):
        return {"client": "mock"} if self.mock else self._req("GET", "/v1/auth/whoami")

    def me(self):
        return self._m.me() if self.mock else self._req("GET", "/v1/me", ttl=60)

    def search(self, q):
        if self.mock:
            return self._m.search(q)
        return self._req("GET", "/v1/search", ttl=300, params={"q": q})

    def services(self, q, size=5):
        if self.mock:
            return self._m.services(q)
        return self._req("GET", "/v1/registry/services", ttl=300, params={"q": q, "size": size})

    def service(self, service_id):
        if self.mock:
            return self._m.service(service_id)
        return self._req("GET", f"/v1/registry/services/{service_id}", ttl=300)

    def pois(self, category=None, lat=None, lng=None, radius_km=2.0, size=20):
        params = {"size": size}
        if category:
            params["category"] = category
        if lat is not None:
            params.update(lat=lat, lng=lng, radius_km=radius_km)
        if self.mock:
            return self._m.pois(**params)
        return self._req("GET", "/v1/pois", ttl=60, params=params)

    def list_requests(self, lat=None, lng=None, radius_km=None, category=None, status=None, mine=False, size=100):
        params = {"size": size}
        if lat is not None:
            params.update(lat=lat, lng=lng, radius_km=radius_km or 2.0)
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        if mine:
            params["mine"] = "true"
        if self.mock:
            return self._m.list_requests(**params)
        return self._req("GET", "/v1/requests", ttl=3, params=params)

    def create_request(self, category, title, address, description="", lat=None, lng=None, district=None):
        body = {"category": category, "title": title[:200], "address": address, "description": description[:4000]}
        if lat is not None:
            body.update(lat=lat, lng=lng)
        if district:
            body["district"] = district
        if self.mock:
            return self._m.create_request(body)
        return self._req("POST", "/v1/requests", json=body)

    def get_request(self, request_id):
        if self.mock:
            return self._m.get_request(request_id)
        return self._req("GET", f"/v1/requests/{request_id}", ttl=3)

    def update_request(self, request_id, status=None, note=None):
        body = {k: v for k, v in {"status": status, "note": note}.items() if v}
        if self.mock:
            return self._m.update_request(request_id, body)
        return self._req("PATCH", f"/v1/requests/{request_id}", json=body)

    def upvote(self, request_id):
        if self.mock:
            return self._m.upvote(request_id)
        return self._req("POST", f"/v1/requests/{request_id}/upvote")

    def reset(self):
        if self.mock:
            self._m = _MockData()
            return {"ok": True}
        return self._req("POST", "/v1/sandbox/reset")


# ---------------------------------------------------------------- mock data
def _now():
    return datetime.now(timezone.utc).isoformat()


class _MockData:
    """Fictional data shaped like the sandbox responses. Not real places."""

    def __init__(self):
        self._ids = itertools.count(1001)
        self.requests = {}
        self._pois = [
            {"id": "poi-mock-1", "name": "Λέσχη Φιλίας Παγκρατίου (mock)", "category": "friendship_club",
             "lat": 37.9689, "lng": 23.7476, "address": "Mock address 1, Παγκράτι", "open_now": True},
            {"id": "poi-mock-2", "name": "Λέσχη Φιλίας Μετς (mock)", "category": "friendship_club",
             "lat": 37.9655, "lng": 23.7385, "address": "Mock address 2, Μετς", "open_now": True},
            {"id": "poi-mock-3", "name": "Δημοτική Βιβλιοθήκη Παγκρατίου (mock)", "category": "library",
             "lat": 37.9702, "lng": 23.7440, "address": "Mock address 3, Παγκράτι", "open_now": True},
        ]

    def me(self):
        return {"persona": "p2", "name": "Μαρία (mock)", "area": "pagkrati",
                "profile": "Συνταξιούχος στο Παγκράτι, ΚΑΠΗ, «Βοήθεια στο σπίτι»"}

    def search(self, q):
        return {
            "query": q, "source": "mock", "fallback_reason": None,
            "answer": {
                "text": ("(mock) Για τη βεβαίωση μόνιμης κατοικίας χρειάζεστε αστυνομική ταυτότητα "
                         "και αποδεικτικό διεύθυνσης. Μπορείτε να κάνετε αίτηση ηλεκτρονικά ή στο ΚΕΠ."),
                "sources": [{"title": "Βεβαίωση μόνιμης κατοικίας (mock)", "url": "https://www.cityofathens.gr/"}],
            },
            "results": [],
        }

    def services(self, q):
        return {"total": 1, "page": 1, "size": 5, "items": [
            {"id": "svc-mock-1", "title": "Βεβαίωση μόνιμης κατοικίας (mock)", "cost_eur": 0,
             "online_url": "https://www.cityofathens.gr/", "score": 1.0}]}

    def service(self, sid):
        return {"id": sid, "title": "Βεβαίωση μόνιμης κατοικίας (mock)",
                "documents": ["Αστυνομική ταυτότητα", "Αποδεικτικό διεύθυνσης"], "cost_eur": 0,
                "online_url": "https://www.cityofathens.gr/"}

    def pois(self, size=20, category=None, lat=None, lng=None, radius_km=2.0):
        items = [dict(p) for p in self._pois if not category or p["category"] == category]
        if lat is not None:
            for p in items:
                p["distance_km"] = round(haversine_km(lat, lng, p["lat"], p["lng"]), 3)
            items = sorted([p for p in items if p["distance_km"] <= radius_km], key=lambda p: p["distance_km"])
        return {"total": len(items), "page": 1, "size": size, "items": items[:size]}

    def _view(self, r, lat=None, lng=None):
        r = dict(r)
        r["created_by_you"] = True
        if lat is not None and r.get("lat") is not None:
            r["distance_km"] = round(haversine_km(lat, lng, r["lat"], r["lng"]), 3)
        return r

    def list_requests(self, size=100, lat=None, lng=None, radius_km=2.0, category=None, status=None, mine=None):
        out = []
        for r in self.requests.values():
            if category and r["category"] != category:
                continue
            if status and r["status"] != status:
                continue
            v = self._view(r, lat, lng)
            if lat is not None and v.get("distance_km", 1e9) > radius_km:
                continue
            out.append(v)
        out.sort(key=lambda r: r["created_at"], reverse=True)
        return {"total": len(out), "page": 1, "size": size, "items": out[:size]}

    def create_request(self, body):
        if body["category"] not in CATEGORIES:
            raise SandboxError("422 validation: unknown category")
        rid = f"REQ-{next(self._ids)}"
        now = _now()
        r = {"id": rid, "category_name": body["category"], "district": body.get("district"),
             "status": "submitted", "created_at": now, "updated_at": now, "upvotes": 0,
             "history": [{"status": "submitted", "at": now, "note": "Η αναφορά καταχωρήθηκε"}], **body}
        self.requests[rid] = r
        return self._view(r)

    def get_request(self, rid):
        if rid not in self.requests:
            raise SandboxError("404 not_found: request not found")
        return self._view(self.requests[rid])

    def update_request(self, rid, body):
        r = self.requests.get(rid)
        if not r:
            raise SandboxError("404 not_found: request not found")
        now = _now()
        if "status" in body:
            if body["status"] not in STATUSES:
                raise SandboxError("422 validation: bad status")
            r["status"] = body["status"]
        r["updated_at"] = now
        r["history"].append({"status": r["status"], "at": now, "note": body.get("note")})
        return self._view(r)

    def upvote(self, rid):
        r = self.requests.get(rid)
        if not r:
            raise SandboxError("404 not_found: request not found")
        r["upvotes"] += 1
        return self._view(r)
