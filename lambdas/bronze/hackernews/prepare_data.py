import requests
import json

print("Fetching HackerNews dataset...")

top_ids = requests.get(
    "https://hacker-news.firebaseio.com/v0/topstories.json"
).json()

data = []

for story_id in top_ids[:200]:
    item = requests.get(
        f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
    ).json()

    if item:
        data.append(item)

with open("data/hn_data.json", "w", encoding="utf-8") as f:
    json.dump(data, f)

print(f"Saved {len(data)} items")