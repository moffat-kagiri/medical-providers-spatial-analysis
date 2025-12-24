# -------------------------------------------------
# Provider Geocoding and Mapping Script (Phase 1)
# -------------------------------------------------
import logging
import pandas as pd
import re
from time import sleep
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
import shelve
import os

# -------------------------------------------------
# Logging configuration
# -------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# -------------------------------------------------
# Configuration
# -------------------------------------------------
INPUT_FILE = "data/providers.xlsx"
OUTPUT_FILE = "outputs/providers_geocoded.xlsx"
MAP_FILE = "outputs/provider_map.html"
SUMMARY_MD_FILE = "outputs/provider_summary.md"

GEOCODER_USER_AGENT = "medical_providers_panel"
GEOCODE_DELAY = 1  # seconds (Nominatim requirement)

PHYSICAL_COLOR = "green"
CENTROID_COLOR = "blue"
INACTIVE_COLOR = "gray"

# -------------------------------------------------
# Address Cleaning Functions
# -------------------------------------------------
def normalize_address(text):
    if pd.isna(text):
        return ""

    text = text.lower()

    # Remove floor numbers (e.g. 3rd floor, floor 2)
    text = re.sub(r"\b\d+(st|nd|rd|th)?\s*floor\b", "", text)

    # Remove room numbers (e.g. room 101, rm 5)
    text = re.sub(r"\b\d+(st|nd|rd|th)?\s*room\b", "", text)

    # Remove common terms
    text = re.sub(r"\bnext to\b", "", text)
    text = re.sub(r"\boff\b", "", text)

    # Compress suffixes (short forms)
    compressions = {
        r"\broad\b": "rd",
        r"\bstreet\b": "st",
        r"\bavenue\b": "ave",
        r"\bopposite\b": "opp",
        r"\bnear\b": "nr"
    }

    for pattern, replacement in compressions.items():
        text = re.sub(pattern, replacement, text)

    return re.sub(r"\s+", " ", text).strip()


def is_virtual_provider(address):
    if not isinstance(address, str):
        return False
    keywords = ["virtual", "online", "telemedicine", "telehealth"]
    return any(k in address.lower() for k in keywords)

# -------------------------------------------------
# Geocoding Functions
# -------------------------------------------------
def build_geocode_query(row):
    return f"{row['Physical Address']}, {row['Town']}, {row['County']}, Kenya"


def geocode_town(row, geocode_func):
    try:
        location = geocode_func(f"{row['Town']}, {row['County']}, Kenya")
        if location:
            return location.latitude, location.longitude
    except Exception:
        pass
    return None, None


def geocode_row(row, geocode_func, cache):
    if row["IsVirtual"]:
        return pd.Series([None, None, "VIRTUAL", "N/A"])

    query = row["GeocodeQuery"]

    # Check cache first
    if query in cache:
        cached = cache[query]
        return pd.Series(cached)

    retries = 3

    # 1. Full address
    for attempt in range(retries):
        try:
            location = geocode_func(query)
            if location:
                result = [location.latitude, location.longitude, "PHYSICAL", "STREET"]
                cache[query] = result  # store in cache
                return pd.Series(result)
        except Exception:
            sleep(2)

    # 2. Town-level fallback
    for attempt in range(retries):
        try:
            lat, lon = geocode_town(row, geocode_func)
            if lat and lon:
                result = [lat, lon, "TOWN_CENTROID", "TOWN_CENTROID"]
                cache[query] = result
                return pd.Series(result)
        except Exception:
            sleep(2)

    # 3. Total failure
    result = [None, None, "FAILED", "FAILED"]
    cache[query] = result
    return pd.Series(result)


