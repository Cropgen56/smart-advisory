"""
KNOWLEDGE BASE MANAGER
======================
Parses CropGen_India_Filled_AAS.xlsx and exposes per-crop agronomic data
to the advisory engine.

Excel structure (transposed layout):
  - Rows    = Parameters (e.g. "Critical Low Moisture", "Primary Fungicide")
  - Columns = One column per crop (90 crops) + 5 meta columns at the start

Sheets:
  1. "Phenology & Growth Stages (GDD)"   → GDD stages, Kc, base temp, growing days
  2. "Irrigation & Soil Thresholds"      → Soil moisture thresholds, water demand
  3. "Crop Protection (Disease & Pest"   → Fungicides, insecticides, dosages
  4. "Nutrition & Fertilizer Triggers"   → NDVI thresholds, NPK, fertilizer
"""

import os
import json
import pandas as pd
from typing import Dict, Any, Optional
# CROP NAME ALIASES
# Maps any incoming variant (lowercase) → canonical Excel column name (lowercase)
# Add more variants here as needed without touching the engine.

CROP_ALIASES: Dict[str, str] = {
    # Legacy JSON KB names → Excel names
    "paddy":            "rice",
    "chili":            "chilli",
    "chilly":           "chilli",
    # Common alternate spellings
    "maize":            "corn",
    "groundnut":        "groundnut",
    "brinjal":          "brinjal",
    "eggplant":         "brinjal",
    "lady finger":      "okra",
    "ladyfinger":       "okra",
    "bhindi":           "okra",
    "bitter melon":     "bitter gourd",
    "capsicum":         "capsicum",
    "bell pepper":      "capsicum",
    "green pepper":     "capsicum",
    "coriander":        "coriander",
    "cilantro":         "coriander",
    "dhania":           "coriander",
    "moong":            "green gram",
    "mung":             "green gram",
    "urad":             "black gram",
    "arhar":            "red gram",
    "tur":              "red gram",
    "pigeon pea":       "red gram",
    "masoor":           "lentil",
    "gram":             "chickpea",
    "chana":            "chickpea",
    "jowar":            "sorghum",
    "bajra":            "pearl millet",
    "ragi":             "finger millet",
    "rajma":            "kidney beans",
    "french beans":     "beans",
    "cluster beans":    "beans",
    "lobia":            "cowpea",
    "sugarcane":        "sugarcane",
    "ganna":            "sugarcane",
    "sarson":           "mustard",
    "til":              "sesame",
    "sunhemp":          "jute",
    "palak":            "spinach",
    "methi":            "fenugreek",
    "gajar":            "carrot",
    "muli":             "radish",
    "shalgam":          "turnip",
    "aloo":             "potato",
    "tamatar":          "tomato",
    "gehu":             "wheat",
    "dhan":             "rice",
    "makka":            "corn",
    "nariyel":          "coconut",
    "aam":              "mango",
    "amrud":            "guava",
    "anaar":            "pomegranate",
    "angoor":           "grapes",
    "kela":             "banana",
    "papita":           "papaya",
}

# ---------------------------------------------------------------------------
# META COLUMNS — first 5 columns in every sheet, not crop data
# ---------------------------------------------------------------------------
_META_COLS = {
    "Parameter Name",
    "Description / Instruction for Agronomist",
    "Unit",
    "Agronomist Input",
    "Example (Strawberry)",
}

# ---------------------------------------------------------------------------
# FALLBACK VALUES
# Used when a parameter is missing/None in the Excel cell.
# When the Excel is properly filled, these will rarely be hit.
# ---------------------------------------------------------------------------
FALLBACK = {
    # Phenology
    "base_temperature":     10.0,
    "growing_days":         120.0,
    "stage_1_gdd":          150.0,
    "stage_1_kc":           0.40,
    "stage_2_gdd":          400.0,
    "stage_2_kc":           0.75,
    "stage_3_gdd":          800.0,
    "stage_3_kc":           1.05,
    "stage_4_gdd":          1100.0,
    "stage_4_kc":           0.70,
    # Irrigation
    "soil_moisture_critical": 35.0,
    "ideal_moisture_min":    50.0,
    "ideal_moisture_max":    70.0,
    "water_demand":          "Moderate",
    "standing_water_needed": False,
    # Protection
    "fungal_temp_min":       20.0,
    "fungal_temp_max":       28.0,
    "critical_humidity":     75.0,
    "primary_fungal_disease": "Leaf spot",
    "primary_fungicide":     "Mancozeb 75% WP",
    "fungicide_dosage_ml_per_l": 2.0,
    "primary_pest":          "Aphids",
    "primary_insecticide":   "Chlorpyrifos 20%EC",
    "insecticide_dosage_ml_per_l": 2.0,
    # Nutrition
    "ndvi_threshold_for_spray":     0.65,
    "ndvi_threshold_for_fertilize": 0.60,
    "default_npk_mix":       "19:19:19",
    "default_npk_dose_kg_per_acre": 25.0,
    "stage_specific_nutrient":  "Vegetative",
    "stage_specific_chemical":  "Urea",
}


