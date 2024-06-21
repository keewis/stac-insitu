"""recipe for creating a STAC catalog for the Copernicus Marine Service's In-situ Ocean TAC

Data portal at: https://marineinsitu.eu
Dashboard at: https://marineinsitu.eu/dashboard/
Data server: https://data-marineinsitu.ifremer.fr
"""

import pathlib
import re
from dataclasses import dataclass, field

import apache_beam as beam
import fsspec
import pystac

# from apache_beam.options.pipeline_options import PipelineOptions
# from apache_beam.runners.dask.dask_runner import DaskRunner
from pangeo_forge_recipes.transforms import OpenURLWithFSSpec, OpenWithXarray
from rich.console import Console
from stac_recipes.patterns import FilePattern
from stac_recipes.transforms import (
    CreateCatalog,
    CreateCollection,
    CreateStacItem,
    ToStaticJson,
)
from tlz.functoolz import curry

from stac_insitu.geometry import extract_geometry
from stac_insitu.io import glob_files

console = Console()

category_names = {
    "bo": "bottles",
    "ct": "conductivity, temperature, and depth sensors (CTD)",
    "db": "drifting buoys",
    "fb": "ferrybox",
    "gl": "gliders",
    "hf": "high frequency radars",
    "ml": "mini loggers",
    "mo": "moorings",
    "pf": "profilers",
    "rf": "river flows",
    "sd": "saildrones",
    "sm": "sea mammals",
    "tg": "tide gauges",
    "ts": "thermosalinometer",
    "tx": "thermistor chains",
    "xb": "expendable bathythermographs (XBT)",
}

filename_re = re.compile(
    r"^(?P<region>[A-Z]+)_(?P<data_type>[A-Z]+)_(?P<category>[A-Z]+)_(?P<platform>.{2,})_(?P<time>[0-9]+)"
)


def tokenize_filename(url):
    stem = url.rsplit("/", maxsplit=1)[-1].removesuffix(".nc")

    match = filename_re.match(stem)
    if match is None:
        raise ValueError(f"unexpected filename structure: {url}")

    return match.groupdict()


def generate_item_template(ds):
    url = ds.encoding["source"]
    parts = tokenize_filename(url)
    item_id = "-".join(parts.values())

    bbox = [
        float(ds.attrs["geospatial_lon_min"]),
        float(ds.attrs["geospatial_lat_min"]),
        float(ds.attrs["geospatial_lon_max"]),
        float(ds.attrs["geospatial_lat_max"]),
    ]
    geometry, time = extract_geometry(
        ds, tolerance=0.001, x="LONGITUDE", y="LATITUDE", time="TIME"
    )

    properties = {
        "start_datetime": None,
        "end_datetime": None,
        "collection": parts["category"],
    }
    if time is not None:
        properties["datetimes"] = time

    item = pystac.Item(
        item_id,
        geometry=geometry,
        bbox=bbox,
        datetime=None,
        properties=properties | {"filename_parts": parts, "attrs": ds.attrs},
    )

    extra_fields = {"xarray:open_kwargs": {"engine": "h5netcdf"}}
    item.add_asset(
        "https",
        pystac.Asset(
            href=url, media_type="application/netcdf", extra_fields=extra_fields
        ),
    )

    return item


def postprocess_item(item, ds):
    item.extra_fields |= ds.attrs

    return item


def generate_collection(col, item):
    parts = item.properties.pop("filename_parts")
    attrs = item.properties.pop("attrs")

    id = parts["category"]

    col = pystac.Collection(
        id,
        title=f"{category_names[parts['category'].lower()]}",
        description="",
        extent=pystac.Extent.from_dict(
            {
                "spatial": {"bbox": [[-180, -90, 180, 90]]},
                "temporal": {"interval": [["1900-01-01", "2100-01-01"]]},
            }
        ),
        providers=[],
        keywords=[],
        extra_fields={},
        license=attrs["license"],
    )

    return col


def postprocess_collection(col):
    return col


def generate_root_catalog(collections):
    return pystac.Catalog(
        id="cmems-ocean-insitu-tac",
        description="Copernicus Marine Service – In-situ Ocean TAC",
    )


def intact_sensor(item: tuple[str, str], broken: set[str]):
    _, url = item

    _, name = url.rsplit("/", maxsplit=1)

    return not any(pattern in name for pattern in broken)


@dataclass
class RemoveBrokenSensors(beam.PTransform):
    broken: set[str]

    def expand(self, pcoll):
        return pcoll | "Filter broken sensors" >> beam.Filter(
            curry(intact_sensor, broken=self.broken)
        )


def select_categories(item: tuple[str, str], select: set[str], drop: set[str]):
    _, url = item

    category = url.rsplit("/", maxsplit=3)[1]

    return category in select and category not in drop


@dataclass
class SelectCategories(beam.PTransform):
    select: set[str]
    drop: set[str] = field(default_factory=set)

    def expand(self, pcoll):
        return pcoll | "Filter categories" >> beam.Filter(
            curry(select_categories, select=self.select, drop=self.drop)
        )


fs = fsspec.filesystem("http")

console.print(
    "[bold blue]creating a STAC catalog for the CMEMS marine in-situ ocean TAC[/]"
)

data_root = "https://data-marineinsitu.ifremer.fr/glo_multiparameter_nrt/monthly"
# TODO: figure out how to allow customizing this (maybe we can make use of `pangeo-forge-runner`?)
out_root = pathlib.Path.home() / "work/data/insitu/catalogs/cmems-insitu-tac"
out_root.mkdir(parents=True, exist_ok=True)
cache_dir = out_root / "cache/urls"
cache_dir.mkdir(exist_ok=True, parents=True)

with console.status("querying file urls"):
    console.log("file urls: querying the data server")
    urls = glob_files(fs, f"{data_root}/**/20230[4-5]/*.nc", cache_dir)
    console.log(f"file urls: found {len(urls)} files")

broken_sensors = {
    "BO_LYTN",
}

pattern = FilePattern.from_sequence(urls, file_type="netcdf4")
console.log("file urls: assembled pattern")

console.log("pipeline: constructing")
recipe = (
    beam.Create(pattern.items())
    | RemoveBrokenSensors(broken=broken_sensors)
    | SelectCategories(select=["MO", "TG", "BO", "DB", "DC", "TS"])
    | OpenURLWithFSSpec()
    | OpenWithXarray(file_type=pattern.file_type)
    | CreateStacItem(
        template=generate_item_template,
        postprocess=postprocess_item,
        xstac_kwargs={"reference_system": "epsg:4326"},
    )
    | CreateCollection(
        template=generate_collection,
        postprocess=postprocess_collection,
        spatial_extent="global",
    )
    | CreateCatalog(template=generate_root_catalog)
    | ToStaticJson(
        href=str(out_root), catalog_type=pystac.CatalogType.RELATIVE_PUBLISHED
    )
)
console.log("pipeline: done constructing")

console.log("pipeline: connecting to runner")
with beam.Pipeline() as p:
    console.log("pipeline: starting execution")
    p | recipe
    console.log("pipeline: finished execution")
console.log("pipeline: disconnected")
