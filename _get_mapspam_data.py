"""Downloads required input data files from specified URLs (mapspami and hyde databases) 
and saves them to designated directories

Annoyingly gets all the data from dataverse every time at the moment (because the output files aren't named consistently)
TB 31st Oct 2025"""

import requests
import os
import json
from easyDataverse import Dataverse  # type: ignore
import zipfile
import subprocess

overwrite = False

data_urls = {
    "mapspam": {
        "2010": {
            "url": "https://dataverse.harvard.edu/file.xhtml?persistentId=doi:10.7910/DVN/PRFF8V/HUCRCD&version=4.2",
            "doi": "https://doi.org/10.7910/DVN/PRFF8V",
            "version": "4"
        },
        "2020": {
            "url": "https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/SWPENT&version=6.0",
            "doi": "https://doi.org/10.7910/DVN/SWPENT",
            "version": "6"
        }
    },
    "hyde": {
        "2010": {
            "url": "https://geo.public.data.uu.nl/vault-hyde/hyde35_c9_apr2025%5B1749214444%5D/original/gbc2025_7apr_base/zip/2010AD_lu.zip",
            "version": "3.5",
            "unit": "grazing area in km2 / pixel"
        },
        "2020": {
            "url": "https://geo.public.data.uu.nl/vault-hyde/hyde35_c9_apr2025%5B1749214444%5D/original/gbc2025_7apr_base/zip/2020AD_lu.zip",
            "version": "3.5",
            "unit": "grazing area in km2 / pixel"
        }
    }
}

dataverse_api_token = os.environ["DATAVERSE_API_TOKEN"]

def download_file(url, filename):
        try:
            print(f"Attempting to download from: {url}")
            with requests.get(url, stream=True, allow_redirects=True) as r:
                r.raise_for_status() 
                total_size = int(r.headers.get('content-length', 0))
                print(f"File size to download: {total_size / (1024 * 1024):.2f} MB")
                
                with open(filename, 'wb') as f:
                    print(f"Saving content to: {os.path.abspath(f.name)}")

                    for chunk in r.iter_content(chunk_size=8192):

                        if chunk: 
                            f.write(chunk)

        except requests.exceptions.RequestException as e:
            print(f"\n An error occurred during download: {e}")
            
        except Exception as e:
            print(f"\n An unexpected error occurred: {e}")

def get_data(data_urls=data_urls, dataverse_api_token=dataverse_api_token):

    for dataname, datasets in data_urls.items():
        fpath = os.path.join('data', 'downloads', dataname)
        if not os.path.isdir(fpath):
            os.makedirs(fpath)

        for dataset, info in datasets.items():
            url = info.get('url')
            filename = f"{dataname}_{dataset}"
            target_path = os.path.join(fpath, filename)

            if not os.path.isfile(target_path):

                if "dataverse" in url.lower():
                    if not os.path.isdir(target_path):
                        print(f"\n--- Downloading **{dataset}** ---")
                        # This gets the mapspam data
                        doi = info.get("doi")
                        version = info.get("version", "latest")

                        dataverse = Dataverse("https://dataverse.harvard.edu/",
                            api_token = dataverse_api_token)

                        dataset = dataverse.load_dataset(
                            pid=doi,
                            version=version,
                            filedir=target_path,
                        )
                             
                elif url:
                    
                    # this gets the HYDE data and unzips it
                    download_file(url, target_path)
                    if os.path.isfile(target_path):
                        with zipfile.ZipFile(target_path, 'r') as zip_ref:
                            zip_ref.extractall(fpath)
            
                else:
                    print(f"\nError: Missing 'url' or 'doi' in data_urls.json file for **{dataset}**")#

    # out_dir = os.path.join("data", "inputs", "livestock")
    # if not os.path.isfile(os.path.join(out_dir, "LivestockMap.zip")) or not os.path.isfile(os.path.join(out_dir, "MapUncertainty.zip")):    
    #     os.makedirs(out_dir, exist_ok=True)

    #     url1 = "https://zenodo.org/records/17128483/files/LivestockMap.zip?download=1/LivestockMap.zip"
    #     url2 = "https://zenodo.org/records/17128483/files/MapUncertainty.zip?download=1/MapUncertainty.zip"

    #     subprocess.run(["curl", "-L", "-o", os.path.join(out_dir, "LivestockMap.zip"), url1], check=True)
    #     subprocess.run(["unzip", "-o", os.path.join(out_dir, "LivestockMap.zip"), "-d", out_dir], check=True)

    #     subprocess.run(["curl", "-L", "-o", os.path.join(out_dir, "MapUncertainty.zip"), url2], check=True)
    #     subprocess.run(["unzip", "-o", os.path.join(out_dir, "MapUncertainty.zip"), "-d", out_dir], check=True)

    #     # clean up files - not sure why these are included in the repo...
    #     subprocess.run( f'rm {os.path.join(out_dir, "*", "._*.tif")}',
    #                     shell=True,
    #                     )
    #     subprocess.run( f'rm -r {os.path.join(out_dir, "__MACOSX")}',
    #                     shell=True,
    #                     )
    # else:
    #     print("Livestock data already present - skipping download and processing")

    # unzip all the mapspam files
    f = []
    for path, subdirs, files in os.walk(os.path.join("data", "downloads", "mapspam")):
        for name in files:
            f.append(os.path.join(path, name))
    mapspam_files = [_ for _ in f if ("phys_area" in _ or "physical_area" in _ or "physical-area" in _) and ".geotiff" in _ and "mapspam" in _]  # terrible
    mapspam_out_root = os.path.join("data", "inputs", "mapspam")
    os.makedirs(mapspam_out_root, exist_ok=True)
    print("Extracting mapspam files...")
    extracted_any = False

    for file in mapspam_files:
        out_dir = os.path.join(mapspam_out_root, os.path.basename(file).split(".zip")[0])

        if os.path.isdir(out_dir) and not overwrite:
            print(f"  {os.path.basename(file)} already extracted - skipping")
            continue

        os.makedirs(out_dir, exist_ok=True)
        with zipfile.ZipFile(file, "r") as zip_ref:
            zip_ref.extractall(out_dir)
        print(f"  extracted {os.path.basename(file)}")
        extracted_any = True

if __name__ == "__main__":
    get_data()