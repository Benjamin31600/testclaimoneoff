import json
import math
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, quote, parse_qs
from urllib.request import Request, urlopen

UA = 'Mozilla/5.0 (compatible; RadarPoupon/1.0)'
OFFICIAL = [
    'https://www.milieufamiliallaurentides.ca/fr/',
    'https://www.milieufamiliallaurentides.ca/fr/trouver-une-place',
]

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.parts = []
        self.href = None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')

    def handle_endtag(self, tag):
        if tag == 'a':
            self.href = None

    def handle_data(self, data):
        text = ' '.join(data.split())
        if text:
            self.parts.append(text)
        if self.href and '/membres/' in self.href:
            self.links.append(self.href)


def get(url, timeout=12):
    request = Request(url, headers={
        'User-Agent': UA,
        'Accept-Language': 'fr-CA,fr;q=0.9',
    })
    return urlopen(request, timeout=timeout).read().decode('utf-8', 'ignore')


def first(pattern, text):
    match = re.search(pattern, text, re.I | re.M)
    return re.sub(r'\s+', ' ', match.group(1)).strip(' |') if match else None


def hav(a, b, c, d):
    radius = 6371
    p = math.pi / 180
    x = (math.sin((c-a)*p/2)**2 +
         math.cos(a*p) * math.cos(c*p) * math.sin((d-b)*p/2)**2)
    return radius * 2 * math.atan2(math.sqrt(x), math.sqrt(1-x))


def geocode(query):
    try:
        raw = get(
            'https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + quote(query),
            10,
        )
        data = json.loads(raw)
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        pass
    return None, None


def member(url):
    html = get(url)
    parser = Parser()
    parser.feed(html)
    text = ' | '.join(parser.parts)

    city = first(r'Ville\s*:\s*([^|]+)', text)
    postal = first(r'Code postal\s*:\s*([A-Z]\d[A-Z]\s?\d[A-Z]\d)', text)
    if not city:
        return None

    infant = first(r'(\d+)\s+places?\s+0-18 mois', text)
    name = (first(r'#\s*([^|]+?)\s+Nombre de place', text)
            or first(r'^([^|]+?)\s+Nombre de place', text))
    phone = first(r'Téléphone\s*:\s*([0-9 .()\-]{10,})', text)
    email = first(r'Courriel\s*:\s*([^ |]+@[^ |]+)', text)
    available = first(r'Place\(s\) disponible\(s\) dès\s*:\s*([^|]+)', text)
    hours = first(r'Heures et jours d[’\']ouverture\s*:\s*([^|]+)', text)

    lat, lon = geocode((postal or '') + ' ' + city + ', Québec, Canada')
    return {
        'name': name or 'Milieu familial',
        'city': city,
        'postalCode': postal,
        'address': (postal + ', ' if postal else '') + city,
        'phone': phone,
        'email': email,
        'subsidized': True,
        'infantPlaces': int(infant or 0),
        'availableFrom': available,
        'hours': hours,
        'source': url,
        'website': url,
        'lat': lat,
        'lon': lon,
    }


def search(lat, lon, radius):
    links = []
    for source in OFFICIAL:
        try:
            parser = Parser()
            parser.feed(get(source))
            for link in parser.links:
                absolute = urljoin(source, link)
                if absolute not in links:
                    links.append(absolute)
        except Exception:
            continue

    results = []
    for url in links:
        try:
            provider = member(url)
            if not provider:
                continue
            if provider['lat'] is not None and provider['lon'] is not None:
                provider['distanceKm'] = round(
                    hav(lat, lon, provider['lat'], provider['lon']), 1
                )
                if provider['distanceKm'] > radius:
                    continue
            else:
                provider['distanceKm'] = None
            results.append(provider)
        except Exception:
            continue

    results.sort(key=lambda x: x.get('distanceKm', 999))
    seen = set()
    clean = []
    for provider in results:
        if provider['source'] not in seen:
            seen.add(provider['source'])
            clean.append(provider)

    return clean


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            query = parse_qs(urlparse(self.path).query)
            lat = float(query.get('lat', ['45.748591'])[0])
            lon = float(query.get('lon', ['-74.066237'])[0])
            radius = float(query.get('radius', ['10'])[0])
            radius = max(0.1, min(radius, 50))
            providers = search(lat, lon, radius)
            payload = {
                'ok': True,
                'updatedAt': datetime.now(timezone.utc).isoformat(),
                'center': {'lat': lat, 'lon': lon},
                'radiusKm': radius,
                'providers': providers,
                'count': len(providers),
            }
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store, max-age=0')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        return
