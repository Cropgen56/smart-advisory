import os
import pandas as pd
from typing import Dict, Any

# ─── STANDARD FALLBACK VALUES ─────────────────────────────────────────────
DEFAULT_CROP_DATA = {
    "gdd_total": 1500,
    "soil_moisture_critical": 30.0,
    "water_demand": "moderate",
    "ndvi_threshold_spray": 0.65,
    "ndvi_threshold_fertilize": 0.60,
    "fungal_risk_humidity": 75.0,
    "base_temperature_c": 10.0
}

class KnowledgeBaseManager:
    def __init__(self, data_dir: str = "data", filename: str = "CropGen_India_Filled_AAS.xlsx"):
        self.file_path = os.path.join(os.getcwd(), data_dir, filename)
        self.crops_db: Dict[str, Dict[str, Any]] = {}
        self._load_excel()

    def _load_excel(self):
        print(f"🌱 Loading CropGen Knowledge Base from {self.file_path}...")
        
        if not os.path.exists(self.file_path):
            print(f"⚠️ Warning: Excel file not found at {self.file_path}. Using default fallback values only.")
            return

        try:
            # sheet_name=None loads all sheets into a dictionary of DataFrames
            sheets = pd.read_excel(self.file_path, sheet_name=None)
            
            # Map your actual Excel sheet names to internal categories
            # Note: Update the left side if your exact sheet names differ slightly!
            sheet_mapping = {
                "Phenology & Growth Stages (GDD)": "phenology",
                "Irrigation & Soil Thresholds": "irrigation",
                "Crop Protection (Disease & Pest": "protection", 
                "Nutrition & Fertilizer Triggers": "nutrition"
            }

            for actual_sheet_name, internal_category in sheet_mapping.items():
                if actual_sheet_name in sheets:
                    df = sheets[actual_sheet_name]
                    
                    # Convert pandas NaNs to Python None (so JSON doesn't break later)
                    df = df.where(pd.notnull(df), None)
                    
                    for _, row in df.iterrows():
                        # We assume every sheet has a column named "Crop" or "Crop_Name"
                        crop_name = str(row.get("Crop", row.get("Crop_Name", ""))).strip().lower()
                        
                        if not crop_name or crop_name == 'none' or crop_name == 'nan':
                            continue
                            
                        # Initialize crop if it doesn't exist yet
                        if crop_name not in self.crops_db:
                            self.crops_db[crop_name] = {}
                            
                        # Store the row data as a dictionary under the category
                        self.crops_db[crop_name][internal_category] = row.to_dict()
                        
            print(f"✅ Loaded specific threshold data for {len(self.crops_db)} crops.")
            
        except Exception as e:
            print(f"❌ Error loading Excel file: {e}")

    def get_crop(self, crop_name: str) -> Dict[str, Any]:
        """
        Retrieves crop data. Combines specific Excel data with defaults.
        """
        target_crop = crop_name.strip().lower()
        
        if target_crop in self.crops_db:
            specific_data = self.crops_db[target_crop]
            
            # --- MAP YOUR EXCEL COLUMNS TO INTERNAL VARIABLES HERE ---
            # Example: pulling from the 'irrigation' sheet, falling back to default if missing
            mapped_data = {
                "soil_moisture_critical": specific_data.get("irrigation", {}).get("Critical_Moisture_Pct", DEFAULT_CROP_DATA["soil_moisture_critical"]),
                "ndvi_threshold_spray": specific_data.get("protection", {}).get("NDVI_Spray_Threshold", DEFAULT_CROP_DATA["ndvi_threshold_spray"]),
                # Add more mappings as you look at your Excel column names...
            }
            
            # Merge defaults with our mapped specific data
            return {**DEFAULT_CROP_DATA, **mapped_data}
        
        # Fallback for entirely unknown crops
        return DEFAULT_CROP_DATA

# Initialize a singleton instance
kb_manager = KnowledgeBaseManager()