import pandas as pd
import re
from time import sleep
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
import tabulate
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

    # Remove room numbers and similar terms (e.g. room 101, rm 5)
    text = re.sub(r"\b\d+(st|nd|rd|th)?\s*room\b", "", text)

    # Compress suffixes (never expand)
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

def geocode_row(row, geocode_func):
    if row["IsVirtual"]:
        return pd.Series([None, None, "VIRTUAL", "N/A"])

    # 1. Full address
    for attempt in range(retries:=3):
        try:
            location = geocode_func(row["GeocodeQuery"])
            if location:
                return pd.Series([
                    location.latitude,
                    location.longitude,
                    "PHYSICAL",
                    "STREET"
                ])
        except Exception:
            sleep(2)  # wait before retrying

    # 2. Town-level fallback
    for attempt in range(retries):
        try:
            lat, lon = geocode_town(row, geocode_func)
            if lat and lon:
                return pd.Series([
                    lat,
                    lon,
                    "TOWN_CENTROID",
                    "TOWN_CENTROID"
                ])
        except Exception:
            sleep(2)  # wait before retrying
    

    # 3. Total failure
    return pd.Series([None, None, "FAILED", "FAILED"])


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

    # Apply geocoding
    df[["Latitude", "Longitude", "GeoSource", "GeoConfidence"]] = df.apply(
        geocode_row, axis=1, geocode_func=geocode
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

        # Determine color
        if row["Status"].lower() != "active":
            color = INACTIVE_COLOR
        elif row["GeoSource"] == "PHYSICAL":
            color = PHYSICAL_COLOR
        elif row["GeoSource"] == "TOWN_CENTROID":
            color = CENTROID_COLOR
        else:
            continue  # skip FAILED or VIRTUAL for mapping

        popup_html = f"""
        <b>{row['Name']}</b><br>
        Specialty: {row['Specialty']}<br>
        Phone: {row['Phone']}<br>
        Email: {row['Email']}<br>
        Address: {row['Physical Address']}<br>
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
# Summary Metrics per County
# -------------------------------------------------
    summary = df.groupby('County').agg(
        Total_Providers=('Name', 'count'),
        Active_Providers=('Status', lambda x: (x.str.lower() == 'active').sum()),
        Inactive_Providers=('Status', lambda x: (x.str.lower() != 'active').sum())
    ).reset_index()


    # Save as markdown
    with open(SUMMARY_MD_FILE, 'w') as f:
        f.write('# Provider Summary per County\n\n')
        f.write(summary.to_markdown(index=False))


print("Geocoding and summary complete.")
print(f"Output file: {OUTPUT_FILE}")
print(f"Map file: {MAP_FILE}")
print(f"Summary markdown file: {SUMMARY_MD_FILE}")


# -------------------------------------------------
# Phase 2 Planning: Population Data Suggestion
# -------------------------------------------------
# Phase 2 suggestion: Source Kenyan population data from a reliable source such as:
# Kenya National Bureau of Statistics (KNBS) - https://www.knbs.or.ke
# WorldPop Kenya dataset - https://www.worldpop.org
# This data can be overlaid on the map to highlight underserved counties.

# -------------------------------------------------
if __name__ == "__main__":
    main()
