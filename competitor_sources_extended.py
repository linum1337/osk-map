"""Scoped catalogue adapters for the additional network-equipment suppliers."""
import re,json
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
import competitor_catalog as c

# Card selectors exclude sliders, modal basket recommendations and global navigation.
PROFILES={
 'component':('li.catalog-products__item','.product__name','.product__price-current, .product__price, [itemprop="price"]'),
 'kdds':('.catalog_item, .item_block, .list_item_wrapp','.item-title a, .name a, a.name','.cost .price[data-value], .price-opt-value'),
 'sparta':('.shop_list .shop-item, .shop-item, .shop_item, .shop-item-container, [class*="shop-list-item"]','a.name, .name a, .shop_name a, h2 a, a.shop-item-title','.shop_price_value'),
 'komss':('div.product','a.titl','.fprice, .price>span'),
 'hard':('.product-item','.item-title a','.item-price'),
 'lenservice':('main .catalog-items .js-item, .page-content .catalog-items .js-item','.info a.name','.price-current, .price .value, .price'),
 'investtelecom':('a.wrap_good','a.wrap_good','.price'),
 'progress':('.product-layout, .product-thumb, .card.product, .product-card, .card','.product-title a, .name a, h4 a, .card-title a, a.grey-text','.card-price, .price-tax'),
 'optel':('.product-grid>div, .product-list>div, .product-thumb, .product-block','.name a, h4 a','.price-new, .price'),
 'fbtrade':('.card-type','.eq-product-title span','.eq-product-title p'),
 'fibertool':('.catalog_item','.item-title a, .item_info .name a','.price[data-value], .price_value'),
 'alphanets':('.node-product-display','a.title, .title a, h2 a, h3 a','.price__value'),
 'telecomo':('.catalog-card','a.catalog-card__name','.catalog-card__price'),
 'komtel':('.list_item_wrapp, .catalog_item','.item-title a, .js-notice-block__title','.price[data-value], .price_value'),
 'netsol':('.product-layout.product-category','.product-small__title','.price-new, .price'),
 'skp':('.jshop_list_product .product, .jshop .product, .row-fluid .product','.name a, h3 a','.jshop_price, .price'),
 'lancentre':('[itemtype$="/Product"]','.catalog-block__info-title a','.price__new-val'),
 'kabco':('[itemtype$="/Product"]','.item-title a, .js-notice-block__title','.price[data-value], .price_value'),
 'bazis':('[itemtype$="/Product"]','.catalog-block__info-title a','.price__new-val'),
 'anlan':('.product-item, .product','.product_name a, .product-name a, a.name','.price'),
 'linesv':('.shop-item, .product-item, .product','.name a, .product-title a, h3 a','.price'),
 'skeo':('#yoo-zoo .jbzoo-item-teaser','h3.item-title a','.item-price .price, [itemprop="price"]'),
 'kabis':('article, [data-product-id]','a[href*="/product/"]','[data-price], .price'),
 'etm':('[class*="listItem-item"]','a[href*="/cat/nn/"]','[data-testid^="catalog-list-item-price-details-"]:not([data-testid$="-unit"]), [data-testid^="catalog-list-item-price560-"]:not([data-testid$="-unit"])'),
}
EXCLUDED=re.compile(r'термометр|медицин|водоснаб|сантех|затироч|бетономеш|бензопил|садов|насос|электродвигател|автомобиль|бытов[а-я]+\s|опалубк',re.I)
FORBIDDEN=re.compile(r'/(?:news|novosti|article|blog|company|about|contacts?|auth|cart|basket|compare|search|brand|upload|image|arhiv|archive)(?:/|$)',re.I)
CAT_CLASSES=re.compile(r'categor|section|subcategory|catalog-menu|sidebar|pagination|pager|navigation|jshop_categ|menu',re.I)

def scope_allowed(src,url):
 if not c.safe_url(src,url):return False
 path=urlsplit(url).path
 if src['id']=='etm':
  return path=='/catalog/090_telekommunikacionnoe_oborudovanie_i_sks' or any(re.match(r'/catalog/'+re.escape(code)+r'(?:\d*_)',path) for code in src.get('categoryPrefixes',[]))
 return any(path==urlsplit(seed).path.rstrip('/') or path.startswith(urlsplit(seed).path.rstrip('/')+'/') for seed in src['seeds'])

def blocked(soup):
 title=c.text(soup.title);body=c.text(soup)[:2000]
 return bool(re.search(r'подтвердите.{0,30}человек|я не робот|access denied|checking your browser|just a moment|antibot|javascript отключен',title+' '+body,re.I))

def ignored(node):
 return node.find_parent(class_=re.compile(r'modal|cart-related|recommend|viewed|recent|similar|upsell|swiper|slick-slide',re.I)) is not None

