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
    CONUS = US.geometry.intersection(contiguous_48_bbox)

    # Loop over the years
    logging.info(f"Processing {year}")

    # Define the cutout; this will not yet trigger any major operations
    cutout = atlite.Cutout(
        path=f"conus-{year}", module="era5", bounds=CONUS.unary_union.bounds, time=slice(f"{year}-01", f"{year}-12"))
    # This is where all the work happens (this can take some time).
    cutout.prepare()

    # Extract the wind power generation capacity factors
    wind_power_generation = cutout.wind(
        "Vestas_V112_3MW", 
        shapes=CONUS,
        per_unit=True
        )

    # Extract the solar power generation capacity factors
    solar_power_generation = cutout.pv(
        panel="CSi", 
        orientation='latitude_optimal', 
        shapes=CONUS,
        tracking="horizontal",
        per_unit=True)

    solar_power_generation = solar_power_generation.to_pandas().rename(columns={"United States of America": "solar_cf"})
    wind_power_generation = wind_power_generation.to_pandas().rename(columns={"United States of America": "wind_cf"})

    # Save the data as a csv
    solar_power_generation.to_csv(f"CONUS_solar_CF_{year}.csv")
    wind_power_generation.to_csv(f"CONUS_wind_CF_{year}.csv")

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--year", type=int, help="Get data for this year")
    args = parser.parse_args()
    main(args.year)
