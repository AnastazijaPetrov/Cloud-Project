import pandas as pd

df = pd.read_csv("data/Covid-19 Twitter Dataset (Apr-Jun 2020).csv")

df = df.sample(50000)

df.to_json("data/twitter_data.json", orient="records")