class KnowledgeBaseManager:
    """
    Loads the CropGen Excel knowledge base and exposes per-crop data
    via get_crop(). Supports 90 crops with alias-based name resolution.
    """

    def __init__(
        self,
        data_dir: str = "data",
        filename: str = "CropGen_India_Filled_AAS.xlsx",
        generated_json_name: str = "advisory_knowledge_base_generated.json",
    ):
        self.file_path = os.path.join(os.getcwd(), data_dir, filename)
        self._generated_json_path = os.path.join(os.getcwd(), data_dir, generated_json_name)

        # Internal store: { "tomato": { "phenology": {...}, "irrigation": {...}, ... } }
        # Keys are always lowercased canonical crop names (matching Excel column names).
        self._crops_db: Dict[str, Dict[str, Any]] = {}

        # Yield store: { "tomato": { "standard_yield": 80, "unit": "Quintals/Acre", ... } }
        self._yield_db: Dict[str, Dict[str, Any]] = {}

        # Set of all known canonical crop names (lowercase)
        self.known_crops: set = set()

        self._load_excel()
        self._auto_export_json()
        self._load_yield_csv()

    # -----------------------------------------------------------------------
    # EXCEL LOADING
    # -----------------------------------------------------------------------
    def _load_excel(self) -> None:
        print(f"🌱 Loading CropGen Knowledge Base from: {self.file_path}")

        if not os.path.exists(self.file_path):
            print(
                f"⚠️  Excel not found at '{self.file_path}'. "
                f"Engine will use fallback defaults for all crops."
            )
            return

        try:
            sheets = pd.read_excel(self.file_path, sheet_name=None)
        except Exception as exc:
            print(f"❌ Failed to open Excel: {exc}")
            return

        # Map the exact (possibly truncated) Excel sheet names to internal categories
        sheet_map = {
            "Phenology & Growth Stages (GDD)":  "phenology",
            "Irrigation & Soil Thresholds":      "irrigation",
            "Crop Protection (Disease & Pest":   "protection",   # truncated sheet name
            "Nutrition & Fertilizer Triggers":   "nutrition",
        }

        # Parameter-name → internal key mapping for each sheet
        param_key_maps = {
            "phenology": {
                "Base Temperature":                   "base_temperature",
                "Total Growing Days":                 "growing_days",
                "Stage 1: Germination/Establishment": "stage_1_gdd",
                "Stage 1: Crop Coefficient (Kc)":     "stage_1_kc",
                "Stage 2: Vegetative":                "stage_2_gdd",
                "Stage 2: Crop Coefficient (Kc)":     "stage_2_kc",
                "Stage 3: Flowering":                 "stage_3_gdd",
                "Stage 3: Crop Coefficient (Kc)":     "stage_3_kc",
                "Stage 4: Fruiting/Harvest":          "stage_4_gdd",
                "Stage 4: Crop Coefficient (Kc)":     "stage_4_kc",
            },
            "irrigation": {
                "Critical Low Moisture":  "soil_moisture_critical",
                "Ideal Moisture Min":     "ideal_moisture_min",
                "Ideal Moisture Max":     "ideal_moisture_max",
                "Water Demand Category":  "water_demand",
                "Standing Water Needed?": "standing_water_needed",
            },
            "protection": {
                "Optimal Fungal Temp (Min)": "fungal_temp_min",
                "Optimal Fungal Temp (Max)": "fungal_temp_max",
                "Critical Humidity":         "critical_humidity",
                "Primary Fungal Disease":    "primary_fungal_disease",
                "Primary Fungicide":         "primary_fungicide",
                "Fungicide Dosage":          "fungicide_dosage_ml_per_l",
                "Primary Pest":              "primary_pest",
                "Primary Insecticide":       "primary_insecticide",
                "Insecticide Dosage":        "insecticide_dosage_ml_per_l",
            },
            "nutrition": {
                "Critical NDVI (Spray)":       "ndvi_threshold_for_spray",
                "Critical NDVI (Fertilizer)":  "ndvi_threshold_for_fertilize",
                "Default NPK Mix":             "default_npk_mix",
                "Default NPK Dose":            "default_npk_dose_kg_per_acre",
                "Stage-Specific Nutrient":     "stage_specific_nutrient",
                "Stage-Specific Chemical":     "stage_specific_chemical",
            },
        }

        loaded_sheets = []

        for sheet_name, category in sheet_map.items():
            if sheet_name not in sheets:
                print(f"  ⚠️  Sheet not found: '{sheet_name}' — skipping.")
                continue

            df = sheets[sheet_name]
            pkey_map = param_key_maps[category]

            # The Excel is transposed:
            #   Each ROW = one parameter (e.g. "Critical Low Moisture")
            #   Each COL = one crop (e.g. "Tomato", "Rice", ...)
            # We iterate COLUMNS (crops), not rows.

            crop_cols = [c for c in df.columns if c not in _META_COLS]

            for crop_col in crop_cols:
                canonical_key = crop_col.strip().lower()

                if canonical_key not in self._crops_db:
                    self._crops_db[canonical_key] = {
                        "display_name": crop_col.strip()
                    }

                category_data: Dict[str, Any] = {}

                # For each row (parameter), read the cell for this crop column
                for _, row in df.iterrows():
                    param_name = str(row.get("Parameter Name", "")).strip()
                    if not param_name:
                        continue

                    internal_key = pkey_map.get(param_name)
                    if not internal_key:
                        continue  # ignore unrecognised parameter rows

                    cell_value = row[crop_col]

                    # Pandas returns NaN for empty cells — convert to None
                    if pd.isna(cell_value) if not isinstance(cell_value, str) else False:
                        cell_value = None

                    # Coerce "Standing Water Needed?" → bool
                    if internal_key == "standing_water_needed":
                        cell_value = str(cell_value).strip().lower() in ("yes", "true", "1")

                    # Coerce numeric strings to float where needed
                    if cell_value is not None and isinstance(cell_value, str):
                        try:
                            cell_value = float(cell_value)
                        except ValueError:
                            pass  # keep as string

                    category_data[internal_key] = cell_value

                self._crops_db[canonical_key][category] = category_data

            loaded_sheets.append(sheet_name)

        self.known_crops = set(self._crops_db.keys())
        print(
            f"✅ Knowledge base loaded: {len(self.known_crops)} crops from "
            f"{len(loaded_sheets)} sheet(s)."
        )

    # -----------------------------------------------------------------------
    # AUTO-EXPORT
    # -----------------------------------------------------------------------
    def _auto_export_json(self) -> None:
        """
        Automatically writes advisory_knowledge_base_generated.json next to the
        Excel file whenever:
          - the generated JSON does not yet exist, OR
          - the Excel file is newer than the generated JSON.

        This keeps the JSON always in sync with the Excel source of truth
        without requiring a manual export step.
        """
        if not self.known_crops:
            # Nothing was loaded (Excel missing / parse error) — skip export
            return

        needs_export = False

        if not os.path.exists(self._generated_json_path):
            needs_export = True
        else:
            excel_mtime = os.path.getmtime(self.file_path) if os.path.exists(self.file_path) else 0
            json_mtime  = os.path.getmtime(self._generated_json_path)
            if excel_mtime > json_mtime:
                needs_export = True

        if needs_export:
            self.export_to_json(self._generated_json_path)

    # -----------------------------------------------------------------------
    # YIELD DATA
    # -----------------------------------------------------------------------
    def _load_yield_csv(
        self,
        filename: str = "yield_per_crop.csv",
    ) -> None:
        """
        Loads per-crop yield data from yield_per_crop.csv.
        CSV columns expected: Crop, standard_yield, min_yield, max_yield, unit, season, notes
        Crop names in the CSV must match Excel column names (same canonical source).
        """
        import csv
        yield_path = os.path.join(os.getcwd(), "data", filename)

        if not os.path.exists(yield_path):
            print(f"⚠️  Yield CSV not found at '{yield_path}'. Yield data will be unavailable.")
            return

        try:
            with open(yield_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    crop_col = row.get("Crop", "").strip()
                    if not crop_col:
                        continue
                    canonical_key = crop_col.lower()
                    try:
                        self._yield_db[canonical_key] = {
                            "display_name":    crop_col,
                            "standard_yield":  float(row["standard_yield"]),
                            "min_yield":        float(row["min_yield"]),
                            "max_yield":        float(row["max_yield"]),
                            "unit":             row["unit"].strip(),
                            "season":           row["season"].strip(),
                            "notes":            row.get("notes", "").strip(),
                        }
                        count += 1
                    except (KeyError, ValueError) as e:
                        print(f"  ⚠️  Skipping yield row for '{crop_col}': {e}")

            print(f"✅ Yield data loaded: {count} crops from '{filename}'.")
        except Exception as exc:
            print(f"❌ Error loading yield CSV: {exc}")

    def get_yield(self, crop_name: str) -> Optional[Dict[str, Any]]:
        """
        Returns yield data for the given crop (or any known alias).
        Returns None if the crop has no yield entry.

        Example return value::
            {
                "display_name":   "Tomato",
                "standard_yield": 80.0,
                "min_yield":      35.0,
                "max_yield":      140.0,
                "unit":           "Quintals/Acre",
                "season":         "Kharif",
                "notes":          "Hybrid varieties can exceed 150",
            }
        """
        resolved = self.resolve_crop_name(crop_name)
        if resolved and resolved in self._yield_db:
            return self._yield_db[resolved]
        # Fallback: try direct lowercase match (CSV crop name may differ slightly)
        key = crop_name.strip().lower()
        return self._yield_db.get(key)

    # -----------------------------------------------------------------------
    # CROP NAME RESOLUTION
    # -----------------------------------------------------------------------
    def resolve_crop_name(self, crop_name: str) -> Optional[str]:
        """
        Resolves any crop name variant to its canonical lowercase key used in
        the internal DB.  Returns None if the crop is completely unknown.

        Resolution order:
          1. Exact match (case-insensitive) against loaded crop columns
          2. Alias lookup in CROP_ALIASES
        """
        if not crop_name:
            return None

        key = crop_name.strip().lower()

        if key in self.known_crops:
            return key

        alias_target = CROP_ALIASES.get(key)
        if alias_target and alias_target in self.known_crops:
            return alias_target

        return None

    # -----------------------------------------------------------------------
    # PUBLIC DATA ACCESS
    # -----------------------------------------------------------------------
    def get_crop(self, crop_name: str) -> Dict[str, Any]:
        """
        Returns a flat dict of all agronomic parameters for the given crop.
        Falls back to FALLBACK values for any missing or None cells.

        The returned keys are the same ones the ActivitiesEngine expects,
        so the engine can use crop_kb.get("ndvi_threshold_for_spray") etc.

        Args:
            crop_name: Any name variant (e.g. "Paddy", "paddy", "Rice").

        Returns:
            Dict with all parameters. Never raises — worst case returns all
            fallback values.
        """
        resolved = self.resolve_crop_name(crop_name)

        if resolved and resolved in self._crops_db:
            raw = self._crops_db[resolved]

            # Flatten all sheets into a single dict, preferring Excel values,
            # falling back to FALLBACK for None/missing cells.
            flat: Dict[str, Any] = {
                "display_name": raw.get("display_name", crop_name),
            }

            for category in ("phenology", "irrigation", "protection", "nutrition"):
                sheet_data = raw.get(category, {})
                for key, fallback_val in FALLBACK.items():
                    # Only apply keys relevant to this category
                    if key in sheet_data:
                        excel_val = sheet_data[key]
                        flat[key] = excel_val if excel_val is not None else fallback_val
                    elif key not in flat:
                        # Not in this sheet — will be filled by another category or FALLBACK
                        pass

            # Fill any remaining keys that didn't appear in any sheet
            for key, fallback_val in FALLBACK.items():
                if key not in flat:
                    flat[key] = fallback_val

            # Convenience aliases so the engine can use either naming convention
            flat.setdefault("ndvi_threshold_for_spray",
                            flat.get("ndvi_threshold_for_spray", FALLBACK["ndvi_threshold_for_spray"]))
            flat.setdefault("ndvi_threshold_for_fertilize",
                            flat.get("ndvi_threshold_for_fertilize", FALLBACK["ndvi_threshold_for_fertilize"]))
            flat.setdefault("soil_moisture_critical",
                            flat.get("soil_moisture_critical", FALLBACK["soil_moisture_critical"]))

            # Build a human-readable ideal_range string (used by engine for irrigation message)
            ideal_min = flat.get("ideal_moisture_min", FALLBACK["ideal_moisture_min"])
            ideal_max = flat.get("ideal_moisture_max", FALLBACK["ideal_moisture_max"])
            flat["ideal_range"] = f"{int(ideal_min)}-{int(ideal_max)}%"

            return flat

        # Completely unknown crop — return all fallback values
        return {
            "display_name":  crop_name,
            "ideal_range":   f"{int(FALLBACK['ideal_moisture_min'])}-{int(FALLBACK['ideal_moisture_max'])}%",
            **FALLBACK,
        }

    def get_display_name(self, crop_name: str) -> str:
        """Returns the proper-cased display name from the Excel column header."""
        resolved = self.resolve_crop_name(crop_name)
        if resolved and resolved in self._crops_db:
            return self._crops_db[resolved].get("display_name", crop_name)
        return crop_name

    def is_known_crop(self, crop_name: str) -> bool:
        """Returns True if the crop (or any alias) is in the knowledge base."""
        return self.resolve_crop_name(crop_name) is not None

    def list_all_crops(self) -> list:
        """Returns all canonical crop display names (proper-cased) sorted."""
        return sorted(
            self._crops_db[k].get("display_name", k)
            for k in self.known_crops
        )

    def export_to_json(self, output_path: str) -> None:
        """
        Exports the full parsed knowledge base to a JSON file.
        Useful for inspection and backward compatibility.
        """
        export_data = {}
        for key in self.known_crops:
            raw = self._crops_db[key]
            export_data[raw.get("display_name", key)] = self.get_crop(key)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2, default=str)

        print(f"📄 Knowledge base exported to: {output_path}")


# ---------------------------------------------------------------------------
# MODULE-LEVEL SINGLETON
# Instantiated once at import time. The path is resolved relative to cwd,
# which works when the app is started from the 'advisory/' directory.
# ---------------------------------------------------------------------------
kb_manager = KnowledgeBaseManager()