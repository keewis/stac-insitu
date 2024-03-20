from importlib.metadata import version

try:
    __version__ = version("stac_insitu")
except Exception:
    __version__ = "9999"
