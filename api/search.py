import json, math, re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, quote, parse_qs
from urllib.request import Request, urlopen

UA='Mozilla/5.0 (compatible; RadarPoupon/2.0)'
SOURCES=['https://www.milieufamiliallaurentides.ca/fr/','https://www.milieufamiliallaurentides.ca/fr/trouver-une-place']
class Parser(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]; self.parts=[]; self.href=None; self.anchor=[]
    def handle_starttag(self,t,a):
        if t=='a': self.href=dict(a).get('href'); self.anchor=[]
    def handle_endtag(self,t):
        if t=='a':
            if self.href: self.links.append((self.href,' '.join(self.anchor)))
            self.href=None; self.anchor=[]
    def handle_data(self,d):
        s=' '.join(d.split())
        if s: self.parts.append(s); self.anchor.append(s)

def get(url,timeout=15):
    r=Request(url,headers={'User-Agent':UA,'Accept-Language':'fr-CA,fr;q=0.9'}); return urlopen(r,timeout=timeout).read().decode('utf-8','ignore')
def first(p,t):
    m=re.search(p,t,re.I|re.M); return re.sub(r'\s+',' ',m.group(1)).strip(' |') if m else None
def hav(a,b,c,d):
    p=math.pi/180; x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2; return 6371*2*math.atan2(math.sqrt(x),math.sqrt(1-x))
def geocode(q):
    try:
        d=json.loads(get('https://nominatim.openstreetmap.org/search?format=json&limit=1&q='+quote(q),10)); return (float(d[0]['lat']),float(d[0]['lon'])) if d else (None,None)
    except: return (None,None)

def member(url,anchor=''):
    t=' | '.join((p:=Parser()).parts) if False else None
    html=get(url); p=Parser(); p.feed(html); t=' | '.join(p.parts)
    city=first(r'Ville\s*:\s*([^|]+)',t); postal=first(r'Code postal\s*:\s*([A-Z]\d[A-Z]\s?\d[A-Z]\d)',t)
    infant=first(r'(\d+)\s+places?\s+0-18 mois',t) or first(r'(\d+)\s+places?\s+0\s*[-–]\s*18 mois',anchor)
    # Only accept actual poupon availability; do not invent a place.
    if not infant or int(infant)==0: return None
    name=first(r'#\s*([^|]+?)\s+Nombre de place',t) or first(r'^([^|]+?)\s+Nombre de place',t) or anchor.split(' Saint-')[0].strip()
    phone=first(r'Téléphone\s*:\s*([0-9 .()\-]{10,})',t); email=first(r'Courriel\s*:\s*([^ |]+@[^ |]+)',t)
    avail=first(r'Place\(s\) disponible\(s\) dès\s*:\s*([^|]+)',t); hours=first(r'Heures et jours d[’\']ouverture\s*:\s*([^|]+)',t)
    lat,lon=geocode(((postal or '')+' '+(city or '')+', Québec, Canada').strip())
    return {'name':name or 'Milieu familial','city':city,'postalCode':postal,'address':((postal+', ') if postal else '')+(city or ''),'phone':phone,'email':email,'subsidized':True,'infantPlaces':int(infant),'availableFrom':avail,'hours':hours,'source':url,'website':url,'lat':lat,'lon':lon}

def search(lat,lon,radius):
    candidates=[]
    for source in SOURCES:
        try:
            p=Parser(); p.feed(get(source))
            for href,anchor in p.links:
                u=urljoin(source,href)
                # Keep only likely provider/detail links, not navigation.
                low=(u+' '+anchor).lower()
                if u.startswith('http') and u not in [x[0] for x in candidates] and ('membre' in low or 'poupon' in low or 'place' in low): candidates.append((u,anchor))
        except: pass
    out=[]
    for u,a in candidates:
        try:
            x=member(u,a)
            if not x: continue
            if x['lat'] is not None:
                x['distanceKm']=round(hav(lat,lon,x['lat'],x['lon']),1)
                if x['distanceKm']>radius: continue
            else: x['distanceKm']=None
            out.append(x)
        except: pass
    out.sort(key=lambda x:x.get('distanceKm',999)); seen=set(); final=[]
    for x in out:
        key=(x['name'],x.get('city'),x['source'])
        if key not in seen: seen.add(key); final.append(x)
    return final

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            q=parse_qs(urlparse(self.path).query); lat=float(q.get('lat',['45.748591'])[0]); lon=float(q.get('lon',['-74.066237'])[0]); radius=max(.1,min(float(q.get('radius',['10'])[0]),50))
            providers=search(lat,lon,radius); body=json.dumps({'ok':True,'updatedAt':datetime.now(timezone.utc).isoformat(),'center':{'lat':lat,'lon':lon},'radiusKm':radius,'providers':providers,'count':len(providers)},ensure_ascii=False).encode()
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        except Exception as e:
            body=json.dumps({'ok':False,'error':str(e)},ensure_ascii=False).encode(); self.send_response(500); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass
