from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from datetime import datetime, timezone
import json, math, re, urllib.request, urllib.error

SEARCH_INSTANCES = ["https://priv.au", "https://na.priv.au"]
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

def fetch_json(url, timeout=8):
    req=urllib.request.Request(url, headers={"User-Agent":"RadarPoupon/1.0 public-search"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))

def distance(a,b,c,d):
    p=math.pi/180; x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2
    return 6371*2*math.atan2(math.sqrt(x),math.sqrt(max(0,1-x)))

def geocode(address):
    try:
        q=quote(address); data=fetch_json(f"https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q={q}",6)
        if data: return float(data[0]['lat']),float(data[0]['lon'])
    except Exception: pass
    return None

def classify(text):
    t=text.lower()
    explicit=any(x in t for x in ["place disponible","place poupon disponible","disponible immédiatement","place disponible immédiatement","une place poupon"])
    intent=any(x in t for x in ["se libère","va se libérer","à partir de","prend un poupon","recherche famille","place pour septembre","place pour octobre"])
    infant=any(x in t for x in ["poupon","0-18","0 à 18","0–18","18 mois","poupons"])
    subsidized=any(x in t for x in ["subventionné","subventionnée","subventionne","contribution réduite","8,85","9,65"])
    if explicit: status="Disponibilité explicite"
    elif intent: status="Intention / disponibilité probable"
    elif infant: status="Milieu poupon pertinent — disponibilité à confirmer"
    else: status="Information pertinente — disponibilité inconnue"
    return status, infant, subsidized

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query)
        city=q.get('city',['Mirabel'])[0].strip() or 'Mirabel'
        address=q.get('address',['10774 rue du Cerf, Mirabel'])[0].strip()
        radius=float(q.get('radius',['10'])[0])
        age=int(q.get('age',['14'])[0])
        lat=float(q.get('lat',['45.748591'])[0]); lon=float(q.get('lon',['-74.066237'])[0])
        if address and address != '10774 rue du Cerf, Mirabel':
            gp=geocode(address)
            if gp: lat,lon=gp
        sources=[]; seen={}; errors=[]
        for instance in SEARCH_INSTANCES:
            for template in QUERIES:
                query=template.format(city=city)
                try:
                    url=instance+"/search?q="+quote(query)+"&format=json&language=fr-FR&time_range=month&categories=general"
                    data=fetch_json(url,8)
                    sources.append(instance)
                    for item in data.get('results',[]):
                        title=item.get('title','').strip(); href=item.get('url','').strip(); content=item.get('content','').strip()
                        if not href or not title: continue
                        key=re.sub(r'[^a-z0-9]','',href.lower())
                        if key in seen: continue
                        text=title+' '+content
                        status,infant,sub=classify(text)
                        if not infant and not any(w in text.lower() for w in ['garderie','milieu familial','service de garde','rsg','poupon']): continue
                        seen[key]={'name':title,'city':city,'address':'','phone':'','email':'','infantPlaces':1 if infant else 0,'status':status,'subsidized':sub,'distanceKm':round(distance(lat,lon,lat,lon),1),'source':href,'sourceEngine':instance,'published':item.get('publishedDate') or item.get('published_date'),'snippet':content,'score':70 if infant else 45}
                except Exception as e:
                    errors.append(instance+': '+type(e).__name__)
        providers=list(seen.values())
        # Public web search does not reliably expose professional coordinates, so keep distance unknown rather than invent it.
        for x in providers: x['distanceKm']=None
        providers.sort(key=lambda x:(-x['score'],x['name']))
        body=json.dumps({'ok':True,'updatedAt':datetime.now(timezone.utc).isoformat(),'city':city,'address':address,'radiusKm':radius,'ageMonths':age,'sourcesChecked':len(set(sources)),'searchQueries':len(QUERIES),'count':len(providers),'providers':providers[:100],'diagnostic':('Recherche SearXNG active.' if providers else 'Aucun résultat public retourné par les instances SearXNG. '+('; '.join(errors[:3]) if errors else '')),'sourceErrors':errors[:10]},ensure_ascii=False).encode()
        self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass
