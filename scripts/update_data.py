import json,re,requests
from bs4 import BeautifulSoup
from datetime import datetime,timezone
URL='https://www.milieufamiliallaurentides.ca/fr/'
r=requests.get(URL,timeout=30,headers={'User-Agent':'Mozilla/5.0 RadarPoupon/1.0'})
r.raise_for_status()
s=BeautifulSoup(r.text,'html.parser')
items=[]
# Discover member links and scrape their public detail pages.
for a in s.select('a[href*="/fr/membres/"]'):
    href=a.get('href','')
    if href.startswith('/'):
        href='https://www.milieufamiliallaurentides.ca'+href
    name=a.get_text(' ',strip=True)
    if not name: continue
    try:
        p=requests.get(href,timeout=20,headers={'User-Agent':'Mozilla/5.0 RadarPoupon/1.0'})
        p.raise_for_status()
        ps=BeautifulSoup(p.text,'html.parser')
        text=ps.get_text(' ',strip=True)
        m=re.search(r'(\d+)\s+place[s]?\s+0-18 mois',text,re.I)
        if not m: continue
        poupons=int(m.group(1))
        if poupons<=0: continue
        def grab(label):
            mm=re.search(re.escape(label)+r'\s*:?\s*([^\n]+?)(?=\s+(?:Courriel|Téléphone|Ville|Code postal|Heures|Caractéristiques|Description)\s*:|$)',text,re.I)
            return mm.group(1).strip() if mm else ''
        phone=''
        tel=ps.select_one('a[href^="tel:"]')
        if tel: phone=tel.get_text(' ',strip=True) or tel.get('href','').replace('tel:','')
        email=''
        em=ps.select_one('a[href^="mailto:"]')
        if em: email=em.get('href','').replace('mailto:','')
        city=grab('Ville')
        postal=grab('Code postal')
        availability=grab('Place(s) disponible(s) dès')
        hours=grab('Heures et jours d’ouverture')
        items.append({'name':name,'city':city,'postalCode':postal,'phone':phone,'email':email,'poupons':poupons,'availabilityFrom':availability,'hours':hours,'url':href,'source':'Guichet unique Laurentides'})
    except Exception:
        pass
# de-duplicate by URL/name
uniq={x['url']:x for x in items}
out={'updatedAt':datetime.now(timezone.utc).isoformat(),'source':URL,'count':len(uniq),'items':list(uniq.values())}
with open('data.json','w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2)
print(f"Collected {len(uniq)} public poupon listings")
