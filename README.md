[README.md](https://github.com/user-attachments/files/32064399/README.md)
# S3D ISO Weekly Case Closure Report — Dash App

An interactive browser-based dashboard for the S3D Isometric case closure report.

## Local setup

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:8050` in your browser.

## Deploy to Render (free, public URL)

1. Push this folder to a GitHub repository
2. Go to [render.com](https://render.com) and sign up (free)
3. Click **New** → **Web Service**
4. Connect your GitHub repo
5. Render auto-detects the `render.yaml` config — click **Deploy**
6. Your app will be live at `https://s3d-iso-report.onrender.com` (or similar)
7. Share the URL with your team — no accounts needed

## How to use

1. Open the URL in any browser
2. Upload the three Salesforce exports:
   - **File 1**: Last_12M_S3D_ISO_Parent_Closed_Cases_V1...
   - **File 2**: Last_12M_Parent___Helper_Case_Closed_V2...
   - **File 3**: Last_7D_Parent___Helper_Case_Closed_V3...
3. Click **Generate Report**
4. Navigate between tabs:
   - **Weekly Snapshot** — KPIs, metric comparison, case detail with filter buttons
   - **Parent Cases Closed** — parent cases split by with/without helper
   - **12 Month Trend** — interactive volume + resolution time chart
   - **Ownership** — engineer workload trend with initiative marker
   - **Benchmarks** — UCL reference table

## Interactive features

- **Filter buttons** on case detail: All Cases / Outliers Only / Open Parents
- **Hover** on any chart point to see exact values
- **Click legend entries** on charts to show/hide series
- **Sort and filter** any data table column
- **Zoom and pan** on trend charts

## Configuration

The initiative date (18 May 2026) is hardcoded in `app.py`.
Search for `2026-05` to update it when needed.

## Notes

- Free Render tier spins down after 15 min inactivity — first load after idle takes ~30 seconds
- Upgrade to paid ($7/month) for always-on hosting
