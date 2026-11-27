# Start the durable 24-hour supplier price refresh after the web worker is ready.
def post_worker_init(worker):
 import closure_prices
 closure_prices.start_scheduler()
