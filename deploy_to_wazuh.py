import os
import requests
import urllib3
from pathlib import Path

# Suppress self-signed certificate warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WAZUH_URL = os.environ["WAZUH_API_URL"]
USER = os.environ["WAZUH_API_USER"]
PASSWORD = os.environ["WAZUH_API_PASSWORD"]

def get_token():
    url = f"{WAZUH_URL}/security/user/authenticate"
    print(f"🔍 Connecting to: {url}")
    print(f"🔍 Using user: {USER}")
    print(f"🔍 Password length: {len(PASSWORD)}")
    response = requests.get(
        url,
        auth=(USER, PASSWORD),
        verify=False,
        params={"raw": "true"}
    )
    print(f"🔍 Response status: {response.status_code}")
    response.raise_for_status()
    return response.text.strip()

def upload_file(token, endpoint, filename, content):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream"
    }
    params = {"overwrite": "true"}
    response = requests.put(
        f"{WAZUH_URL}/{endpoint}/{filename}",
        headers=headers,
        params=params,
        data=content.encode("utf-8"),
        verify=False
    )
    if response.status_code == 200:
        print(f"✅ Uploaded {filename}")
    else:
        print(f"❌ Failed to upload {filename}: {response.status_code} - {response.text}")
        raise Exception(f"Upload failed for {filename}")

def main():
    token = get_token()
    print("🔐 Authenticated with Wazuh API")

    # Upload rules
    for rule_file in Path("rules").glob("*.xml"):
        content = rule_file.read_text()
        upload_file(token, "rules/files", rule_file.name, content)

    # Upload decoders
    for decoder_file in Path("decoders").glob("*.xml"):
        content = decoder_file.read_text()
        upload_file(token, "decoders/files", decoder_file.name, content)

    print("\n🎉 All rulesets deployed successfully.")

if __name__ == "__main__":
    main()
