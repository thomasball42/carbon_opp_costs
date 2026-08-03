import os
import subprocess
import rasterio
import numpy as np
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import from_bounds
from pathlib import Path
import argparse

def align_rasters(file_path: Path, 
                  output_dir: Path, 
                  resolution=(0.083333333333333, -0.083333333333333), 
                  bounds = (-180.0, -90.0, 180.0, 90.0), 
                  target_shape=(2160, 4320)):

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_path = os.path.join(output_dir, file_path.name)

    with rasterio.open(file_path) as src:
        # Calculate the transform and shape for the target resolution and bounds
        transform = from_bounds(*bounds, width=target_shape[1],
                                height=target_shape[0])

        # Create an empty array for the reprojected data
        destination = np.empty(target_shape, dtype=src.dtypes[0])

        # Reproject the raster
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=src.crs,
            resampling=Resampling.average
        )

        # Save the aligned raster
        profile = src.profile
        profile.update({
            "height": target_shape[0],
            "width": target_shape[1],
            "transform": transform
        })

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(destination, 1)


def get_livestock_data(year, 
                        search_dir = os.path.join("data", "downloads", "livestock"), 
                        processed_dir = os.path.join("data", "inputs", "livestock"),
                        resolution=(0.083333333333333, -0.083333333333333),
                        bounds=(-180.0, -90.0, 180.0, 90.0),
                        target_shape=(2160, 4320)):

    if not os.path.isfile(os.path.join(search_dir, "LivestockMap.zip")):
        os.makedirs(search_dir, exist_ok=True)

        url1 = "https://zenodo.org/records/17128483/files/LivestockMap.zip?download=1/LivestockMap.zip"
        # url2 = "https://zenodo.org/records/17128483/files/MapUncertainty.zip?download=1/MapUncertainty.zip"

        subprocess.run(["curl", "-L", "-o", os.path.join(search_dir, "LivestockMap.zip"), url1], check=True)
        subprocess.run(["unzip", "-o", os.path.join(search_dir, "LivestockMap.zip"), "-d", search_dir], check=True)

        # subprocess.run(["curl", "-L", "-o", os.path.join(search_dir, "MapUncertainty.zip"), url2], check=True)
        # subprocess.run(["unzip", "-o", os.path.join(search_dir, "MapUncertainty.zip"), "-d", search_dir], check=True)

        # clean up files - not sure why these are included in the repo...
        subprocess.run(f'rm {os.path.join(search_dir, "*", "._*.tif")}', shell=True)
        subprocess.run(f'rm -r {os.path.join(search_dir, "__MACOSX")}', shell=True)
    else:
        print("Livestock data already present - skipping download and processing")

    livestock_files = []
    for root, dirs, files in os.walk(search_dir):
        for file in files:
            if str(year) in file and file.endswith(".tif"):        
                livestock_files.append(os.path.join(root, file))

    processed_files = []
    uncertainty_files = []
    for file in livestock_files:
        processed_file = os.path.join(processed_dir, os.path.split(file)[-1])
        if not os.path.isfile(processed_file):
            print(f"Livestock file {file} not processed yet - processing...")
            os.makedirs(processed_dir, exist_ok=True)
            align_rasters(Path(file), Path(processed_dir),
                          resolution=(0.083333333333333, -0.083333333333333),
                          bounds=(-180.0, -90.0, 180.0, 90.0),
                          target_shape=(2160, 4320))
        if "uncertainty" not in file.lower():
            processed_files.append(processed_file)
        elif "uncertainty" in file.lower():
            uncertainty_files.append(processed_file)
            
    return processed_files, uncertainty_files

if __name__ == "__main__":
    
    f = get_livestock_data(year=2020)

    print(f)
