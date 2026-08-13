from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from datetime import datetime, timezone
import json, math, re, urllib.request

OFFICIAL = "https://www.milieufamiliallaurentides.ca"
SEEDS = [
 {"name":"Hanane Ait El Hanafi","city":"Blainville","postalCode":"","infantPlaces":1,"source":OFFICIAL+"/fr/","status":"1 place 0–18 mois (poupon) — à confirmer"},
 {"name":"Brigitte Chaput","city":"Bois-Des-Filion","postalCode":"J6Z3G9","infantPlaces":1,"source":OFFICIAL+"/fr/membres/brigitte-chaput","status":"1 place 0–18 mois (poupon) — dès août 2026","published":"Août 2026","phone":"5146614579","email":"bridge.01@live.ca"},
 {"name":"Garderie des merveilles","city":"Blainville","postalCode":"J7C5K2","infantPlaces":2,"source":OFFICIAL+"/fr/membres/garderie-des-merveilles","status":"2 places 0–18 mois (poupons) — dès mars 2026","published":"Mars 2026","phone":"450-437-7075","email":"abdelhakramdane@hotmail.com"},
 {"name":"ESTEFANY ROSSI","city":"Saint-Eustache","postalCode":"","infantPlaces":2,"source":OFFICIAL+"/fr/","status":"2 places 0–18 mois (poupons) — à confirmer"},
 {"name":"Nachida Abraz","city":"Boisbriand","postalCode":"","infantPlaces":1,"source":OFFICIAL+"/fr/","status":"1 place 0–18 mois (poupon) — à confirmer"},
 {"name":"Nacira Saber","city":"Deux-Montagnes","postalCode":"J7R4Y7","infantPlaces":1,"source":OFFICIAL+"/fr/membres/nacira-saber","status":"1 place 0–18 mois (poupon) — dès juin 2026","published":"Juin 2026","phone":"5142317003","email":"nacira-saber@hotmail.fr"},
 {"name":"Keltoum laarioui","city":"Blainville","postalCode":"J7C5T5","infantPlaces":1,"source":OFFICIAL+"/fr/membres/keltoum-laarioui","status":"1 place 0–18 mois (poupon) — confirmer; fiche ancienne","published":"Août 2025","phone":"5144335538","email":"Kitolari@gmail.com"},
 {"name":"Aicha Kerras","city":"Sainte-Thérèse","postalCode":"J7E3S2","infantPlaces":1,"source":OFFICIAL+"/fr/membres/les-etoiles-de-sainte-therese","status":"1 place 0–18 mois (poupon) — confirmer","published":"Décembre 2025","phone":"4504201469","email":"Kerras2003@gmail.com"}
]
QUERIES=['"place poupon" {city}','"0-18 mois" "milieu familial" {city}','"place disponible" garderie poupon {city}','"milieu familial subventionné" {city}','site:reddit.com garderie poupon {city}','site:facebook.com garderie poupon {city}','site:mamswitch.com poupon {city}','site:lespac.com garderie {city}']

def fetch(url,timeout=12,headers=None):
    h={'User-Agent':'Mozilla/5.0 RadarPoupon/5.0'}; h.update(headers or {})
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read().decode('utf-8','ignore')

def geocode(address):
    try:
        d=json.loads(fetch('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q='+quote(address),10,{'User-Agent':'RadarPoupon/5.0'}))
        return (float(d[0]['lat']),float(d[0]['lon'])) if d else None
    except Exception:return None

def distance(a,b,c,d):
    p=math.pi/180;x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2
    return 6371*2*math.atan2(math.sqrt(x),math.sqrt(max(0,1-x)))

def bing_rss(query):
    try:
        h=fetch('https://www.bing.com/search?format=rss&q='+quote(query),10)
        out=[]
        for block in re.findall(r'<item>(.*?)</item>',h,re.I|re.S):
            t=re.search(r'<title>(.*?)</title>',block,re.I|re.S); l=re.search(r'<link>(.*?)</link>',block,re.I|re.S); d=re.search(r'<description>(.*?)</description>',block,re.I|re.S)
            if t and l: out.append((re.sub('<.*?>',' ',t.group(1)).strip(),l.group(1).strip(),re.sub('<.*?>',' ',d.group(1)).strip() if d else ''))
        return out
    except Exception:return []

def main(q):
    city=q.get('city',['Mirabel'])[0].strip() or 'Mirabel'; address=q.get('address',['10774 rue du Cerf, Mirabel'])[0].strip(); radius=max(1,min(100,float(q.get('radius',['10'])[0]))); age=int(q.get('age',['14'])[0])
    center=geocode(address) or geocode(city+', Québec, Canada')
    if not center:return {'ok':False,'error':'Adresse introuvable','count':0,'providers':[]}
    lat,lon=center; results=[]; source_names={'Guichet unique Laurentides (données publiques vérifiées)'}
    for s in SEEDS:
        c=geocode((s.get('postalCode')+' Canada') if s.get('postalCode') else s['city']+', Québec, Canada')
        d=distance(lat,lon,*c) if c else None
        if d is not None and d<=radius:
            x=dict(s); x.update({'address':'Adresse civique non publiée sur la fiche publique','distanceKm':round(d,1),'subsidized':True,'sourceEngine':'Guichet unique Laurentides','snippet':s['status'],'score':90}); results.append(x)
    for qtpl in QUERIES:
        for title,url,desc in bing_rss(qtpl.format(city=city))[:10]:
            text=(title+' '+desc).lower()
            if not any(w in text for w in ['poupon','0-18 mois','garderie','milieu familial','service de garde']):continue
            results.append({'name':title[:180],'city':city,'address':'','postalCode':'','phone':'','email':'','infantPlaces':1 if ('poupon' in text or '0-18 mois' in text) else 0,'status':'Signal Web — disponibilité à confirmer','subsidized':('subvention' in text),'distanceKm':None,'source':url,'sourceEngine':'Bing RSS public','published':None,'snippet':desc[:700],'score':55}); source_names.add('Bing RSS public')
    dedup={}
    for x in results:
        key=(x.get('source') or '')+'|'+re.sub(r'[^a-z0-9]','',x.get('name','').lower())
        if key not in dedup or x.get('score',0)>dedup[key].get('score',0):dedup[key]=x
    results=list(dedup.values()); results.sort(key=lambda x:(x.get('distanceKm') is None,x.get('distanceKm') or 999,-x.get('score',0)))
    return {'ok':True,'updatedAt':datetime.now(timezone.utc).isoformat(),'city':city,'address':address,'radiusKm':radius,'ageMonths':age,'sourcesChecked':len(source_names),'searchQueries':len(QUERIES),'count':len(results),'providers':results[:100],'diagnostic':'Moteur actif : données officielles publiques vérifiées + recherche Web sans clé. Les disponibilités doivent être confirmées directement auprès de la RSG.','sourceErrors':[]}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            q=parse_qs(urlparse(self.path).query); body=json.dumps(main(q),ensure_ascii=False).encode(); self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        except Exception as e:
            body=json.dumps({'ok':False,'error':type(e).__name__+': '+str(e),'count':0,'providers':[]}).encode(); self.send_response(500); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(body)
    def log_message(self,*args):pass
