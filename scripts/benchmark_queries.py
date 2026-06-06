from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
import csv
import math
import os
import statistics
import warnings

import pandas as pd
import urllib3
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk, scan

import generate_routes


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"
CSV_PATH = BASE_DIR / "data" / "generated" / "generated_routes_sample.csv"
REPORT_PATH = BASE_DIR / "reports" / "benchmark_results.csv"

GEO_INDEX = "lokalizacje_geo"
PLAIN_INDEX = "lokalizacje_plain"

DISTANCE_METERS = 2
COLLISION_METERS = 1
HUMIDITY_THRESHOLD = 70

if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

client = OpenSearch(
    hosts=["https://localhost:9200"],
    http_auth=(
        "admin",
        os.getenv("OPENSEARCH_PASSWORD"),
    ),
    use_ssl=True,
    verify_certs=False,
    timeout=5,
    max_retries=0,
    retry_on_timeout=False,
)


def load_routes():
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH)
    return generate_routes.generate_routes()


def make_sensors(df, bucket_from, bucket_to):
    bad_to = bucket_from + (bucket_to - bucket_from) // 2
    data = df.copy()
    data["time_bucket"] = data["timestamp"].apply(lambda timestamp: int(round(timestamp * 10)))
    data = data[(data["time_bucket"] >= bucket_from) & (data["time_bucket"] <= bad_to)]

    if data.empty:
        data = df.copy()

    data = data.reset_index(drop=True)
    positions = [0.25, 0.50, 0.75]
    sensors = []

    for sensor_id, position in enumerate(positions, start=1):
        row = data.iloc[min(int(len(data) * position), len(data) - 1)]
        sensors.append(
            {
                "id": sensor_id,
                "lat": float(row["latitude"]),
                "lon": float(row["longitude"]),
                "bad_from": bucket_from,
                "bad_to": bad_to,
                "humidity_bad": 85,
                "humidity_ok": 45,
            }
        )

    return sensors


def make_docs(df, index_name, with_location):
    for _, row in df.iterrows():
        lat = float(row["latitude"])
        lon = float(row["longitude"])
        doc = {
            "Id": int(row["Id"]),
            "timestamp": float(row["timestamp"]),
            "time_bucket": int(round(float(row["timestamp"]) * 10)),
            "latitude": lat,
            "longitude": lon,
        }
        if with_location:
            doc["location"] = {"lat": lat, "lon": lon}
        yield {"_index": index_name, "_source": doc}


def opensearch_is_running():
    try:
        client.info()
        return True
    except Exception as error:
        print("OpenSearch nie dziala na https://localhost:9200")
        print("Najpierw uruchom: docker compose up -d")
        print(f"Blad: {error}")
        return False


def prepare_indices(df):
    geo_body = {
        "settings": {"index": {"requests.cache.enable": True}},
        "mappings": {
            "properties": {
                "Id": {"type": "integer"},
                "timestamp": {"type": "double"},
                "time_bucket": {"type": "long"},
                "latitude": {"type": "double"},
                "longitude": {"type": "double"},
                "location": {"type": "geo_point"},
            }
        },
    }

    plain_body = {
        "mappings": {
            "properties": {
                "Id": {"type": "integer", "index": False},
                "timestamp": {"type": "double", "index": False},
                "time_bucket": {"type": "long", "index": False},
                "latitude": {"type": "double", "index": False},
                "longitude": {"type": "double", "index": False},
            }
        },
    }

    results = []

    start = perf_counter()
    if client.indices.exists(index=GEO_INDEX):
        client.indices.delete(index=GEO_INDEX)
    client.indices.create(index=GEO_INDEX, body=geo_body)
    bulk(client, make_docs(df, GEO_INDEX, True))
    client.indices.refresh(index=GEO_INDEX)
    results.append(("build_index", "geo_index", perf_counter() - start, len(df)))

    start = perf_counter()
    if client.indices.exists(index=PLAIN_INDEX):
        client.indices.delete(index=PLAIN_INDEX)
    client.indices.create(index=PLAIN_INDEX, body=plain_body)
    bulk(client, make_docs(df, PLAIN_INDEX, False))
    client.indices.refresh(index=PLAIN_INDEX)
    results.append(("build_index", "no_geo_index", perf_counter() - start, len(df)))

    return results


