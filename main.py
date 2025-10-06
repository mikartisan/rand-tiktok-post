import json
import subprocess
from pathlib import Path
import os
import requests
import sys
import re

# USERNAME is not used - this script is for scraping random TWICE fan videos
# You'll need to provide video URLs manually or modify to search by hashtag
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

# ✅ Official TWICE accounts to IGNORE (you have separate code for these)
OFFICIAL_ACCOUNTS_TO_SKIP = [
    "twice_tiktok_official",
    "twice.official",
    "jypetwice",
    "twicetagram",
]

# Set to True to allow fan content, False to only allow official accounts
ALLOW_FAN_CONTENT = True


def is_twice_related(caption: str, hashtags: list, uploader: str) -> tuple[bool, str]:
    """
    Determine if video is TWICE-related with multiple safety checks.
    For fan content: requires STRONG evidence (multiple indicators)
    EXCLUDES official accounts (handled by separate script)
    Returns: (is_valid, reason)
    """
    caption_lower = caption.lower()
    hashtags_lower = [h.lower() for h in hashtags]
    
    # ❌ SKIP official accounts (you have separate code for them)
    is_official = uploader.lower() in [acc.lower() for acc in OFFICIAL_ACCOUNTS_TO_SKIP]
    if is_official:
        return False, f"⏭️ Skipping official account: {uploader} (handled by separate script)"
    
    # ✅ MUST have #twice hashtag (basic requirement)
    has_twice_tag = "twice" in hashtags_lower
    if not has_twice_tag:
        return False, "Missing #twice hashtag"
    
    # ✅ Count TWICE-related indicators (need multiple for fan content)
    evidence_count = 0
    evidence_list = []
    
    # 1. Member hashtags
    matching_members = [m for m in TWICE_MEMBERS if m in hashtags_lower]
    if matching_members:
        evidence_count += len(matching_members)
        evidence_list.append(f"member tags: {', '.join(matching_members)}")
    
    # 2. Member names in caption (not just hashtags)
    caption_members = [m for m in TWICE_MEMBERS if m in caption_lower]
    if caption_members:
        evidence_count += 1
        evidence_list.append(f"members mentioned: {', '.join(set(caption_members))}")
    
    # 3. TWICE-specific hashtags (Korean name, official tags, albums, etc.)
    twice_specific_tags = [
        "트와이스", "twice_", "once", "jypentertainment", "jype",
        "feelspecial", "fancyyou", "twicetagram", "formula_of_love",
        "between1and2", "readytobe", "with_you_th", "celebrate",
        "talk_that_talk", "scientist", "perfect_world", "the_feels"
    ]
    matching_specific = [tag for tag in twice_specific_tags 
                        if any(tag in ht for ht in hashtags_lower)]
    if matching_specific:
        evidence_count += len(matching_specific)
        evidence_list.append(f"specific tags: {', '.join(matching_specific[:3])}")
    
    # 4. Group content keywords
    group_keywords = [
        "트와이스", "anniversary", "comeback", "debut",
        "mv", "choreography", "performance", "stage", "concert",
        "showcase", "once", "ot9", "edit", "fanmade", "cover"
    ]
    matching_keywords = [kw for kw in group_keywords if kw in caption_lower]
    if matching_keywords:
        evidence_count += 1
        evidence_list.append(f"keywords: {', '.join(matching_keywords[:2])}")
    
    # ✅ Fan content requires strong evidence
    required_evidence = 2  # Require at least 2 pieces of evidence
    
    if evidence_count < required_evidence:
        return False, f"Insufficient evidence ({evidence_count}/{required_evidence}). Only generic #twice tag found"
    
    # ✅ BLOCKLIST: Even with evidence, reject obvious spam/unrelated
    blocklist = [
        "not twice", "vs twice", "better than twice",
        "blackpink", "bts", "itzy", "aespa",  # other groups (unless crossover content)
        "tutorial", "how to", "challenge",  # generic content
        "giveaway", "contest", "follow for"  # spam
    ]
    for blocked in blocklist:
        if blocked in caption_lower:
            return False, f"Blocklist keyword detected: '{blocked}'"
    
    return True, f"✅ Valid TWICE fan content (evidence: {evidence_count}) - {'; '.join(evidence_list)}"


def get_video_info(video_url: str):
    """Fetch video metadata from a specific TikTok URL."""
    try:
        # Get video metadata
        video_cmd = ["python", "-m", "yt_dlp", "-j", video_url]
        video_result = subprocess.run(video_cmd, capture_output=True, text=True, check=True)
        video_data = json.loads(video_result.stdout)

        caption = video_data.get("description") or ""
        uploader = video_data.get("uploader") or video_data.get("uploader_id") or "unknown"

        # 🔍 Extract hashtags from caption using regex
        hashtags = re.findall(r"#(\w+)", caption)  # Capture without #

        # 🔍 Debugging
        print("=" * 50)
        print("DEBUG >>> Video ID:", video_data.get("id"))
        print("DEBUG >>> Uploader:", uploader)
        print("DEBUG >>> Caption:", caption[:100], "..." if len(caption) > 100 else "")
        print("DEBUG >>> Hashtags:", hashtags)
        print("=" * 50)

        # ✅ Validate if video is TWICE-related
        is_valid, reason = is_twice_related(caption, hashtags, uploader)
        
        if not is_valid:
            print(f"⚠️ Skipping video: {reason}")
            return None
        
        print(f"✅ {reason}")

        return {
            "id": video_data["id"],
            "url": video_data["webpage_url"],
            "caption": caption or "No caption",
            "username": uploader
        }

    except subprocess.CalledProcessError as e:
        print("❌ yt-dlp error:", e.stderr)
        return None
    except json.JSONDecodeError as e:
        print("❌ JSON parsing error:", str(e))
        return None
    except Exception as e:
        print("❌ Unexpected error:", str(e))
        return None


