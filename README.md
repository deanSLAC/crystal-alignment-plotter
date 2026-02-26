# Alignment Plotter

A Streamlit app for parsing and plotting SPEC data files from beamline scans. Upload a SPEC file, filter by scan range and motor, and interactively plot scan data with Plotly. Includes per-scan statistics (peak position, centroid, FWHM) and motor position change tracking between scans.

## Getting Started

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
