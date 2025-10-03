import json
import subprocess
from pathlib import Path
import os
import requests
import sys

USERNAME = "twice_tiktok_official"
SAVE_DIR = Path("downloads")
SAVE_DIR.mkdir(exist_ok=True)

ID_LIST_FILE = SAVE_DIR / "video_id_list.txt"

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID")

# TWICE members list (lowercase for matching)
TWICE_MEMBERS = [
    "nayeon", "jeongyeon", "momo", "sana", "jihyo",
    "mina", "dahyun", "chaeyoung", "tzuyu"
]

def get_latest_video(username: str):
    """Fetch the latest TikTok video with full caption and tags."""
    try:
        # Step 1: Get latest video ID
        playlist_cmd = ["python", "-m", "yt_dlp", "-J", "--flat-playlist", f"https://www.tiktok.com/@{username}"]
        result = subprocess.run(playlist_cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)

        if not data.get("entries"):
            print("⚠️ No videos found.")
            return None

        latest_id = data["entries"][0]["id"]
        video_url = f"https://www.tiktok.com/@{username}/video/{latest_id}"

        # Step 2: Get video metadata
        video_cmd = ["python", "-m", "yt_dlp", "-j", video_url]
        video_result = subprocess.run(video_cmd, capture_output=True, text=True, check=True)
        video_data = json.loads(video_result.stdout)

        caption = (video_data.get("description") or "").lower()
        tags = [t.lower() for t in video_data.get("tags", [])]

        # ✅ Filter: must include "twice" + at least one member
        if "twice" not in caption and "twice" not in tags:
            print("⚠️ Skipping: no 'twice' mention.")
            return None

        if not any(member in caption or member in " ".join(tags) for member in TWICE_MEMBERS):
            print("⚠️ Skipping: no member name found.")
            return None

        return {
            "id": video_data["id"],
            "url": video_data["webpage_url"],
            "caption": video_data.get("description") or "No caption",
            "username": video_data.get("uploader") or "unknown"
        }

    except subprocess.CalledProcessError as e:
        print("❌ yt-dlp error:", e.stderr)
        return None

def download_video(url: str, video_id: str):
    """Download TikTok video to disk."""
    video_path = SAVE_DIR / f"{video_id}.mp4"
    cmd = ["python", "-m", "yt_dlp", "-o", str(video_path), url]

    try:
        subprocess.run(cmd, check=True)
        print(f"🎉 Download complete: {video_path}")
        return video_path
    except subprocess.CalledProcessError as e:
        print("❌ Download failed:", e.stderr)
        return None

def post_to_facebook(video_path: Path, caption: str):
    """Upload video to Facebook Page via Graph API."""
    url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/videos"
    files = {"source": open(video_path, "rb")}
    data = {"description": caption, "access_token": PAGE_ACCESS_TOKEN}

    response = requests.post(url, files=files, data=data)
    if response.status_code == 200:
        print("✅ Uploaded to Facebook:", response.json())
        return True
    else:
        print("❌ Upload failed:", response.text)
        return False

if __name__ == "__main__":
    latest = get_latest_video(USERNAME)
    if not latest:
        sys.exit(0)

    # Ensure file exists
    if not ID_LIST_FILE.exists():
        ID_LIST_FILE.write_text("")

    uploaded_ids = set(ID_LIST_FILE.read_text().splitlines())

    if latest["id"] in uploaded_ids:
        print(f"⏩ Skipping: Video ({latest['id']}) already uploaded.")
        sys.exit(0)

    print("🔗 Latest video URL:", latest['url'])
    print("📝 Caption:", latest['caption'])

    video_path = download_video(latest["url"], latest["id"])
    if video_path:
        fb_caption = f"{latest['caption']}\n\ncrdts : {latest['username']}"
        if post_to_facebook(video_path, fb_caption):
            # Append video ID to history
            with open(ID_LIST_FILE, "a") as f:
                f.write(latest["id"] + "\n")

            video_path.unlink()  # cleanup
            print("🧹 Cleaned up local file.")
