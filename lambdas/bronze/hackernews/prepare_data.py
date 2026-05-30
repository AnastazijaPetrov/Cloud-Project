from datetime import datetime, timedelta
import os, json, requests

print("Fetching HackerNews dataset...")

os.makedirs("lambdas/bronze/hackernews/data", exist_ok=True)

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

yesterday = datetime.utcnow() - timedelta(days=1)

filename = f"hn_{yesterday.strftime('%Y%m%d')}.json"

path = f"lambdas/bronze/hackernews/data/{filename}"

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f)

print(f"Saved {len(data)} items to {path}")