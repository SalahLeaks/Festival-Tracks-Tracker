import requests
import json
import time
from datetime import datetime
from dateutil import parser

# Discord Webhook URL - replace with your actual webhook URL
DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL"

# Fortnite API URL for spark tracks
FORTNITE_API_URL = "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/spark-tracks"

# Local file to store previous API data
DATA_FILE = "spark_tracks.json"

# Maximum number of blocks for the difficulty bar (everything is out of 7)
MAX_BLOCKS = 7

# Number of retries for handling Discord rate limits
MAX_RETRIES = 3

# Custom offsets per song title for each difficulty field.
# Keys: 'pb' = base Lead, 'pd' = base Drums, 'vl' = Vocals,
#       'pg' = Pro Lead, 'ds' = Pro Drums, 'ba' = Bass (and used for Pro Bass too).
custom_offsets = {
    "The Emptiness Machine": {"pb": 1, "pd": 1, "vl": 1, "pg": 1, "ds": 1, "ba": 1},
    "Faint": {"pb": 3, "pd": 2, "vl": 1, "pg": 1, "ds": 0, "ba": 1},
    "Gasolina": {"pb": 4, "pd": 1, "vl": 1, "pg": 1, "ds": 1, "ba": 1},
}

def get_difficulty_bar(value):
    """
    Returns a visual bar for the difficulty based on the given value.
    """
    filled = "▰" * value
    empty = "▱" * (MAX_BLOCKS - value)
    return filled + empty

def get_adjusted_difficulty(track, key):
    """
    Returns the adjusted difficulty value for a given key.
    Looks up a custom offset based on the track title (if provided),
    otherwise defaults to adding 1. Clamped to MAX_BLOCKS.
    """
    title = track.get("tt", "").strip()
    raw = track.get("in", {}).get(key, 0)
    # Get the song-specific offset if available; default offset is 1.
    offset = custom_offsets.get(title, {}).get(key, 1)
    adjusted = raw + offset
    return min(adjusted, MAX_BLOCKS)

def format_duration(seconds):
    """
    Converts seconds into a human-readable format: `X minutes and Y seconds`.
    """
    minutes = seconds // 60
    sec = seconds % 60
    return f"{minutes} minutes and {sec} seconds"

def parse_date(date_str):
    """
    Parses an ISO date string and returns a Unix timestamp.
    """
    if not date_str:
        return None  # Return None if no date is provided
    try:
        print(f"[DEBUG] Parsing date: {date_str}")
        dt = parser.isoparse(date_str)
        timestamp = int(dt.timestamp())
        return timestamp
    except Exception as e:
        print(f"[DEBUG] Error parsing date '{date_str}':", e)
        return None

def fetch_tracks():
    """
    Fetches data from the Fortnite API and returns the JSON response.
    """
    try:
        response = requests.get(FORTNITE_API_URL)
        if response.status_code == 200:
            data = response.json()
            print("[DEBUG] Successfully fetched API data.")
            return data
        else:
            print(f"[DEBUG] API responded with status code {response.status_code}: {response.text}")
    except Exception as e:
        print("[DEBUG] Error fetching API:", e)
    return None

def load_previous_data():
    """
    Loads stored track data from the local file.
    """
    try:
        with open(DATA_FILE, "r") as file:
            data = json.load(file)
            print("[DEBUG] Successfully loaded previous track data.")
            return data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print("[DEBUG] No previous data found or JSON decode error:", e)
        return {}

def save_data(data):
    """
    Saves the current track data to the local file.
    """
    try:
        with open(DATA_FILE, "w") as file:
            json.dump(data, file, indent=4)
        print("[DEBUG] Saved current track data.")
    except Exception as e:
        print("[DEBUG] Error saving data:", e)

