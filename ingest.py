import argparse
import json
import os
import pathlib
import re

import pystac
from pypgstac.db import PgstacDB
from pypgstac.load import Loader, Methods
from rich.console import Console
from rich.progress import track

os.environ.update(
    {
        "PGHOST": "127.0.0.1",
        "PGPORT": "5439",
        "PGUSER": "username",
        "PGPASSWORD": "password",
        "PGDATABASE": "postgis",
    }
)

console = Console()

surrogate_re = re.compile(r"\\u[dD][89a-fA-F][0-9A-Fa-f]{2}")


def strip_surrogates(text):
    replaced = surrogate_re.sub("", text)
    return replaced


def read_item(path):
    text = path.read_text()
    try:
        stripped = strip_surrogates(text)
        loaded = json.loads(stripped)
        item = pystac.Item.from_dict(loaded)
    except Exception as e:
        raise ValueError(f"failed to prepare item: {path}") from e

    return item


def ingest_collection(db, collection_root, method=Methods.insert):
    loader = Loader(db=db)
    collection = str(collection_root / "collection.json")

    loader.load_collections(collection, method)

    paths = [
        p for p in collection_root.glob("**/*.json") if p.stem not in ["collection"]
    ]
    data = [read_item(p).to_dict() for p in paths]
    loader.load_items(data, Methods.upsert, dehydrated=False, chunksize=10000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("collections", nargs="+", type=pathlib.Path)
    parser.add_argument(
        "--method",
        required=False,
        default="insert",
        choices=[item.value for item in Methods],
    )
    args = parser.parse_args()

    db = PgstacDB(dsn="", debug=False)

    for collection in track(args.collections, description="ingesting..."):
        ingest_collection(db, collection, method=Methods.upsert)
