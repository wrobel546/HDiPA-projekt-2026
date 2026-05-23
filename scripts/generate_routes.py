from pathlib import Path
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "generated" / "generated_routes_sample.csv"
PLOT_PATH = Path(__file__).resolve().parents[1] / "reports" / "generated_routes_sample.png"

NUM_ROBOTS = 10
START_TS = 1714398000.523
END_TS = START_TS + 100
INTERVAL_SECONDS = 0.1

AVG_ACTIVE_ROBOTS = 5

LAT_MIN = 52.401220
LAT_MAX = 52.401965
LON_MIN = 16.951101
LON_MAX = 16.952410

RANDOM_SEED = int(time.time())


def clamp_position(lat, lon):
    lat = min(max(lat, LAT_MIN), LAT_MAX)
    lon = min(max(lon, LON_MIN), LON_MAX)
    return lat, lon


def generate_routes():
    rng = np.random.default_rng(RANDOM_SEED)

    total_time = END_TS - START_TS
    route_time = total_time * min(AVG_ACTIVE_ROBOTS, NUM_ROBOTS) / NUM_ROBOTS

    lat_margin = (LAT_MAX - LAT_MIN) * 0.10
    lon_margin = (LON_MAX - LON_MIN) * 0.10

    safe_lat_min = LAT_MIN + lat_margin
    safe_lat_max = LAT_MAX - lat_margin
    safe_lon_min = LON_MIN + lon_margin
    safe_lon_max = LON_MAX - lon_margin

    max_start_offset = max(total_time - route_time, 0)
    step_size = min(LAT_MAX - LAT_MIN, LON_MAX - LON_MIN) * 0.0025

    rows = []

    for robot_id in range(1, NUM_ROBOTS + 1):
        if NUM_ROBOTS == 1:
            start_offset = 0
        else:
            start_offset = max_start_offset * (robot_id - 1) / (NUM_ROBOTS - 1)

        if robot_id != 1:
            start_offset += rng.normal(0, route_time * 0.08)
            start_offset = min(max(start_offset, 0), max_start_offset)

        start_offset = round(start_offset / INTERVAL_SECONDS) * INTERVAL_SECONDS
        robot_start = START_TS + start_offset
        robot_end = robot_start + route_time

        timestamps = np.arange(
            robot_start,
            robot_end + INTERVAL_SECONDS / 2,
            INTERVAL_SECONDS,
        )

        lat = rng.uniform(safe_lat_min, safe_lat_max)
        lon = rng.uniform(safe_lon_min, safe_lon_max)
        dir = rng.uniform(0, 2 * np.pi)
        speed = rng.uniform(step_size * 0.6, step_size * 1.2)

        for timestamp in timestamps:
            dir += rng.normal(0, 0.12)
            speed = 0.95 * speed + 0.05 * rng.uniform(step_size * 0.5, step_size * 1.3)

            new_lat = lat + np.sin(dir) * speed
            new_lon = lon + np.cos(dir) * speed

            if new_lat < safe_lat_min or new_lat > safe_lat_max:
                dir = -dir
                new_lat = lat

            if new_lon < safe_lon_min or new_lon > safe_lon_max:
                dir = np.pi - dir
                new_lon = lon

            new_lat, new_lon = clamp_position(new_lat, new_lon)

            lat = new_lat
            lon = new_lon

            rows.append(
                {
                    "Id": robot_id,
                    "timestamp": round(float(timestamp), 3),
                    "latitude": round(float(lat), 7),
                    "longitude": round(float(lon), 7),
                }
            )

    routes_df = pd.DataFrame(rows)
    routes_df = routes_df.sort_values(["Id", "timestamp"]).reset_index(drop=True)

    return routes_df


def save_routes_plot(routes_df):
    fig, ax = plt.subplots(figsize=(10, 7))

    grouped_routes = list(routes_df.groupby("Id"))

    color_map = plt.colormaps["hsv"]
    colors = color_map(np.linspace(0, 1, len(grouped_routes), endpoint=False))

    for i, (robot_id, robot_df) in enumerate(grouped_routes):
        robot_df = robot_df.sort_values("timestamp")

        ax.plot(
            robot_df["longitude"],
            robot_df["latitude"],
            linewidth=2,
            color=colors[i],
            label=f"Robot {robot_id}",
        )

    ax.set_title("Wygenerowane trasy robotow")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.grid(True)
    ax.axis("equal")

    if len(grouped_routes) <= 15:
        ax.legend(loc="best", fontsize=9)

    fig.tight_layout()
    fig.savefig(PLOT_PATH, dpi=150)
    plt.close(fig)


def main():
    routes_df = generate_routes()
    routes_df.to_csv(CSV_PATH, index=False)

    print("Liczba wygenerowanych punktow:", len(routes_df))
    print("Liczba robotow:", routes_df["Id"].nunique())
    print("Zakres czasu:")
    print(routes_df["timestamp"].min(), "-", routes_df["timestamp"].max())
    print("Zapisano plik:", CSV_PATH)

    print(
        routes_df.groupby("Id").agg(
            points_count=("timestamp", "count"),
            start_time=("timestamp", "min"),
            end_time=("timestamp", "max"),
            min_lat=("latitude", "min"),
            max_lat=("latitude", "max"),
            min_lon=("longitude", "min"),
            max_lon=("longitude", "max"),
        )
    )

    save_routes_plot(routes_df)
    print("Zapisano wykres:", PLOT_PATH)


if __name__ == "__main__":
    main()