import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import competitor_catalog as c
from competitor_sources_extended import listing
src=c.BY_SOURCE['skeo'];html='<div id="yoo-zoo"><h2><a href="/katalog/fusion">Сварочное оборудование</a></h2><div class="jbzoo-item jbzoo-item-teaser"><h3 class="item-title"><a href="/katalog/fusion/item">Скалыватель тест</a></h3><div class="item-text">Описание</div></div></div><aside><h3><a href="/news/other">Новости</a></h3></aside>'
products,links=listing(src,src['url']+'katalog/',html)
assert len(products)==1 and products[0]['name']=='Скалыватель тест' and not products[0]['prices'] and not products[0]['availability']
assert links==['https://skeo.ru/katalog/fusion']
print('PASS SKEO: real catalogue cards/category links, unknown price and availability preserved, news excluded')
