"""Usage: python update_closure_prices.py [--ids PRODUCT_ID ...]."""
import argparse,json
import crm_store,closure_prices
if __name__=='__main__':
 parser=argparse.ArgumentParser(description='Обновить публичные цены муфт с сайтов поставщиков');parser.add_argument('--ids',nargs='+');args=parser.parse_args()
 crm_store.init();closure_prices.init();job=closure_prices.start('scheduled-price-update',args.ids,background=False);state=closure_prices.snapshot();print(json.dumps({'jobId':job,'job':state['job']},ensure_ascii=False))
