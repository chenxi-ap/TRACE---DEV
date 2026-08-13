"""
Transaction Intelligence Tool — Flask backend
Auth: Service principal via Databricks OIDC endpoint.
DATABRICKS_HOST, DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET are injected
automatically by the Databricks Apps runtime — do not set them manually.
"""
import os
import time
import logging
import requests
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='.')

_host   = os.environ.get("DATABRICKS_HOST", "adb-7619020834316660.0.azuredatabricks.net")
DB_HOST = _host if _host.startswith("https://") else f"https://{_host}"

# Warehouse ID is extracted from DATABRICKS_HTTP_PATH (e.g. /sql/1.0/warehouses/<id>)
# so you never hard-code it here.
WH_ID         = os.environ.get("DATABRICKS_HTTP_PATH", "").split("/")[-1]
CLIENT_ID     = os.environ.get("DATABRICKS_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("DATABRICKS_CLIENT_SECRET", "")


def get_sp_token():
    """
    Fetch a short-lived token from Databricks' own OIDC endpoint using
    service principal credentials (Basic auth with client_id:client_secret).
    This is identical to the GL dashboard pattern.
    """
    r = requests.post(
        f"{DB_HOST}/oidc/v1/token",
        data={"grant_type": "client_credentials", "scope": "all-apis"},
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def query_table(token, catalog, schema, table, limit, filter_clause=""):
    """Fetch rows using INLINE disposition with chunked pagination."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    where = f"WHERE {filter_clause}" if filter_clause else ""
    sql = f"SELECT * FROM {catalog}.{schema}.{table} {where} LIMIT {limit}"

    logger.info("WH_ID=%s DB_HOST=%s", WH_ID, DB_HOST)
    logger.info("SQL: %s", sql)

    if not WH_ID:
        raise RuntimeError("DATABRICKS_HTTP_PATH is not set or empty — cannot determine warehouse ID.")

    r = requests.post(f"{DB_HOST}/api/2.0/sql/statements", headers=headers, json={
        "warehouse_id": WH_ID,
        "statement": sql,
        "wait_timeout": "0s",
        "format": "JSON_ARRAY",
        "disposition": "INLINE",
    }, timeout=30)

    logger.info("Submit response %d: %s", r.status_code, r.text[:500])

    if not r.ok:
        raise RuntimeError(f"Submit failed {r.status_code}: {r.text[:500]}")

    result = r.json()
    stmt_id = result.get("statement_id")
    if not stmt_id:
        raise RuntimeError(f"No statement_id in response: {result}")

    logger.info("Statement submitted: %s", stmt_id)

    for attempt in range(90):
        state = result.get("status", {}).get("state")
        logger.info("Poll %d: state=%s", attempt, state)
        if state == "SUCCEEDED":
            break
        if state not in ("RUNNING", "PENDING"):
            err = result.get("status", {}).get("error", {})
            raise RuntimeError(f"Query {state}: {err}")
        time.sleep(2)
        r = requests.get(f"{DB_HOST}/api/2.0/sql/statements/{stmt_id}", headers=headers, timeout=30)
        result = r.json()

    if result.get("status", {}).get("state") != "SUCCEEDED":
        raise RuntimeError(f"Query timed out after 90 polls. Last state: {result.get('status',{}).get('state')}")

    cols = [c["name"] for c in result["manifest"]["schema"]["columns"]]
    logger.info("Columns: %s", cols[:5])

    all_data = list(result.get("result", {}).get("data_array", []))
    chunk_index = result.get("result", {}).get("next_chunk_index")

    while chunk_index is not None:
        logger.info("Fetching chunk %s", chunk_index)
        r = requests.get(
            f"{DB_HOST}/api/2.0/sql/statements/{stmt_id}/result/chunks/{chunk_index}",
            headers=headers, timeout=60
        )
        chunk = r.json()
        all_data.extend(chunk.get("data_array", []))
        chunk_index = chunk.get("next_chunk_index")

    rows = [dict(zip(cols, row)) for row in all_data]
    logger.info("Total fetched: %d rows", len(rows))
    return rows


@app.route("/api/data")
def api_data():
    catalog = request.args.get("catalog")
    schema  = request.args.get("schema")
    table   = request.args.get("table")
    limit   = int(request.args.get("limit", 10000))
    filter_ = request.args.get("filter", "")

    if not all([catalog, schema, table]):
        return jsonify({"error": "catalog, schema, and table are required"}), 400

    try:
        token = get_sp_token()
        rows = query_table(token, catalog, schema, table, limit, filter_)
        return jsonify({"rows": rows, "count": len(rows)})
    except Exception as e:
        logger.exception("Error in /api/data")
        import traceback
        tb = traceback.format_exc()
        logger.error("TRACEBACK: %s", tb)
        return jsonify({"error": str(e), "detail": tb}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok", "wh_id": WH_ID})


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT", os.environ.get("PORT", 8000)))
    logger.info("Starting on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
