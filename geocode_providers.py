# -------------------------------------------------
# Medical Providers Spatial Analysis - Phase 1
# -------------------------------------------------
from pyparsing import Diagnostics
import rasterio
import numpy as np
from folium.plugins import HeatMap
import logging
import pandas as pd
import re
import time
from time import sleep
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
import shelve
import os
import markdown

from data.population_ingestion import (
    compute_county_population,
    format_population_dataframe,
    diagnose_population_extraction
)
#from weasyprint import HTML, CSS
#import pdfkit

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
GEOCODE_DELAY = 1  # seconds

#Marker colors
PHYSICAL_COLOR = "green"
CENTROID_COLOR = "yellow"
INACTIVE_COLOR = "gray"

CACHE_FILE = "outputs/geocode_cache.db"
os.makedirs("outputs", exist_ok=True)

# -------------------------------------------------
# Address Cleaning Functions
# -------------------------------------------------
def normalize_address(text):
    if pd.isna(text):
        return ""
    text = text.lower()
    text = re.sub(r"\b\d+(st|nd|rd|th)?\s*floor\b", "", text)
    text = re.sub(r"\b\d+(st|nd|rd|th)?\s*room\b", "", text)
    text = re.sub(r"\bnext to\b", "", text)
    text = re.sub(r"\boff\b", "", text)

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
        return pd.Series(cache[query])

    retries = 3

    # 1. Full address
    for _ in range(retries):
        try:
            location = geocode_func(query)
            if location:
                result = [location.latitude, location.longitude, "PHYSICAL", "STREET"]
                cache[query] = result
                return pd.Series(result)
        except Exception:
            sleep(2)

    # 2. Town-level fallback
    for _ in range(retries):
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
    df["IsVirtual"] = df["Physical Address"].apply(is_virtual_provider)
    df["GeocodeQuery"] = df.apply(build_geocode_query, axis=1)

    # Initialize geocoder
    geolocator = Nominatim(
        user_agent="medical_providers_panel (contact: moffat.kagiri@libertylife.co.ke)",
        timeout=10
    )
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=GEOCODE_DELAY)

    # Open geocode cache
    geocode_cache = shelve.open(CACHE_FILE)

    # Apply geocoding with caching
    df[["Latitude", "Longitude", "GeoSource", "GeoConfidence"]] = df.apply(
        lambda row: geocode_row(row, geocode, geocode_cache), axis=1
    )

    # Close cache
    geocode_cache.close()

    # Save geocoded Excel
    df.to_excel(OUTPUT_FILE, index=False)
    logger.info(f"Geocoded data saved to {OUTPUT_FILE}")

    pop_raster_path = "data/ken_pop_2026_CN_100m_R2025A_v1.tif"

    heat_data = []

    with rasterio.open(pop_raster_path) as src:
        band = src.read(1)
        transform = src.transform

        # Downsample aggressively for web map (every 50th pixel ≈ 5km)
        step = 50

        for row in range(0, band.shape[0], step):
            for col in range(0, band.shape[1], step):
                value = band[row, col]
                if value and value > 0:
                    lon, lat = rasterio.transform.xy(transform, row, col)
                    heat_data.append([lat, lon, float(value)])

    # -------------------------------------------------
    # Map Visualization
    # -------------------------------------------------
    valid_coords = df.dropna(subset=["Latitude", "Longitude"])
    map_center = [valid_coords["Latitude"].mean(), valid_coords["Longitude"].mean()] if not valid_coords.empty else [0, 0]
    provider_map = folium.Map(location=map_center, zoom_start=7)

    HeatMap(
        heat_data,
        radius=20,
        blur=15,
        min_opacity=0.2,
        name="Population Density"
    ).add_to(provider_map)

    folium.LayerControl().add_to(provider_map)

    for _, row in df.iterrows():
        if pd.isna(row["Latitude"]) or pd.isna(row["Longitude"]):
            continue

        if row["Status"].lower() != "active":
            color = INACTIVE_COLOR
        elif row["GeoSource"] == "PHYSICAL":
            color = PHYSICAL_COLOR
        elif row["GeoSource"] == "TOWN_CENTROID":
            color = CENTROID_COLOR
        else:
            continue

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
    # Logging summary
    # -------------------------------------------------
    logger.info(
        "Providers input: %d | Mapped: %d (Green/Physical: %d, Yellow/Centroid: %d, Grey/Inactive: %d)",
        len(df),
        df[['Latitude', 'Longitude']].dropna().shape[0],
        df[(df['GeoSource'] == 'PHYSICAL') & (df['Status'].str.lower() == 'active')].shape[0],
        df[(df['GeoSource'] == 'TOWN_CENTROID') & (df['Status'].str.lower() == 'active')].shape[0],
        df[df['Status'].str.lower() != 'active'].shape[0],
    )

    # -------------------------------------------------
    # Load population density raster (downsampled)
    # -------------------------------------------------
    population_df = compute_county_population(
        population_raster_path="data/ken_pop_2026_CN_100m_R2025A_v1.tif",
        county_shapefile_path="data/admin/ken_admin1.shp",
        county_name_field="adm1_name",
        alternative_name_fields=["adm1_name", "adm1_ref_n"]
    )

    # -------------------------------------------------
    # Summary Metrics per County
    # -------------------------------------------------
    summary = df.groupby('County').agg(
        Total_Providers=('Name', 'count'),
        Active_Providers=('Status', lambda x: (x.str.lower() == 'active').sum()),
        Inactive_Providers=('Status', lambda x: (x.str.lower() != 'active').sum())
    ).reset_index()

    summary = summary.merge(
        population_df,
        on="County",
        how="left"
    )

    summary["Providers_per_100k"] = (
        summary["Active_Providers"] / summary["Population"] * 100_000
    ).round(2)

    # Add totals row at the bottom
    totals_row = pd.DataFrame({
        'County': ['NATIONAL TOTAL'],
        'Total_Providers': [summary['Total_Providers'].sum()],
        'Active_Providers': [summary['Active_Providers'].sum()],
        'Inactive_Providers': [summary['Inactive_Providers'].sum()],
        'Population': [summary['Population'].sum()],
        'Extraction_Status': ['AGGREGATE'],
        # Calculate national average for Providers_per_100k (weighted average)
        'Providers_per_100k': [
            (summary['Active_Providers'].sum() / summary['Population'].sum() * 100_000).round(2)
        ]
    })
    
    # Append totals row to summary
    summary_with_totals = pd.concat([summary, totals_row], ignore_index=True)
    
    # Format population numbers for display (optional - for markdown)
    summary_for_display = summary_with_totals.copy()
    summary_for_display['Population'] = summary_for_display['Population'].apply(
        lambda x: f"{int(x):,}" if pd.notna(x) and x != 'AGGREGATE' else x
    )

    # Save Markdown summary
    with open(SUMMARY_MD_FILE, 'w') as f:
        f.write("# Provider Distribution by County\n\n")
        f.write(
            "This section summarizes the distribution of medical providers across counties, "
            "based on the latest geocoded provider panel. Active providers represent facilities "
            "currently operational, while inactive providers are retained for historical and "
            "planning reference.\n\n"
        )
        f.write("**Key notes:**\n\n")
        f.write(f"- Total providers in dataset: {len(df)}\n")
        f.write(f"- Counties covered: {summary['County'].nunique()}\n")
        f.write(f"- National total population: {int(round(summary['Population'].sum(), 0)):,}\n")
        f.write(f"- National active providers: {summary['Active_Providers'].sum()}\n")
        f.write("- Counts are based on provider records, not facility capacity.\n")
        f.write("- Providers per 100k is calculated as (Active Providers / Population) × 100,000\n\n")
        
        f.write("## County-level Summary\n\n")
        f.write(summary_for_display.to_markdown(index=False))
        f.write("\n\n")
        
        # Add summary statistics section
        f.write("## Summary Statistics\n\n")
        f.write(f"- **Total Counties Analyzed**: {summary['County'].nunique()}\n")
        f.write(f"- **Total Population Coverage**: {int(round(summary['Population'].sum(), 0)):,}\n")
        f.write(f"- **Total Active Providers**: {summary['Active_Providers'].sum()}\n")
        f.write(f"- **Average Providers per 100k (Unweighted)**: {summary['Providers_per_100k'].mean():.2f}\n")
        f.write(f"- **Weighted Average Providers per 100k**: {totals_row['Providers_per_100k'].iloc[0]}\n")
        f.write(f"- **Median Providers per 100k**: {summary['Providers_per_100k'].median():.2f}\n")
        f.write(f"- **Range (Min-Max) Providers per 100k**: {summary['Providers_per_100k'].min():.2f} - {summary['Providers_per_100k'].max():.2f}\n\n")
        
        # Add data sources/references section
        f.write("## Data Sources and References\n\n")
        f.write("### 1. County Boundary Shapefile\n\n")
        f.write("- **Source**: Kenya - Subnational Administrative Boundaries\n")
        f.write("- **Dataset Link**: [https://data.humdata.org/dataset/cod-ab-ken](https://data.humdata.org/dataset/cod-ab-ken)\n")
        f.write("- **Time Period**: 31 October 2019 - 28 January 2025\n")
        f.write("- **Last Modified**: 18 December 2025\n")
        f.write("- **Dataset Added on HDX**: 1 September 2015\n")
        f.write("- **Expected Update Frequency**: Every year\n")
        f.write("- **Location**: Kenya\n")
        f.write("- **Source Organization**: IEBC\n")
        f.write("- **Contributor**: OCHA Field Information Services Section (FISS)\n\n")
        
        f.write("### 2. Population Data\n\n")
        f.write("- **Source**: Kenya - Spatial Distribution of Population Estimates of 2026\n")
        f.write("- **Dataset Link**: [https://hub.worldpop.org/geodata/summary?id=74000](https://hub.worldpop.org/geodata/summary?id=74000)\n")
        f.write("- **Resolution**: 3 arc-seconds (approximately 100m at the equator)\n")
        f.write("- **Format**: GeoTIFF\n")
        f.write("- **Projection**: Geographic Coordinate System, WGS84\n")
        f.write("- **Units**: Number of people per pixel\n")
        f.write("- **Methodology**: Random Forest-based dasymetric redistribution\n")
        f.write("- **Citation**:\n")
        f.write("  Bondarenko M., Priyatikanto R., Tejedor-Garavito N., Zhang W., McKeen T., ")
        f.write("Cunningham A., Woods T., Hilton J., Cihan D., Nosatiuk B., Brinkhoff T., ")
        f.write("Tatem A., Sorichetta A.. 2025 Constrained estimates of 2015-2030 total ")
        f.write("number of people per grid square at a resolution of 3 arc (approximately ")
        f.write("100m at the equator) R2025A version v1. Global Demographic Data Project - ")
        f.write("Funded by The Bill and Melinda Gates Foundation (INV-045237). WorldPop - ")
        f.write("School of Geography and Environmental Science, University of Southampton. ")
        f.write("DOI:10.5258/SOTON/WP00839\n\n")
        
        f.write("### 3. Provider Data\n\n")
        f.write("- **Source**: Internal provider registry\n")
        f.write(f"- **Total Providers**: {len(df)}\n")
        f.write(f"- **Active Providers**: {df[df['Status'].str.lower() == 'active'].shape[0]}\n")
        f.write(f"- **Inactive Providers**: {df[df['Status'].str.lower() != 'active'].shape[0]}\n")
        f.write(f"- **Analysis Date**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
        
    # Convert Markdown to PDF
    #with open(SUMMARY_MD_FILE, "r") as f:
    #    md_text = f.read()
    #    html = markdown.markdown(md_text, extensions=['tables'])
    #css = CSS(string="""
    #    body { font-family: Arial, sans-serif; margin: 20px; }
    #    h1, h2, h3 { color: #2c3e50; }
    #    table { border-collapse: collapse; width: 100%; margin-top: 10px; }
    #    th, td { border: 1px solid #999; padding: 8px; text-align: left; }
    #    th { background-color: #2c3e50; color: white; }
    #    tr:nth-child(even) { background-color: #f2f2f2; }
    #""")
    #pdf_file = SUMMARY_MD_FILE.replace(".md", ".pdf")
    #pdfkit.from_file(SUMMARY_MD_FILE, pdf_file)
    #logger.info(f"PDF summary report saved to {pdf_file}")


    logger.info(f"Summary Markdown saved to {SUMMARY_MD_FILE} and PDF report saved to ")

    print("Geocoding, mapping, and summary report generation complete.")
    print(f"Geocoded Excel: {OUTPUT_FILE}")
    print(f"Map file: {MAP_FILE}")
    print(f"Markdown summary: {SUMMARY_MD_FILE}")

# -------------------------------------------------
if __name__ == "__main__":
    main()
