import requests
import os
import json

dir_path = os.path.dirname(os.path.realpath(__file__)) + "/.."

def download_latest_release_artifacts(owner, repo):
    # GitHub API URL for releases
    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    # Get the latest release information
    response = requests.get(api_url)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch releases: {response.status_code} {response.text}")

    release_data = response.json()

    # Create a directory for the artifacts
    local_path = dir_path + "/artifacts/firmware/" + repo
    os.makedirs( local_path, exist_ok=True)

    # save the release data
    with open(os.path.join(local_path, "github_release_data.json"), 'w') as fout:
            json.dump(release_data, fp=fout)
                
    # Download each asset
    for asset in release_data.get('assets', []):
        asset_name = asset['name']
        asset_url = asset['url']
        browser_download_url = asset.get("browser_download_url", asset_url)
        download_url = browser_download_url

        # Get the asset content
        asset_response = requests.get(download_url, headers={'Accept': 'application/octet-stream'})
        if asset_response.status_code == 200:
            with open(os.path.join(local_path, asset_name), 'wb') as f:
                f.write(asset_response.content)
            print(f"Downloaded: {asset_name}")
        else:
            print(f"Failed to download {asset_name}: {asset_response.status_code} {asset_response.text}")
            
if __name__ == "__main__":
    download_latest_release_artifacts("markqvist","RNode_Firmware")
    download_latest_release_artifacts("attermann","microReticulum_Firmware")
    download_latest_release_artifacts("liberatedsystems","RNode_Firmware_CE")
    