def send_discord_message(track):
    """
    Sends an embed message to Discord with the new track information.
    Implements retry logic to handle rate limits.
    """
    active_date = track.get("_activeDate", "")
    print(f"[DEBUG] '_activeDate' field value: {active_date}")
    active_date_ts = parse_date(active_date)
    if not active_date_ts:
        active_date_ts = int(time.time())
        print("[DEBUG] Using fallback timestamp:", active_date_ts)
    active_date_timestamp = f"<t:{active_date_ts}:f>"

    rating_code = track.get("ar", "N/A")
    rating_mapping = {
        "E": "Everyone",
        "T": "Teen",
        "M": "Mature",
        "E10+": "Everyone 10+",
        "RP": "Rating Pending",
    }
    rating_description = rating_mapping.get(rating_code, "Unknown")

    song_id = track.get("ti", "").split(":")[-1] if track.get("ti") else "N/A"

    # Build the embed using our adjusted difficulties.
    embed = {
        "title": "New Track Detected",
        "thumbnail": {"url": track.get("au", "")},
        "fields": [
            {"name": "Jam Track", "value": track.get("tt", "Unknown"), "inline": False},
            {"name": "Artist", "value": track.get("an", "Unknown"), "inline": False},
            {"name": "Rating", "value": rating_description, "inline": True},
            {"name": "Song ID", "value": f"```{song_id}```", "inline": True},
            {"name": "Active Date", "value": f"Date: {active_date_timestamp}", "inline": True},
            {"name": "Duration", "value": format_duration(track.get("dn", 0)), "inline": True},
            {
                "name": "Difficulty Chart",
                "value": (
                    f"**Lead:** {get_difficulty_bar(get_adjusted_difficulty(track, 'pb'))}\n"
                    f"**Drums:** {get_difficulty_bar(get_adjusted_difficulty(track, 'pd'))}\n"
                    f"**Vocals:** {get_difficulty_bar(get_adjusted_difficulty(track, 'vl'))}\n"
                    f"**Bass:** {get_difficulty_bar(get_adjusted_difficulty(track, 'ba'))}\n"
                    f"**Pro Lead:** {get_difficulty_bar(get_adjusted_difficulty(track, 'pg'))}\n"
                    f"**Pro Drums:** {get_difficulty_bar(get_adjusted_difficulty(track, 'ds'))}\n"
                    f"**Pro Bass:** {get_difficulty_bar(get_adjusted_difficulty(track, 'ba'))}\n"
                    f"**Pro Vocals:** {get_difficulty_bar(get_adjusted_difficulty(track, 'bd'))}\n"
                ),
                "inline": False
            }
        ]
    }

    payload = {"embeds": [embed]}

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            if response.status_code in (200, 204):
                print("[DEBUG] Successfully sent Discord message for track:", track.get("tt"))
                return
            elif response.status_code == 429:
                retry_after = response.json().get("retry_after", 5) / 1000
                print(f"[DEBUG] Rate limited! Retrying in {retry_after:.2f} seconds...")
                time.sleep(retry_after)
            else:
                print("[DEBUG] Failed to send Discord message:", response.text)
                return
        except Exception as e:
            print(f"[DEBUG] Error sending Discord webhook (attempt {attempt + 1}):", e)
            time.sleep(2)

def extract_tracks(api_data):
    """
    Extracts individual track dictionaries from the API data.
    """
    tracks = []
    for key, value in api_data.items():
        if key.startswith("_"):
            continue  # Skip metadata
        if isinstance(value, dict):
            if "track" in value:
                track_data = value["track"]
                track_data["_activeDate"] = value.get("_activeDate", "")
                track_data["lastModified"] = value.get("lastModified", "")
                tracks.append(track_data)
                print(f"[DEBUG] Extracted track '{track_data.get('tt', key)}' from key '{key}'.")
            else:
                tracks.append(value)
                print(f"[DEBUG] Extracted track from key '{key}' without explicit 'track' key.")
    print(f"[DEBUG] Total tracks extracted: {len(tracks)}")
    return tracks

def check_for_new_tracks():
    """
    Checks the API for new tracks compared to stored data and sends a Discord webhook if found.
    """
    api_data = fetch_tracks()
    if not api_data:
        print("[DEBUG] No API data fetched.")
        return

    current_tracks = extract_tracks(api_data)
    previous_data = load_previous_data()

    new_tracks = []
    for track in current_tracks:
        song_id = track.get("su")
        if not song_id:
            print("[DEBUG] Track without a song ID found, skipping:", track)
            continue
        if song_id not in previous_data:
            new_tracks.append(track)
            print(f"[DEBUG] New track detected: {track.get('tt', 'Unknown')} (ID: {song_id})")
        else:
            print(f"[DEBUG] Track already processed: {track.get('tt', 'Unknown')} (ID: {song_id})")

    for track in new_tracks:
        send_discord_message(track)

    all_tracks = {track["su"]: track for track in current_tracks if "su" in track}
    save_data(all_tracks)

if __name__ == "__main__":
    print("[DEBUG] Starting Spark Tracks checker.")
    while True:
        check_for_new_tracks()
        time.sleep(60)