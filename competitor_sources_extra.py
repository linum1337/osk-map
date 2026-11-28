"""Public catalogue adapters: OSK product offers and Mir Cable public content."""
import json,re
from urllib.parse import urljoin,urlencode
from bs4 import BeautifulSoup
import competitor_catalog as c

def osk_prices(scope):
 raw=c.text(scope.select_one('.price'))
 if not raw or 'запрос' in raw.lower():return []
 numeric=raw.split('руб')[0].replace(' ','').replace('\xa0','').replace('Цена:','')
 amounts=re.findall(r'\d+(?:[.,]\d+)?',numeric)
 if not 1<=len(amounts)<=2:return []
 if len(amounts)==2 and not re.search(r'[-–—]',numeric):return []
 labels=['От','До'] if len(amounts)==2 else ['Цена на странице']
 return [p for label,amount in zip(labels,amounts) if (p:=c.price(label,amount,currency='RUB' if 'руб' in raw.lower() else '',unit=c.unit_from(raw)))]

def osk_listing(src,url,html):
 s=BeautifulSoup(html,'html.parser');products=[];links=[]
 for block in s.select('.products-catalog .product-block'):
  a=block.select_one('.name a[href]')
  if not a:continue
  p=c.make(src,urljoin(url,a['href']),c.text(a),category_path=c.text(s.select_one('h1')))
  if p:p.update(prices=osk_prices(block),priceText='По запросу' if 'запрос' in c.text(block.select_one('.price')).lower() else '');products.append(p)
 for a in s.select('a.category-items-block[href], .pagination a[href]'):
  link=c.canonical(src,urljoin(url,a['href']))
  if link and any(link.startswith(seed) for seed in src['seeds']):links.append(link)
 return products,list(dict.fromkeys(links))

def osk_details(src,record,html):
 s=BeautifulSoup(html,'html.parser');title=c.text(s.select_one('h1'));scope=s.select_one('.main-section-block');form=scope.select_one('#product') if scope else None
 if c.norm(title)!=c.norm(record['name']) or scope is None:raise ValueError('OSK current product missing')
 if form is None:
  if record.get('prices'):raise ValueError('Priced OSK product form missing')
  return c.makers.read_claims({**record,'description':c.text(scope.select_one('.simple-text')),'availability':'','checkedAt':c.now(),'detailCheckedAt':c.now()},s)
 pid=form.select_one('input[name="product_id"]')
 if pid is None:raise ValueError('OSK product identity missing')
 out={**record,'properties':{},'checkedAt':c.now(),'detailCheckedAt':c.now(),'sku':c.text(form.select_one('#product-sku span'))}
 prices=[];unit=c.unit_from(c.text(form.select_one('#product_price')));variants_seen=False
 for script in s.select('script'):
  text=script.string or script.get_text()
  marker=re.search(r"ro_params\['ro_data'\]\s*=\s*",text)
  if not marker:continue
  data,_=json.JSONDecoder().raw_decode(text[marker.end():])
  for group in data:
   for variant in group.get('ro',{}).values():
    if str(variant.get('product_id'))!=pid.get('value'):continue
    variants_seen=True
    if variant.get('price_prefix')!='=' or float(variant.get('addition_B') or 0)!=0 or float(variant.get('multiplication_A') or 1)!=1:continue
    options=[]
    for option_id,option_value in variant.get('options',{}).items():
     if not str(option_id).isdigit() or not str(option_value).isdigit():continue
     select=form.find('select',attrs={'name':'option['+str(option_id)+']'})
     option=select.find('option',attrs={'value':str(option_value)}) if select else None
     if option:options.append(c.text(option))
    label=variant.get('location') or ' · '.join(options) or variant.get('sku') or ''
    p=c.price('Исполнение: '+label,variant.get('price',''),currency='RUB',unit=unit)
    if not p:continue
    p.update(sku=variant.get('sku',''),condition='Артикул: '+variant['sku'] if variant.get('sku') else '')
    prices.append(p)
 if prices:out['prices']=prices
 elif variants_seen:out['prices']=record.get('prices',[])
 else:
  plain=osk_prices(form)
  if plain:out['prices']=plain
 out['availability']=c.text(form.select_one('.availability, .stock-status'))
 for tr in scope.select('table tr'):
  cells=tr.find_all(['th','td'],recursive=False)
  if len(cells)==2:
   key,value=map(c.text,cells)
   if key and value and len(key)<120 and len(value)<1500:out['properties'][key]=value
 return c.makers.read_claims(out,s)

def mircable(src,html):
 data=json.loads(html);cats={x['slug']:x for x in data['categories']};products=[]
 for raw in data['products']:
  cat=cats.get(raw.get('cat'))
  if not cat or raw['cat']=='sip_kabel':continue
  if not re.fullmatch(r'[a-zA-Z0-9_-]{1,160}',str(raw['id'])):raise ValueError('Unsupported public product ID')
  # These are the public SPA's actual category and q routes, not invented card URLs.
  url=src['url'].rstrip('/')+'/catalog/'+raw['cat']+'?'+urlencode({'q':raw['name']})
  sub=next((x['title'] for x in cat.get('subs',[]) if x['slug']==raw.get('sub')),'')
  p=c.make(src,url,raw['name'],category_path=' · '.join(x for x in [cat['title'],sub] if x))
  p.update(sourceProductId=str(raw['id']),id=c.product_id(src,c.canonical(src,url),str(raw['id'])),sourceLinkLabel='Товар в каталоге',prices=[],availability='',priceText=data.get('copy',{}).get('catalog',{}).get('price','Цена по запросу'),sourceDataUrl=src['seeds'][0])
  # The public response also contains prices when the UI explicitly hides them.
  if data.get('showPrices') is True:
   value=c.price('Цена на странице',raw.get('price',''),currency='RUB')
   if value:p.update(prices=[value],priceText='')
  products.append(p)
 return products
