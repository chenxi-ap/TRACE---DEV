# TRACE — Transaction Risk Analytics & Connection Explorer

**A visual investigation workbench for tracing money flows, detecting anomalies, and mapping entity relationships across financial transaction data.**

Built for the AlixPartners forensic and regulatory analytics team. TRACE turns raw bank statements and ledger exports into interactive network graphs with automated pattern detection — circular flows, rapid cycling, round-trip laundering paths, timing clusters, and concentration risk — so investigators can see what spreadsheets hide.

---

## Why This Exists

Fraud investigations start with transaction data — thousands of rows of debits, credits, wire transfers, and card payments across dozens of accounts. The patterns that matter (layering, structuring, round-tripping) are invisible in tabular form. Investigators need to see the network: who is connected to whom, how much money moved, when, and whether the flow patterns match known typologies.

TRACE provides that visibility without requiring Visio, i2 Analyst's Notebook, or manual diagramming. Upload a file or query Databricks directly, map your columns, and get an interactive graph with anomaly detection in under a minute.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Databricks App Host                   │
│                                                         │
│  ┌──────────────┐    ┌────────────────────────────────┐ │
│  │   app.py     │    │         index.html              │ │
│  │  (Flask)     │◄──►│  Single-page JS application     │ │
│  │              │    │                                  │ │
│  │  /api/data   │    │  ├─ Cytoscape.js (graph engine) │ │
│  │  endpoint    │    │  ├─ SheetJS (file parsing)      │ │
│  │              │    │  ├─ jsPDF (PDF export)           │ │
│  │  Databricks  │    │  └─ Canvas (timeline rendering) │ │
│  │  SQL via     │    │                                  │ │
│  │  OIDC token  │    └────────────────────────────────┘ │
│  └──────┬───────┘                                       │
│         │                                               │
└─────────┼───────────────────────────────────────────────┘
          │
          ▼
┌─────────────────┐
│  Databricks SQL  │
│  Warehouse       │
│  (Unity Catalog) │
└─────────────────┘
```

**Components:**

- **`index.html`** — The entire frontend: data wizard, graph rendering, visual controls, timeline, anomaly detection, grouping, annotations, and PDF export. Runs entirely in the browser with no build step.
- **`app.py`** — Flask backend. Serves the static frontend and exposes `/api/data` for querying Databricks SQL tables via service principal OIDC authentication. All transaction data stays in the browser session — nothing is stored server-side.
- **`app.yaml`** — Databricks App configuration (command, environment variables).
- **`requirements.txt`** — Python dependencies (`flask`, `requests`).

---

## Quick Start

### Prerequisites

- Access to the AlixPartners Databricks workspace
- Databricks CLI installed and configured (for deployment)
- A running SQL Warehouse (for Databricks SQL imports)

### Run Locally (for development)

```bash
# Clone the repo
git clone https://github.com/chenxi-ap/TRACE---DEV.git
cd TRACE---DEV

# Install Python dependencies
pip install -r requirements.txt

# Start the Flask server
python app.py
```

Open `http://localhost:8000` in your browser. File upload works immediately. Databricks SQL import will not work locally — it requires the service principal credentials that are only injected by the Databricks Apps runtime.

### Deploy to Databricks

The app is deployed as a Databricks App. Files live in the Git-linked workspace folder:

```
/Workspace/Users/cxu@alixpartners.com/GIT_REPO_TRACE/TRACE_APP
```

To deploy after making changes, commit and push from the Databricks Git folder, then redeploy the app pointing to the updated workspace path.

---

## Usage

### Data Import — Two Paths

**1. File Upload (CSV / Excel)**
- Drag and drop or browse for a `.csv`, `.xlsx`, or `.xls` file
- Select the sheet and header row
- Map columns to TRACE fields

**2. Databricks SQL**
- Enter Catalog, Schema, and Table name
- Optionally add a WHERE clause and row limit
- Preview before importing