# -------------------------------------------------
# Main Workflow
# -------------------------------------------------
def main():
    df = pd.read_excel(INPUT_FILE)

    # Standardize fields
    df["Physical Address"] = df["Physical Address"].apply(normalize_address)
    df["Town"] = df["Town"].str.strip()
    df["County"] = df["County"].str.strip()

    # Virtual provider handling
    df["IsVirtual"] = df["Physical Address"].apply(is_virtual_provider)

    # Geocode query
    df["GeocodeQuery"] = df.apply(build_geocode_query, axis=1)

    # Initialize geocoder
    geolocator = Nominatim(
        user_agent="medical_providers_panel (contact: moffat.kagiri@libertylife.co.ke)",
        timeout=10
    )
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=GEOCODE_DELAY)

    CACHE_FILE = "outputs/geocode_cache.db"
    os.makedirs("outputs", exist_ok=True)

    # Open shelve cache
    geocode_cache = shelve.open(CACHE_FILE)


    # Apply geocoding
    df[["Latitude", "Longitude", "GeoSource", "GeoConfidence"]] = df.apply(
        lambda row: geocode_row(row, geocode, geocode_cache),
        axis=1
    )

    # Save enriched dataset
    df.to_excel(OUTPUT_FILE, index=False)

    # -------------------------------------------------
    # Map Visualization
    # -------------------------------------------------
    valid_coords = df.dropna(subset=["Latitude", "Longitude"])
    if not valid_coords.empty:
        map_center = [valid_coords["Latitude"].mean(), valid_coords["Longitude"].mean()]
    else:
        map_center = [0, 0]

    provider_map = folium.Map(location=map_center, zoom_start=7)

    for _, row in df.iterrows():
        if pd.isna(row["Latitude"]) or pd.isna(row["Longitude"]):
            continue

        # Determine marker color
        if row["Status"].lower() != "active":
            color = INACTIVE_COLOR
        elif row["GeoSource"] == "PHYSICAL":
            color = PHYSICAL_COLOR
        elif row["GeoSource"] == "TOWN_CENTROID":
            color = CENTROID_COLOR
        else:
            continue  # skip FAILED or VIRTUAL

        popup_html = f"""
        <b>{row['Name']}</b><br>
        Specialty: <span style='color: blue;'>{row['Specialty']}</span><br>
        Phone: {row['Phone']}<br>
        Email: {row['Email']}<br>
        Address: <span style='color: blue;'>{row['Physical Address']}</span><br>
        Confidence: {row['GeoConfidence']}
        """

        folium.CircleMarker(
            location=[row["Latitude"], row["Longitude"]],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=popup_html
        ).add_to(provider_map)

    provider_map.save(MAP_FILE)

    # -------------------------------------------------
    # Logging summary metrics
    # -------------------------------------------------
    logger.info(
        "Providers input: %d | Mapped: %d (Green/Physical: %d, Blue/Centroid: %d, Grey/Inactive: %d)",
        len(df),
        df[['Latitude', 'Longitude']].dropna().shape[0],
        df[(df['GeoSource'] == 'PHYSICAL') & (df['Status'].str.lower() == 'active')].shape[0],
        df[(df['GeoSource'] == 'TOWN_CENTROID') & (df['Status'].str.lower() == 'active')].shape[0],
        df[df['Status'].str.lower() != 'active'].shape[0],
    )

    # -------------------------------------------------
    # Summary Metrics per County
    # -------------------------------------------------
    summary = df.groupby('County').agg(
        Total_Providers=('Name', 'count'),
        Active_Providers=('Status', lambda x: (x.str.lower() == 'active').sum()),
        Inactive_Providers=('Status', lambda x: (x.str.lower() != 'active').sum())
    ).reset_index()

    # Save summary as Markdown
    with open(SUMMARY_MD_FILE, 'w') as f:
        f.write("# Provider Distribution by County\n\n")
        f.write(
            "This section summarizes the distribution of medical providers across counties, "
            "based on the latest geocoded provider panel. Active providers represent facilities "
            "currently operational, while inactive providers are retained for historical and "
            "planning reference.\n\n"
        )

        f.write("**Key notes:**\n")
        f.write(f"- Total providers in dataset: {len(df)}\n")
        f.write(f"- Counties covered: {summary['County'].nunique()}\n")
        f.write("- Counts are based on provider records, not facility capacity.\n\n")

        f.write("## County-level Summary\n\n")
        f.write(summary.to_markdown(index=False))
        f.write("\n")
        geocode_cache.close()

    print("Geocoding and summary complete.")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Map file: {MAP_FILE}")
    print(f"Summary markdown file: {SUMMARY_MD_FILE}")

# -------------------------------------------------
# Phase 2 Planning: Population Data Suggestion
# -------------------------------------------------
# Source Kenyan population data from reliable sources:
# - Kenya National Bureau of Statistics (KNBS): https://www.knbs.or.ke
# - WorldPop Kenya dataset: https://www.worldpop.org
# Overlay population density to highlight underserved counties.

# -------------------------------------------------
if __name__ == "__main__":
    main()
