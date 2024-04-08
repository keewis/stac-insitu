import functools

import folium
import folium.plugins
import shapely
from tlz.functoolz import curry
from tlz.itertoolz import groupby


def itemwise(func):
    @functools.wraps(func)
    def wrapper(items, **kwargs):
        yield from map(curry(func, **kwargs), items)

    return wrapper


def extract_category(id):
    return id.split("-")[-1].lower()


@itemwise
def transform_to_geojson(item, style_function):
    category = extract_category(item.collection_id)

    marker = folium.CircleMarker()

    return folium.GeoJson(
        item.geometry,
        style_function=curry(style_function, category=category),
        marker=marker,
    )


def transform_to_timestamped_geojson(items, style_function):
    features = [
        {
            "type": "Feature",
            "geometry": item.geometry,
            "properties": {
                "times": item.properties["datetimes"],
                "style": style_function(None, extract_category(item.collection_id)),
            },
        }
        for item in items
    ]

    yield folium.plugins.TimestampedGeoJson(
        {"type": "FeatureCollection", "features": features},
        duration="P10D",
    )


def visualize_items(items, style_function):
    def categorize(item):
        if "datetimes" in item.properties and item.geometry["type"] == "LineString":
            return "trajectory"
        else:
            return "geojson"

    categorized = groupby(categorize, items)

    transforms = {
        "trajectory": transform_to_timestamped_geojson,
        "geojson": transform_to_geojson,
    }

    for category, elems in categorized.items():
        transform = transforms.get(category)

        yield from transform(elems, style_function=style_function)


def visualize_search(geometry, items, style_function=None, m=None):
    if m is None:
        m = folium.Map(width="80%", height="80%", tiles="cartodbpositron")
    if style_function is None:
        style_function = lambda *args, **kwargs: {}

    folium.GeoJson(shapely.to_geojson(geometry)).add_to(m)

    for elem in visualize_items(items, style_function=style_function):
        elem.add_to(m)

    return m
