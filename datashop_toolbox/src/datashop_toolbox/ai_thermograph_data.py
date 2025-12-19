import glob
import matplotlib.pyplot as plt
from matplotlib.widgets import LassoSelector, Button, RadioButtons, CheckButtons
from matplotlib.path import Path
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle, Patch
import matplotlib.colors as mcolors
import numpy as np
import os
import shutil
from datetime import datetime
import pandas as pd
import pathlib
import sys
import time
import geopandas as gpd
from shapely.geometry import Point
from PyQt6.QtWidgets import (
    QApplication,QMessageBox)
from datashop_toolbox.thermograph import ThermographHeader
from datashop_toolbox.historyhdr import HistoryHeader
from datashop_toolbox.validated_base import get_current_date_time
from datashop_toolbox import select_metadata_file_and_data_folder

TEMP_CLIMATOLOGY = {
    "Arctic Basin": {
        "Winter": (-1.8, -1.5),
        "Spring": (-1.6, -0.8),
        "Summer": (-0.5, 1.0),
        "Fall": (-1.0, -0.2),
    },
    "Hudson Bay Complex": {
        "Winter": (-1.8, -1.0),
        "Spring": (-0.5, 0.5),
        "Summer": (4.0, 8.0),
        "Fall": (0.5, 2.0),
    },
    "Gulf of Saint Lawrence": {
        "Winter": (-1.5, 2.0),
        "Spring": (2.0, 6.0),
        "Summer": (8.0, 15.0),
        "Fall": (5.0, 10.0),
    },
    "Newfoundland-Labrador Shelves": {
        "Winter": (-1.5, 2.0),
        "Spring": (2.0, 6.0),
        "Summer": (8.0, 15.0),
        "Fall": (5.0, 10.0),
    },
    "Scotian Shelf": {
        "Winter": (-2.0, 6.0),
        "Spring": (4.0, 9.0),
        "Summer": (10.0, 18.0),
        "Fall": (8.0, 14.0),
    },
    "Offshore Pacific": {
        "Winter": (5.0, 8.0),
        "Spring": (7.0, 11.0),
        "Summer": (12.0, 15.0),
        "Fall": (9.0, 12.0),
    }
}

geojasonfile= "./datashop_toolbox/map/All_Federal_Marine_Bioregions.geojson"
bioregions = gpd.read_file(geojasonfile)

def get_bioregion(lat, lon):
    point = Point(lon, lat)
    match = bioregions[bioregions.contains(point)]
    
    if match.empty:
        return None
    return match.iloc[0]["NAME_E"]


def get_surface_temp_profile(lat, lon):
    region = get_bioregion(lat, lon)
    
    if region is None:
        return {
            "error": "Location outside Canadian marine bioregions"
        }
    
    temps = TEMP_CLIMATOLOGY.get(region)
    
    return {
        "Latitude": lat,
        "Longitude": lon,
        "Bioregion": region,
        "SurfaceTemperatureProfile": temps
    }


def get_season(dt):
    """Return climatological season name for a datetime"""
    month = dt.month
    if month in (12, 1, 2):
        return "Winter"
    elif month in (3, 4, 5):
        return "Spring"
    elif month in (6, 7, 8):
        return "Summer"
    else:
        return "Fall"


def prepare_output_folder(in_folder_path: str, out_folder_path: str, qc_operator: str) -> str:
    base_name_input = "Step_1_Create_ODF"
    in_folder_path = os.path.abspath(in_folder_path)
    
    base_name_output = "Step_2_Assign_QFlag"
    out_folder_path = os.path.abspath(out_folder_path)
    out_odf_path = os.path.join(out_folder_path, base_name_output)
    out_odf_path = os.path.abspath(out_odf_path)

    
    if base_name_input.lower() in in_folder_path.lower():
        if (not os.path.exists(out_odf_path)) and (out_odf_path != in_folder_path):
            print(f"Initial QC Mode: No existing output folder found. Creating new folder, name : Step_2_Assign_QFlag")
            os.makedirs(out_odf_path, exist_ok=True)
            print(f"Created output folder: {out_odf_path}")
        else:
            print(f"Initial QC Mode: Overwriting existing output folder, name : Step_2_Assign_QFlag")
            shutil.rmtree(out_odf_path)
            os.makedirs(out_odf_path, exist_ok=True)
            print(f"Overwriting existing folder: {out_odf_path}")
   
    return out_odf_path


def qc_thermograph_data(in_folder_path: str, wildcard: str, out_folder_path: str, qc_operator: str):

    cwd = os.getcwd()

    try:
        os.chdir(in_folder_path)
        print(f"Changed working dir to the input directory: {in_folder_path}")
    except Exception as e:
        print(f"Cannot change directory: {e}")

    mtr_files = glob.glob(wildcard)
    if not mtr_files:
        print("No ODF files found in selected folder.")
        os.chdir(cwd)
      
    # Prepare output folder
    out_odf_path = prepare_output_folder(in_folder_path, out_folder_path, qc_operator)
    print(f"Created a output data folder name, Step_2_Quality_Flagging ")
    print(f"Path for Step_2_Quality_Flagging: {out_odf_path}")

    os.chdir(cwd)

    for idx, mtr_file in enumerate(mtr_files, start=1):
       
        print(f"Reading file {idx} of {len(mtr_files)}: {mtr_file}")
        print(f"Please wait...reading ODF file for QC visualization...")

        full_path = str(pathlib.Path(in_folder_path, mtr_file))
        
        try:
            mtr = ThermographHeader()
            mtr.read_odf(full_path)
        except Exception as e:
            print(f"Failed to read ODF {full_path}: {e}")
            continue

        orig_df = mtr.data.data_frame
        orig_df_stored = orig_df.copy()
        orig_df =orig_df.copy()
        orig_df.reset_index(drop=True, inplace=True)
        orig_df= pd.DataFrame(orig_df)

        Initial_lat= mtr.event_header.initial_latitude
        Initial_lon= mtr.event_header.initial_longitude

        # Extract temperature and time
        temp = orig_df['TE90_01'].to_numpy()
        sytm = orig_df['SYTM_01'].str.lower().str.strip("'")
        
        if 'QTE90_01' in orig_df.columns:
            qflag = orig_df['QTE90_01'].to_numpy().astype(int)
        else:
            orig_df['QTE90_01']= np.zeros(len(orig_df), dtype=int)
            qflag = orig_df['QTE90_01'].to_numpy().astype(int)
        
        try:
            dt = pd.to_datetime(sytm, format='%d-%b-%Y %H:%M:%S.%f')
        except Exception:
            dt = pd.to_datetime(sytm, infer_datetime_format=True, errors="coerce")

       
        # Create a DataFrame with Temperature as the variable and DateTime as the index.
        df = pd.DataFrame({'Temperature': temp, 'qualityflag': qflag}, index=dt)
        df['qualityflag'] = np.where(df['Temperature'].isna(), 4, df['qualityflag'])
        sst_location= get_surface_temp_profile(Initial_lat, Initial_lon)
        df["Season"] = df.index.to_series().apply(get_season)
        seasonal_limits = sst_location["SurfaceTemperatureProfile"]
        for season, (tmin, tmax) in seasonal_limits.items():
            mask = (
                (df["Season"] == season) &
                (df["Temperature"] > tmax)
            )
        df.loc[mask, "qualityflag"] = 4
        df.loc[~df["qualityflag"].isin([3, 4]), "qualityflag"] = 1
       


if __name__ == "__main__":
    qc_thermograph_data()
    
















