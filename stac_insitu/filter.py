import geopandas as gpd
import movingpandas as mpd
import pandas as pd
import shapely
from tlz.itertoolz import remove


def extract_trajectory(item):
    geometry = item.geometry
    coordinates = shapely.points(geometry["coordinates"])
    time = pd.to_datetime(item.properties["datetimes"], format="ISO8601").astype(
        "datetime64[s]"
    )

    # TODO: find the crs info from the item properties
    gdf = gpd.GeoDataFrame({"time": time}, geometry=coordinates, crs=4326).set_index(
        "time"
    )
    return mpd.Trajectory(gdf, traj_id=item.id)


def filter_trajectories(items, geometry, timespan):
    def predicate(item):
        if "datetimes" not in item.properties:
            # not a trajectory, assume this item is stationary
            return False

        traj = extract_trajectory(item)

        segment = traj.get_segment_between(*pd.to_datetime(timespan))
        return not segment.intersects(geometry)

    return list(remove(predicate, items))