def get_area(df):
    lat_min = df["latitude"].quantile(0.25)
    lat_max = df["latitude"].quantile(0.75)
    lon_min = df["longitude"].quantile(0.25)
    lon_max = df["longitude"].quantile(0.75)
    ts_min = float(df["timestamp"].min())
    ts_max = float(df["timestamp"].max())
    window_start = ts_min + (ts_max - ts_min) * 0.40
    window_end = window_start + min(10, (ts_max - ts_min) * 0.25)
    center = {
        "lat": float(df["latitude"].mean()),
        "lon": float(df["longitude"].mean()),
    }
    sensors = make_sensors(df, int(round(window_start * 10)), int(round(window_end * 10)))
    return (
        float(lat_min),
        float(lat_max),
        float(lon_min),
        float(lon_max),
        center,
        int(round(window_start * 10)),
        int(round(window_end * 10)),
        sensors,
    )


def geo_geofencing(params):
    lat_min, lat_max, lon_min, lon_max, _, bucket_from, bucket_to, _ = params
    body = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"range": {"time_bucket": {"gte": bucket_from, "lte": bucket_to}}},
                    {
                        "geo_bounding_box": {
                            "location": {
                                "top_left": {"lat": lat_max, "lon": lon_min},
                                "bottom_right": {"lat": lat_min, "lon": lon_max},
                            }
                        }
                    },
                ]
            }
        },
    }
    result = client.search(index=GEO_INDEX, body=body)
    return result["hits"]["total"]["value"]


def geo_proximity(params):
    _, _, _, _, _, _, _, sensors = params
    count = 0

    for sensor in sensors:
        if sensor["humidity_bad"] <= HUMIDITY_THRESHOLD:
            continue

        body = {
            "size": 0,
            "query": {
                "bool": {
                    "filter": [
                        {
                            "range": {
                                "time_bucket": {
                                    "gte": sensor["bad_from"],
                                    "lte": sensor["bad_to"],
                                }
                            }
                        },
                        {
                            "geo_distance": {
                                "distance": f"{DISTANCE_METERS}m",
                                "location": {
                                    "lat": sensor["lat"],
                                    "lon": sensor["lon"],
                                },
                            }
                        },
                    ]
                }
            },
        }
        result = client.search(index=GEO_INDEX, body=body)
        count += result["hits"]["total"]["value"]

    return count


def fetch_all_plain():
    docs = scan(
        client,
        index=PLAIN_INDEX,
        query={"query": {"match_all": {}}},
        _source=["Id", "timestamp", "time_bucket", "latitude", "longitude"],
    )
    return [item["_source"] for item in docs]


def plain_geofencing(params):
    lat_min, lat_max, lon_min, lon_max, _, bucket_from, bucket_to, _ = params
    count = 0
    for doc in fetch_all_plain():
        in_time = bucket_from <= doc["time_bucket"] <= bucket_to
        in_area = lat_min <= doc["latitude"] <= lat_max and lon_min <= doc["longitude"] <= lon_max
        if in_time and in_area:
            count += 1
    return count


def haversine_meters(lat1, lon1, lat2, lon2):
    radius = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def plain_proximity(params):
    _, _, _, _, _, bucket_from, bucket_to, sensors = params
    count = 0
    for doc in fetch_all_plain():
        if not bucket_from <= doc["time_bucket"] <= bucket_to:
            continue
        for sensor in sensors:
            if sensor["bad_from"] <= doc["time_bucket"] <= sensor["bad_to"]:
                humidity = sensor["humidity_bad"]
            else:
                humidity = sensor["humidity_ok"]

            if humidity <= HUMIDITY_THRESHOLD:
                continue
            dist = haversine_meters(
                sensor["lat"],
                sensor["lon"],
                doc["latitude"],
                doc["longitude"],
            )
            if dist <= DISTANCE_METERS:
                count += 1
    return count


