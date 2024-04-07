import json

import geopandas as gpd
import movingpandas as mpd
import pandas as pd
import shapely


def geometry_type(ds, x=None, y=None, time=None):
    if x is None:
        x = "longitude"
    if y is None:
        y = "latitude"
    if time is None:
        time = "time"

    # TODO: use `cf-xarray`
    coord_names = [x, y, time]
    coordinate_vars = ds[coord_names].variables
    x_var = coordinate_vars[x]
    y_var = coordinate_vars[y]
    time_var = coordinate_vars[time]

    # cases:
    # 1. len(x) == len(y) (one of 0, 1): point
    # 2. x.dims == y.dims == time.dims (all have a single dimension): trajectory (but check for duplicates)
    # 3. x.dims != y.dims or len(x.dims) == len(y.dims) (both > 1): most likely a grid
    #    1. len(time) == 1: normal image
    #    2. len(time) > 1: model or image stack
    #    3. time in x.dims: moving feature
    if (
        x_var.dims == y_var.dims
        and len(x_var.dims) in (0, 1)
        and (time not in x_var.dims or time_var.size <= 1)
    ):
        return "point" if x_var.size in (0, 1) else "linestring"
    elif x_var.dims == y_var.dims and time in x_var.dims and len(x_var.dims) == 1:
        return "trajectory"
    else:
        raise ValueError(f"unknown dataset geometry:\n{ds}")


def extract_point(ds, x=None, y=None, time=None):
    coord_names = [x, y]
    data = {k: v["data"] for k, v in ds[coord_names].to_dict()["coords"].items()}

    geometry = shapely.Point(data[x], data[y])

    return geometry, None


def extract_linestring(ds, x=None, y=None, time=None):
    coord_names = [x, y]
    df = (
        ds[coord_names]
        .to_dataframe()
        .pipe(lambda df: df.drop(columns=[col for col in df if col not in coord_names]))
    )
    data = df.to_dict()

    geometry = shapely.LineString(data[x], data[y])

    return geometry, None


def extract_trajectory(ds, x=None, y=None, time=None):
    coord_names = [x, y, time]
    # print(ds[coord_names].to_dataframe())
    df = (
        ds[coord_names]
        .to_dataframe()
        .pipe(lambda df: df.drop(columns=[col for col in df if col not in coord_names]))
        .reset_index()
    )
    data = {k: list(v.values()) for k, v in df.to_dict().items()}
    # print(data)

    geometry = shapely.LineString(list(zip(data[x], data[y])))
    time = data[time]

    return geometry, time


def generalize_linestring(geom, time, tolerance):
    return geom.simplify(tolerance=tolerance), time


def generalize_trajectory(geom, time, tolerance):
    points = shapely.points(geom.coords)

    gdf = gpd.GeoDataFrame({"time": time}, geometry=points, crs=4326).set_index("time")
    traj = mpd.Trajectory(gdf, traj_id="traj")

    simplified = mpd.DouglasPeuckerGeneralizer(traj).generalize(tolerance=tolerance)

    return simplified.to_linestring(), simplified.df.index.to_list()


def extract_geometry(ds, x=None, y=None, time=None, tolerance=0.001):
    type_ = geometry_type(ds, x=x, y=y, time=time)
    extraction_funcs = {
        "point": extract_point,
        "linestring": extract_linestring,
        "trajectory": extract_trajectory,
    }

    extraction_func = extraction_funcs.get(type_)
    if extraction_func is None:
        raise RuntimeError(
            "extraction funcs are out of sync with the geometry type detection"
        )

    raw_geometry, raw_time = extraction_func(ds, x=x, y=y, time=time)

    generalization_funcs = {
        "point": lambda geom, time, tolerance: (geom, time),
        "linestring": generalize_linestring,
        "trajectory": generalize_trajectory,
    }

    generalization_func = generalization_funcs.get(type_)
    if generalization_func is None:
        raise RuntimeError(
            "generalization funcs are out of sync with the geometry type detection"
        )

    geometry, time = generalization_func(raw_geometry, raw_time, tolerance=tolerance)

    if time is None:
        time_ = time
    else:
        time_ = [t.isoformat() for t in pd.to_datetime(time)]

    return json.loads(shapely.to_geojson(geometry)), time_