def get_prices(card,selector):
 result=[];nodes=card.select(selector)
 for node in nodes:
  if node.find_parent(['s','del','strike']) or node.find_parent(class_=re.compile(r'old[_-]?price|price[_-]?old',re.I)):continue
  if node.has_attr('itemprop') and node['itemprop']=='price':raw=node.get('content') or c.text(node)
  else:raw=node.get('data-value') or c.text(node)
  if not raw or re.search('запрос|авторизац|войдите',raw,re.I):continue
  # A price container may have several monetary values: only its specific current-price child is usable.
  if len(re.findall(r'\d[\d\s\xa0]*(?:[.,]\d+)?\s*(?:₽|руб)',raw))>1:continue
  if re.search(r'\bот\s+\d',raw,re.I):condition=raw
  else:condition=''
  row=node.find_parent(class_='price__item')
  row_label=c.text(row.select_one('.price__name')) if row else ''
  tooltip=node.select_one('[data-content]')
  if tooltip:condition=tooltip['data-content']
  etm_legal=str(node.get('data-testid','')).startswith('catalog-list-item-price560-')
  label=('Для юрлиц' if etm_legal else row_label) or ('Без НДС' if 'price-tax' in node.get('class',[]) else 'Оптовая цена' if 'price-opt-value' in node.get('class',[]) else 'Розничная цена' if node.find_parent(class_='shop_price') else 'Цена на странице')
  value=c.price(label,raw,currency='RUB',unit=c.unit_from(c.text(node.parent)),condition=condition,tax='Без НДС' if label=='Без НДС' else '')
  if value and not any((p['amount'],p['label'])==(value['amount'],value['label']) for p in result):result.append(value)
 return result

def listing(src,url,html):
 soup=BeautifulSoup(html,'html.parser')
 if blocked(soup):raise PermissionError('Public browser verification required')
 if src['id'] not in PROFILES:raise ValueError('Missing source profile')
 sel,name_sel,price_sel=PROFILES[src['id']];products={};title=c.text(soup.select_one('h1'));cards=soup.select(sel)
 for card in cards:
  if ignored(card):continue
  # Ignore catalogue AggregateOffer metadata, which is not an individual product.
  if card.select_one('[itemtype$="/AggregateOffer"]'):continue
  name_node=card if src['id']=='investtelecom' else card.select_one(name_sel)
  if name_node is None:continue
  a=name_node if name_node.get('href') else name_node.find_parent('a',href=True)
  if a is None:continue
  name=c.text(name_node) or a.get('title','');link=c.canonical(src,urljoin(src['url'] if not a['href'].startswith(('/','http')) else url,a['href']))
  if src['id']=='alphanets':name+=' '+c.text(card.select_one('.article-container'))
  if not link or not name or len(name)>600 or EXCLUDED.search(name):continue
  if src['id']=='progress' and '/product-' not in link:continue
  if src['id']=='hard' and not card.select_one('.item-price, .item-marking'):continue
  # Structural cards that only link to categories must not become products.
  if src['id'] in ('alphanets','skp') and not card.select_one('[itemprop="offers"], .price, .jshop_price, .product-price, button[onclick*="cart"], input[name="product_id"]'):continue
  p=c.make(src,link,name,category_path=title)
  if not p:continue
  if src['id']=='netsol' and p['category']=='Прочие комплектующие':continue
  p.update(prices=get_prices(card,price_sel),priceText='Цена по запросу' if re.search(r'по запросу|уточн.{0,12}цен',c.text(card),re.I) else '',availability=c.text(card.select_one('.item-stock, .stock-label, .product-small__stock, .shop-property, .green-href, .nal, .stock, .availability')))
  sku=card.select_one('.sku,.skutop,.item-marking,.js-articles,.js-replace-article,.product-small__vendor-code')
  if sku:p['sku']=re.sub(r'^(?:Артикул|Код)\s*:\s*','',c.text(sku),flags=re.I)
  if src['id']=='etm':
   p['availability']=c.text(card.select_one('[class*="availability-availRoot"]'))
   for amount in p['prices']:
    if amount['label']=='Для юрлиц':amount['condition']='Для юридических лиц'
   label=card.find(string=re.compile(r'^Артикул$'))
   if label and label.parent.find_next_sibling('span'):p['sku']=c.text(label.parent.find_next_sibling('span'))
  brand=card.select_one('.catalog-card__brand-name, .brand img[alt], [data-testid="link-good-brand"]')
  if brand:p['brandDeclaration']=brand.get('alt') or c.text(brand)
  p['sourceCategoryUrl']=url;p['catalogueParser']='extended-v1';products[p['id']]=p
 links=[];product_urls={p['url'] for p in products.values()}
 for a in soup.select('a[href]'):
  href=c.canonical(src,urljoin(src['url'] if not a['href'].startswith(('/','http')) else url,a['href']))
  if not href or href in product_urls or FORBIDDEN.search(urlsplit(href).path) or not scope_allowed(src,href):continue
  # Follow actual category navigation and pagination, not arbitrary product/recommendation URLs.
  ancestors=[a,*list(a.parents)[:4]]
  extra=(src['id']=='hard' and a.find_parent(class_='product-item') is not None and not a.find_parent(class_='product-item').select_one('.item-price')) or (src['id']=='progress' and '/product-' not in href and a.find_parent(class_='card') is not None)
  if src['id']=='skeo' and a.find_parent('h2') is not None and a.find_parent(id='yoo-zoo') is not None:extra=True
  if extra or any(CAT_CLASSES.search(' '.join(n.get('class',[]))) for n in ancestors if getattr(n,'attrs',None)) or a.get('rel')==['next'] or re.search(r'[?&](?:page|PAGEN_\d|start|limitstart)=',a['href']):links.append(href)
 # Catalog-only suppliers can expose the product page as a link-card without a price.
 return list(products.values()),list(dict.fromkeys(links))

