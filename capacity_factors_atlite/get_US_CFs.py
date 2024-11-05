import atlite
import cartopy.io.shapereader as shpreader
import geopandas as gpd
from shapely.geometry import box
import pandas as pd
import logging
from argparse import ArgumentParser

def main(year):
    
    logging.basicConfig(level=logging.INFO)

    shpfilename = shpreader.natural_earth(
        resolution="10m", category="cultural", name="admin_0_countries"
    )
    reader = shpreader.Reader(shpfilename)
    US = gpd.GeoSeries(
        {r.attributes["NAME_EN"]: r.geometry for r in reader.records()},
        crs={"init": "epsg:4326"}).reindex(["United States of America"])

    # Only keep contiguous US
    contiguous_48_bbox = box(minx=-125, miny=24.396308, maxx=-66.93457, maxy=49.384358)
    # Clip the US geometry to the bounding box
    region = US.geometry.intersection(contiguous_48_bbox)

    region_name = "conus"

    # Define the cutout; this will not yet trigger any major operations
    cutout = atlite.Cutout(
        path=f"{region_name}-{year}", module="era5", 
        bounds=region.unary_union.bounds, 
        time=f"{year}",
        chunks={"time": 100,},)
    # This is where all the work happens (this can take some time).
    cutout.prepare(
        compression={"zlib": True, "complevel": 9},
        monthly_requests=True,
        concurrent_requests=True)

    # Extract the wind power generation capacity factors
    wind_power_generation = cutout.wind(
        "Vestas_V112_3MW", 
        capacity_factor_timeseries=True,
        )

    # Extract the solar power generation capacity factors
    solar_power_generation = cutout.pv(
        panel="CSi", 
        orientation='latitude_optimal', 
        tracking="horizontal",
        capacity_factor_timeseries=True,)
    
    # Save as netcdf
    wind_power_generation.to_netcdf(f"{region_name}_wind_CF_timeseries_{year}.nc")
    solar_power_generation.to_netcdf(f"{region_name}_solar_CF_timeseries_{year}.nc")
    
if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--year", type=int, help="Get data for this year")
    args = parser.parse_args()
    main(args.year)