### Column Mapping — Two Data Shapes

| Shape | When to Use | Required Columns |
|---|---|---|
| **From → To** | Your data has explicit sender/receiver columns | From Entity, To Entity |
| **Entity + Counterparty** | Bank statement format — one account per row, amount sign indicates direction | Entity, Counterparty, Amount |

**Optional columns** (both shapes): Amount, Date, Time, Description, Transaction Type.

### Views

- **Summary** — One edge per entity pair with aggregated totals and transaction counts. Best for seeing the big picture.
- **Detail** — One edge per individual transaction. Best for timeline playback and drilling into specific movements.
- **Side-by-side** — Both views simultaneously.

### Key Features

- **Anomaly Detection** — Automatic detection of circular flows, rapid cycling (receive-and-send within 48h), round-trip paths (money leaving and returning through intermediaries), timing clusters (statistically unusual daily volumes), and concentration risk (single-counterparty dominance).
- **Entity Grouping** — Shift+click nodes to select, then right-click → Group. Grouped entities collapse into a single hexagonal node with aggregated flows. Use this to group a person's multiple bank accounts.
- **Timeline** — Available in Detail view. Shows transactions chronologically with gap detection, playback animation, and click-to-highlight coordination with the graph.
- **Layout Options** — Force-directed (clustered), concentric (hub detection), radial from entity, hierarchy from entity, circle, grid, and classic force-directed.
- **Visual Customization** — Per-entity node shapes, colors, and icons. Edge thickness scaling, directional coloring (in/out relative to main entity), font controls, annotations with rich text editing.
- **Export** — PDF report with graph capture, timeline, and narrative summary. PNG graph snapshot. Clipboard-ready text summary.

---

## Configuration

### Environment Variables

| Variable | Description | Set By |
|---|---|---|
| `DATABRICKS_HOST` | Workspace URL (e.g. `adb-xxxxx.0.azuredatabricks.net`) | Injected by Databricks Apps runtime |
| `DATABRICKS_CLIENT_ID` | Service principal client ID | Injected by Databricks Apps runtime |
| `DATABRICKS_CLIENT_SECRET` | Service principal client secret | Injected by Databricks Apps runtime |
| `DATABRICKS_HTTP_PATH` | SQL Warehouse path (e.g. `/sql/1.0/warehouses/<id>`) | Set in `app.yaml` |

> **Note:** `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, and `DATABRICKS_CLIENT_SECRET` are injected automatically by the Databricks Apps runtime. Do not set them manually. `DATABRICKS_HTTP_PATH` is configured in `app.yaml` to point to the target SQL Warehouse.

### app.yaml

```yaml
command: ["python", "app.py"]

env:
  - name: DATABRICKS_HTTP_PATH
    value: "/sql/1.0/warehouses/8fe165e8fbe54d3e"