def get_latest_video(username: str):
    """Fetch the latest TikTok video with full caption and hashtags extracted from caption text."""
    try:
        # Step 1: Get latest video ID
        playlist_cmd = [
            "python", "-m", "yt_dlp", "-J", "--flat-playlist",
            f"https://www.tiktok.com/@{username}"
        ]
        result = subprocess.run(playlist_cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)

        if not data.get("entries"):
            print("⚠️ No videos found.")
            return None

        latest_id = data["entries"][0]["id"]
        video_url = f"https://www.tiktok.com/@{username}/video/{latest_id}"

        return get_video_info(video_url)

    except subprocess.CalledProcessError as e:
        print("❌ yt-dlp error:", e.stderr)
        return None
    except json.JSONDecodeError as e:
        print("❌ JSON parsing error:", str(e))
        return None
    except Exception as e:
        print("❌ Unexpected error:", str(e))
        return None


def download_video(url: str, video_id: str):
    """Download TikTok video to disk."""
    video_path = SAVE_DIR / f"{video_id}.mp4"
    cmd = ["python", "-m", "yt_dlp", "-o", str(video_path), url]

    try:
        subprocess.run(cmd, check=True, timeout=300)  # 5 min timeout
        print(f"🎉 Download complete: {video_path}")
        return video_path
    except subprocess.TimeoutExpired:
        print("❌ Download timeout (5 minutes)")
        return None
    except subprocess.CalledProcessError as e:
        print("❌ Download failed:", e.stderr)
        return None


def post_to_facebook(video_path: Path, caption: str):
    """Upload video to Facebook Page via Graph API."""
    if not PAGE_ACCESS_TOKEN or not PAGE_ID:
        print("❌ Facebook credentials not set")
        return False
    
    url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/videos"
    
    try:
        with open(video_path, "rb") as video_file:
            files = {"source": video_file}
            data = {"description": caption, "access_token": PAGE_ACCESS_TOKEN}
            
            response = requests.post(url, files=files, data=data, timeout=300)
        
        if response.status_code == 200:
            print("✅ Uploaded to Facebook:", response.json())
            return True
        else:
            print("❌ Upload failed:", response.text)
            return False
    except requests.exceptions.RequestException as e:
        print("❌ Upload error:", str(e))
        return False


if __name__ == "__main__":
    print("🚀 Starting TWICE video checker...")
    
    # Method 1: Check a specific video URL
    if len(sys.argv) > 1:
        video_url = sys.argv[1]
        print(f"📹 Checking video: {video_url}")
        video_info = get_video_info(video_url)
    else:
        # Method 2: Check latest from a user (for testing)
        print("ℹ️ No URL provided. Usage:")
        print("   python main.py <tiktok_video_url>")
        print("\nExample:")
        print("   python main.py https://www.tiktok.com/@username/video/1234567890")
        sys.exit(1)
    
    if not video_info:
        print("ℹ️ No valid TWICE video found.")
        sys.exit(0)

    # Ensure file exists
    if not ID_LIST_FILE.exists():
        ID_LIST_FILE.write_text("")

    uploaded_ids = set(ID_LIST_FILE.read_text().splitlines())

    if video_info["id"] in uploaded_ids:
        print(f"⏩ Skipping: Video ({video_info['id']}) already processed.")
        sys.exit(0)

    print("🔗 Latest video URL:", video_info['url'])
    print("📝 Caption:", video_info['caption'][:200], "..." if len(video_info['caption']) > 200 else "")
    print("\n" + "="*50)
    print("🎬 WATCH VIDEO HERE:")
    print(video_info['url'])
    print("="*50 + "\n")

    video_path = download_video(video_info["url"], video_info["id"])
    if video_path and video_path.exists():
        print("✅ Video downloaded successfully!")
        print(f"📁 Saved to: {video_path}")
        
        # 🔧 TESTING MODE: Facebook posting disabled
        # Uncomment below to enable Facebook posting
        """
        fb_caption = f"{video_info['caption']}\n\ncrdts : {video_info['username']}"
        if post_to_facebook(video_path, fb_caption):
            # Append video ID to history
            with open(ID_LIST_FILE, "a") as f:
                f.write(video_info["id"] + "\n")

            video_path.unlink()  # cleanup
            print("🧹 Cleaned up local file.")
        else:
            print("⚠️ Keeping video file due to upload failure")
        """
        
        # For testing: just mark as processed without uploading
        print("ℹ️ Skipping Facebook upload (testing mode)")
        with open(ID_LIST_FILE, "a") as f:
            f.write(video_info["id"] + "\n")
        print("✅ Video ID added to history")
    
    print("✨ Process complete!")
