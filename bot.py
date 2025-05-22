# Updated Code with pro vocals and modified tracks
import requests
import json
import time
from datetime import datetime
from dateutil import parser

# Discord Webhook URL
DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK"

# Fortnite API URL for spark tracks
FORTNITE_API_URL = "https://fortnitecontent-website-prod07.ol.epicgames.com/content/api/pages/fortnite-game/spark-tracks"

# Local file to store previous API data
DATA_FILE = "spark_tracks.json"

# Maximum number of blocks for the difficulty bar (everything is out of 7)
MAX_BLOCKS = 7

# Number of retries for handling Discord rate limits
MAX_RETRIES = 3

# Which difficulties to include in the embed
ENABLED_DIFFICULTIES = {'pb', 'pd', 'vl', 'ba', 'pg', 'ds', 'bd'}

# Custom offsets per song title for each difficulty field.
custom_offsets = {
    "The Emptiness Machine": {"pb": 1, "pd": 1, "vl": 1, "pg": 1, "ds": 1, "ba": 1, "bd": 1},
    "Faint":                 {"pb": 3, "pd": 2, "vl": 1, "pg": 1, "ds": 0, "ba": 1, "bd": 2},
    "Gasolina":              {"pb": 4, "pd": 1, "vl": 1, "pg": 1, "ds": 1, "ba": 1, "bd": 1},
}

DIFFICULTY_NAMES = {
    'pb': "Lead",
    'pd': "Drums",
    'vl': "Vocals",
    'ba': "Bass",
    'pg': "Pro Lead",
    'ds': "Pro Drums",
    'bd': "Pro Vocals",
}

def get_difficulty_bar(value):
    return "▰" * value + "▱" * (MAX_BLOCKS - value)

def get_adjusted_difficulty(track, key):
    title = track.get("tt", "").strip()
    raw   = track.get("in", {}).get(key, 0)
    offset = custom_offsets.get(title, {}).get(key, 1)
    return max(0, min(raw + offset, MAX_BLOCKS))

def format_duration(seconds):
    return f"{seconds//60} minutes and {seconds%60} seconds"

def parse_date(date_str):
    if not date_str:
        return None
    try:
        return int(parser.isoparse(date_str).timestamp())
    except:
        return None

def fetch_tracks():
    try:
        r = requests.get(FORTNITE_API_URL)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def load_previous_data():
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def build_embed(track, is_update=False):
    title = "Updated Track Detected" if is_update else "New Track Detected"
    ts = parse_date(track.get("_activeDate", "")) or int(time.time())
    rating_map = {"E":"Everyone","T":"Teen","M":"Mature","E10+":"Everyone 10+","RP":"Rating Pending"}
    embed = {
        "title": title,
        "thumbnail": {"url": track.get("au", "")},
        "fields": [
            {"name":"Jam Track","value":track.get("tt","Unknown"),"inline":False},
            {"name":"Artist","value":track.get("an","Unknown"),"inline":False},
            {"name":"Rating","value":rating_map.get(track.get("ar",""),"Unknown"),"inline":True},
            {"name":"Song ID","value":f"```{track.get('ti','').split(':')[-1] or 'N/A'}```","inline":True},
            {"name":"Active Date","value":f"<t:{ts}:f>","inline":True},
            {"name":"Duration","value":format_duration(track.get("dn",0)),"inline":True},
            {"name":"Difficulty Chart",
             "value":"\n".join(
                 f"**{DIFFICULTY_NAMES[k]}:** {get_difficulty_bar(get_adjusted_difficulty(track,k))}"
                 for k in ['pb','pd','vl','ba','pg','ds','bd'] if k in ENABLED_DIFFICULTIES
             ),
             "inline":False}
        ]
    }
    return embed

def send_discord_message(track, is_update=False):
    payload = {"embeds":[build_embed(track, is_update)]}
    for _ in range(MAX_RETRIES):
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if r.status_code in (200,204):
            print(f"[DEBUG] Sent {'update' if is_update else 'new'}: {track.get('tt')}")
            return
        if r.status_code == 429:
            time.sleep(r.json().get("retry_after",5)/1000)
        else:
            print("[DEBUG] Webhook error:", r.text)
            return

def extract_tracks(api_data):
    tracks = []
    for key, val in api_data.items():
        # skip metadata or non-dicts
        if not isinstance(val, dict) or key.startswith("_"):
            continue
        entry = val.get("track", val)
        entry["_activeDate"]  = val.get("_activeDate","")
        entry["lastModified"] = val.get("lastModified","")
        tracks.append(entry)
    return tracks

def check_for_new_or_modified_tracks():
    data = fetch_tracks()
    if not data:
        return
    current = extract_tracks(data)
    previous = load_previous_data()
    next_save = {}

    for t in current:
        uid = t.get("su")
        if not uid:
            continue
        next_save[uid] = t

        old = previous.get(uid)
        if old is None:
            send_discord_message(t, is_update=False)
        else:
            if json.dumps(old, sort_keys=True) != json.dumps(t, sort_keys=True):
                send_discord_message(t, is_update=True)

    save_data(next_save)

if __name__ == "__main__":
    while True:
        check_for_new_or_modified_tracks()
        time.sleep(60)