def details(src,record,html):
 soup=BeautifulSoup(html,'html.parser')
 if blocked(soup):raise PermissionError('Public browser verification required')
 title=c.text(soup.select_one('h1'))
 if not title or c.norm(title)!=c.norm(record['name']):raise ValueError('Different current product')
 # Structured Product must have matching identity and actual Offer, never global recommendations.
 product=None
 for node in soup.select('[itemtype$="/Product"]'):
  name=node.select_one('[itemprop="name"]');value=(name.get('content') or c.text(name)) if name else ''
  if c.norm(value)==c.norm(title) and node.select_one('[itemprop="offers"]'):product=node;break
 if product is None:
  for selector in ['.item_main_info','.product-detail','.product-card-detail','.product-info','#product','.product-page','article.node-product','.product-full']:
   candidate=soup.select_one(selector)
   if candidate is not None:product=candidate;break
 if product is None:raise ValueError('Current product scope missing')
 selector=PROFILES[src['id']][2];prices=get_prices(product,selector)
 if not prices:prices=get_prices(product,'[itemprop="price"]')
 out={**record,'properties':{},'checkedAt':c.now(),'detailCheckedAt':c.now()}
 if prices:out['prices']=prices
 # Keep scoped catalogue offers when a detail page does not expose prices (e.g. dynamic pricing).
 for row in product.select('tr, [itemprop="additionalProperty"]'):
  if row.get('itemprop')=='additionalProperty':cells=[row.select_one('[itemprop="name"]'),row.select_one('[itemprop="value"]')]
  else:cells=row.find_all(['th','td'],recursive=False)
  if len(cells)==2 and all(cells):
   key,val=map(c.text,cells)
   if key and val and len(key)<120 and len(val)<1500:out['properties'][key]=val;c.makers.declaration(out,key,val)
 stock=product.select_one('.item-stock, .product-stock, .availability, .stock-label')
 if stock:out['availability']=c.text(stock)
 return c.makers.read_claims(out,soup)

def document_products(src,raw):
 import io,zipfile,hashlib,openpyxl
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if sum(i.file_size for i in z.infolist())>75_000_000:raise ValueError('Price document too large')
 sheet=openpyxl.load_workbook(io.BytesIO(raw),read_only=True,data_only=True).active
 if sheet.max_row>100000 or sheet.max_column>30:raise ValueError('Unexpected price document')
 if src['id']=='anlan':return anlan_document_products(src,sheet)
 products=[];group=''
 for rownum,row in enumerate(sheet.iter_rows(values_only=True),1):
  name=str(row[0] or '').strip();amount=row[9] if len(row)>9 else None
  if name and not isinstance(amount,(int,float)):
   group=name;continue
  if not name or not isinstance(amount,(int,float)) or amount<=0 or EXCLUDED.search(name):continue
  # The supplier publishes one amount per product in column J; no availability or tax is inferred.
  identity='price-'+hashlib.sha256(name.encode()).hexdigest()[:16]
  p=c.make(src,src['priceDocument'],name,category_path=group)
  if not p or p['category']=='Прочие комплектующие' and not re.search('pon|sfp|оптич|волс|витая|патч|муфт|кросс|кабел|зажим|коннектор|адаптер|коммутатор|маршрутизатор|трансивер',name+' '+group,re.I):continue
  unit=re.search(r',\s*(шт|м|км|компл|упак)\.?\s*$',name)
  value=c.price('Цена по прайсу',str(amount),currency='RUB',unit=unit[1] if unit else '')
  if value:
   p.update(id=c.product_id(src,p['url'],identity),sourceProductId=identity,sourceLinkLabel='Официальный прайс · строка '+str(rownum),prices=[value],sourceDocumentRow=rownum,detailCheckedAt=c.now(),catalogueParser='netsol-public-xlsx-v1')
   products.append(p)
 return products

