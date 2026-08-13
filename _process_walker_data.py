import os
import rasterio
import numpy as np
from pathlib import Path
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling

walker_dir = Path("data") / "downloads" / "walker"
constra_file = walker_dir / "Base_Con_Unr_AGB_BGB_SOC_MgCha_500m.tif"
unconst_file = walker_dir / "Base_Unr_AGB_BGB_SOC_MgCha_500m.tif"

output_dir = Path("data") / "inputs" / "walker"
output_file = output_dir / "walker22_carbon_opp_cost_MgCha.tif"

target_georef = {
    "resolution": (0.083333333333333, -0.083333333333333),
    "bounds": (-180.0, -90.0, 180.0, 90.0),
    "target_shape": (2160, 4320),
    "crs": "EPSG:4326"
}

nodata_val = -32768


def check_rasters_aligned(meta_a, meta_b):
    for key in ("crs", "transform", "width", "height"):
        if meta_a[key] != meta_b[key]:
            raise ValueError(f"Rasters are not aligned: '{key}' differs ({meta_a[key]!r} != {meta_b[key]!r})")


def process_walker_data():

    try:

        with rasterio.open(constra_file, nodata=nodata_val) as src:
            const_data = src.read(1).astype(np.int32)
            const_meta = src.meta

        with rasterio.open(unconst_file, nodata=nodata_val) as src:
            unconst_data = src.read(1).astype(np.int32)
            unconst_meta = src.meta

    except FileNotFoundError as e:
        print(f"Error: {e}. Please make sure that the two input files ({constra_file}, {unconst_file}) are present in the 'data/downloads/walker' directory.")
        return
    
    check_rasters_aligned(const_meta, unconst_meta)
    print("Input rasters confirmed aligned (same crs, transform, width, height)")

    nodata_mask = (const_data == nodata_val) | (unconst_data == nodata_val)
    diff_data = unconst_data - const_data
    diff_data = np.where(nodata_mask, nodata_val, diff_data)

    dst_transform = from_bounds(*target_georef["bounds"],
                                 width=target_georef["target_shape"][1],
                                 height=target_georef["target_shape"][0])

    destination = np.full(target_georef["target_shape"], nodata_val, dtype=np.float32)

    reproject(
        source=diff_data,
        destination=destination,
        src_transform=const_meta["transform"],
        src_crs=const_meta["crs"],
        dst_transform=dst_transform,
        dst_crs=target_georef["crs"],
        resampling=Resampling.average,
        src_nodata=nodata_val,
        dst_nodata=nodata_val,
    )

    os.makedirs(output_dir, exist_ok=True)

    with rasterio.open(
        output_file,
        "w",
        driver="GTiff",
        height=target_georef["target_shape"][0],
        width=target_georef["target_shape"][1],
        count=1,
        dtype=np.float32,
        crs=target_georef["crs"],
        transform=dst_transform,
        nodata=float(nodata_val),
    ) as dst:
        dst.write(destination, 1)

    print(f"Wrote carbon opportunity cost raster to {output_file}")
    return output_file


if __name__ == "__main__":
    process_walker_data()