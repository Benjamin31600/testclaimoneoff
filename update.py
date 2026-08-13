import json, re, math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import urljoin, quote
from html.parser import HTMLParser

HOME=(45.748591,-74.066237)
SOURCES=['https://www.milieufamiliallaurentides.ca/fr/','https://www.milieufamiliallaurentides.ca/fr/trouver-une-place']
UA='Mozilla/5.0 (compatible; RadarPoupon/1.0)'

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.text=[]; self.href=None
    def handle_starttag(self,t,a):
        if t=='a': self.href=dict(a).get('href')
    def handle_endtag(self,t):
        if t=='a': self.href=None
    def handle_data(self,d):
        s=' '.join(d.split())
        if s: self.text.append(s)
        if self.href and '/membres/' in self.href: self.links.append(self.href)

def get(url):
    r=Request(url,headers={'User-Agent':UA}); return urlopen(r,timeout=30).read().decode('utf-8','ignore')

def distance(lat,lon):
    R=6371; p=math.pi/180
    a1=HOME[0]*p; a2=lat*p; d1=(lat-HOME[0])*p; d2=(lon-HOME[1])*p
    a=math.sin(d1/2)**2+math.cos(a1)*math.cos(a2)*math.sin(d2/2)**2
    return R*2*math.atan2(math.sqrt(a),math.sqrt(1-a))

def geocode(q):
    try:
        u='https://nominatim.openstreetmap.org/search?format=json&limit=1&q='+quote(q)
        r=Request(u,headers={'User-Agent':UA}); x=json.loads(urlopen(r,timeout=20).read())
        return (float(x[0]['lat']),float(x[0]['lon'])) if x else (None,None)
    except Exception: return (None,None)

def clean(s): return re.sub(r'\s+',' ',s or '').strip(' |')

def first(pattern, text):
    m=re.search(pattern,text,re.I|re.M); return clean(m.group(1)) if m else None

def parse_member(url):
    html=get(url); p=Parser(); p.feed(html); txt=' | '.join(p.text)
    name=first(r'#\s*([^|]+?)\s+Nombre de place',txt) or first(r'^([^|]+?)\s+Nombre de place',txt)
    city=first(r'Ville\s*:\s*([^|]+)',txt)
    postal=first(r'Code postal\s*:\s*([A-Z]\d[A-Z]\s?\d[A-Z]\d)',txt)
    phone=first(r'Téléphone\s*:\s*([0-9 .()\-]{10,})',txt)
    email=first(r'Courriel\s*:\s*([^ |]+@[^ |]+)',txt)
    inf=first(r'(\d+)\s+places?\s+0-18 mois',txt)
    other=first(r'(\d+)\s+places?\s+18 mois',txt)
    avail=first(r'Place\(s\) disponible\(s\) dès\s*:\s*([^|]+)',txt)
    hours=first(r'Heures et jours d[’\']ouverture\s*:\s*([^|]+)',txt)
    if not city: return None
    lat,lon=geocode((postal or '')+' '+city+', Québec, Canada')
    return {
      'name':name or 'Milieu familial', 'city':city, 'postalCode':postal,
      'phone':phone, 'email':email, 'subsidized':True,
      'infantPlaces':int(inf) if inf else 0, 'otherPlaces':int(other) if other else 0,
      'availableFrom':avail, 'hours':hours, 'website':url, 'source':url,
      'lat':lat, 'lon':lon,
      'distanceKm':round(distance(lat,lon),1) if lat is not None else None,
      'status':'confirmed-public' if inf and int(inf)>0 else 'contact-to-confirm',
      'mapUrl':('https://www.google.com/maps/search/?api=1&query='+quote((postal or '')+' '+city+', Quebec'))
    }

links=[]
for source in SOURCES:
    try:
        p=Parser(); p.feed(get(source))
        for link in p.links:
            u=urljoin(source,link)
            if u not in links: links.append(u)
    except Exception as e: print('source error',source,e)

providers=[]
for u in links:
    try:
        x=parse_member(u)
        if x and (x.get('distanceKm') is None or x['distanceKm']<=15): providers.append(x)
    except Exception as e: print('member error',u,e)

# dédoublonnage par URL
seen=set(); unique=[]
for x in providers:
    if x['source'] not in seen: seen.add(x['source']); unique.append(x)
unique.sort(key=lambda x:x.get('distanceKm',999))

out={'updatedAt':datetime.now(timezone.utc).isoformat(),'home':{'lat':HOME[0],'lon':HOME[1],'address':'10774 rue du Cerf, Mirabel'},'providers':unique,'sources':SOURCES}
open('data.json','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
print('providers:',len(unique),'public member links:',len(links))
