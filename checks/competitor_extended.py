"""Public supplier offers: precise price tiers and document identities."""
import sys,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import competitor_catalog as c
from competitor_sources_extended import get_prices,document_products,kabis_products
from bs4 import BeautifulSoup
from openpyxl import Workbook
import json
card=BeautifulSoup('<div><del><b class="price">9999 руб.</b></del><div class="price__item"><span class="price__name">Мелкий опт</span><span class="price__value">532,16 ₽</span></div></div>','html.parser')
ps=get_prices(card,'.price,.price__value');assert len(ps)==1 and ps[0]['amount']=='532.16' and ps[0]['label']=='Мелкий опт'
w=Workbook();s=w.active;s.append(['Код товара','Артикул','Наименование','Розница','От 25т. руб','От 100т. руб','Наличие','Бренд']);s.append(['Оптика']);s.append(['42','Att-FM LC-SM-3dB','Аттенюатор оптический LC 3dB','636,90','591,80','554,40','в наличии','Cabeus']);s.append(['43','other','Аттенюатор оптический LC 2dB','по запросу','по запросу','по запросу','ожидается','Cabeus']);b=io.BytesIO();w.save(b)
ps=document_products(c.BY_SOURCE['anlan'],b.getvalue());assert len(ps)==2 and len(ps[0]['prices'])==3 and ps[0]['prices'][2]['amount']=='554.40';assert ps[1]['availability']=='ожидается' and not ps[1]['prices'];assert ps[0]['id']!=ps[1]['id'] and ps[0]['prices'][1]['condition'] and ps[0]['prices'][0]['tax']=='С НДС'
rows,pagination=kabis_products(c.BY_SOURCE['kabis'],json.dumps({'success':True,'data':[{'id':287,'is_active':True,'name':'Терминал GPON','price':998,'old_price':99999,'stock':100,'unit':'шт'},{'id':288,'is_active':False,'name':'Муфта скрытая','price':1}],'pagination':{'pages':1}}));assert len(rows)==1 and rows[0]['prices'][0]['amount']=='998.00' and 'id=287' in rows[0]['url'] and '100' in rows[0]['availability']
assert c.canonical(c.BY_SOURCE['kabis'],rows[0]['url'])==rows[0]['url']
print('PASS extended suppliers: current scoped prices, wholesale conditions, XLSX stock/tax, stable identities, inactive products and old prices excluded')
