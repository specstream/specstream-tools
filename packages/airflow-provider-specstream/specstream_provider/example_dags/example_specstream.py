"""Search the live web, read the pages it found, and build a list, each in its own task.

Set up a connection named specstream_default of type SpecStream with your API key, or export
AIRFLOW_CONN_SPECSTREAM_DEFAULT='{"conn_type": "specstream", "password": "<your API key>"}'.
"""

from __future__ import annotations

from datetime import datetime

try:
    from airflow.sdk import DAG
except ImportError:
    from airflow import DAG

from specstream_provider.operators.specstream import (
    SpecStreamDeepSearchOperator,
    SpecStreamExtractOperator,
    SpecStreamSearchOperator,
)

with DAG(dag_id="example_specstream", start_date=datetime(2026, 1, 1), schedule=None, catchup=False, tags=["specstream"]):
    search = SpecStreamSearchOperator(task_id="search", query="Apache Airflow latest release", speed="fast")

    read = SpecStreamExtractOperator(
        task_id="read",
        urls="{{ ti.xcom_pull(task_ids='search')['sources'][0]['url'] }}",
    )

    deep = SpecStreamDeepSearchOperator(
        task_id="deep_search",
        request="Open-source workflow orchestrators with their website and license",
        max_results=25,
        max_price_usd=5,
        retries=2,
    )

    search >> read
