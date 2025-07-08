from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from datetime import timedelta
import os

DEFAULT_ARGS = {
    "owner": "scraper_team",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "tiktok_shop_hourly",
    default_args=DEFAULT_ARGS,
    schedule="@hourly",
    start_date=days_ago(1),
    catchup=False,
)

with dag:
    crawl = BashOperator(
        task_id="crawl",
        bash_command="python -m tiktok_scraper.scraper",
        env=os.environ,
    )

    etl = BashOperator(
        task_id="etl",
        bash_command="python -m etl.consume_kafka",
        env=os.environ,
    )

    crawl >> etl