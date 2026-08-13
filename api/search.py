from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote, urljoin
from datetime import datetime, timezone
from html.parser import HTMLParser
import json, math, re, urllib.request

OFFICIAL = "https://www.milieufamiliallaurentides.ca"
SEARX = ["https://priv.au", "https://na.priv.au"]
QUERIES = ['"place poupon" {city}','"0-18 mois" "milieu familial" {city}','"place disponible" garderie poupon {city}','"milieu familial subventionné" {city}','garderie poupon {city} annonce','site:reddit.com garderie poupon {city}','site:facebook.com garderie poupon {city}','site:mamswitch.com poupon {city}','site:lespac.com garderie {city}']

class Parser(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]; self.text=[]; self.href=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='a':
            href=a.get('href') or a.get('data-href') or a.get('data-url')
            if href: self.href=href; self.links.append((href,''))
    def handle_data(self,data):
        s=' '.join(data.split())
        if s:self.text.append(s)
        if self.href and self.links:
            h,t=self.links[-1]; self.links[-1]=(h,(t+' '+s).strip())
    def handle_endtag(self,tag):
        if tag=='a': self.href=None

def fetch(url,timeout=15):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; RadarPoupon/4.0)'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read().decode('utf-8','ignore')
def fetch_json(url,timeout=8):return json.loads(fetch(url,timeout))
def distance(a,b,c,d):
    p=math.pi/180;x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2
    return 6371*2*math.atan2(math.sqrt(x),math.sqrt(max(0,1-x)))
def geocode(address):
    try:
        d=fetch_json('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q='+quote(address),8)
        if d:return float(d[0]['lat']),float(d[0]['lon'])
    except Exception:pass
    return None
def classify(text):
    t=text.lower(); infant=any(x in t for x in ['poupon','0-18 mois','0 à 18 mois','0–18 mois','18 mois']); explicit=any(x in t for x in ['place disponible','disponible immédiatement','une place poupon']); intent=any(x in t for x in ['se libère','va se libérer','à partir de','prend un poupon','place pour septembre','place pour octobre']); sub=any(x in t for x in ['subventionné','subventionnée','contribution réduite','9,65','8,85','9.65','8.85'])
    status='Disponibilité explicite' if explicit else ('Intention / disponibilité probable' if intent else ('Milieu poupon pertinent — disponibilité à confirmer' if infant else 'Information pertinente — disponibilité inconnue'))
    return status,infant,sub

def member_urls_from_html(html):
    urls=set()
    # Works whether member cards are ordinary anchors, data attributes, or embedded in script/HTML.
    patterns=[r'(?:href|data-href|data-url)=[\"\']([^\"\']*?/fr/membres/[^\"\'#?]*)',r'https?://[^\"\'\\s<>]+/fr/membres/[^\"\'\\s<>#?]*']
    for pat in patterns:
        for m in re.finditer(pat,html,re.I):
            u=m.group(1) if m.lastindex else m.group(0)
            urls.add(urljoin(OFFICIAL+'/',u))
    p=Parser();p.feed(html)
    for href,_ in p.links:
        u=urljoin(OFFICIAL+'/',href)
        if '/fr/membres/' in u: urls.add(u.split('#')[0].split('?')[0])
    return urls

def official_urls():
    urls=set()
    # The public site exposes the cards on both pages. Do not assume a sitemap exists.
    for path in ['/fr/','/fr/trouver-une-place']:
        try: urls.update(member_urls_from_html(fetch(OFFICIAL+path,15)))
        except Exception: pass
    # Sitemap is only a bonus fallback.
    for path in ['/sitemap.xml','/sitemap_index.xml']:
        try:
            h=fetch(OFFICIAL+path,10)
            urls.update(u for u in re.findall(r'<loc>\s*(https?://[^<]+)\s*</loc>',h,re.I) if '/fr/membres/' in u)
        except Exception: pass
    return sorted(urls)

