
import json
import random
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

FEED = Path("data/feed.json")
TODAY = datetime.now(timezone.utc)
SEED = TODAY.strftime("%Y-%m-%d")
randomizer = random.Random(SEED)

GENRES = {
    "R&B": ["r&b", "rnb", "neo soul", "alternative r&b"],
    "Soul": ["soul", "modern soul"],
    "Funk": ["funk", "funk soul"],
    "Jazz": ["jazz", "jazz soul"],
    "Hip-hop": ["hip hop", "hip-hop", "boom bap"],
    "Rap": ["rap", "underground rap"]
}

QUERIES = [
    "neo soul", "alternative r&b", "modern soul",
    "jazz soul", "funk", "hip hop", "underground rap",
    "contemporary r&b", "soul music", "jazz",
    "independent soul", "alternative hip hop"
]

def search(term, limit=100):
    params = urllib.parse.urlencode({
        "term": term,
        "country": "ca",
        "media": "music",
        "entity": "song",
        "limit": limit
    })
    request = urllib.request.Request(
        "https://itunes.apple.com/search?" + params,
        headers={"User-Agent": "FreshSpin/1.0"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response).get("results", [])

def genre_of(song):
    name = song.get("primaryGenreName", "").lower()
    for label, keywords in GENRES.items():
        if any(word in name for word in keywords):
            return label
    return None

def release_date(song):
    try:
        return datetime.fromisoformat(
            song["releaseDate"].replace("Z", "+00:00")
        )
    except (KeyError, ValueError):
        return None

def valid(song):
    return (
        song.get("kind") == "song"
        and song.get("trackId")
        and song.get("previewUrl", "").startswith("https://")
        and song.get("artworkUrl100", "").startswith("https://")
        and song.get("trackViewUrl", "").startswith("https://")
        and genre_of(song) is not None
        and release_date(song) is not None
    )

def make_item(song, category):
    artwork = song["artworkUrl100"]
    return {
        "id": str(song["trackId"]),
        "title": song["trackName"],
        "artist": song["artistName"],
        "genre": genre_of(song),
        "category": category,
        "description": (
            f"{release_date(song).year} · "
            + song.get("collectionName", "Music discovery")
        ),
        "artwork": artwork.replace("100x100", "600x600"),
        "previewUrl": song["previewUrl"],
        "listenUrl": song["trackViewUrl"]
    }

pool = {}
for term in QUERIES:
    try:
        for song in search(term):
            if valid(song):
                pool[str(song["trackId"])] = song
        print("Searched:", term)
    except Exception as error:
        print("Search failed:", term, error)
    time.sleep(4)

songs = list(pool.values())
randomizer.shuffle(songs)
selected = []
used_ids = set()
used_artists = set()

def add_from(candidates, category, limit=10):
    count = 0
    for song in candidates:
        song_id = str(song["trackId"])
        artist = song.get("artistName", "").lower()
        if song_id in used_ids or artist in used_artists:
            continue
        selected.append(make_item(song, category))
        used_ids.add(song_id)
        used_artists.add(artist)
        count += 1
        if count == limit:
            break
    print(category, count, "tracks selected")

recent = [
    s for s in songs
    if TODAY - timedelta(days=90) <= release_date(s) <= TODAY
]
add_from(recent, "new")

# Discovery candidates, not verified debut artists.
artist_candidates = [
    s for s in songs
    if TODAY - timedelta(days=730) <= release_date(s) <= TODAY
    and str(s["trackId"]) not in used_ids
]
add_from(artist_candidates, "artist")

# Catalogue dates can reflect reissues, not original releases.
older = [
    s for s in songs
    if 1960 <= release_date(s).year <= 1999
]
add_from(older, "old")

# Retain previous Rediscover selections when discovery is short.
previous = json.loads(FEED.read_text(encoding="utf-8"))
old_count = sum(x["category"] == "old" for x in selected)

for item in previous.get("items", []):
    if old_count >= 10:
        break
    if item.get("category") != "old":
        continue
    if not item.get("previewUrl") or not item.get("artwork"):
        continue
    if str(item["id"]) in used_ids:
        continue
    selected.append(item)
    used_ids.add(str(item["id"]))
    old_count += 1

# Avoid publishing an empty or unusually small feed.
if len(selected) < 15:
    raise RuntimeError(
        f"Only {len(selected)} tracks found; keeping existing feed"
    )

randomizer.shuffle(selected)

FEED.write_text(
    json.dumps({
        "updated": SEED,
        "items": selected
    }, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8"
)

print("Published", len(selected), "discoveries")

