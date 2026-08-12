"""Note this doesn't work because dataverse has some probably accidental block on API calls, I think it's an issue with AWS bot detection
and is unlikely to be intentional. I downloaded the data manually and put it in the data/downloads/walker folder"""
import requests
import os
import json
from easyDataverse import Dataverse  # type: ignore
import zipfile
import subprocess


dataverse_api_token = os.environ["DATAVERSE_API_TOKEN"]

dataverse = Dataverse("https://dataverse.harvard.edu/",
                        api_token = dataverse_api_token)

data_urls = {
            "walker22" : { # https://doi.org/10.1073/pnas.2111312119
                "doi" : "doi:10.7910/DVN/DSDDQK",
                "files" : [
                        "Base_Unr_AGB_BGB_SOC_MgCha_500m.tif",
                        # "Base_Cur_AGB_UI_500m.tif",
                        # "Base_Pot_AGB_UI_500m.tif",
                    ],  # only these get downloaded
                }
}

if not os.path.isdir("data/downloads/walker"):
    os.makedirs("data/downloads/walker", exist_ok=True)

dataset = dataverse.load_dataset(
    pid=data_urls["walker22"]["doi"],
    filedir="data/downloads/walker",
    filenames=data_urls["walker22"]["files"]
)