# Roadmap for Geocoding Medical Providers Data

## Phase 1: Provider Geocoding & Mapping

### 1. Data Preparation & Standardization

* Ingest provider master dataset ✅
* Normalize address suffixes (Rd/Road, St/Street, Ave/Avenue) ✅
* Remove floor numbers and internal building descriptors✅
* Standardize town names and short forms (e.g. Nrb → Nairobi)
* Resolve relative location phrases (e.g. "near", "opposite", "behind") by retaining the referenced landmark ✅
* Flag records explicitly marked as *Virtual* or *Online* ✅

### 2. Handling Virtual / Online Providers

* Retain the provider website or platform link in the Physical Address field ✅
* Assign a standardized location proxy based on: ✅
  * Registered town/country of operation, or
  * Corporate head office location, if available
* Flag these records as *Non-Physical Providers* to exclude from distance-based analyses ✅

### 3. Address Cleaning Output

* Create a cleaned, geocoding-ready address field ✅
* Retain original address fields for audit and traceability ✅

### 4. Geocoding

* Submit cleaned addresses to: ✅
  * Primary: Google Maps Geocoding API
  * Fallback: Nominatim (OpenStreetMap) ✅
* Implement multi-pass geocoding (full address → town + landmark → town centroid) ✅
* Capture latitude, longitude, geocoding source, and confidence level ✅

### 5. Quality Review

* Identify low-confidence or failed geocodes ✅
* Manually review and correct high-priority providers
* Re-run geocoding where necessary ✅

### 6. Dataset Enrichment

* Append latitude and longitude columns to provider dataset ✅
* Add geocoding metadata (source, confidence, date) ✅

### 7. Outputs

* Spreadsheet output (CSV/Excel) with coordinates and metadata ✅
* Interactive map visualization of provider locations ✅
* Summary metrics (counts by town, physical vs virtual)

---

## Phase 2: Spatial & Proximity Analysis (Future Work)

### 8. Proximity & Coverage Analysis

* Distance to nearest provider
* Provider density by town/region
* Identification of coverage gaps and overlaps

### 9. Advanced Spatial Use Cases

* Catchment area buffering
* Urban vs peri-urban vs rural access analysis
* Scenario testing for new provider placement

### 10. Iteration & Expansion

* Refine address rules and re-geocode as data improves
* Integrate population or membership data
* Productionize workflow for periodic refresh
