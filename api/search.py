from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
import json

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query)
        city=q.get('city',['Mirabel'])[0]
        address=q.get('address',['10774 rue du Cerf, Mirabel'])[0]
        radius=float(q.get('radius',['10'])[0])
        body=json.dumps({
            'ok': True,
            'updatedAt': datetime.now(timezone.utc).isoformat(),
            'city': city,
            'address': address,
            'radiusKm': radius,
            'sourcesChecked': 0,
            'count': 0,
            'providers': [],
            'diagnostic': 'API Vercel active. Le collecteur multi-sources doit être ajouté avec des accès de recherche autorisés.'
        }).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,*args):
        pass
