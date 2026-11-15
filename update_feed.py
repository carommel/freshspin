
import json
import random
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

FEED = Path("data/feed.json")
LIBRARY = Path("data/library.json")

TODAY = datetime.now(timezone.utc)
SEED = TODAY.strftime("%Y-%m-%d")
RNG = random.Random(SEED)

TARGETS = {"new": 5, "artist": 4, "old": 6}

GENRES = {
    "R&B": ["r&b", "rnb", "neo soul"],
    "Soul": ["soul", "modern soul"],
    "Funk": ["funk"],
    "Jazz": ["jazz"],
    "Hip-hop": ["hip hop", "hip-hop", "boom bap"],
    "Rap": ["rap"]
}

QUERIES = [
    "neo soul", "alternative r&b", "modern soul",
    "jazz soul", "funk", "hip hop", "underground rap",
    "contemporary r&b", "soul music", "jazz",
    "independent soul", "alternative hip hop",
    "rare soul", "jazz funk", "boogie",
    "quiet storm", "deep soul", "classic funk",
    "jazz rap", "independent r&b", "boom bap",
    "1970s funk", "1980s soul", "1990s hip hop"
]

def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )
    temp.replace(path)

def search(term):
    params = urllib.parse.urlencode({
        "term": term,
        "country": "ca",
        "media": "music",
        "entity": "song",
        "limit": 200
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
        and song.get("trackId") is not None
        and all(
            str(song.get(field, "")).startswith("https://")
            for field in (
                "previewUrl",
                "artworkUrl100",
                "trackViewUrl"
            )
        )
        and genre_of(song) is not None
        and release_date(song) is not None
    )

def make_item(song, category):
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
        "artwork": song["artworkUrl100"].replace(
            "100x100", "600x600"
        ),
        "previewUrl": song["previewUrl"],
        "listenUrl": song["trackViewUrl"],
        "added": SEED
    }
if FEED.exists():
    existing_feed = read_json(FEED, {})
    if (
        existing_feed.get("updated") == SEED
        and LIBRARY.exists()
    ):
        print("Already updated today. No changes needed.")
        raise SystemExit(0)
previous = read_json(FEED, {"items": []})
library_data = read_json(LIBRARY, {"items": []})

# Preserve existing songs and their original categories.
library = {}

for item in library_data.get("items", []):
    sid = str(item.get("id", ""))
    if sid and item.get("category") in TARGETS:
        library[sid] = dict(item)

# Import the current feed into the permanent archive.
# Keep existing metadata and original category.
for item in previous.get("items", []):
    sid = str(item.get("id", ""))
    if not sid or item.get("category") not in TARGETS:
        continue
    if sid not in library:
        archived = dict(item)
        archived["added"] = previous.get("updated", SEED)
        library[sid] = archived

# Existing library IDs cannot be featured again.
used_ids = set(library)
used_artists = set()
selected = []

# Search Apple for candidate discoveries.
pool = {}
for term in QUERIES:
    try:
        results = search(term)
        for song in results:
            if valid(song):
                pool[str(song["trackId"])] = song
        print("Searched:", term, len(results))
    except Exception as error:
        print("Search failed:", term, error)
    time.sleep(3)

songs = list(pool.values())
RNG.shuffle(songs)

def choose(candidates, category, target):
    count = 0
    for song in candidates:
        sid = str(song["trackId"])
        artist = song.get("artistName", "").lower()

        if sid in used_ids or artist in used_artists:
            continue

        selected.append(make_item(song, category))
        used_ids.add(sid)
        used_artists.add(artist)
        count += 1

        if count >= target:
            break

    print(category, "selected:", count)
    return count

recent = [
    s for s in songs
    if 0 <= (TODAY - release_date(s)).days <= 120
]

artist_candidates = [
    s for s in songs
    if 0 <= (TODAY - release_date(s)).days <= 730
]

older = [
    s for s in songs
    if 1960 <= release_date(s).year <= 1999
]

# One exclusive category per song.
# New Artists are recent discovery candidates,
# not yet verified emerging artists.
choose(artist_candidates, "artist", TARGETS["artist"])
choose(recent, "new", TARGETS["new"])
choose(older, "old", TARGETS["old"])

# Publish partial daily selections when necessary.
# Never replace the feed with an empty selection.
if not selected:
    print("No new qualifying tracks found.")
    print("Keeping the previous daily feed.")
else:
    RNG.shuffle(selected)

    for item in selected:
        library[item["id"]] = item

    print("New discoveries:", len(selected))

# Keep all archived songs, newest first.
all_items = sorted(
    library.values(),
    key=lambda item: (
        item.get("added", ""),
        str(item.get("id", ""))
    ),
    reverse=True
)

# Always save the permanent archive, including
# imported songs from the previous feed.
write_json(LIBRARY, {"items": all_items})

if selected:
    # Preserve today's selections if the updater
    # runs a second time on the same UTC date.
    if previous.get("updated") == SEED:
        existing = previous.get("items", [])
        existing_ids = {
            str(item["id"]) for item in existing
        }
        new_items = [
            item for item in selected
            if str(item["id"]) not in existing_ids
        ]
        remaining = max(0, 15 - len(existing))
        daily_items = existing + new_items[:remaining]
    else:
        daily_items = selected

    write_json(FEED, {
        "updated": SEED,
        "items": daily_items
    })

    print("Today's featured tracks:", len(daily_items))

print("Permanent library size:", len(all_items))
print("Finished.")
