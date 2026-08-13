import json, math, re, html as htmlmod
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, quote, parse_qs
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
UA='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/605.1.15 RadarPoupon/3.0'
OFFICIAL=['https://www.milieufamiliallaurentides.ca/fr/','https://www.milieufamiliallaurentides.ca/fr/trouver-une-place']
class Parser(HTMLParser):
 def __init__(self): super().__init__(); self.links=[]; self.parts=[]; self.href=None; self.anchor=[]
 def handle_starttag(self,t,a):
  if t=='a': self.href=dict(a).get('href'); self.anchor=[]
 def handle_endtag(self,t):
  if t=='a':
   if self.href:self.links.append((self.href,' '.join(self.anchor)))
   self.href=None;self.anchor=[]
 def handle_data(self,d):
  s=' '.join(d.split())
  if s:self.parts.append(s);self.anchor.append(s)
def get(url,timeout=8):
 r=Request(url,headers={'User-Agent':UA,'Accept-Language':'fr-CA,fr;q=0.9'});return urlopen(r,timeout=timeout).read().decode('utf-8','ignore')
def clean(s):return re.sub(r'\s+',' ',htmlmod.unescape(s or '')).strip()
def first(p,t):
 m=re.search(p,t,re.I|re.M);return clean(m.group(1)) if m else None
def hav(a,b,c,d):
 p=math.pi/180;x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2;return 6371*2*math.atan2(math.sqrt(x),math.sqrt(1-x))
def geocode(q):
 try:
  d=json.loads(get('https://nominatim.openstreetmap.org/search?format=json&limit=1&q='+quote(q),5));return (float(d[0]['lat']),float(d[0]['lon'])) if d else (None,None)
 except:return (None,None)
def official():
 out=[]
 for src in OFFICIAL:
  try:
   p=Parser();p.feed(get(src));out += [(urljoin(src,h),a) for h,a in p.links if h]
  except:pass
 return list(dict.fromkeys(out))
def member(item):
 u,a=item
 try:p=Parser();p.feed(get(u));t=' | '.join(p.parts)
 except:return None
 city=first(r'Ville\s*:\s*([^|]+)',t);postal=first(r'Code postal\s*:\s*([A-Z]\d[A-Z]\s?\d[A-Z]\d)',t)
 infant=first(r'(\d+)\s+places?\s+(?:0\s*[-–]\s*18\s*mois|poupons?)',t) or first(r'(\d+)\s+places?\s+(?:0\s*[-–]\s*18\s*mois|poupons?)',a)
 if not city or not infant:return None
 name=first(r'#\s*([^|]+?)\s+Nombre de place',t) or first(r'^([^|]+?)\s+Nombre de place',t) or clean(a)[:100] or 'Milieu familial'
 lat,lon=geocode((postal or '')+' '+city+', Québec, Canada')
 return {'name':name,'city':city,'postalCode':postal,'address':((postal+', ') if postal else '')+city,'phone':first(r'Téléphone\s*:\s*([0-9 .()\-]{10,})',t),'email':first(r'Courriel\s*:\s*([^ |]+@[^ |]+)',t),'subsidized':True,'infantPlaces':int(infant),'availableFrom':first(r'Place\(s\) disponible\(s\) dès\s*:\s*([^|]+)',t),'hours':first(r'Heures et jours d[’\']ouverture\s*:\s*([^|]+)',t),'source':u,'sourceType':'Répertoire officiel','lat':lat,'lon':lon,'publishedAt':None,'evidence':[],'confidence':95}
def google(q):
 try:
  u='https://www.google.com/search?hl=fr&num=10&q='+quote(q);p=Parser();p.feed(get(u,7));links=[]
  for h,a in p.links:
   if h.startswith('/url?q='):h=h.split('/url?q=',1)[1].split('&',1)[0]
   if h.startswith('http') and 'google.' not in urlparse(h).netloc:links.append(h)
  return list(dict.fromkeys(links))[:10]
 except:return []
