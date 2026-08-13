import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
import rasterio.features
import os
import re
from pathlib import Path
import _process_livestock_data
import _build_spam_layer

import numpy as np
import pandas as pd
import geopandas as gpd
from tqdm import tqdm
import warnings
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings("ignore", category=RuntimeWarning)
carbon_data = "walker"
years = [
        "2010",
        "2020"
        ]


input_data_path = Path("data") / "inputs" / "walker" / "walker22_carbon_opp_cost_MgCha.tif"

output_dir = Path("outputs")

# backup_band_names = ["median", "5th_percentile", "95th_percentile"] # these apply to hayek
backup_band_names = ["agri_potential_carbon"] # these apply to walker

input_unit_conversion = 100  # ha to km2, input is "tonnes c / ha" (for hayek)
input_unit_conversion = 1 * 100  # Mg->tonnes, ha->km2, input is "Mg / ha" (for walker)

unit_label = "tonnes carbon per km2"

NUM_THREADS = 48

if len(sys.argv) > 1:
    if sys.argv[1] in years:
        years = [sys.argv[1]]
    else:
        print(f"Year {sys.argv[1]} not recognised, defaulting to all years: {years}")

def main(years = years):
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    # global params
    target_shape = (2160, 4320)
    global_bounds = (-180.0, -90.0, 180.0, 90.0)
    global_transform = from_bounds(*global_bounds, target_shape[1], target_shape[0])

    countries_shapefile = os.path.join("data", "inputs", "country_data", "geoBoundariesCGAZ_ADM0.shp")

    if not os.path.isfile(countries_shapefile):
        import _get_country_boundaries
        _get_country_boundaries.get_country_data()

    countries_data = gpd.read_file(countries_shapefile)

    isoa3_str = "shapeGroup"
    country_isos = countries_data[isoa3_str].unique()

    country_masks = {}
    for iso3 in tqdm(country_isos, desc="Precomputing country masks"):
        country_geom = countries_data.loc[countries_data[isoa3_str] == iso3.upper(), 'geometry'].values[0]
        country_masks[iso3] = rasterio.features.geometry_mask(
            [country_geom],
            out_shape=target_shape,
            transform=global_transform,
            invert=True
        )

    # flat pixel indices per country, computed once so per-item/per-band processing
    # only ever touches the (small) subset of the global raster each country covers,
    # instead of re-scanning the full 2160x4320 grid for every country every time
    country_flat_indices = {iso3: np.flatnonzero(mask) for iso3, mask in country_masks.items()}

    def process_country(idx, weights_flat, vals_flat, extra_weights_flat=None):
        """weights are assumed to be raw km2 values, extra_weights can be anything.
        idx are the precomputed flat indices of this country's pixels."""
        w = weights_flat[idx]
        v = vals_flat[idx]

        if extra_weights_flat is None:
            extra_valid = np.ones_like(w, dtype=bool)
            raw_extra_weights = np.ones_like(w, dtype=float)
        else:
            raw_extra_weights = extra_weights_flat[idx]
            extra_valid = ~np.isnan(raw_extra_weights)

        valid_indices = (~np.isnan(w)) & (~np.isnan(v)) & extra_valid

        if not np.any(valid_indices):
            return np.nan, np.nan, np.nan, np.nan

        physical_area = np.nansum(w[valid_indices])

        weights_used = w[valid_indices] * raw_extra_weights[valid_indices]
        vals_used = v[valid_indices]

        weights_normalised = weights_used / np.nansum(weights_used)

        mean_value = np.nansum(vals_used * weights_normalised)

        pixel_count = vals_used.size

        variance = np.var(vals_used)
        mean_sem = np.sqrt(variance * np.sum(weights_normalised ** 2))

        return mean_value, mean_sem, int(pixel_count), physical_area

    def convert_units(data_array, unit_conv=100, no_data=-1):
        proportional_output = data_array / unit_conv
        proportional_output = np.where(proportional_output < 0, no_data, proportional_output)
        return proportional_output

    output_columns = ["ISO3", "item_name", "band_name", "data_mean", "data_mean_sem", "unit", "pixel_count", "physical_area_km2"]
    max_workers = min(NUM_THREADS, os.cpu_count() or 1)

    # run the thing!
    for year in years:

        output_file = os.path.join(output_dir, f"processed_coc_data_{carbon_data}_mapspam{year}.csv")
        output_rows = []

        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        input_dataset = rasterio.open(input_data_path)
        band_count = input_dataset.count
        band_names = [desc if desc is not None else backup_band_names[i] for i, desc in enumerate(input_dataset.descriptions)]

        spam_data = {}
        for tif_path in Path("data", "inputs", "mapspam").rglob(f"*{year}*_A.tif"):
            crop_match = re.search(r"_([A-Z]{4})_A\.tif$", tif_path.name)
            if crop_match:
                spam_data[crop_match.group(1)] = {"path": str(tif_path)}

        spam_all_dir = os.path.join("data", "inputs", "mapspam_allc")
        os.makedirs(spam_all_dir, exist_ok=True)
        spam_all_path = os.path.join(spam_all_dir, f"mapspam_all_{year}.tif")
        spam_all_total_hectares_path = spam_all_path.replace(".tif", "_total_hectares.tif")
        if not os.path.isfile(spam_all_total_hectares_path):
            _build_spam_layer.summarise_spam_layers({"mapspam": spam_data}, year, spam_all_path, target_shape=target_shape)

        spam_data["ALLC"] = {
            "path": spam_all_total_hectares_path,
            "unit": 'harvested area in hectares / pixel'
        }

        pasture_path = os.path.join("data", "downloads", "hyde", f"pasture{year}AD.asc")
        livestock_files, uncertainty_files = _process_livestock_data.get_livestock_data(year)

        total_items = (len(spam_data) + len(livestock_files)) * len(country_isos) * band_count

        with tqdm(total=total_items, desc=f"Calculating ({year}, {len(country_isos)} countries)", unit="item") as pbar:

            for band_idx in range(1, band_count + 1):

                # allows the processing of different taxa
                band_name = band_names[band_idx - 1]
                band_data = np.zeros(target_shape, dtype=np.float64)
                reproject(
                    source=rasterio.band(input_dataset, band_idx),
                    destination=band_data,
                    src_transform=input_dataset.transform,
                    src_crs=input_dataset.crs,
                    dst_transform=global_transform,
                    dst_crs=input_dataset.crs,
                    resampling=Resampling.nearest,
                    src_nodata=input_dataset.nodata,
                    dst_nodata=np.nan,
                )
                band_data = band_data / input_unit_conversion

                def process_item(item_name, item_path):
                    """reproject + normalise + per-country stats for one crop item, independent of every other item"""
                    with rasterio.open(item_path) as src:
                        item_dataset = np.full(target_shape, np.nan, dtype=np.float64)
                        reproject(
                            source=rasterio.band(src, 1),
                            destination=item_dataset,
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=global_transform,
                            dst_crs=src.crs,
                            resampling=Resampling.nearest,
                            src_nodata=src.nodata,
                            dst_nodata=np.nan,
                        )

                    normalised_data = convert_units(item_dataset, unit_conv=100, no_data=np.nan) #ha to km2

                    weights_flat = normalised_data.ravel()
                    vals_flat = band_data.ravel()

                    rows = []
                    for iso3 in country_isos:
                        mean_value, mean_sem, pixel_count, physical_area = process_country(country_flat_indices[iso3], weights_flat, vals_flat)
                        rows.append((iso3, item_name, band_name, mean_value, mean_sem, unit_label, pixel_count, physical_area))
                    return item_name, rows

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(process_item, item_name, item_index['path']): item_name for item_name, item_index in spam_data.items()}
                    for future in as_completed(futures):
                        item_name, rows = future.result()
                        pbar.set_postfix(item=item_name, band=band_name)
                        output_rows.extend(rows)
                        pbar.update(len(country_isos))

                with rasterio.open(pasture_path) as src:
                        pasture_data = np.zeros(target_shape, dtype=np.float64)
                        reproject(
                            source=rasterio.band(src, 1),
                            destination=pasture_data,
                            src_transform=src.transform,
                            src_crs=src.crs or input_dataset.crs,
                            dst_transform=global_transform,
                            dst_crs=input_dataset.crs,
                            resampling=Resampling.nearest,
                            src_nodata=src.nodata,
                            dst_nodata=np.nan,
                        )

                def process_livestock_item(file):
                    """reproject + normalise + per-country stats for one livestock file, independent of every other file"""
                    item_name = os.path.basename(file).split(".tif")[0].split("_")[0].upper()

                    with rasterio.open(file) as src:
                        item_dataset = np.full(target_shape, np.nan, dtype=np.float64)
                        reproject(
                            source=rasterio.band(src, 1),
                            destination=item_dataset,
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=global_transform,
                            dst_crs=src.crs,
                            resampling=Resampling.nearest,
                            src_nodata=src.nodata,
                            dst_nodata=np.nan,
                        )

                    item_data = convert_units(item_dataset, unit_conv=1, no_data=np.nan)

                    weights_flat = pasture_data.ravel()
                    vals_flat = band_data.ravel()
                    extra_weights_flat = item_data.ravel()

                    rows = []
                    for iso3 in country_isos:
                        mean_value, mean_sem, pixel_count, physical_area = process_country(country_flat_indices[iso3], weights_flat, vals_flat, extra_weights_flat=extra_weights_flat)
                        rows.append((iso3, item_name, band_name, mean_value, mean_sem, unit_label, pixel_count, physical_area))
                    return item_name, rows

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(process_livestock_item, file): file for file in livestock_files}
                    for future in as_completed(futures):
                        item_name, rows = future.result()
                        pbar.set_postfix(item=item_name, band=band_name)
                        output_rows.extend(rows)
                        pbar.update(len(country_isos))

            output_data = pd.DataFrame(output_rows, columns=output_columns)
            output_data.to_csv(output_file, index=False)

if __name__ == "__main__":
    main(years=years)