# Data

The raw CSVs are **not included** in this repository. The source dataset contains real hospital record/protocol numbers (pseudonymous but not fully anonymous), so it's excluded here for privacy. This file documents the schema so the pipeline in `src/analysis.py` can be run against any dataset with a matching structure.

To reproduce the analysis, place these two files in this folder:
- `hospital_data.csv`
- `icd_codes.csv`

## `hospital_data.csv`: 79,485 rows × 20 columns

| Column | Description |
|---|---|
| `PROTOCOL.NUMBER` | Internal admission protocol ID (excluded from analysis, not a predictor) |
| `OPENING.MEDICAL.RECORD.DATE` | Date the medical record was first opened |
| `ADMISSION.DATE` | Date/time of hospital admission |
| `DISCHARGE.FORECAST` | Predicted discharge date/time (not used, forward-looking field) |
| `DISCHARGE.DATE` | Actual date/time of discharge |
| `MEDICAL.RECORD` | Internal patient record ID (excluded from analysis, not a predictor) |
| `AGE` | Patient age in years |
| `SEX` | M / F |
| `HOSPITALIZATION.TYPE` | Admission category (surgical, urgency, regulation, etc.), ~33% missing |
| `SERVICE` | Specialty/department (e.g. HIP, KNEE, SPINE, ELDERLY TRAUMA) |
| `FIRST.SURGERY.DATE` | Date/time of first surgery, if any |
| `NUMBER.OF.SURGERIES` | Count of surgeries during the admission |
| `TRANSFER.PLACE` | Discharge destination (HOME, or a receiving facility) |
| `DOCTOR` | Anonymised numeric code for attending doctor |
| `ICD` | ICD-10 diagnosis code (e.g. `M17.1`) |
| `REASON.FOR.DISCHARGE` | Discharge reason (medical decision, transfer, death, etc.) |
| `COMORBIDITIES` | 0 = none recorded, 1 = one or more recorded |
| `DATE.OF.ACCIDENT` | Date of the precipitating injury, where applicable |
| `TIME.BETWEEN.INJURY.AND.HOSPITALIZATION` | 100% empty in the source data, dropped entirely |

**Derived fields** (created in `src/analysis.py`, not in the raw file): `LOS` (discharge − admission, in days), `TIME_TO_SURGERY` (first surgery − admission, in days), `ICD_CATEGORY` (mapped from the 3-character ICD prefix via `icd_codes.csv`), `TRANSFERRED` (boolean, derived from `TRANSFER.PLACE`).

## `icd_codes.csv`: ICD-10 lookup (71,704 codes, no header row)

Columns in order: `cat_code` (3-char chapter), `sub`, `full_code`, `desc_long`, `desc_short`, `category`.

**Note on matching:** joining on the full ICD code only succeeds for ~22% of records, because this lookup includes 7th-character extension codes the hospital dataset doesn't use. Matching on the 3-character prefix instead (`M17`, `S72`, `T84`, ...) gets a 92% match rate with clinically meaningful categories; that's the approach used in `analysis.py`.
