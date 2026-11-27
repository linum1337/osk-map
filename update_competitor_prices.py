"""Collect every public network-product price tier from the configured competitors."""
import argparse,json,os
import crm_store,competitor_catalog
if __name__=='__main__':
 p=argparse.ArgumentParser(description='Сбор продукции и всех публичных цен конкурентов');p.add_argument('--sources',nargs='+',choices=list(competitor_catalog.BY_SOURCE));p.add_argument('--catalog-only',action='store_true',help='Загрузить только каталоги без полного обхода карточек');args=p.parse_args()
 crm_store.DB.parent.mkdir(parents=True,exist_ok=True);competitor_catalog.init();job=competitor_catalog.start('command-line',args.sources,not args.catalog_only,background=False)
 with crm_store.connect() as c:
  row=c.execute('SELECT state,phase,source FROM competitor_jobs WHERE id=?',(job,)).fetchone();sources=c.execute('SELECT id,state,checked,last_success FROM competitor_sources').fetchall()
 print(json.dumps({'jobId':job,'result':row,'sources':sources},ensure_ascii=False))
