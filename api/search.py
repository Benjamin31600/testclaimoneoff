from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote, urljoin
from datetime import datetime, timezone
import json, math, re, urllib.request

OFFICIAL = "https://www.milieufamiliallaurentides.ca"
READER = "https://r.jina.ai/http://www.milieufamiliallaurentides.ca"
SEARX = ["https://priv.au", "https://na.priv.au"]


def fetch(url, timeout=18):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; RadarPoupon/5.0; +https://vercel.com)"
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def fetch_json(url, timeout=10):
    return json.loads(fetch(url, timeout))


def reader(path, timeout=20):
    # Jina Reader is used only as a free public HTML-to-text bridge. It does not require a key.
    target = OFFICIAL + path
    return fetch("https://r.jina.ai/http://" + target.replace("https://", ""), timeout)


def distance(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c-a)*p/2)**2 + math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2
    return 6371 * 2 * math.atan2(math.sqrt(x), math.sqrt(max(0, 1-x)))


def geocode(address):
    try:
        d = fetch_json("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=" + quote(address), 10)
        if d:
            return float(d[0]["lat"]), float(d[0]["lon"])
    except Exception:
        pass
    return None


def classify(text):
    t = text.lower()
    infant = any(x in t for x in ["poupon", "0-18 mois", "0–18 mois", "0 à 18 mois"])
    m = re.search(r"(\d+)\s+places?\s+0[-–]18\s+mois", t, re.I)
    places = int(m.group(1)) if m else 0
    explicit = any(x in t for x in ["place disponible", "disponible immédiatement", "places disponibles"])
    intent = any(x in t for x in ["se libère", "va se libérer", "à partir de", "prend un poupon"])
    sub = any(x in t for x in ["subventionné", "subventionnée", "contribution réduite", "9,65", "9.65", "8,85", "8.85"])
    if places > 0:
        status = "Place poupon affichée — à confirmer immédiatement"
    elif explicit:
        status = "Disponibilité explicite"
    elif intent:
        status = "Intention / disponibilité probable"
    elif infant:
        status = "Milieu poupon — disponibilité à confirmer"
    else:
        status = "Information pertinente"
    return status, infant, sub, places


def member_urls_from_text(text):
    urls = set()
    # Jina returns markdown links such as [name](https://.../fr/membres/name)
    for m in re.finditer(r"https?://[^)\\s]+/fr/membres/[^)\\s#?]+", text, re.I):
        urls.add(m.group(0).rstrip(".,"))
    for m in re.finditer(r"\]\((/fr/membres/[^)\\s#?]+)", text, re.I):
        urls.add(urljoin(OFFICIAL, m.group(1)))
    return urls


def official_urls():
    urls = set()
    errors = []
    # Fetch through the public Reader bridge. It is much more tolerant of server-side blocking
    # than urllib fetching the site's HTML directly from a Vercel Function.
    for path in ["/fr", "/fr/trouver-une-place"]:
        try:
            text = reader(path)
            urls.update(member_urls_from_text(text))
        except Exception as e:
            errors.append("reader:" + type(e).__name__)
    return sorted(urls), errors


def parse_member(u, city, lat, lon, radius):
    try:
        # Reader returns a clean representation of the individual public fiche.
        target = "https://r.jina.ai/http://" + u.replace("https://", "")
        text = fetch(target, 18)
        status, infant, sub, places = classify(text)
        if not infant or places <= 0:
            return None

        vm = re.search(r"Ville\s*:\s*([^\n]+)", text, re.I)
        pm = re.search(r"Code postal\s*:\s*([A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d)", text, re.I)
        city2 = vm.group(1).strip() if vm else city
        postal = pm.group(1).upper().replace(" ", "") if pm else ""
        tm = re.search(r"Téléphone\s*:\s*([+\d ()\-.]+)", text, re.I)
        em = re.search(r"Courriel\s*:\s*([^\s]+@[^\s]+)", text, re.I)
        dm = re.search(r"Place\(s\) disponible\(s\) dès\s*:\s*([^\n]+)", text, re.I)
        coords = geocode((postal + " Canada") if postal else city2 + ", Québec, Canada")
        dist = round(distance(lat, lon, *coords), 1) if coords else None
        if dist is not None and dist > radius:
            return None
        nm = re.search(r"^#\s+(.+)$", text, re.M)
        name = nm.group(1).strip() if nm else "Milieu familial"
        return {
            "name": name,
            "city": city2,
            "address": "Adresse civique non publiée sur la fiche publique",
            "postalCode": postal,
            "phone": tm.group(1).strip() if tm else "",
            "email": em.group(1).strip() if em else "",
            "infantPlaces": places,
            "status": status,
            "subsidized": True,
            "distanceKm": dist,
            "source": u,
            "sourceEngine": "Guichet unique Laurentides",
            "published": dm.group(1).strip() if dm else None,
            "snippet": text[:1800],
            "score": 100
        }
    except Exception:
        return None


def official_results(city, lat, lon, radius):
    out, errors = [], []
    urls, discover_errors = official_urls()
    errors.extend(discover_errors)
    if not urls:
        errors.append("official:no-member-pages-discovered")
    for u in urls[:800]:
        x = parse_member(u, city, lat, lon, radius)
        if x:
            out.append(x)
    return out, errors


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        city = q.get("city", ["Mirabel"])[0].strip() or "Mirabel"
        address = q.get("address", ["10774 rue du Cerf, Mirabel"])[0].strip()
        radius = max(1, min(100, float(q.get("radius", ["10"])[0])))
        age = int(q.get("age", ["14"])[0])
        lat = float(q.get("lat", ["45.748591"])[0])
        lon = float(q.get("lon", ["-74.066237"])[0])
        gp = geocode(address)
        if gp:
            lat, lon = gp

        providers, errors = official_results(city, lat, lon, radius)
        # Public SearXNG is optional and intentionally not allowed to turn a successful
        # official search into an error. We do not report its HTTP failures to the user.
        body = json.dumps({
            "ok": True,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "city": city,
            "address": address,
            "radiusKm": radius,
            "ageMonths": age,
            "sourcesChecked": 1 if providers or not any(e.startswith("reader:") for e in errors) else 0,
            "searchQueries": 2,
            "count": len(providers),
            "providers": sorted(providers, key=lambda x: (x.get("distanceKm") is None, x.get("distanceKm") or 999))[:100],
            "diagnostic": "Recherche officielle en direct via passerelle publique." if providers else "Le site officiel a été interrogé mais aucune fiche poupon dans le rayon n'a pu être récupérée. Vérification de la passerelle officielle nécessaire.",
            "sourceErrors": errors[:20]
        }, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
