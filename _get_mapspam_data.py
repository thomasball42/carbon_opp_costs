"""Downloads required input data files from specified URLs (mapspami and hyde databases) 
and saves them to designated directories

Annoyingly gets all the data from dataverse every time at the moment 
(because the output files aren't named consistently)
TB 31st Oct 2025"""

import requests
import os
import json
import hashlib
import re
import time
import urllib.parse
from easyDataverse import Dataverse  # type: ignore
import zipfile

overwrite = False

# geo.public.data.uu.nl (HYDE) is behind Anubis, which turns away anything that
# looks like a script. Ask like a browser and be ready to do its sums.
BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Layers worth keeping out of each archive, by filename prefix. Everything else
# is extracted-and-binned weight: HYDE ships 13 layers per year and only
# pasture{year}AD.asc is read downstream.
KEEP_PREFIXES = {"hyde": ("pasture",)}

data_urls = {
    # "mapspam": {
    #     "2010": {
    #         "url": "https://dataverse.harvard.edu/file.xhtml?persistentId=doi:10.7910/DVN/PRFF8V/HUCRCD&version=4.2",
    #         "doi": "https://doi.org/10.7910/DVN/PRFF8V",
    #         "version": "4"
    #     },
    #     "2020": {
    #         "url": "https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/SWPENT&version=6.0",
    #         "doi": "https://doi.org/10.7910/DVN/SWPENT",
    #         "version": "6"
    #     }
    # },
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

# Only the dataverse (mapspam) downloads need this, so don't die at import time
# when just fetching HYDE.
dataverse_api_token = os.environ.get("DATAVERSE_API_TOKEN")

_ANUBIS_CHALLENGE_RE = re.compile(
    r'id="anubis_challenge" type="application/json">(.*?)</script>', re.S)


def make_session():
    session = requests.Session()
    session.headers["User-Agent"] = BROWSER_UA
    return session


def solve_anubis(session, response):
    """Answer an Anubis proof-of-work page so `session` picks up its auth cookie.

    Anubis serves the challenge as an HTTP *200* HTML page in place of the file,
    so a plain download quietly writes the challenge to disk instead of failing.
    Returns True if a challenge was found and solved."""

    match = _ANUBIS_CHALLENGE_RE.search(response.text)
    if not match:
        return False

    challenge = json.loads(match.group(1))
    data = challenge["challenge"]["randomData"]
    difficulty = challenge["rules"]["difficulty"]
    prefix = "0" * difficulty

    print(f"  Anubis challenge found - solving (difficulty {difficulty})...")
    start = time.time()
    nonce = 0
    while True:
        digest = hashlib.sha256(f"{data}{nonce}".encode()).hexdigest()
        if digest.startswith(prefix):
            break
        nonce += 1
    elapsed_ms = max(int((time.time() - start) * 1000), 1)

    root = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(response.url))
    params = urllib.parse.urlencode({
        "id": challenge["challenge"]["id"],
        "response": digest,
        "nonce": str(nonce),
        "redir": response.url,
        "elapsedTime": str(elapsed_ms),
    })
    session.get(f"{root}/.within.website/x/cmd/anubis/api/pass-challenge?{params}",
                allow_redirects=False)
    print(f"  solved in {elapsed_ms} ms (nonce {nonce})")
    return True


