# -------------------------------------------------
# Population Ingestion Module – WorldPop (Constrained)
# -------------------------------------------------
import os
import warnings
from typing import List, Optional, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
import logging

logger = logging.getLogger(__name__)

# -------------------------------------------------
# Helper Functions
# -------------------------------------------------

def normalize_county_name(name: str) -> str:
    """Helper: Normalize county names by handling hyphenation, case, and formatting issues."""
    if pd.isna(name):
        return ""
    
    # Convert to string and strip whitespace
    name_str = str(name).strip()
    
    # Replace hyphens with spaces (common in multi-word county names)
    name_str = name_str.replace('-', ' ')
    
    # Replace underscores with spaces
    name_str = name_str.replace('_', ' ')
    
    # Remove extra spaces and normalize spacing
    name_str = ' '.join(name_str.split())
    
    return name_str


def format_population_number(population: float) -> str:
    """Helper: Format population numbers with comma separators for thousands/millions."""
    if pd.isna(population):
        return "N/A"
    
    try:
        # Round to nearest integer
        pop_int = int(round(float(population), 0))
        # Format with comma separators
        return f"{pop_int:,}"
    except (ValueError, TypeError):
        return "N/A"


def extract_population_for_geometry(src: rasterio.DatasetReader, geometry) -> Tuple[float, str]:
    """Helper: Extract population sum for a single geometry with robust error handling."""
    try:
        # Extract raster data for the geometry
        masked, _ = rasterio.mask.mask(
            src,
            [geometry],
            crop=True,
            nodata=0,
            all_touched=True  # Include all pixels touching the boundary
        )
        
        # Check if masked array is valid
        if masked is None or masked.size == 0:
            return np.nan, "NO_RASTER_DATA"
        
        # Convert to float and handle special values
        masked_float = masked.astype(np.float64)
        
        # Replace invalid values
        masked_float[masked_float < 0] = 0
        masked_float[np.isnan(masked_float)] = 0
        masked_float[np.isinf(masked_float)] = 0
        
        population_sum = float(np.sum(masked_float))
        
        # Validate result
        if population_sum < 0:
            return np.nan, "NEGATIVE_VALUE"
        elif population_sum == 0:
            return 0.0, "ZERO_POPULATION"
        else:
            return population_sum, "SUCCESS"
            
    except rasterio.errors.RasterioError as e:
        return np.nan, f"RASTER_ERROR: {str(e)[:100]}"
    except Exception as e:
        return np.nan, f"EXTRACTION_ERROR: {type(e).__name__}"


def select_county_name_field(counties_gdf: gpd.GeoDataFrame, 
                           primary_field: str,
                           alternative_fields: Optional[List[str]] = None) -> str:
    """Helper: Select the best available county name field from shapefile."""
    available_fields = list(counties_gdf.columns)
    
    # Try primary field first
    if primary_field in available_fields:
        return primary_field
    
    # Try alternative fields if provided
    if alternative_fields:
        for field in alternative_fields:
            if field in available_fields:
                logger.info(f"Using alternative county name field: {field}")
                return field
    
    # If no field found, show available options
    raise ValueError(
        f"County name field '{primary_field}' not found.\n"
        f"Available fields: {available_fields}\n"
        f"Alternative fields tried: {alternative_fields or 'None'}"
    )


# -------------------------------------------------
# Core Functions
# -------------------------------------------------

