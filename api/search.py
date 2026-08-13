import json, math, re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, quote, parse_qs
from urllib.request import Request, urlopen

UA='Mozilla/5.0 (compatible; RadarPoupon/1.0)'
OFFICIAL=['https://www.milieufamiliallaurentides.ca/fr/','https://www.milieufamiliallaurentides.ca/fr/trouver-une-place']

class Parser(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]; self.parts=[]; self.href=None
    def handle_starttag(self,t,a):
        if t=='a': self.href=dict(a).get('href')
    def handle_endtag(self,t):
        if t=='a': self.href=None
    def handle_data(self,d):
        s=' '.join(d.split())
        if s: self.parts.append(s)
        if self.href and '/membres/' in self.href: self.links.append(self.href)

def get(url,timeout=12):
    r=Request(url,headers={'User-Agent':UA,'Accept-Language':'fr-CA,fr;q=0.9'}); return urlopen(r,timeout=timeout).read().decode('utf-8','ignore')

def first(p,t):
    m=re.search(p,t,re.I|re.M); return re.sub(r'\s+',' ',m.group(1)).strip(' |') if m else None

def hav(a,b,c,d):
    R=6371;p=math.pi/180; x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2; return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))

def geocode(q):
    try:
        raw=get('https://nominatim.openstreetmap.org/search?format=json&limit=1&q='+quote(q),10); x=json.loads(raw); return (float(x[0]['lat']),float(x[0]['lon'])) if x else (None,None)
    except Exception:return (None,None)

def member(url):
    html=get(url); p=Parser();p.feed(html);t=' | '.join(p.parts)
    city=first(r'Ville\s*:\s*([^|]+)',t); postal=first(r'Code postal\s*:\s*([A-Z]\d[A-Z]\s?\d[A-Z]\d)',t)
    if not city:return None
    inf=first(r'(\d+)\s+places?\s+0-18 mois',t); name=first(r'#\s*([^|]+?)\s+Nombre de place',t) or first(r'^([^|]+?)\s+Nombre de place',t)
    phone=first(r'Téléphone\s*:\s*([0-9 .()\-]{10,})',t); email=first(r'Courriel\s*:\s*([^ |]+@[^ |]+)',t)
    avail=first(r'Place\(s\) disponible\(s\) dès\s*:\s*([^|]+)',t); hours=first(r'Heures et jours d[’\']ouverture\s*:\s*([^|]+)',t)
    lat,lon=geocode((postal or '')+' '+city+', Québec, Canada')
    return {'name':name or 'Milieu familial','city':city,'postalCode':postal,'phone':phone,'email':email,'subsidized':True,'infantPlaces':int(inf or 0),'availableFrom':avail,'hours':hours,'source':url,'website':url,'lat':lat,'lon':lon}

def handler(req):
    q=parse_qs(urlparse(req.get('url','')).query)
    try: lat=float(q.get('lat',[45.748591])[0]); lon=float(q.get('lon',[-74.066237])[0]); radius=float(q.get('radius',[10])[0])
    except: lat,lon,radius=45.748591,-74.066237,10
    links=[]
    for s in OFFICIAL:
        try:
            p=Parser();p.feed(get(s));
            for l in p.links:
                u=urljoin(s,l)
                if u not in links:links.append(u)
        except Exception: pass
    out=[]
    for u in links:
        try:
            x=member(u)
            if x:
                x['distanceKm']=round(hav(lat,lon,x['lat'],x['lon']),1) if x['lat'] is not None else None
                if x['distanceKm'] is None or x['distanceKm']<=radius: out.append(x)
        except Exception: pass
    out.sort(key=lambda x:x.get('distanceKm',999))
    seen=set(); clean=[]
    for x in out:
        if x['source'] not in seen:seen.add(x['source']);clean.append(x)
    return {'updatedAt':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'center':{'lat':lat,'lon':lon},'radiusKm':radius,'providers':clean,'count':len(clean)}

def main(request):
    data=handler({'url':request.url})
    return {'statusCode':200,'headers':{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'},'body':json.dumps(data,ensure_ascii=False)}

# Vercel Python runtime entrypoint
