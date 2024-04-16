# stac-insitu

`stac-insitu` is a library that leverages `movingpandas` and `shapely` to generate and filter time-varying in-situ data (currently restricted to trajectories / moving points).

It uses the OGC moving features standard ([OGC MF-JSON](https://docs.ogc.org/is/19-045r3/19-045r3.html)) to extend the STAC specification to contain additional information about the time varying nature of the items. See also [STAC moving-features](https://github.com/iaocea/moving-features) for a work-in-progress STAC extension.

It is currently restricted to just trajectories but should be extensible to varying objects of higher dimensions by replacing the MF-JSON trajectory with the MF-JSON prism.
