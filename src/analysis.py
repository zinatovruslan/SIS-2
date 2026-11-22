"""EDA stage: reads the cleaned data from SQLite (not from CSV) and builds figures.

Run: python -m src.analysis
Input : config.DB_PATH, table `earthquakes`
Output: figures/*.png, data/stats/analysis.json
"""
import sqlite3
import sys

import matplotlib

matplotlib.use("Agg")  # no window needed, figures are only saved to files
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import config

NUMERIC_COLS = ["mag", "depth_km", "sig", "distance_from_equator_km", "energy_log10_j"]
STRENGTH_ORDER = ["minor", "light", "moderate", "strong", "major"]
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
STRENGTH_COLORS = {
    "minor": "#9ecae1",
    "light": "#4292c6",
    "moderate": "#fd8d3c",
    "strong": "#e6550d",
    "major": "#a50f15",
}


def load_data():
    """Read the whole table from SQLite and add date columns for the analysis."""
    if not config.DB_PATH.exists():
        print(f"ERROR: database {config.DB_PATH.name} not found, run: python -m src.loader")
        sys.exit(1)
    connection = sqlite3.connect(config.DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM earthquakes", connection)
    except (pd.errors.DatabaseError, sqlite3.Error) as error:
        print(f"ERROR: cannot read table 'earthquakes': {error}")
        sys.exit(1)
    finally:
        connection.close()
    if df.empty:
        print("ERROR: table 'earthquakes' is empty")
        sys.exit(1)

    df["time_utc"] = pd.to_datetime(df["time_utc"], utc=True, format="ISO8601")
    df["date"] = df["time_utc"].dt.date
    df["day_of_week"] = df["time_utc"].dt.day_name()
    # strength category is derived here from the magnitude (the table does not store it)
    df["strength_category"] = pd.cut(
        df["mag"], bins=[-np.inf, 4, 5, 6, 7, np.inf], labels=STRENGTH_ORDER, right=False
    )
    return df


def print_overview(df):
    print("=" * 60)
    print("1. DATASET OVERVIEW")
    print("=" * 60)
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    print("\nData types:")
    print(df.dtypes.to_string())
    print("\nDescriptive statistics (numerical columns):")
    numeric_cols = [c for c in NUMERIC_COLS if c in df.columns]
    print(df[numeric_cols].describe().round(2).to_string())
    print("\nMissing values per column:")
    print(df.isna().sum().to_string())


def print_categorical(df):
    print("\n" + "=" * 60)
    print("2. CATEGORICAL STATISTICS (value_counts)")
    print("=" * 60)
    for column in ["strength_category", "depth_band", "mag_type", "status", "tsunami", "alert"]:
        if column in df.columns:
            print(f"\n{column}:")
            print(df[column].value_counts(dropna=False).to_string())


def print_correlations(df):
    print("\n" + "=" * 60)
    print("3. CORRELATIONS")
    print("=" * 60)
    corr_cols = ["mag", "depth_km", "sig", "distance_from_equator_km", "tsunami"]
    corr = df[corr_cols].corr().round(2)
    print(corr.to_string())
    return corr


def print_grouped(df):
    print("\n" + "=" * 60)
    print("4. GROUPED ANALYSIS (groupby + agg)")
    print("=" * 60)
    by_region = (
        df.groupby("region")
        .agg(events=("id", "count"), mean_mag=("mag", "mean"), max_mag=("mag", "max"), mean_depth=("depth_km", "mean"))
        .round(2)
        .sort_values("events", ascending=False)
    )
    print("\nTop 10 regions by number of events:")
    print(by_region.head(10).to_string())

    by_day = (
        df.groupby("day_of_week")
        .agg(events=("id", "count"), mean_mag=("mag", "mean"))
        .round(2)
        .reindex(DAY_ORDER)
    )
    print("\nBy day of week:")
    print(by_day.to_string())

    by_strength = (
        df.groupby("strength_category", observed=True)
        .agg(events=("id", "count"), mean_depth=("depth_km", "mean"), mean_sig=("sig", "mean"))
        .round(2)
    )
    by_tsunami = (
        df.groupby("tsunami")
        .agg(events=("id", "count"), mean_mag=("mag", "mean"), max_mag=("mag", "max"))
        .round(2)
    )
    print("\nBy tsunami flag:")
    print(by_tsunami.to_string())

    print("\nBy strength category:")
    print(by_strength.to_string())
    return by_region, by_day, by_strength


def save_figure(name):
    config.ensure_dirs()
    path = config.FIGURES_DIR / name
    plt.tight_layout()
    plt.savefig(path, dpi=130)
    plt.close()
    print(f"  saved: figures/{name}")


def plot_magnitude_hist(df):
    mean_mag = df["mag"].mean()
    median_mag = df["mag"].median()
    plt.figure(figsize=(8, 5))
    plt.hist(df["mag"], bins=25, color="#4292c6", edgecolor="black", alpha=0.8)
    plt.axvline(mean_mag, color="red", linestyle="--", label=f"Mean = {mean_mag:.2f}")
    plt.axvline(median_mag, color="green", linestyle="-.", label=f"Median = {median_mag:.2f}")
    plt.title("Distribution of earthquake magnitudes")
    plt.xlabel("Magnitude")
    plt.ylabel("Number of earthquakes")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.4)
    save_figure("magnitudes_hist.png")
    share_below_4 = (df["mag"] < 4).mean() * 100
    share_above_6 = (df["mag"] >= 6).mean() * 100
    return (
        f"Mean magnitude is {mean_mag:.2f}, median {median_mag:.2f}; {share_below_4:.1f}% of events are below M4 "
        f"and only {share_above_6:.1f}% are M6 or stronger (max M{df['mag'].max():.1f}). "
        f"Skewness is {df['mag'].skew():.2f}; the histogram may mix two groups (small local events and M4-5 global events), "
        f"which is related to the 2.5 magnitude threshold and to different networks."
    )


