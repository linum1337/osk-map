# Start the durable 24-hour supplier price refresh after the web worker is ready.
def post_worker_init(worker):
 import closure_prices
 closure_prices.start_scheduler()

 import competitor_catalog,threading,time,os
 if os.environ.get('COMPETITOR_PRICES_AUTOMATIC','1')!='0':
  def competitors_daily():
   while True:
    try:
     if competitor_catalog.schedule_due():competitor_catalog.start('automatic-daily')
    except Exception:pass
    time.sleep(60)
  threading.Thread(target=competitors_daily,name='competitors-daily',daemon=True).start()
