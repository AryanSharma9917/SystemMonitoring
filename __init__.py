import pandas as pd
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from utils import *

APP_VERSION = "1.0.0"
APP_NAME = "Recommendation Engine"
API_PREFIX = "/"
NAMESPACE = "recommendation_engine"
SUBSYSTEM = "online_store"
DATA_PATH = "data/"

user_user_sim_matrix = pd.read_pickle(DATA_PATH+'user_user_sim_matrix.p')
item_item_sim_matrix = pd.read_pickle(DATA_PATH+'item_item_sim_matrix.p')
customer_item_matrix = pd.read_pickle(DATA_PATH+'customer_item_matrix.p')
df = pd.read_pickle(DATA_PATH+'df.p')


app = FastAPI(title="Recommendation Engine",  version=APP_VERSION,
              description="This API is built for Recommendation Engine Backend services.")

instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_respect_env_var=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics", "/metrics/"],
    env_var_name="ENABLE_METRICS",
    inprogress_name="inprogress",
    inprogress_labels=True
)

instrumentator.add(
    metrics.request_size(
        should_include_handler=True,
        should_include_method=True,
        should_include_status=True,
        metric_namespace=NAMESPACE,
        metric_subsystem=SUBSYSTEM))
instrumentator.add(
    metrics.response_size(
        should_include_handler=True,
        should_include_method=True,
        should_include_status=True,
        metric_namespace=NAMESPACE,
        metric_subsystem=SUBSYSTEM))
instrumentator.add(
    metrics.requests(
        should_include_handler=True,
        should_include_method=True,
        should_include_status=True,
        metric_namespace=NAMESPACE,
        metric_subsystem=SUBSYSTEM))
instrumentator.add(
    metrics.latency(
        should_include_handler=True,
        should_include_method=True,
        should_include_status=True,
        metric_namespace=NAMESPACE,
        metric_subsystem=SUBSYSTEM))

Instrumentator().instrument(app).expose(app, tags=["metrics"])


@app.get("/", status_code=200, summary="Returns 200 for healthcheck.", tags=["root"])
def index():
    return {"staus": "ok"}


@app.get("/predict/user/{user_id}", summary="Returns user-based recommendations", response_description="User Based Recommendation Results.", tags=["prediction"])
async def predict(user_id: str = '12350', n: int = 5):

    pred = recommend_customer(user_user_sim_matrix,
                              customer_item_matrix, df, user_id, n=n)

    return {"success": True, "type": "user_based", "total": n, "data": {user_id: str(pred)}}


@app.get("/predict/item/{item_id}", summary="Returns item-based recommendations", response_description="Item Based Recommendation Results.", tags=["prediction"])
async def predict(item_id: str, n: int = 5):

    pred = get_similar_items(item_item_sim_matrix, item_id, n=n)

    return {"success": True, "type": "item_based", "total": n, "data": {item_id: str(pred)}}
