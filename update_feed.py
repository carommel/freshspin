
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

FEED = Path("data/feed.json")
data = json.loads(FEED.read_text(encoding="utf-8"))

def find_song(artist, title):
    query = urllib.parse.urlencode({
        "term": f"{artist} {title}",
        "country": "ca",
        "media": "music",
        "entity": "song",
        "limit": 15
    })
    url = "https://itunes.apple.com/search?" + query
    request = urllib.request.Request(
        url, headers={"User-Agent": "FreshSpin/1.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        results = json.load(response).get("results", [])

    def normalize(value):
        return "".join(c for c in value.lower() if c.isalnum())

    for song in results:
        if (normalize(song.get("artistName", "")) == normalize(artist)
            and normalize(song.get("trackName", "")) == normalize(title)):
            return song
    return None

for item in data["items"]:
    try:
        song = find_song(item["artist"], item["title"])
        if song:
            item["previewUrl"] = song.get("previewUrl", "")
            item["artwork"] = song.get("artworkUrl100", "").replace(
                "100x100", "600x600"
            )
            item["listenUrl"] = song.get(
                "trackViewUrl", item.get("listenUrl", "")
            )
            print("Updated:", item["title"])
        else:
            print("No exact match:", item["title"])
    except Exception as error:
        print("Error:", item["title"], error)
    time.sleep(4)

FEED.write_text(
    json.dumps(data, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8"
)