def plot_magnitude_depth_scatter(df):
    plt.figure(figsize=(9, 6))
    for category in STRENGTH_ORDER:
        subset = df[df["strength_category"] == category]
        if subset.empty:
            continue
        plt.scatter(
            subset["mag"], subset["depth_km"], s=14, alpha=0.6,
            color=STRENGTH_COLORS[category], label=f"{category} (n={len(subset)})",
        )
    plt.gca().invert_yaxis()  # deeper events are lower on the plot
    plt.title("Magnitude vs depth by strength category")
    plt.xlabel("Magnitude")
    plt.ylabel("Depth (km, inverted axis)")
    plt.legend(title="Strength category")
    plt.grid(True, linestyle="--", alpha=0.4)
    save_figure("magnitude_depth_scatter.png")
    corr = df["mag"].corr(df["depth_km"])
    deep_share = (df["depth_km"] > 300).mean() * 100
    return (
        f"Correlation between magnitude and depth is {corr:.2f}, so depth hardly explains magnitude. "
        f"Events deeper than 300 km are {deep_share:.1f}% of the data; most earthquakes are shallow."
    )


def plot_top_regions(df):
    top = df["region"].value_counts().head(10).sort_values()
    plt.figure(figsize=(10, 6))
    plt.barh(top.index, top.values, color="#fd8d3c", edgecolor="black", label="Events")
    for position, value in enumerate(top.values):
        plt.text(value + 0.5, position, str(value), va="center")
    plt.title("Top 10 regions by number of earthquakes")
    plt.xlabel("Number of earthquakes")
    plt.ylabel("Region")
    plt.legend(loc="lower right")
    plt.grid(True, axis="x", linestyle="--", alpha=0.4)
    save_figure("top_regions_bar.png")
    top_share = df["region"].value_counts().head(10).sum() / len(df) * 100
    leader = top.index[-1]
    return (
        f"The most active region is {leader} ({top.iloc[-1]} events). "
        f"The top 10 regions give {top_share:.1f}% of all earthquakes, so activity is concentrated "
        f"in a few seismic belts."
    )


def plot_daily_counts(df):
    daily = df.groupby("date").size()
    plt.figure(figsize=(11, 5))
    plt.plot(daily.index, daily.values, marker="o", color="green", label="Earthquakes per day")
    plt.axhline(daily.mean(), color="red", linestyle="--", label=f"Mean = {daily.mean():.1f}")
    plt.title("Number of earthquakes per day")
    plt.xlabel("Date")
    plt.ylabel("Number of earthquakes")
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.4)
    save_figure("earthquakes_by_day_line.png")
    peak_day = daily.idxmax()
    return (
        f"On average {daily.mean():.1f} earthquakes per day. The peak day is {peak_day} with {daily.max()} events, "
        f"the quietest has {daily.min()}. A peak day may be linked to a strong earthquake and its aftershocks."
    )


def plot_correlation_heatmap(corr):
    plt.figure(figsize=(7, 6))
    image = plt.imshow(corr.values, cmap="coolwarm", vmin=-1, vmax=1)
    plt.colorbar(image, label="Pearson correlation")
    plt.xticks(range(len(corr.columns)), corr.columns, rotation=45, ha="right")
    plt.yticks(range(len(corr.index)), corr.index)
    for row in range(len(corr.index)):
        for col in range(len(corr.columns)):
            plt.text(col, row, f"{corr.values[row, col]:.2f}", ha="center", va="center", fontsize=8)
    plt.title("Correlation matrix of numerical features")
    save_figure("correlation_heatmap.png")
    pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack()
    strongest = pairs.abs().idxmax()
    return (
        f"The strongest relation is between {strongest[0]} and {strongest[1]} (r = {pairs[strongest]:.2f}); "
        f"correlation of mag with depth_km is {corr.loc['mag', 'depth_km']:.2f}."
    )


def run_analysis():
    print("[INFO] EDA: reading data from SQLite...")
    df = load_data()
    print_overview(df)
    print_categorical(df)
    corr = print_correlations(df)
    by_region, by_day, by_strength = print_grouped(df)

    print("\n" + "=" * 60)
    print("5. VISUALIZATIONS AND FINDINGS")
    print("=" * 60)
    findings = {}
    plots = [
        ("magnitudes_hist", lambda: plot_magnitude_hist(df)),
        ("magnitude_depth_scatter", lambda: plot_magnitude_depth_scatter(df)),
        ("top_regions_bar", lambda: plot_top_regions(df)),
        ("earthquakes_by_day_line", lambda: plot_daily_counts(df)),
        ("correlation_heatmap", lambda: plot_correlation_heatmap(corr)),
    ]
    for number, (name, make_plot) in enumerate(plots, start=1):
        findings[name] = make_plot()
        print(f"[{number}/{len(plots)}] Finding: {findings[name]}\n")

    config.save_stats("analysis", {
        "rows_analysed": int(len(df)),
        "figures": len(plots),
        "top_region": str(by_region.index[0]),
        "mean_magnitude": round(float(df["mag"].mean()), 3),
        "findings": findings,
    })
    print(f"[INFO] Done. {len(plots)} figures saved to {config.FIGURES_DIR.name}/")


def main():
    try:
        run_analysis()
    except KeyError as error:
        print(f"ERROR: column {error} is missing in table 'earthquakes' (check the loader schema)")
        sys.exit(1)


if __name__ == "__main__":
    main()
