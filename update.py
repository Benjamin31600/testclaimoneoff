import json,re,math
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from html.parser import HTMLParser

HOME=(45.748591,-74.066237)
INDEX='https://www.milieufamiliallaurentides.ca/fr/'
UA='Mozilla/5.0 (compatible; RadarPoupon/1.0)'

class Parser(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]; self.text=[]; self.href=None
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

def dist(lat,lon):
    R=6371; p1=math.radians(HOME[0]);p2=math.radians(lat);dp=math.radians(lat-HOME[0]);dl=math.radians(lon-HOME[1]);a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return R*2*math.atan2(math.sqrt(a),math.sqrt(1-a))

def geocode(q):
    try:
        url='https://nominatim.openstreetmap.org/search?format=json&limit=1&q='+__import__('urllib.parse').parse.quote(q)
        r=Request(url,headers={'User-Agent':UA}); x=json.loads(urlopen(r,timeout=20).read());
        return (float(x[0]['lat']),float(x[0]['lon'])) if x else (None,None)
    except Exception:return (None,None)

def clean(s): return re.sub(r'\s+',' ',s).strip()

def parse_member(url):
    html=get(url); p=Parser();p.feed(html); txt=' '.join(p.text)
    def find(pattern):
        m=re.search(pattern,txt,re.I); return clean(m.group(1)) if m else None
    name=find(r'#\s*([^|]+?)\s+Nombre de place') or find(r'([A-ZÀ-Ÿ][^|]+?)\s+Nombre de place')
    city=find(r'Ville\s*:\s*([^|]+)'); postal=find(r'Code postal\s*:\s*([A-Z]\d[A-Z]\s?\d[A-Z]\d)')
    phone=find(r'Téléphone\s*:\s*([0-9 .()-]{10,})'); email=find(r'Courriel\s*:\s*([^ ]+@[^ ]+)')
    inf=find(r'(\d+)\s+places?\s+0-18 mois'); other=find(r'(\d+)\s+places?\s+18 mois')
    avail=find(r'Place\(s\) disponible\(s\) dès\s*:\s*([^|]+)')
    hours=find(r'Heures et jours d’ouverture\s*:\s*([^|]+)')
    if not city:return None
    lat,lon=geocode((postal or '')+' '+city+', Québec, Canada')
    return {'name':name or 'Milieu familial','city':city,'postalCode':postal,'phone':phone,'email':email,'subsidized':True,'infantPlaces':int(inf) if inf else None,'otherPlaces':int(other) if other else None,'availableFrom':avail,'hours':hours,'website':url,'source':url,'lat':lat,'lon':lon,'distanceKm':round(dist(lat,lon),1) if lat else None,'status':'confirmed-public' if inf and int(inf)>0 else 'contact-to-confirm'}

html=get(INDEX); p=Parser();p.feed(html); links=[]
for x in p.links:
    u=urljoin(INDEX,x)
    if u not in links: links.append(u)
providers=[]
for u in links[:100]:
    try:
        x=parse_member(u)
        if x and x.get('distanceKm') is not None and x['distanceKm']<=15: providers.append(x)
    except Exception: pass
providers.sort(key=lambda x:x.get('distanceKm',999))
out={'updatedAt':datetime.now(timezone.utc).isoformat(),'home':{'lat':HOME[0],'lon':HOME[1],'address':'10774 rue du Cerf, Mirabel'},'providers':providers,'sources':[INDEX]}
open('data.json','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
print('providers:',len(providers))