def parse_member(u,city,lat,lon,radius):
    h=fetch(u,12);p=Parser();p.feed(h);text=' '.join(p.text)
    status,infant,sub=classify(text)
    if not infant:return None
    m=re.search(r'(\d+)\s+places?\s+0[-–]18\s+mois',text,re.I)
    places=int(m.group(1)) if m else 0
    if places<=0:return None
    vm=re.search(r'Ville\s*:\s*([^\n]+?)\s+Code postal\s*:\s*([A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d)',text,re.I)
    city2=vm.group(1).strip() if vm else city;postal=vm.group(2).upper().replace(' ','') if vm else ''
    tm=re.search(r'Téléphone\s*:\s*([+\d ()\-.]+)',text,re.I);em=re.search(r'Courriel\s*:\s*([^\s]+@[^\s]+)',text,re.I);dm=re.search(r'Place\(s\) disponible\(s\) dès\s*:\s*([^\n]+)',text,re.I)
    coords=geocode((postal+' Canada') if postal else city2+', Québec, Canada');dist=round(distance(lat,lon,*coords),1) if coords else None
    if dist is not None and dist>radius:return None
    hm=re.search(r'<h1[^>]*>\s*([^<]+)',h,re.I);name=' '.join(hm.group(1).split()) if hm else 'Milieu familial'
    return {'name':name,'city':city2,'address':'Adresse civique non publiée sur la fiche','postalCode':postal,'phone':tm.group(1).strip() if tm else '','email':em.group(1).strip() if em else '','infantPlaces':places,'status':status,'subsidized':True,'distanceKm':dist,'source':u,'sourceEngine':'Guichet unique Laurentides','published':dm.group(1).strip() if dm else None,'snippet':text[:1400],'score':100}

def official_results(city,lat,lon,radius):
    out=[];errors=[];urls=official_urls()
    if not urls:errors.append('official:no-member-pages-discovered')
    for u in urls[:500]:
        try:
            x=parse_member(u,city,lat,lon,radius)
            if x:out.append(x)
        except Exception as e:errors.append('official-member:'+type(e).__name__)
    return out,errors

def searx_html(query,instance):
    h=fetch(instance+'/search?q='+quote(query)+'&language=fr-FR&categories=general',10);p=Parser();p.feed(h);return [(l,u) for u,l in p.links if u.startswith('http') and l and 'priv.au' not in u and '/search' not in u]

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query);city=q.get('city',['Mirabel'])[0].strip() or 'Mirabel';address=q.get('address',['10774 rue du Cerf, Mirabel'])[0].strip();radius=max(1,min(100,float(q.get('radius',['10'])[0])));age=int(q.get('age',['14'])[0]);lat=float(q.get('lat',['45.748591'])[0]);lon=float(q.get('lon',['-74.066237'])[0])
        gp=geocode(address) if address else None
        if gp:lat,lon=gp
        providers=[];errors=[];sources=['Guichet unique Laurentides']
        official,err=official_results(city,lat,lon,radius);providers.extend(official);errors.extend(err)
        # SearXNG is strictly optional. Its HTTP errors are not surfaced as application errors.
        searx_ok=0
        for instance in SEARX:
            for template in QUERIES:
                try:
                    rows=searx_html(template.format(city=city),instance)
                    if rows:searx_ok+=1
                    for title,href in rows[:12]:
                        status,infant,sub=classify(title)
                        if not infant and not any(w in title.lower() for w in ['garderie','milieu familial','service de garde','poupon']):continue
                        providers.append({'name':title[:180],'city':city,'address':'','postalCode':'','phone':'','email':'','infantPlaces':1 if infant else 0,'status':status,'subsidized':sub,'distanceKm':None,'source':href,'sourceEngine':'SearXNG','published':None,'snippet':title,'score':65 if infant else 40})
                except Exception:pass
        if searx_ok:sources.extend(SEARX)
        dedup={}
        for x in providers:
            key=re.sub(r'[^a-z0-9]','',(x.get('source','') or x.get('name','')).lower())
            if key not in dedup or x.get('score',0)>dedup[key].get('score',0):dedup[key]=x
        providers=list(dedup.values());providers.sort(key=lambda x:(x.get('distanceKm') is None,x.get('distanceKm') or 999,-x.get('score',0),x.get('name','')))
        body=json.dumps({'ok':True,'updatedAt':datetime.now(timezone.utc).isoformat(),'city':city,'address':address,'radiusKm':radius,'ageMonths':age,'sourcesChecked':len(set(sources)),'searchQueries':len(QUERIES),'count':len(providers),'providers':providers[:100],'diagnostic':('Recherche officielle + Web complémentaire active.' if providers else 'Aucune fiche poupon officielle accessible dans le rayon. SearXNG est optionnel et ses refus HTTP ne bloquent plus le moteur.'),'sourceErrors':errors[:20]},ensure_ascii=False).encode()
        self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass
