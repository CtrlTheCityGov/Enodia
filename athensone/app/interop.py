"""Open standards out: other systems can read our data without knowing our API.

  Open311 GeoReport v2   /open311/v2/services.json, /requests.json, /requests/{id}.json
                         the format FixMyStreet and many city 311 systems speak (read-only here)
  NGSI-LD (FIWARE)       /ngsi-ld/v1/entities?type=ServiceRequest|WorksRecord|AirQualityObserved
                         for a FIWARE Context Broker (Orion-LD); entity shapes follow Smart Data Models
                         naming where one exists (AirQualityObserved), our own context otherwise
  DCAT-AP (JSON-LD)      /dcat/catalog.jsonld  — so opendata.cityofathens.gr (CKAN) can harvest our datasets

Only public, non-personal fields are exposed: no photos of people, no citizen identity.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import works

OPEN = {"submitted", "received", "in_progress"}
SERVICE_NAMES_EL = {
    "pothole": "Λακκούβα", "streetlight": "Φωτισμός", "garbage": "Απορρίμματα", "bulky_waste": "Ογκώδη",
    "graffiti": "Γκράφιτι", "tree": "Δέντρα / πράσινο", "sidewalk": "Πεζοδρόμιο / ράμπα",
    "abandoned_vehicle": "Εγκαταλελειμμένο όχημα", "noise": "Θόρυβος", "stray_animals": "Αδέσποτα",
    "water_leak": "Διαρροή νερού", "other": "Άλλο",
}
CTX = ["https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
       {"athensone": "https://github.com/apps4athens/athensone#"}]


# ------------------------------------------------------------------ Open311 GeoReport v2
def o311_services(categories) -> list[dict]:
    return [{"service_code": c, "service_name": SERVICE_NAMES_EL.get(c, c), "description": SERVICE_NAMES_EL.get(c, c),
             "metadata": False, "type": "realtime", "keywords": "", "group": "AthensOne"} for c in categories]


def o311_request(r: dict, base_url: str = "") -> dict:
    hist = r.get("history") or []
    local = r.get("local") or {}
    cat = local.get("category") or r.get("category") or r.get("category_name")
    return {
        "service_request_id": r["id"],
        "status": "open" if r.get("status") in OPEN else "closed",
        "status_notes": (hist[-1].get("note") if hist else None),
        "service_name": SERVICE_NAMES_EL.get(cat, cat),
        "service_code": cat,
        "description": r.get("title"),
        "agency_responsible": "Δήμος Αθηναίων",
        "requested_datetime": hist[0].get("at") if hist else r.get("created_at"),
        "updated_datetime": hist[-1].get("at") if hist else r.get("updated_at"),
        "address": r.get("address"),
        "lat": r.get("lat"),
        "long": r.get("lng"),
        "media_url": f"{base_url}{local['photo_url']}" if local.get("photo_url") else None,  # faces already blurred
    }


# ------------------------------------------------------------------ NGSI-LD
def _prop(v):
    return {"type": "Property", "value": v}


def _geo(lat, lng):
    return {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [lng, lat]}}


def ngsi_service_request(r: dict) -> dict:
    o = o311_request(r)
    e = {"id": f"urn:ngsi-ld:ServiceRequest:athensone:{r['id']}", "type": "ServiceRequest",
         "status": _prop(o["status"]), "service_code": _prop(o["service_code"]),
         "service_name": _prop(o["service_name"]), "description": _prop(o["description"]),
         "requested_datetime": _prop(o["requested_datetime"]), "updated_datetime": _prop(o["updated_datetime"]),
         "address": _prop(o["address"]), "@context": CTX}
    if r.get("lat") is not None:
        e["location"] = _geo(r["lat"], r["lng"])
    if r.get("district_name"):
        e["areaServed"] = _prop(r["district_name"])
    return e


def ngsi_works(c: dict) -> dict:
    v = lambda f: (c.get(f) or {}).get("value")
    clock = c["clock"]
    return {"id": f"urn:ngsi-ld:WorksRecord:athensone:{c['id']}", "type": "WorksRecord",
            "worksType": _prop(c.get("works_type")), "street": _prop(v("street")), "contractor": _prop(v("contractor")),
            "amountPaidEur": _prop(v("amount_paid_eur")), "completionDate": _prop(v("completion_date")),
            "guaranteeUntil": _prop(clock["until"]), "guaranteeStatus": _prop(clock["status"]),
            "tier": _prop(clock["tier"]),
            "sourceAda": _prop(((c.get("completion_date") or {}).get("source") or {}).get("ada")),
            "dataSource": _prop(works.meta()["source"]),
            "location": {"type": "GeoProperty", "value": c["geometry"]}, "@context": CTX}


def ngsi_air(s: dict) -> dict:
    e = {"id": f"urn:ngsi-ld:AirQualityObserved:athens:{s['station_id']}", "type": "AirQualityObserved",
         "name": _prop(s.get("name")), "dateObserved": _prop(s.get("time")), "location": _geo(s["lat"], s["lng"]),
         "dataProvider": _prop("AthensGov opendata.cityofathens.gr (CC BY 4.0)"),
         "@context": CTX + ["https://smart-data-models.github.io/dataModel.Environment/context.jsonld"]}
    for k, name in (("aqi", "airQualityIndex"), ("pm25", "pm25"), ("pm10", "pm10"), ("no2", "no2"),
                    ("temp_c", "temperature"), ("humidity", "relativeHumidity")):
        if s.get(k) is not None:
            e[name] = _prop(s[k])
    return e


# ------------------------------------------------------------------ DCAT-AP catalog
def dcat_catalog(base: str) -> dict:
    now = datetime.now(timezone.utc).date().isoformat()
    lic = "https://creativecommons.org/licenses/by/4.0/"

    def ds(ident, title, desc, url, fmt, theme):
        return {"@type": "dcat:Dataset", "dct:identifier": ident, "dct:title": {"@language": "el", "@value": title},
                "dct:description": desc, "dct:publisher": {"foaf:name": "Δήμος Αθηναίων (Enodia)"},
                "dct:modified": now, "dct:license": lic, "dcat:theme": theme,
                "dct:spatial": "https://www.geonames.org/264371/athens.html",
                "dcat:distribution": [{"@type": "dcat:Distribution", "dcat:accessURL": url, "dct:format": fmt,
                                       "dct:license": lic}]}

    gov = "http://publications.europa.eu/resource/authority/data-theme/GOVE"
    env = "http://publications.europa.eu/resource/authority/data-theme/ENVI"
    tran = "http://publications.europa.eu/resource/authority/data-theme/TRAN"
    return {
        "@context": {"dcat": "http://www.w3.org/ns/dcat#", "dct": "http://purl.org/dc/terms/",
                     "foaf": "http://xmlns.com/foaf/0.1/"},
        "@type": "dcat:Catalog", "dct:title": "Enodia open data", "dct:language": "el",
        "dct:license": lic, "dct:modified": now,
        "dcat:dataset": [
            ds("athensone-service-requests", "Αναφορές πολιτών (Open311)",
               "Citizen reports, anonymised, Open311 GeoReport v2", f"{base}/open311/v2/requests.json", "JSON", gov),
            ds("athensone-works-guarantees", "Δημόσια έργα και εγγυήσεις (Stoa)",
               "Works records with guarantee clock and source ΑΔΑ", f"{base}/api/works/geojson", "GeoJSON", gov),
            ds("athensone-walking-environment", "Σκιά, στάσεις και δρόμοι με κίνηση",
               "Environment layer used for route ranking (from OpenStreetMap, ODbL)", f"{base}/api/env/geojson",
               "GeoJSON", env),
            ds("athensone-equity", "Ισότητα εξυπηρέτησης ανά Δημοτική Κοινότητα",
               "Reports and response times per district", f"{base}/api/equity", "JSON", gov),
            ds("athensone-ngsi-ld", "NGSI-LD entities", "ServiceRequest, WorksRecord, AirQualityObserved",
               f"{base}/ngsi-ld/v1/entities?type=ServiceRequest", "JSON-LD", tran),
        ],
    }
