# Medical Providers Panel – Spatial Analysis

This repository contains a Python-based spatial analytics workflow for
geocoding, mapping, and summarizing a medical providers panel in Kenya.

The project is structured in phases. Phase 1 focuses on reliable location
enrichment and visualization, while Phase 2 extends into proximity and
population-based coverage analysis.

---

## Project Objectives

- Standardize and clean provider address data
- Geocode provider locations using OpenStreetMap (Nominatim)
- Apply hierarchical fallback logic with explicit confidence tiers
- Visualize providers on an interactive map
- Generate county-level summary metrics for reporting
- Lay the foundation for coverage and underserved-area analysis

---

## Data Inputs

The workflow expects an Excel file with the following columns:

- Name  
- Town  
- Physical Address  
- County  
- Specialty  
- Phone  
- Email  
- Status (Active / Inactive)

> Note: Sensitive or identifiable provider data should be anonymized
> before committing to this repository.

---

## Geocoding Logic

Geocoding is performed using a controlled, hierarchical approach:

1. **Physical Address + Town + County**
   - Confidence: `STREET`
2. **Town + County fallback**
   - Confidence: `TOWN_CENTROID`
3. **Failure**
   - Flagged as `FAILED`
4. **Virtual / Online providers**
   - Explicitly excluded from spatial analysis

Each provider record is tagged with a geocoding source and confidence level.

---

## Visualization Rules

- **Green markers**: Providers located using physical address
- **Blue markers**: Providers approximated using town centroid
- **Grey markers**: Inactive providers
- Provider details (name, specialty, contact info) appear in map popups

---

## Outputs

The script generates the following outputs:

- Enriched Excel file with coordinates and geocoding metadata
- Interactive HTML map of provider locations
- Markdown summary of providers per county (suitable for PDF export)

---

## Technology Stack

- Python
- pandas
- geopy (Nominatim)
- folium

---

## Usage Notes

- The public Nominatim service is used for exploratory geocoding only
- Requests are rate-limited to comply with OpenStreetMap usage policies
- For production or recurring geocoding, a commercial or self-hosted solution
  is recommended

---

## Phase 2 (Planned)

- Integration of Kenyan population data (KNBS / WorldPop)
- Provider-to-population ratios by county
- Identification of underserved regions
- Proximity and catchment area analysis
- Population density overlays on maps

---

## Disclaimer

This project is intended for analytical and exploratory purposes.
Geocoding accuracy varies by location and data quality, and confidence
levels should be respected in downstream analysis.

