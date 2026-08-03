import requests
import zipfile
from pathlib import Path

data_urls = {
            "hayek21" : { # https://doi.org/10.1038/s41893-020-00603-4
                "carbon_diff": {
                    "data" : "https://archive.nyu.edu/bitstream/2451/60073/1/nyu_2451_60073.zip",
                    "readme" : "https://archive.nyu.edu/bitstream/2451/60073/3/nyu_2451_60073_doc.zip",
                    },
                "animal_hectares": {
                    "data" : "https://archive.nyu.edu/bitstream/2451/60073/2/nyu_2451_60074.zip",
                    "readme" : "https://archive.nyu.edu/bitstream/2451/60073/4/nyu_2451_60074_doc.zip",
                    }
                }
}

inputs_path = Path("data") / "downloads"


def fetch_data(urls=data_urls, base_path=inputs_path, force=False):
    """Download each url in `urls` and extract it into base_path/{dataset}/{subset}/{key}.

    `urls` is a nested dict of dataset -> subset -> {key: url}, e.g.
    urls["hayek21"]["carbon_diff"]["data"] -> saved under base_path/hayek21/carbon_diff/data.
    Skips downloads whose destination folder is already populated, unless force=True.
    """
    for dataset, subsets in urls.items():
        for subset, files in subsets.items():
            for key, url in files.items():
                dest_dir = base_path / dataset / subset / key
                if dest_dir.exists() and any(dest_dir.iterdir()) and not force:
                    print(f"Skipping {dataset}/{subset}/{key}, already exists at {dest_dir}")
                    continue

                dest_dir.mkdir(parents=True, exist_ok=True)
                zip_path = dest_dir / Path(url).name

                print(f"Downloading {dataset}/{subset}/{key} from {url}")
                with requests.get(url, stream=True) as response:
                    response.raise_for_status()
                    with open(zip_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            f.write(chunk)

                if zip_path.suffix == ".zip":
                    with zipfile.ZipFile(zip_path) as zf:
                        zf.extractall(dest_dir)
                    zip_path.unlink()

    return base_path

if __name__ == "__main__":
    fetch_data()

