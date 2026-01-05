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
- Integrate population data for coverage analysis
- Calculate provider-to-population ratios by county
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

> Note: Sensitive or identifiable provider data is anonymized
> for this repository.

---

## Enhanced Features (Phase 2)

### Population Data Integration
- **WorldPop Constrained Estimates**: 2026 population data at 100m resolution
- **County Boundaries**: Official administrative boundaries from HDX
- **Automated Extraction**: Population sums calculated per county using raster masking
- **Robust Name Matching**: Handles hyphenated and alternative county name formats

### Enhanced Analysis
- **Provider-to-Population Ratios**: Calculates providers per 100,000 population
- **National Coverage Metrics**: Weighted averages accounting for population distribution
- **Data Quality Diagnostics**: Tracks extraction success rates and issues
- **Formatted Outputs**: Population numbers with comma separators for readability

### Comprehensive Reporting
- **Interactive Maps**: Color-coded providers with population density overlays (planned)
- **Detailed Summaries**: County-level statistics with national totals
- **Data Source Documentation**: Complete references for reproducibility
- **Multiple Output Formats**: Excel, HTML, Markdown, and PDF export options

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

## Population Data Processing

### Raster Population Extraction
- **Source**: WorldPop Constrained Estimates (2026, 100m resolution)
- **Method**: Dasymetric redistribution using Random Forest modeling
- **Processing**: Automated zonal statistics per county boundary
- **Validation**: Status tracking and diagnostic reporting for each county

### County Name Normalization
  - Handles hyphenated county names (e.g., "Nairobi City" vs "Nairobi-City")
  - Supports alternative name field mappings
  - Preserves original names while creating normalized versions for matching

---

## Visualization Rules

- **Green markers**: Providers located using physical address
- **Blue markers**: Providers approximated using town centroid
- **Grey markers**: Inactive providers
- Provider details (name, specialty, contact info) appear in map popups
- *Planned: Population density heatmap overlays*

---

## Outputs

The script generates the following outputs:

### Core Outputs
- `outputs/providers_geocoded.xlsx` - Enriched Excel file with coordinates and geocoding metadata
- `outputs/providers_map.html` - Interactive HTML map of provider locations
- `outputs/summary.md` - Detailed Markdown summary of providers per county

### Enhanced Outputs (Phase 2)
- `outputs/county_population.csv` - County population statistics with extraction status
- `outputs/coverage_analysis.md` - Provider-to-population coverage analysis
- `outputs/summary.pdf` - PDF version of summary report (via Pandoc)

### Report Contents
- County-level provider counts and population statistics
- Providers per 100,000 population metrics
- National coverage totals and weighted averages
- Data source references and methodology documentation
- Data quality notes and extraction diagnostics

---

## Technology Stack

- **Core**: Python 3.9+
- **Data Processing**: pandas, numpy
- **Geospatial**: geopandas, rasterio, shapely
- **Geocoding**: geopy (Nominatim)
- **Visualization**: folium, matplotlib
- **Reporting**: markdown, Pandoc (for PDF export)
- **Population Data**: WorldPop Constrained Estimates (2026)

---

## Data Sources

### County Boundaries
- **Source**: Kenya - Subnational Administrative Boundaries (HDX)
- **Provider**: OCHA Field Information Services Section (FISS)
- **Update Frequency**: Annual
- **Link**: [https://data.humdata.org/dataset/cod-ab-ken](https://data.humdata.org/dataset/cod-ab-ken)

### Population Data
- **Source**: WorldPop Constrained Estimates (2026)
- **Resolution**: 3 arc-seconds (~100m at equator)
- **Methodology**: Random Forest dasymetric redistribution
- **Citation**: Bondarenko et al., 2025
- **Link**: [https://hub.worldpop.org/geodata/summary?id=74000](https://hub.worldpop.org/geodata/summary?id=74000)

---

## Usage

### Basic Setup
```bash 
# Clone repository
git clone https://github.com/yourusername/medical-providers-analysis.git
cd medical-providers-analysis

# Install dependencies
pip install -r requirements.txt

# Prepare input data
# Place providers.xlsx in the data/ directory
# Download county shapefile and population raster (see data_sources.md)
```
### Running the Analysis
```bash
# Run full analysis pipeline
python geocode_providers.py

# Generate PDF report (requires Pandoc)
python export_report.py
```

### Configuration
Key configuration options in config.py:
 - Input/output file paths
 - Geocoding parameters (rate limits, retries)
 - Population data sources
 - Report formatting options

## Key Metrics Calculated

### County Level
 - Total providers (active/inactive)
 - Population estimates (2026)
 - Providers per 100,000 population
 - Geocoding success rates

### National Level
 - Total population coverage
 - Weighted average providers per 100k
 - County coverage completeness
 - Data extraction success rates

## Important Notes

### Geocoding Limitations

 - Public Nominatim service used for exploratory geocoding only
 - Rate-limited to comply with OpenStreetMap usage policies
 - For production use, consider commercial or self-hosted solutions

### Population Data Caveats
 - WorldPop estimates are modeled data with inherent uncertainty
 - Constrained estimates adjust for uninhabitable areas
 - 2026 projections based on current demographic trends

### Data Privacy
 - Provider data in this repository is anonymized
 - Sensitive location data should be handled according to local regulations
 - Output files exclude personally identifiable information
