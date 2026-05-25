# AI-READI Dataset of Type 2 Diabetes Explorer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Data: AI-READI](https://img.shields.io/badge/Data-AI--READI-blue)](https://aireadi.org)

In this repository we provide code for exploring the Flagship Dataset of Type 2 Diabetes from the AI-READI Project (v3.0.0). Currently this version primarily serves as an exploratory dashboard for understanding the dataset structure and quality. Raw signals visualization supports wearable data and CGM. 

*Note: The aggregation of daily summaries and participant-level dataset preparation is not provided in this release and will be included in the next release. Additionally, this explorer is only for the modalities we included (wearables, CGM, and ECG). An explorer for images of the retina is not included in this version.*

It includes functionality for:

- Quality checks - currently just functions for further exploration
- Exploratory **dashboard** as a Streamlit app

## ⚙️ Installation & Running the Dashboard

First, install the required Python packages using the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

Once the data is placed in `data/raw` (see Data Setup below), you can run the dashboard using:

```bash
cd src
streamlit run dashboard.py
```

## 📁 Repository Structure

- `src/dashboard.py`: Main entry point for the Streamlit interactive QC dashboard.
- `src/loader.py`: Contains data loaders for parsing raw JSON files and clinical CSVs.
- `src/config.py`: Shared configuration for paths and parsing rules.
- `src/cohort_explorer.py` & `src/visualizations.py`: Modules for rendering cohort summaries and multimodal data plots.
- `src/qc_tracker.py`: Tracks and logs quality control metrics.

## 💾 Data Setup

**Researchers are expected to request the AI-READI dataset and place the raw files into the `data/raw` directory.**

The `data/raw` directory should follow the standard AI-READI structure, containing:

- `participants.tsv`: Master list of participants and demographics.
- `clinical_data/`: Contains CSV files like `measurement.csv`, `observation.csv`, `condition_occurrence.csv`, and `procedure_occurrence.csv`.
- `wearable_activity_monitor/`: Contains Garmin Vivosmart 5 JSON data for sleep, heart rate, stress, SpO2, respiratory rate, and physical activity.
- `wearable_blood_glucose/`: Contains Dexcom G6 continuous glucose monitoring JSON data.
- `cardiac_ecg/`: Contains resting ECG data files.


## Acknowledgements

This code was developed with the help of Gemini 3.1 and Opus 4.6. Please note that this is just a fun side project and should not be used for medical decision making.

## License

Code in this repository is released under the [MIT License](LICENSE). Data files derived from the AI-READI dataset are subject to the [AI-READI Data Use Agreement](https://aireadi.org).