def download_file(url, filename, session=None):
    """Download `url` to `filename`. Returns True only on a complete download.

    The body goes to a .part file and is moved into place once it has all
    arrived, so an interrupted or blocked download never leaves behind something
    that later runs mistake for a finished file."""

    session = session or make_session()
    part_path = f"{filename}.part"

    try:
        print(f"Attempting to download from: {url}")

        for attempt in range(2):
            with session.get(url, stream=True, allow_redirects=True) as r:
                r.raise_for_status()

                content_type = r.headers.get('content-type', '')
                if 'text/html' in content_type:
                    # Not the file - an interstitial. Solve it and retry once.
                    if attempt == 0 and solve_anubis(session, r):
                        continue
                    print(f"\n Server returned an HTML page rather than the file "
                          f"(content-type {content_type!r}) - not saving it.")
                    return False

                total_size = int(r.headers.get('content-length', 0))
                print(f"File size to download: {total_size / (1024 * 1024):.2f} MB")
                print(f"Saving content to: {os.path.abspath(filename)}")

                with open(part_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):

                        if chunk:
                            f.write(chunk)

            written = os.path.getsize(part_path)
            if total_size and written != total_size:
                print(f"\n Incomplete download: got {written} of {total_size} bytes.")
                return False

            os.replace(part_path, filename)
            return True

        print("\n Could not get past the server's bot check.")
        return False

    except requests.exceptions.RequestException as e:
        print(f"\n An error occurred during download: {e}")

    except Exception as e:
        print(f"\n An unexpected error occurred: {e}")

    finally:
        if os.path.isfile(part_path):
            os.remove(part_path)

    return False

def drop_unused(fpath, keep):
    """Delete extracted .asc layers we don't use.

    Each HYDE zip holds 13 layers but only pasture is read downstream
    (calculate_intersect_values.py), so the rest is ~1.4 GB of dead weight -
    including anything left behind by earlier runs that extracted everything.
    The zips themselves stay, so nothing needs re-downloading."""

    removed = 0
    for name in sorted(os.listdir(fpath)):
        path = os.path.join(fpath, name)
        if (name.endswith(".asc") and not name.startswith(keep)
                and os.path.isfile(path)):
            removed += os.path.getsize(path)
            os.remove(path)

    if removed:
        print(f"  cleaned up {removed / 1e9:.2f} GB of unused layers")


def get_data(data_urls=data_urls, dataverse_api_token=dataverse_api_token):

    session = make_session()

    for dataname, datasets in data_urls.items():
        fpath = os.path.join('data', 'downloads', dataname)
        if not os.path.isdir(fpath):
            os.makedirs(fpath)

        for dataset, info in datasets.items():
            url = info.get('url')
            filename = f"{dataname}_{dataset}"
            target_path = os.path.join(fpath, filename)

            if not url:
                print(f"\nError: Missing 'url' or 'doi' in data_urls.json file for **{dataset}**")
                continue

            if "dataverse" in url.lower():
                if not os.path.isdir(target_path):
                    print(f"\n--- Downloading **{dataset}** ---")
                    if not dataverse_api_token:
                        raise RuntimeError(
                            "DATAVERSE_API_TOKEN is not set - needed to download "
                            f"{dataname} {dataset}")
                    # This gets the mapspam data
                    doi = info.get("doi")
                    version = info.get("version", "latest")

                    dataverse = Dataverse("https://dataverse.harvard.edu/",
                        api_token = dataverse_api_token)

                    dataverse.load_dataset(
                        pid=doi,
                        version=version,
                        filedir=target_path,
                    )
                continue

            # this gets the HYDE data and unzips it
            if os.path.isfile(target_path) and not zipfile.is_zipfile(target_path):
                # e.g. a saved bot-check page from an earlier run
                print(f"\n {filename} is not a zip file - discarding and re-downloading")
                os.remove(target_path)

            if not os.path.isfile(target_path):
                print(f"\n--- Downloading **{dataname} {dataset}** ---")
                if not download_file(url, target_path, session=session):
                    print(f" Skipping **{dataname} {dataset}** - download failed")
                    continue

                if not zipfile.is_zipfile(target_path):
                    print(f" {filename} downloaded but is not a zip file - discarding")
                    os.remove(target_path)
                    continue

            keep = KEEP_PREFIXES.get(dataname)

            with zipfile.ZipFile(target_path, 'r') as zip_ref:
                members = zip_ref.namelist()
                if keep:
                    members = [m for m in members
                               if os.path.basename(m).startswith(keep)]
                if overwrite or any(not os.path.exists(os.path.join(fpath, m))
                                    for m in members):
                    zip_ref.extractall(fpath, members=members)
                    print(f"  extracted {len(members)} file(s) from {filename}")
                else:
                    print(f"  {filename} already extracted - skipping")

            if keep:
                drop_unused(fpath, keep)

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