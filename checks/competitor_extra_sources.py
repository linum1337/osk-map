import sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
import competitor_catalog as c,competitor_sources_extra as extra
from bs4 import BeautifulSoup
src=c.BY_SOURCE['osk'];url=src['seeds'][0]
html='<h1>Кабель ОСК</h1><div class="products-catalog"><div class="product-block"><div class="name"><a href="/kabel-osk/current">Кабель текущий</a></div><div class="price">10.37-46.81 <small>руб./м</small></div></div></div><div class="product-block"><div class="name"><a href="/wrong">Рекомендация</a></div><div class="price">99999 руб.</div></div>'
rows,_=extra.osk_listing(src,url,html);assert len(rows)==1 and [p['amount'] for p in rows[0]['prices']]==['10.37','46.81'];assert all(p['unit']=='м' for p in rows[0]['prices'])
data=[{'ro':{'one':{'product_id':'42','price_prefix':'=','price':'14.99','location':'ОСКД-п-4Е2-1,5','sku':'OC-04'},'wrong':{'product_id':'99','price_prefix':'=','price':'99999'}}}]
page='<h1>Кабель текущий</h1><div class="main-section-block"><div id="product"><input name="product_id" value="42"><div class="price"><span id="product_price">0.00 руб./м</span></div></div></div><script>ro_params[\'ro_data\'] = '+json.dumps(data)+';</script>'
p=extra.osk_details(src,rows[0],page);assert len(p['prices'])==1 and p['prices'][0]['amount']=='14.99' and p['prices'][0]['sku']=='OC-04';assert p['availability']==''
mir=c.BY_SOURCE['mircable'];payload={'categories':[{'slug':'fiber','title':'Оптический кабель','subs':[]}],'products':[{'id':'p1','name':'Кабель один','cat':'fiber','price':100},{'id':'p2','name':'Кабель один','cat':'fiber','price':200}],'showPrices':False,'copy':{'catalog':{'price':'Цена по запросу'}}}
rows=extra.mircable(mir,json.dumps(payload));assert len(rows)==2 and rows[0]['id']!=rows[1]['id'];assert not any(p['prices'] for p in rows),'Respect public price visibility'
payload['showPrices']=True;rows=extra.mircable(mir,json.dumps(payload));assert rows[0]['prices'][0]['amount']=='100.00'
assert 'q=' in rows[0]['url'] and c.safe_url(mir,rows[0]['url'])
print('PASS sources: OSK exact product/variant prices, labelled ranges, no related items or zero placeholders; Mir stable IDs, public visibility and real catalogue links')
