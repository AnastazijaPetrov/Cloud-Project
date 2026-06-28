import pandas as pd
import numpy as np

df = pd.read_csv(
    "data/Covid-19 Twitter Dataset (Apr-Jun 2020).csv",
    dtype={"id": "string"},
    keep_default_na=False,
)

df = df.reset_index().rename(columns={"index": "source_row_id"})

df = df.sample(n=min(50000, len(df)), random_state=42)

df["post_id"] = df["id"].astype(str) + "_" + df["source_row_id"].astype(str)

authors = df.loc[df["original_author"].str.strip() != "", "original_author"].unique()

rng = np.random.default_rng(seed=42)

author_profile = pd.DataFrame({
    "original_author": authors,
    "followers_count": np.clip(rng.lognormal(mean=7.5, sigma=2.0, size=len(authors)).astype(int), 0, 5_000_000),
    "is_verified": rng.choice([True, False], size=len(authors), p=[0.08, 0.92]),
})

df = df.merge(author_profile, on="original_author", how="left")

df.to_json(
    "data/twitter_data.json",
    orient="records",
    force_ascii=False,
)