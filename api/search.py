from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote, urljoin
from datetime import datetime, timezone
from html.parser import HTMLParser
import json, math, re, urllib.request

OFFICIAL = "https://www.milieufamiliallaurentides.ca"
SEARX = ["https://priv.au", "https://na.priv.au"]

QUERIES = [
    '"place poupon" {city}',
    '"0-18 mois" "milieu familial" {city}',
    '"place disponible" garderie poupon {city}',
    '"milieu familial subventionné" {city}',
    'garderie poupon {city} annonce',
    'site:reddit.com garderie poupon {city}',
    'site:facebook.com garderie poupon {city}',
    'site:mamswitch.com poupon {city}',
    'site:lespac.com garderie {city}'
]

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.text=[]; self.href=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=='a' and a.get('href'):
            self.href=a['href']; self.links.append((a['href'],''))
    def handle_data(self, data):
        s=' '.join(data.split())
        if s: self.text.append(s)
        if self.href and self.links:
            h,t=self.links[-1]
            self.links[-1]=(h,(t+' '+s).strip())
    def handle_endtag(self, tag):
        if tag=='a': self.href=None

def fetch(url, timeout=10):
    req=urllib.request.Request(url, headers={
        'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1 RadarPoupon/2.0'
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8','ignore')

def fetch_json(url, timeout=8):
    return json.loads(fetch(url,timeout))

def distance(a,b,c,d):
    p=math.pi/180
    x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2
    return 6371*2*math.atan2(math.sqrt(x),math.sqrt(max(0,1-x)))

def geocode(address):
    try:
        d=fetch_json('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q='+quote(address),8)
        if d: return float(d[0]['lat']),float(d[0]['lon'])
    except Exception: pass
    return None

def classify(text):
    t=text.lower()
    infant=any(x in t for x in ['poupon','0-18 mois','0 à 18 mois','0–18 mois','18 mois'])
    explicit=any(x in t for x in ['place disponible','disponible immédiatement','une place poupon'])
    intent=any(x in t for x in ['se libère','va se libérer','à partir de','prend un poupon','place pour septembre','place pour octobre'])
    subsidized=any(x in t for x in ['subventionné','subventionnée','contribution réduite','9,65','8,85','9.65','8.85'])
    if explicit: status='Disponibilité explicite'
    elif intent: status='Intention / disponibilité probable'
    elif infant: status='Milieu poupon pertinent — disponibilité à confirmer'
    else: status='Information pertinente — disponibilité inconnue'
    return status, infant, subsidized

def official_results(city, origin_lat, origin_lon, radius):
    out=[]; errors=[]
    try:
        html=fetch(OFFICIAL+'/fr/',12)
        p=Parser(); p.feed(html)
        links=[]; seen=set()
        for href,label in p.links:
            u=urljoin(OFFICIAL+'/',href)
            if '/fr/membres/' in u and u not in seen:
                seen.add(u); links.append(u)
        # The home page can contain the currently advertised places. Crawl those member pages.
        for u in links[:80]:
            try:
                h=fetch(u,10); q=Parser(); q.feed(h); text=' '.join(q.text)
                status,infant,sub=classify(text)
                if not infant: continue
                m=re.search(r'Nombre de place\(s\).*?(\d+) place[s]? 0-18 mois',text,re.I)
                infant_places=int(m.group(1)) if m else 1
                vm=re.search(r'Ville\s*:\s*([^\n]+?)\s+Code postal\s*:\s*([A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d)',text,re.I)
                city2=vm.group(1).strip() if vm else city
                postal=vm.group(2).upper().replace(' ','') if vm else ''
                tm=re.search(r'Téléphone\s*:\s*([+\d ()\-\.]+)',text,re.I)
                em=re.search(r'Courriel\s*:\s*([^\s]+@[^\s]+)',text,re.I)
                dm=re.search(r'Place\(s\) disponible\(s\) dès\s*:\s*([^\n]+)',text,re.I)
                coords=geocode((postal+' Canada') if postal else (city2+', Québec, Canada'))
                dist=round(distance(origin_lat,origin_lon,*coords),1) if coords else None
                if dist is not None and dist>radius: continue
                title=(q.text[0] if q.text else 'Milieu familial')
                # Prefer the page H1 as the person's name.
                hm=re.search(r'<h1[^>]*>\s*([^<]+)',h,re.I)
                if hm: title=' '.join(hm.group(1).split())
                out.append({'name':title,'city':city2,'address':'Adresse civique non publiée sur la fiche','postalCode':postal,'phone':tm.group(1).strip() if tm else '','email':em.group(1).strip() if em else '','infantPlaces':infant_places,'status':status,'subsidized':True if sub else True,'distanceKm':dist,'source':u,'sourceEngine':'Guichet unique Laurentides','published':dm.group(1).strip() if dm else None,'snippet':text[:900],'score':100 if infant_places>0 else 70})
            except Exception as e: errors.append('official:'+type(e).__name__)
    except Exception as e: errors.append('official-home:'+type(e).__name__)
    return out,errors

def searx_html(query, instance):
    # HTML is the public-compatible fallback. JSON is often disabled by public instances (403).
    html=fetch(instance+'/search?q='+quote(query)+'&language=fr-FR&categories=general',10)
    p=Parser(); p.feed(html); out=[]
    for href,label in p.links:
        if href.startswith('http') and label and not any(x in href for x in ['/search','priv.au']):
            out.append((label,href))
    return out

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query)
        city=q.get('city',['Mirabel'])[0].strip() or 'Mirabel'
        address=q.get('address',['10774 rue du Cerf, Mirabel'])[0].strip()
        radius=max(1,min(100,float(q.get('radius',['10'])[0])))
        age=int(q.get('age',['14'])[0])
        lat=float(q.get('lat',['45.748591'])[0]); lon=float(q.get('lon',['-74.066237'])[0])
        if address:
            gp=geocode(address)
            if gp: lat,lon=gp
        providers=[]; errors=[]; sources=[]

        # 1) Official Laurentides source: this is the authoritative source for recognized/subsidized family homes.
        official,err=official_results(city,lat,lon,radius); providers.extend(official); sources.append('Guichet unique Laurentides')
        errors.extend(err)

        # 2) Public Web discovery through SearXNG HTML. Do not require JSON; public instances commonly disable it.
        for instance in SEARX:
            for template in QUERIES:
                try:
                    rows=searx_html(template.format(city=city),instance)
                    if rows: sources.append(instance)
                    for title,href in rows[:12]:
                        status,infant,sub=classify(title)
                        if not infant and not any(w in (title.lower()) for w in ['garderie','milieu familial','service de garde','poupon']): continue
                        providers.append({'name':title[:180],'city':city,'address':'','postalCode':'','phone':'','email':'','infantPlaces':1 if infant else 0,'status':status,'subsidized':sub,'distanceKm':None,'source':href,'sourceEngine':'SearXNG','published':None,'snippet':title,'score':65 if infant else 40})
                except Exception as e: errors.append(instance+': '+type(e).__name__)

        # Deduplicate by normalized URL/name.
        dedup={}
        for x in providers:
            key=re.sub(r'[^a-z0-9]','',(x.get('source','') or x.get('name','')).lower())
            if key not in dedup or x.get('score',0)>dedup[key].get('score',0): dedup[key]=x
        providers=list(dedup.values())
        providers.sort(key=lambda x:(x.get('distanceKm') is None, x.get('distanceKm') or 999, -x.get('score',0),x.get('name','')))
        body=json.dumps({'ok':True,'updatedAt':datetime.now(timezone.utc).isoformat(),'city':city,'address':address,'radiusKm':radius,'ageMonths':age,'sourcesChecked':len(set(sources)),'searchQueries':len(QUERIES),'count':len(providers),'providers':providers[:100],'diagnostic':('Recherche multi-source active.' if providers else 'Aucun résultat trouvé. Les sources accessibles ont été interrogées.'),'sourceErrors':errors[:20]},ensure_ascii=False).encode()
        self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass
