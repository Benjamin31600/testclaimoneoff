import json,re,time,requests
from bs4 import BeautifulSoup
from datetime import datetime,timezone
BASE='https://www.milieufamiliallaurentides.ca'; HEAD={'User-Agent':'Mozilla/5.0 RadarPoupon/1.0'}
s=requests.Session(); s.headers.update(HEAD)

def absurl(h): return h if h.startswith('http') else BASE+h

def field(label,text):
 m=re.search(re.escape(label)+r'\s*:?\s*(.*?)(?=\s+(?:Courriel|Téléphone|Ville|Code postal|Heures|Caractéristiques|Description|En éducation|Ouverture du milieu familial)\s*:|$)',text,re.I)
 return m.group(1).strip() if m else ''

home=s.get(BASE+'/fr/',timeout=30); home.raise_for_status(); hs=BeautifulSoup(home.text,'html.parser')
list_urls=[]
for a in hs.find_all('a',href=True):
 label=a.get_text(' ',strip=True).lower()
 if 'afficher toutes les places' in label or 'voir les places disponibles' in label or 'trouver une place' in label: list_urls.append(absurl(a['href']))
list_urls=list(dict.fromkeys(list_urls+[BASE+'/fr/']))
member_urls=set()
for u in list_urls:
 try:
  q=s.get(u,timeout=30); q.raise_for_status(); bs=BeautifulSoup(q.text,'html.parser')
  member_urls.update(absurl(a['href']) for a in bs.select('a[href*="/fr/membres/"]'))
 except Exception as e: print('list error',u,e)
items=[]
for href in sorted(member_urls):
 try:
  p=s.get(href,timeout=20); p.raise_for_status(); ps=BeautifulSoup(p.text,'html.parser'); text=ps.get_text(' ',strip=True)
  m=re.search(r'(\d+)\s+places?\s+0-18 mois',text,re.I)
  if not m or int(m.group(1))<=0: continue
  h1=ps.find('h1'); name=h1.get_text(' ',strip=True) if h1 else ''
  tel=ps.select_one('a[href^="tel:"]'); em=ps.select_one('a[href^="mailto:"]')
  items.append({'name':name,'city':field('Ville',text),'postalCode':field('Code postal',text),'phone':(tel.get_text(' ',strip=True) if tel else ''),'email':(em.get('href','').replace('mailto:','') if em else ''),'infantPlaces':int(m.group(1)),'availableFrom':field('Place(s) disponible(s) dès',text),'hours':field('Heures et jours d’ouverture',text),'address':field('Adresse',text),'url':href,'source':'Guichet unique Laurentides','subsidized':True})
 except Exception as e: print('member error',href,e)
# Geocode public postal-code/city location for distance; never invent a street address.
for x in items:
 q=' '.join(v for v in [x.get('postalCode',''),x.get('city',''),'Quebec, Canada'] if v)
 try:
  time.sleep(1); g=s.get('https://nominatim.openstreetmap.org/search',params={'q':q,'format':'json','limit':1},headers={'User-Agent':'RadarPoupon/1.0'},timeout=20).json()
  if g: x['lat']=float(g[0]['lat']); x['lon']=float(g[0]['lon']); x['distanceApprox']=True
 except Exception as e: print('geo error',q,e)
uniq={x['url']:x for x in items}
out={'updatedAt':datetime.now(timezone.utc).isoformat(),'source':BASE+'/fr/','count':len(uniq),'items':list(uniq.values())}
with open('data.json','w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2)
print('Collected',len(uniq),'public poupon listings')
