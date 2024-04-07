import datetime as dt
import hashlib


def glob_files(fs, glob, cache_dir):
    hash_ = hashlib.new("sha3_256", glob.encode()).hexdigest()
    cache_name = f"{hash_}-{dt.datetime.today().strftime('%Y-%m-%d')}"
    cache_path = cache_dir.joinpath(cache_name).with_suffix(".json")

    try:
        urls = cache_path.read_text().splitlines()
    except IOError:
        urls = fs.glob(glob)

        cache_path.write_text("\n".join(urls))

    return urls