# DATABRICKS_HOST, DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET
# are injected automatically by the Apps runtime — do not set them here.
```

---

## Known Limitations & Gotchas

**Double counting with multi-account data** — If your data contains bank statements from both sides of a transfer (Account A's statement shows -$20 to B, Account B's statement shows +$20 from A), TRACE creates two edges for the same real transaction. Pre-clean your data to deduplicate mirror transactions, or filter to one account at a time using the entity filter.

**Main entity filter behavior** — Setting a Main Entity currently hides all transactions not directly connected to that entity. If you want the full graph visible with only directional coloring applied, modify the `getFilteredTransactions()` function (see development notes below).

**Timeline + Groups** — Timeline playback doesn't coordinate with grouped nodes. Group node positions fall to defaults in timeline layout, and playback highlighting fails for any transaction involving a grouped entity. Ungroup before using timeline.

**Large datasets** — Performance degrades above ~5,000 transactions in Detail view (each transaction = one edge). Use Summary view or filter by date/entity for large files. The Databricks import has a configurable row limit (default 10,000).

**No persistent state** — All data lives in the browser session. Refreshing the page or closing the tab loses everything. Export your work (PDF, PNG, or copy the summary) before closing.

**Local development** — Databricks SQL import does not work locally because the OIDC service principal credentials (`DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`) are only available inside the Databricks Apps runtime. Use file upload for local testing.

---

## Troubleshooting

**"Databricks import failed" error** — Check that your SQL Warehouse is running, your catalog/schema/table names are correct, and the service principal has SELECT access to the table. Verify the warehouse ID in `app.yaml` matches your target warehouse.

**Graph is empty after import** — Verify your column mapping. Both "From" and "To" (or "Entity" and "Counterparty") must be mapped to columns that contain non-empty values. Check the data preview step to confirm your header row is correct.

**Edges overlapping / labels unreadable** — Switch from Detail to Summary view to collapse parallel edges. Or increase arrow size and reduce font size in the left sidebar controls.

**PDF export is blank or cropped** — The export captures the current Cytoscape canvas. Fit the graph to view (right-click → Reset View) before exporting. Very large graphs may exceed the PDF page bounds.

**Layout looks wrong after grouping/ungrouping** — Node positions are cached between renders. If the layout looks broken, switch to a different layout in the dropdown (this clears the position cache) and switch back.

---

## Project Structure

```
TRACE_APP/
├── index.html          # Complete frontend (HTML + CSS + JS, ~3,500 lines)
├── app.py              # Flask backend with Databricks SQL proxy endpoint
├── app.yaml            # Databricks App deployment configuration
├── requirements.txt    # Python dependencies (flask, requests)
└── README.md           # This file
```

---

## Development Notes

This is a single-file frontend (`index.html`) with no build step, no npm, no bundler. All dependencies are loaded from CDNs:

- **Cytoscape.js** + **fcose layout** — Graph rendering and force-directed layout
- **SheetJS (xlsx)** — CSV/Excel parsing in the browser
- **jsPDF** — Client-side PDF generation

To make changes, edit `index.html` directly. The JavaScript is wrapped in an IIFE with a central `STATE` object that holds all application state. Key functions:

| Function | What It Does |
|---|---|
| `processData()` | Transforms raw rows into transactions, entities, and entity pairs |
| `getFilteredTransactions()` | Applies all active filters and returns the visible transaction set |
| `buildGraphElements()` | Converts filtered transactions into Cytoscape nodes and edges |
| `renderCy()` | Creates a Cytoscape instance with styling, tooltips, and event handlers |
| `runAnomalyDetection()` | Runs all five anomaly detection algorithms on the current filtered set |
| `applyGroupsToElements()` | Merges grouped entity nodes and redirects/aggregates their edges |
| `renderTimeline()` | Draws the canvas-based timeline with playback controls |
| `generateSummary()` | Produces the text narrative summary |
| `exportPDF()` | Generates the multi-page PDF report |

---

## Roadmap

- [ ] Transaction deduplication toggle (for multi-account statement imports)
- [ ] Hierarchical entity model (person → accounts with collapse/expand)
- [ ] Automatic node typing by account type (credit card, debit, brokerage)
- [ ] Net flow analysis view (show net directional amounts between entity pairs)
- [ ] Structuring detection (clustering below regulatory thresholds)
- [ ] Counterparty fuzzy matching in the import wizard
- [ ] Presentation export mode (white background, clean layout for slides)

---

## Owner & Support

- **Maintainer:** Channing Xu (`cxu@alixpartners.com`)
- **GitHub:** [chenxi-ap/TRACE---DEV](https://github.com/chenxi-ap/TRACE---DEV)
- **Workspace:** [GIT_REPO_TRACE/TRACE_APP](https://adb-7619020834316660.0.azuredatabricks.net/browse/folders/) — `/Workspace/Users/cxu@alixpartners.com/GIT_REPO_TRACE/TRACE_APP`

---

*Last updated: August 2026*
