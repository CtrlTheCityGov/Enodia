"""Seed demo data through the running backend (works in mock and real mode).

    python seed.py --reset                 # wipe, then add the "older" reports
    python seed.py --reset --ramp 37.9678,23.7457
    python seed.py --with-duplicate        # also add a sidewalk report at the ramp,
                                           # so the live report shows "already reported"

Run it ~5 minutes before the pitch (sandbox reports auto-advance after 2/10/30 min).
"""
import argparse
import io

import httpx
from PIL import Image, ImageDraw


def fake_photo(label: str, color) -> bytes:
    img = Image.new("RGB", (800, 600), color)
    d = ImageDraw.Draw(img)
    d.rectangle([150, 350, 650, 560], fill=(160, 160, 160))
    d.text((40, 40), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def report(api, lat, lng, note, label, color, address):
    files = {"photo": ("seed.jpg", fake_photo(label, color), "image/jpeg")}
    r = httpx.post(f"{api}/api/report", files=files,
                   data={"lat": lat, "lng": lng, "note": note, "address": address}, timeout=60)
    r.raise_for_status()
    j = r.json()
    print(f"  {j['request']['id']:>12}  {j['ai']['category']:<10} dup_of={j['duplicate_of']}  {address}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--ramp", default="37.9678,23.7457", help="lat,lng of the blocked ramp on Maria's route")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--with-duplicate", action="store_true")
    a = ap.parse_args()
    lat, lng = map(float, a.ramp.split(","))

    print("health:", httpx.get(f"{a.api}/api/health").json())
    if a.reset:
        print("reset:", httpx.post(f"{a.api}/api/admin/reset").json())
    print("seeding:")
    # an overflowing bin ~30 m from the ramp -> operator sees "2 nearby reports, one trip"
    report(a.api, lat + 0.0002, lng + 0.0002, "γεμάτος κάδος σκουπιδιών", "garbage", (60, 90, 60),
           "Seed: κάδος κοντά στη ράμπα")
    # something elsewhere so the list isn't empty
    report(a.api, 37.9712, 23.7395, "λακκούβα στον δρόμο", "pothole", (90, 70, 50), "Seed: λακκούβα")
    # Stoa moment: cracked sidewalk on a street relaid last year -> "possibly under guarantee" in the operator screen
    report(a.api, 37.96603, 23.74212, "σπασμένες πλάκες πεζοδρομίου", "sidewalk", (110, 100, 90),
           "Seed: σπασμένο πεζοδρόμιο (Δείγμα Οδός Α)")
    if a.with_duplicate:
        report(a.api, lat, lng, "μηχανάκι πάνω στη ράμπα", "ramp", (70, 70, 110), "Seed: ράμπα (ήδη αναφερθείσα)")
    print("done. Open /web/citizen.html and /web/operator.html")


if __name__ == "__main__":
    main()