def kabis_products(src,payload):
 data=json.loads(payload);rows=data.get('data',[])
 if data.get('success') is not True or not isinstance(rows,list):raise ValueError('Invalid public KABIS response')
 products=[]
 for raw in rows:
  if raw.get('is_active') is not True or not str(raw.get('id','')).isdigit():continue
  name=str(raw.get('name','')).strip();group=raw.get('category') or {};path=group.get('name','') if isinstance(group,dict) else str(group)
  if not name or EXCLUDED.search(name):continue
  url=src['url']+'?'+__import__('urllib.parse',fromlist=['urlencode']).urlencode({'view':'product','id':raw['id']});p=c.make(src,url,name,category_path=path)
  if p['category']=='Прочие комплектующие' and not re.search('оптич|волс|pon|sfp|витая|патч|муфт|кросс|кабел|зажим|коннектор|адаптер|коммутатор|маршрутизатор|терминал|трансивер|инструмент',name+' '+path,re.I):continue
  price=c.price('Цена на странице',str(raw.get('discount_price') or raw.get('price') or ''),currency='RUB',unit=str(raw.get('unit') or ''))
  p.update(sku=str(raw.get('article') or raw.get('sku') or ''),prices=[price] if price else [],availability=('В наличии: '+str(raw['stock'])+' '+str(raw.get('unit') or '')) if isinstance(raw.get('stock'),(int,float)) and raw['stock']>0 else 'Наличие уточняется',properties={str(k):str(v) for k,v in (raw.get('specifications') or {}).items()} if isinstance(raw.get('specifications'),dict) else {},description=BeautifulSoup(str(raw.get('description') or ''),'html.parser').get_text(' ',strip=True),detailCheckedAt=c.now(),catalogueParser='kabis-public-v1')
  # Only the public base/discount amount is used; old_price and private/accounting data are excluded.
  products.append(p)
 return products,data.get('pagination') or {}


def anlan_document_products(src,sheet):
 import hashlib
 products=[];group='';hierarchy=[]
 roots={'Шкафы и стойки 19\"','Кабельная продукция','Компоненты СКС','Металлические кабеленесущие системы','Оптика','Инструмент, протяжки','Монтажные материалы','Источники электропитания','Активное оборудование','Кабель-каналы и аксессуары для монтажа','Труба гофрированная, гладкая, металлорукав'}
 allowed=re.compile(r'шкаф|стойк|оптич|кабел|скс|сетев|коммутатор|маршрутизатор|медиконвертер|медиаконвертер|трансивер|патч|кросс|муфт|адаптер|коннектор|инструмент|крепеж|крепёж|заземлен|заземлён|органайзер|розетк|pdu|sfp|pon',re.I)
 for rownum,row in enumerate(sheet.iter_rows(values_only=True),1):
  if len(row)<8:continue
  if row[0] and not row[1] and not row[2]:
   heading=str(row[0]).strip();depth=len(re.match(r'^(?:—\s*)*',heading)[0].replace(' ',''));hierarchy=hierarchy[:depth]+[heading.lstrip('— ').strip()];group=' / '.join(hierarchy);continue
  code,sku,name=map(lambda x:str(x or '').strip(),row[:3])
  if not code or not sku or not name or EXCLUDED.search(name) or not hierarchy or hierarchy[0] not in roots or re.search(r'силовой|электропровод|usb|hdmi|lightning|монитор|ноутбук|смартфон|для компьютера',group+' '+name,re.I) or not allowed.search(group+' '+name):continue
  p=c.make(src,src['priceDocument'],name,category_path=group)
  if not p:continue
  prices=[]
  for index,label,condition in [(3,'Розница',''),(4,'От 25 тыс. руб.','При сумме заказа от 25 000 руб.'),(5,'От 100 тыс. руб.','При сумме заказа от 100 000 руб.')]:
   raw=str(row[index] or '')
   if re.search(r'запрос|авториз',raw,re.I):continue
   value=c.price(label,raw,currency='RUB',condition=condition,tax='С НДС')
   if value:prices.append(value)
  identity='price-'+hashlib.sha256(code.encode()).hexdigest()[:16]
  p.update(id=c.product_id(src,p['url'],identity),sourceProductId=identity,sku=sku,brandDeclaration=str(row[7] or ''),availability=str(row[6] or ''),prices=prices,sourceDocumentRow=rownum,sourceLinkLabel='Официальный прайс · строка '+str(rownum),detailCheckedAt=c.now(),catalogueParser='anlan-public-xlsx-v1')
  products.append(p)
 return products