def fetch_geo_docs(params):
    _, _, _, _, _, bucket_from, bucket_to, _ = params
    body = {
        "query": {
            "range": {
                "time_bucket": {
                    "gte": bucket_from,
                    "lte": bucket_to,
                }
            }
        },
        "_source": ["Id", "timestamp", "time_bucket", "latitude", "longitude"],
    }
    docs = scan(client, index=GEO_INDEX, query=body)
    return [item["_source"] for item in docs]


def count_collisions(docs):
    grouped = {}
    for doc in docs:
        grouped.setdefault(doc["time_bucket"], []).append(doc)

    collisions = 0
    for group in grouped.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                first = group[i]
                second = group[j]
                if first["Id"] == second["Id"]:
                    continue
                dist = haversine_meters(
                    first["latitude"],
                    first["longitude"],
                    second["latitude"],
                    second["longitude"],
                )
                if dist <= COLLISION_METERS:
                    collisions += 1
    return collisions


def plain_collisions(params):
    _, _, _, _, _, bucket_from, bucket_to, _ = params
    docs = [
        doc
        for doc in fetch_all_plain()
        if bucket_from <= doc["time_bucket"] <= bucket_to
    ]
    return count_collisions(docs)


def measure(name, variant, func, params, repeats=10):
    rows = []
    for run in range(1, repeats + 1):
        start = perf_counter()
        count = func(params)
        seconds = perf_counter() - start
        rows.append(
            {
                "task": name,
                "variant": variant,
                "test": "normal",
                "users": 1,
                "run": run,
                "seconds": seconds,
                "count": count,
            }
        )
    return rows


def measure_cache(name, func, params):
    rows = []
    for run in range(1, 6):
        start = perf_counter()
        count = func(params)
        seconds = perf_counter() - start
        rows.append(
            {
                "task": name,
                "variant": "geo_index",
                "test": "cache_first" if run == 1 else "cache_next",
                "users": 1,
                "run": run,
                "seconds": seconds,
                "count": count,
            }
        )
    return rows


def measure_concurrency(name, func, params, users):
    def one_run(run):
        start = perf_counter()
        count = func(params)
        return {
            "task": name,
            "variant": "geo_index",
            "test": "concurrency",
            "users": users,
            "run": run,
            "seconds": perf_counter() - start,
            "count": count,
        }

    with ThreadPoolExecutor(max_workers=users) as executor:
        return list(executor.map(one_run, range(1, users + 1)))


def print_summary(rows):
    groups = {}
    for row in rows:
        key = (row["task"], row["variant"], row["test"], row["users"])
        groups.setdefault(key, []).append(row["seconds"])

    print("\nSummary:")
    for key, times in sorted(groups.items()):
        task, variant, test, users = key
        print(
            f"{task:12} {variant:12} {test:12} users={users:<2} "
            f"avg={statistics.mean(times):.4f}s "
            f"min={min(times):.4f}s "
            f"max={max(times):.4f}s"
        )


def save_report(rows):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["task", "variant", "test", "users", "run", "seconds", "count"],
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    if not opensearch_is_running():
        return

    df = load_routes()
    params = get_area(df)

    rows = []
    for task, variant, seconds, count in prepare_indices(df):
        rows.append(
            {
                "task": task,
                "variant": variant,
                "test": "build",
                "users": 1,
                "run": 1,
                "seconds": seconds,
                "count": count,
            }
        )

    tests = [
        ("geofencing", geo_geofencing, plain_geofencing),
        ("proximity", geo_proximity, plain_proximity),
        ("collisions", lambda params: count_collisions(fetch_geo_docs(params)), plain_collisions),
    ]

    for name, geo_func, plain_func in tests:
        rows += measure(name, "geo_index", geo_func, params)
        rows += measure(name, "no_geo_index", plain_func, params)
        rows += measure_cache(name, geo_func, params)
        rows += measure_concurrency(name, geo_func, params, users=5)
        rows += measure_concurrency(name, geo_func, params, users=10)

    save_report(rows)
    print_summary(rows)
    print(f"\nSaved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
