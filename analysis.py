"""
NYC Airbnb Market Analysis
--------------------------
Data: Inside Airbnb, New York City listings snapshot (14 June 2026)
      https://insideairbnb.com/get-the-data/  ->  visualisations/listings.csv

Questions:
  1. How do prices differ across boroughs and neighbourhoods?
  2. What is the room-type mix, and how does price vary by room type?
  3. Where is guest demand highest (reviews in the last 12 months as a proxy)?
  4. How has NYC's short-term rental law (Local Law 18) shaped the market?
  5. How concentrated is supply among multi-listing hosts?

Run:  python analysis.py
Output: cleaned data summary in the console, charts in figures/, numbers in results.md
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

DATA = Path("data/listings.csv")
FIG = Path("figures")
FIG.mkdir(exist_ok=True)

sns.set_theme(style="whitegrid")
BOROUGH_ORDER = ["Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"]
results = []  # lines written to results.md


def note(line=""):
    print(line)
    results.append(line)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 1. Load and inspect
# ---------------------------------------------------------------------------
raw = pd.read_csv(DATA)
note("# Results")
note()
note("## Data cleaning")
note(f"- Raw listings: {len(raw):,}")
note(f"- Listings with no price (inactive / unpriced): {raw['price'].isna().sum():,} "
     f"({raw['price'].isna().mean():.0%})")

# ---------------------------------------------------------------------------
# 2. Clean
# ---------------------------------------------------------------------------
df = raw.copy()

# Reviews: a missing value means the listing has never been reviewed
df["reviews_per_month"] = df["reviews_per_month"].fillna(0)
df["last_review"] = pd.to_datetime(df["last_review"], errors="coerce")
df["licensed"] = df["license"].notna() & (df["license"].str.lower() != "exempt")
df["short_term"] = df["minimum_nights"] < 30  # under 30 nights = short-term rental in NYC

# Pricing analysis only uses priced listings, with extreme outliers removed.
# The 1st and 99th percentiles are used so that a few $10,000+/night listings
# don't distort averages.
priced = df.dropna(subset=["price"])
low, high = priced["price"].quantile([0.01, 0.99])
priced = priced[priced["price"].between(low, high)]
note(f"- Priced listings after removing outliers (outside ${low:.0f}-${high:.0f}/night): {len(priced):,}")
note()

# ---------------------------------------------------------------------------
# 3. Price by borough
# ---------------------------------------------------------------------------
city_median = priced["price"].median()
by_borough = (priced.groupby("neighbourhood_group")["price"]
              .agg(listings="count", median="median", mean="mean")
              .reindex(BOROUGH_ORDER))
by_borough["vs_city_median"] = by_borough["median"] / city_median - 1

note("## 1. Price by borough")
note(f"- City-wide median nightly price: ${city_median:.0f}")
for b, r in by_borough.iterrows():
    note(f"- {b}: median ${r['median']:.0f} ({r['vs_city_median']:+.0%} vs city), {r['listings']:,.0f} priced listings")
note()

fig, ax = plt.subplots(figsize=(8, 4.5))
sns.boxplot(data=priced, x="neighbourhood_group", y="price", order=BOROUGH_ORDER,
            showfliers=False, color="#7fa7d6", ax=ax)
ax.set(title="Nightly price by borough (outliers hidden)", xlabel="", ylabel="Price per night ($)")
save(fig, "01_price_by_borough.png")

# Top neighbourhoods (only those with enough listings to be meaningful)
nb = (priced.groupby(["neighbourhood", "neighbourhood_group"])["price"]
      .agg(listings="count", median="median").reset_index())
nb = nb[nb["listings"] >= 50]
top_nb = nb.sort_values("median", ascending=False).head(10)

note("### Most expensive neighbourhoods (50+ priced listings)")
for _, r in top_nb.iterrows():
    note(f"- {r['neighbourhood']} ({r['neighbourhood_group']}): median ${r['median']:.0f}")
note()

fig, ax = plt.subplots(figsize=(8, 5))
sns.barplot(data=top_nb, y="neighbourhood", x="median", hue="neighbourhood_group", dodge=False, ax=ax)
ax.set(title="Top 10 neighbourhoods by median nightly price", xlabel="Median price ($)", ylabel="")
ax.legend(title="")
save(fig, "02_top_neighbourhoods.png")

# ---------------------------------------------------------------------------
# 4. Room types
# ---------------------------------------------------------------------------
mix = df["room_type"].value_counts(normalize=True)
room_price = priced.groupby("room_type")["price"].median()

note("## 2. Room-type mix and price")
for rt, share in mix.items():
    note(f"- {rt}: {share:.0%} of listings, median ${room_price.get(rt, float('nan')):.0f}/night")
note()

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
mix.mul(100).plot.bar(ax=axes[0], color="#7fa7d6")
axes[0].set(title="Share of listings by room type", ylabel="% of listings", xlabel="")
axes[0].tick_params(axis="x", rotation=20)
room_price.reindex(mix.index).plot.bar(ax=axes[1], color="#e39b5b")
axes[1].set(title="Median nightly price by room type", ylabel="Price ($)", xlabel="")
axes[1].tick_params(axis="x", rotation=20)
save(fig, "03_room_types.png")

# ---------------------------------------------------------------------------
# 5. Demand (reviews in the last 12 months as a proxy for stays)
# ---------------------------------------------------------------------------
df["active"] = df["number_of_reviews_ltm"] > 0
demand = (df.groupby("neighbourhood_group")
          .agg(listings=("id", "count"),
               active_share=("active", "mean"),
               reviews_ltm=("number_of_reviews_ltm", "sum"))
          .reindex(BOROUGH_ORDER))
demand["reviews_per_listing"] = demand["reviews_ltm"] / demand["listings"]

note("## 3. Demand (reviews in the last 12 months)")
note(f"- Only {df['active'].mean():.0%} of all listings received a review in the last 12 months")
for b, r in demand.iterrows():
    note(f"- {b}: {r['active_share']:.0%} of listings active, {r['reviews_per_listing']:.1f} reviews per listing")
by_room_active = df.groupby("room_type")["active"].mean()
for rt, s in by_room_active.sort_values(ascending=False).items():
    note(f"- {rt}: {s:.0%} active")
note()

fig, ax = plt.subplots(figsize=(8, 4.5))
demand["reviews_per_listing"].plot.bar(ax=ax, color="#5bab8a")
ax.set(title="Reviews per listing in the last 12 months (demand proxy)", ylabel="Reviews per listing", xlabel="")
ax.tick_params(axis="x", rotation=0)
save(fig, "04_demand_by_borough.png")

# ---------------------------------------------------------------------------
# 6. Regulation: Local Law 18 (Sept 2023) requires registration for stays < 30 nights
# ---------------------------------------------------------------------------
st = df["short_term"]
note("## 4. Impact of short-term rental regulation (Local Law 18)")
note(f"- {(~st).mean():.0%} of listings require a minimum stay of 30+ nights (i.e. operate as monthly rentals)")
note(f"- {st.mean():.0%} of listings allow stays under 30 nights")
note(f"- Of short-term listings, {df.loc[st, 'licensed'].mean():.0%} show a registration/licence number")
note(f"- Active in last 12 months: short-term {df.loc[st, 'active'].mean():.0%} vs 30+ nights {df.loc[~st, 'active'].mean():.0%}")
st_price = priced.groupby(priced['minimum_nights'] < 30)['price'].median()
note(f"- Median price: short-term ${st_price.get(True, float('nan')):.0f} vs 30+ nights ${st_price.get(False, float('nan')):.0f}")
note()

fig, ax = plt.subplots(figsize=(8, 4.5))
clipped = df["minimum_nights"].clip(upper=40)
sns.histplot(clipped, bins=40, ax=ax, color="#7fa7d6")
ax.axvline(30, color="#c0392b", ls="--")
ax.text(30.5, ax.get_ylim()[1] * 0.9, "30-night rule", color="#c0392b")
ax.set(title="Minimum-night requirement (values above 40 grouped at 40)", xlabel="Minimum nights", ylabel="Listings")
save(fig, "05_minimum_nights.png")

# ---------------------------------------------------------------------------
# 7. Host concentration
# ---------------------------------------------------------------------------
hosts = df.dropna(subset=["calculated_host_listings_count"])
multi = hosts["calculated_host_listings_count"] > 1
big = hosts["calculated_host_listings_count"] >= 10
note("## 5. Host concentration")
note(f"- {multi.mean():.0%} of listings belong to hosts with more than one listing")
note(f"- {big.mean():.0%} of listings belong to hosts with 10+ listings (likely commercial operators)")
note(f"- Unique hosts: {hosts['host_id'].nunique():,}")
note()

# ---------------------------------------------------------------------------
# 8. Map
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(7, 7))
sns.scatterplot(data=priced, x="longitude", y="latitude", hue="price", palette="viridis",
                s=4, linewidth=0, alpha=0.6, ax=ax, hue_norm=(0, priced["price"].quantile(0.9)))
ax.set(title="Listings by location, coloured by price", xlabel="", ylabel="")
ax.set_aspect("equal")
ax.legend(title="Price ($)", loc="upper left", fontsize=8)
save(fig, "06_price_map.png")

Path("results.md").write_text("\n".join(results), encoding="utf-8")
print("\nCharts saved to figures/, numbers saved to results.md")