def discover(city,address):
 qs=[f'"{city}" garderie poupon place disponible',f'"{city}" "place poupon" "milieu familial"',f'"{city}" "0-18 mois" garderie',f'site:reddit.com/r/parentsquebecois "{city}" garderie',f'site:reddit.com/r/Quebec "{city}" garderie poupon',f'site:facebook.com "{city}" "place poupon"',f'site:lespac.com "{city}" garderie',f'site:mamswitch.com "{city}" garderie',f'"{address}" garderie']
 out=[]
 with ThreadPoolExecutor(max_workers=5) as ex:
  for f in as_completed([ex.submit(google,q) for q in qs]):
   try:out+=f.result()
   except:pass
 return list(dict.fromkeys(out))[:50]
def public_signal(u,city):
 try:p=Parser();p.feed(get(u,6));t=' '.join(p.parts);low=t.lower()
 except:return None
 if city.lower() not in low:return None
 score=sum(k in low for k in ['poupon','place disponible','place poupon','milieu familial','service de garde','garderie'])
 if score<2:return None
 title=first(r'<title[^>]*>(.*?)</title>',get(u,5)) or urlparse(u).netloc
 avail=any(k in low for k in ['place disponible','place poupon disponible','disponible immédiatement','place libre'])
 intent=any(k in low for k in ['se libère','va se libérer','recherche famille','à la recherche'])
 pub=first(r'(?:Publié|publication|publiée)[^\d]{0,30}(\d{1,2}[ /-]\d{1,2}[ /-]20\d{2})',t)
 return {'name':clean(title)[:160],'source':u,'sourceType':'Web public / moteur de recherche','publishedAt':pub,'phone':first(r'(?:Téléphone|Tel)[^0-9]{0,20}([0-9 .()\-]{10,})',t),'email':first(r'([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})',t),'availabilitySignal':avail,'intentSignal':intent,'excerpt':clean(t)[:650],'confidence':min(98,35+score*7+(30 if avail else 0)+(10 if pub else 0))}
def search(lat,lon,radius,city,address):
 out=[]
 for item in official():
  try:
   x=member(item)
   if x:
    x['distanceKm']=round(hav(lat,lon,x['lat'],x['lon']),1) if x['lat'] else None
    if x['distanceKm'] is None or x['distanceKm']<=radius:out.append(x)
  except:pass
 urls=discover(city,address)
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs=[ex.submit(public_signal,u,city) for u in urls]
  for f in as_completed(fs):
   try:
    s=f.result()
    if not s:continue
    s.update({'city':city,'address':None,'subsidized':None,'infantPlaces':1 if 'poupon' in s['excerpt'].lower() else 0,'availableFrom':None,'hours':None,'website':s['source'],'distanceKm':None,'evidence':[s['excerpt']]})
    out.append(s)
   except:pass
 seen=set();final=[]
 for x in out:
  k=x['source']
  if k not in seen:seen.add(k);final.append(x)
 final.sort(key=lambda x:(-(1 if x.get('availabilitySignal') else 0),-(x.get('confidence') or 0),x.get('distanceKm') if x.get('distanceKm') is not None else 999))
 return final[:80]
class handler(BaseHTTPRequestHandler):
 def do_GET(self):
  try:
   q=parse_qs(urlparse(self.path).query);lat=float(q.get('lat',['45.748591'])[0]);lon=float(q.get('lon',['-74.066237'])[0]);radius=max(.1,min(float(q.get('radius',['10'])[0]),50));city=q.get('city',['Mirabel'])[0];address=q.get('address',['10774 rue du Cerf, Mirabel'])[0]
   p=search(lat,lon,radius,city,address);body=json.dumps({'ok':True,'updatedAt':datetime.now(timezone.utc).isoformat(),'center':{'lat':lat,'lon':lon},'city':city,'address':address,'radiusKm':radius,'count':len(p),'providers':p},ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  except Exception as e:
   body=json.dumps({'ok':False,'error':str(e)},ensure_ascii=False).encode();self.send_response(500);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
