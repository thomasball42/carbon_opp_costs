import os
import zipfile
import requests
import json

country_data = {
        "url": "https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM0.zip",
        "version": "",
        "reference": "Runfola, D. et al. (2020) geoBoundaries: A global database of political administrative boundaries. PLoS ONE 15(4): e0231866. https://doi.org/10.1371/journal.pone.0231866"
    } 

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

def get_country_data(url = country_data["url"]):
    country_data = os.path.join("data", "inputs", "country_data", url.split("/")[-1])
    if not os.path.isfile(country_data):
        print(f"Downloading country shapefiles from {url}...")
        os.makedirs(os.path.dirname(country_data), exist_ok=True)

        download_file(url, country_data)
        with zipfile.ZipFile(country_data, 'r') as zip_ref:
            zip_ref.extractall(os.path.dirname(country_data))
    else:
        print("World Bank shapefiles already present - skipping download")