def compute_county_population(
    population_raster_path: str,
    county_shapefile_path: str,
    county_name_field: str = "adm1_name",
    alternative_name_fields: Optional[List[str]] = None,
    population_year: int = 2026,
    output_formatted: bool = False
) -> pd.DataFrame:
    """
    Computes total population per county using a WorldPop constrained raster.
    Enhanced with better error handling, name normalization, and formatted output.

    Parameters
    ----------
    population_raster_path : str
        Path to the WorldPop GeoTIFF (constrained, 100m).
    county_shapefile_path : str
        Path to the ADM1 (county-level) shapefile.
    county_name_field : str
        Primary column name in the shapefile containing county names.
    alternative_name_fields : Optional[List[str]]
        Additional field names to try if primary field fails.
    population_year : int
        Population reference year.
    output_formatted : bool
        If True, includes formatted population column with comma separators.

    Returns
    -------
    pd.DataFrame
        Columns:
        - County (normalized name)
        - County_Raw (original name)
        - Population (float)
        - Population_Formatted (str with comma separators, if output_formatted=True)
        - Population_Year
        - Extraction_Status
    """
    
    # Validate input files
    if not os.path.exists(population_raster_path):
        raise FileNotFoundError(f"Population raster not found: {population_raster_path}")
    
    if not os.path.exists(county_shapefile_path):
        raise FileNotFoundError(f"County shapefile not found: {county_shapefile_path}")
    
    logger.info("Loading county boundaries")
    counties = gpd.read_file(county_shapefile_path)
    
    # Select the best county name field
    selected_field = select_county_name_field(
        counties, 
        county_name_field, 
        alternative_name_fields
    )
    
    # Prepare counties data with normalized names
    counties = counties[[selected_field, "geometry"]].copy()
    counties = counties.rename(columns={selected_field: "County_Raw"})
    
    # Create normalized county names
    counties["County"] = counties["County_Raw"].apply(normalize_county_name)
    
    # Check for duplicates after normalization
    duplicate_mask = counties.duplicated(subset=["County"], keep=False)
    if duplicate_mask.any():
        duplicates = counties[duplicate_mask]
        logger.warning(f"Found {len(duplicates)} counties with duplicate normalized names:")
        for _, row in duplicates.iterrows():
            logger.warning(f"  - '{row['County_Raw']}' -> '{row['County']}'")
    
    logger.info(f"Processing {len(counties)} counties")
    
    results = []
    extraction_stats = {
        "SUCCESS": 0,
        "ZERO_POPULATION": 0,
        "NO_RASTER_DATA": 0,
        "FAILED": 0
    }
    
    logger.info("Opening population raster")
    with rasterio.open(population_raster_path) as src:
        raster_crs = src.crs
        
        # Reproject counties if needed
        if counties.crs != raster_crs:
            logger.info(f"Reprojecting counties from {counties.crs} to {raster_crs}")
            counties = counties.to_crs(raster_crs)
        
        # Process each county
        for idx, row in counties.iterrows():
            county_raw = row["County_Raw"]
            county_normalized = row["County"]
            
            if (idx + 1) % 10 == 0:  # Log progress every 10 counties
                logger.info(f"Processing county {idx + 1}/{len(counties)}: {county_normalized}")
            
            # Extract population
            population_sum, status = extract_population_for_geometry(src, row["geometry"])
            
            # Update statistics
            if status == "SUCCESS":
                extraction_stats["SUCCESS"] += 1
            elif status == "ZERO_POPULATION":
                extraction_stats["ZERO_POPULATION"] += 1
            elif status == "NO_RASTER_DATA":
                extraction_stats["NO_RASTER_DATA"] += 1
                logger.warning(f"No raster data for county: {county_raw}")
            else:
                extraction_stats["FAILED"] += 1
                logger.warning(f"Extraction failed for {county_raw}: {status}")
            
            # Prepare result row
            result_row = {
                "County": county_normalized,
                "County_Raw": county_raw,
                "Population": population_sum if not pd.isna(population_sum) else np.nan,
                "Population_Year": population_year,
                "Extraction_Status": status
            }
            
            # Add formatted population if requested
            if output_formatted:
                result_row["Population_Formatted"] = format_population_number(population_sum)
            
            results.append(result_row)
    
    # Create DataFrame
    population_df = pd.DataFrame(results)
    
    # Log summary statistics
    logger.info("Population extraction summary:")
    logger.info(f"  - Successfully extracted: {extraction_stats['SUCCESS']} counties")
    logger.info(f"  - Zero population: {extraction_stats['ZERO_POPULATION']} counties")
    logger.info(f"  - No raster data: {extraction_stats['NO_RASTER_DATA']} counties")
    logger.info(f"  - Failed extractions: {extraction_stats['FAILED']} counties")
    
    # Calculate and log population statistics
    valid_populations = population_df["Population"].dropna()
    if len(valid_populations) > 0:
        total_population = valid_populations.sum()
        avg_population = valid_populations.mean()
        logger.info(f"  - Total population: {format_population_number(total_population)}")
        logger.info(f"  - Average county population: {format_population_number(avg_population)}")
    
    logger.info("County population computation complete")
    return population_df


def format_population_dataframe(df: pd.DataFrame, 
                              population_col: str = "Population",
                              output_col: str = "Population_Formatted",
                              inplace: bool = False) -> pd.DataFrame:
    """
    Format population numbers in a DataFrame with comma separators.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing population data
    population_col : str
        Column name with population numbers
    output_col : str
        Column name for formatted output
    inplace : bool
        If True, modify the DataFrame in-place
    
    Returns
    -------
    pd.DataFrame
        DataFrame with formatted population column
    """
    if not inplace:
        df = df.copy()
    
    df[output_col] = df[population_col].apply(format_population_number)
    return df


# -------------------------------------------------
# Convenience Function
# -------------------------------------------------

def get_county_population(
    population_raster_path: str,
    county_shapefile_path: str,
    county_name_field: str,
    alternative_name_fields: Optional[List[str]] = None,
    return_formatted: bool = True
) -> pd.DataFrame:
    """
    Convenience function to get county population with optional formatting.
    
    Returns
    -------
    pd.DataFrame
        Formatted county population data
    """
    population_df = compute_county_population(
        population_raster_path=population_raster_path,
        county_shapefile_path=county_shapefile_path,
        county_name_field=county_name_field,
        alternative_name_fields=alternative_name_fields,
        output_formatted=return_formatted
    )
    
    return population_df


# -------------------------------------------------
# Utility Function for Debugging
# -------------------------------------------------

def diagnose_population_extraction(
    population_df: pd.DataFrame,
    log_level: str = "INFO"
) -> dict:
    """
    Helper: Generate diagnostic information about population extraction.
    
    Returns
    -------
    dict
        Dictionary with diagnostic statistics
    """
    diagnostics = {
        "total_counties": len(population_df),
        "successful_extractions": len(population_df[population_df["Extraction_Status"] == "SUCCESS"]),
        "failed_extractions": len(population_df[population_df["Extraction_Status"] != "SUCCESS"]),
        "counties_with_nan": population_df["Population"].isna().sum(),
        "counties_with_zero": len(population_df[population_df["Population"] == 0]),
        "status_counts": population_df["Extraction_Status"].value_counts().to_dict(),
        "problematic_counties": []
    }
    
    # Identify problematic counties
    problematic = population_df[population_df["Extraction_Status"] != "SUCCESS"]
    if len(problematic) > 0:
        diagnostics["problematic_counties"] = problematic[["County", "County_Raw", "Extraction_Status"]].to_dict("records")
    
    # Log diagnostics based on requested level
    if log_level.upper() == "INFO":
        logger.info(f"Diagnostics: {diagnostics['successful_extractions']}/{diagnostics['total_counties']} successful")
        if diagnostics["failed_extractions"] > 0:
            logger.warning(f"  - {diagnostics['failed_extractions']} counties had extraction issues")
    
    return diagnostics