import json
import time
import asyncio
import httpx
import subprocess
import os
import requests
from datetime import datetime
from typing import Dict, Optional

# --- Settings ---
RELEASE_VERSION = "OB50"
USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 13; CPH2095 Build/RKQ1.211119.001)"
TELEGRAM_TOKEN = "8379507521:AAFtx7QE-9MuGSL3j0wU-WEHwoYhHww4K5Y"
TELEGRAM_CHAT_ID = 7968668273
BRANCH_NAME = "main"
JWT_API_URL = "https://jetdeco.vercel.app/token"

# --- Telegram ---
def send_telegram_message(message: str, markdown: bool = True):
    """Send message to Telegram chat"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown" if markdown else None
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Telegram send error: {e}")

# --- Git Helpers ---
def run_git_command(cmd: str) -> str:
    try:
        result = subprocess.check_output(
            cmd, shell=True, stderr=subprocess.STDOUT, universal_newlines=True
        )
        return result.strip()
    except subprocess.CalledProcessError as e:
        return e.output.strip()

def detect_git_conflict() -> bool:
    status = run_git_command("git status")
    return any(
        key in status
        for key in ["both modified", "Unmerged paths", "rebase in progress"]
    )

def resolve_git_conflict():
    print("\n⚠️ Git Conflict Detected.")
    input("➡️ Resolve conflicts and press Enter to continue...")
    run_git_command("git add .")
    run_git_command("git rebase --continue")
    print("✅ Rebase continued successfully.")

def push_to_git():
    """Push to remote repository"""
    run_git_command(f"git checkout {BRANCH_NAME}")
    run_git_command("git add .")
    commit_msg = f"Token update {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    run_git_command(f'git commit -m "{commit_msg}" || echo "No changes to commit"')
    run_git_command(f"git push origin {BRANCH_NAME}")
    print(f"🚀 Changes pushed to {BRANCH_NAME} branch.")

# --- File / Region Helpers ---
def get_token_filename(region: str) -> str:
    mapping = {
        "IND": "token_ind.json",
        "BR": "token_br.json",
        "US": "token_br.json",
        "SAC": "token_br.json",
        "NA": "token_br.json"
    }
    return mapping.get(region, "token_bd.json")

# --- Token Generation ---
async def generate_jwt_token(client, uid: str, password: str) -> Optional[Dict]:
    try:
        url = f"{JWT_API_URL}?uid={uid}&password={password}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        resp = await client.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"❌ [{uid}] HTTP {resp.status_code} - {resp.text[:60]}")
        return None
    except Exception as e:
        print(f"⚠️ Error fetching token for {uid}: {e}")
        return None

async def process_account(client, idx: int, uid: str, password: str, retries=3):
    for attempt in range(retries):
        token_data = await generate_jwt_token(client, uid, password)
        if token_data and "token" in token_data:
            return {
                "serial": idx + 1,
                "uid": uid,
                "password": password,
                "token": token_data["token"],
                "region": token_data.get("notiRegion", "")
            }
        print(f"⏳ Retry {attempt + 1}/{retries} for UID #{idx + 1} ({uid})...")
        await asyncio.sleep(10 + attempt * 5)  # Progressive delay
    return {"serial": idx + 1, "uid": uid, "password": password, "token": None, "region": ""}

async def generate_tokens_for_region(region: str):
    start_time = time.time()
    input_file = f"uid_{region}.json"

    if not os.path.exists(input_file):
        print(f"⚠️ {input_file} missing, skipping...")
        return 0

    with open(input_file, "r") as f:
        accounts = json.load(f)

    total_accounts = len(accounts)
    print(f"\n🚀 Starting token generation for {region} region ({total_accounts} accounts)...")

    region_tokens = []
    failed = []

    async with httpx.AsyncClient() as client:
        tasks = [
            process_account(client, i, acc["uid"], acc["password"])
            for i, acc in enumerate(accounts)
        ]
        for result in await asyncio.gather(*tasks):
            if result["token"] and result["region"] == region:
                region_tokens.append({"uid": result["uid"], "token": result["token"]})
                print(f"✅ UID #{result['serial']} {result['uid']} — Success ({region})")
            else:
                failed.append(result["uid"])
                print(f"❌ UID #{result['serial']} {result['uid']} — Failed")

    # Write tokens
    output_file = get_token_filename(region)
    with open(output_file, "w") as f:
        json.dump(region_tokens, f, indent=2)

    total_time = int(time.time() - start_time)
    summary = (
        f"✅ *{region} Token Generation Completed*\n\n"
        f"📦 *Accounts:* {total_accounts}\n"
        f"🔑 *Tokens Generated:* {len(region_tokens)}\n"
        f"❌ *Failed:* {len(failed)}\n"
        f"🕒 *Time Taken:* {total_time // 60}m {total_time % 60}s\n"
        f"📅 *Updated:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(summary)
    print(summary)

    return len(region_tokens)

# --- Main ---
if __name__ == "__main__":
    regions = ["IND", "BD", "NA"]
    total_tokens = 0
    send_telegram_message(f"🤖 *Token Generation Started for {', '.join(regions)}...* ⚙️")

    for region in regions:
        count = asyncio.run(generate_tokens_for_region(region))
        total_tokens += count

    send_telegram_message(f"✅ *All Regions Completed*\n🔹 Total Tokens: {total_tokens}")

    if detect_git_conflict():
        resolve_git_conflict()

    push_to_git()
    print("\n🎯 All tasks completed successfully.")
