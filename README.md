# Abuse Ring Sentinel

Abuse Ring Sentinel is a fraud and abuse-ring detection dashboard built around a graph-based risk pipeline. It ingests account, transaction, instrument, and payout data, builds a multi-signal entity graph, detects suspicious communities, scores clusters, and presents the results in a browser-based investigation UI.

This repo is designed for both:
- live AI-assisted investigation when Gemini quota is available
- demo-safe fallback operation when live Gemini calls are rate-limited or unavailable

## What the project does

- Builds a multi-entity graph using shared accounts, devices, IPs, payout destinations, and transaction behavior
- Detects suspicious abuse-ring communities with community detection and clustering logic
- Scores each cluster using a feature matrix focused on risk, density, transaction flow, and decline activity
- Saves cluster data and evidence in SQLite
- Exposes a lightweight frontend for operator review and investigation
- Provides a structured AI investigation/critique flow when Gemini is available

## Architecture

- `backend/` – FastAPI app, database initialization, routing, and API endpoints
- `agent/` – investigator/critic orchestration and Gemini-powered analysis
- `pipeline/` – ingestion, graph construction, feature extraction, clustering, and evaluation
- `frontend/` – vanilla JavaScript dashboard and static UI served by FastAPI
- `data/` – synthetic data generation and CSV datasets
- `tests/` – regression and pipeline validation checks

## Repository structure

```text
Abuse_ring_sentinel/
├── agent/
│   ├── agent.py
│   ├── critic.py
│   ├── investigator.py
│   └── tools.py
├── backend/
│   ├── __init__.py
│   ├── db.py
│   ├── main.py
│   └── routes/
│       ├── __init__.py
│       ├── agent_route.py
│       ├── audit.py
│       └── clusters.py
├── data/
│   ├── accounts.csv
│   ├── generate_synthetic_data.py
│   ├── ground_truth.csv
│   ├── instruments.csv
│   ├── payout_destinations.csv
│   └── transactions.csv
├── frontend/
│   ├── app.js
│   ├── index.html
│   └── style.css
├── pipeline/
│   ├── build_graph.py
│   ├── cluster_features.py
│   ├── detect_clusters.py
│   ├── evaluate.py
│   ├── run_pipeline.py
│   └── train_model.py
├── tests/
│   ├── __init__.py
│   ├── test_day3.py
│   ├── test_pipeline.py
│   └── test_synthetic_data.py
├── .gitignore
├── README.md
├── save_investigation.py
├── sentinel.db
├── evaluation_results.json
├── .env
└── venv/
```

## Prerequisites

- Python 3.10+
- A virtual environment is recommended
- Optional: Gemini API access for live investigation generation

## Local setup

From the project root:

```bash
python -m venv venv
venv\Scripts\activate
pip install fastapi uvicorn sqlalchemy pandas networkx scikit-learn python-dotenv google-genai
```

If you want live AI analysis, create a local `.env` file:

```env
GEMINI_API_KEY=your_key_here
```

> Keep `.env` local and untracked; do not commit secrets.

## Generate data

```bash
python data/generate_synthetic_data.py
```

## Run the pipeline

```bash
python pipeline/run_pipeline.py
```

This initializes the database, ingests the raw CSV files, builds the graph, identifies candidate abuse rings, and stores cluster data in `sentinel.db`.

## Start the app

```bash
python backend/main.py
```

Open the app in the browser at:

```text
http://127.0.0.1:8000/
```

## Main API endpoints

- `GET /api/health` – service health check
- `GET /api/clusters` – list all detected clusters
- `GET /api/clusters/{cluster_id}` – cluster detail, graph edges, members, and supporting evidence
- `PATCH /api/clusters/{cluster_id}` – update cluster status
- `GET /api/agent/explain/{cluster_id}` – investigation summary and critique payload

## Gemini / quota-safe behavior

The AI flow is implemented in `agent/` and runs:
1. investigator analysis
2. critic review
3. final recommendation and confidence output

If Gemini quota is exhausted or the API is unavailable, the backend automatically returns a cached fallback payload from the stored database summary so the dashboard stays usable for demos and local testing.

This keeps the repo operational even when live model calls are temporarily blocked.

## Testing

```bash
pytest
```

## Notes

- `sentinel.db` is the working local database for the dashboard
- `evaluation_results.json` is an output artifact from evaluation runs
- The UI is intentionally lightweight and operationally focused rather than a polished enterprise dashboard
- The live AI path is optional and depends on a valid API key and quota availability

## Summary

Abuse Ring Sentinel demonstrates a complete abuse-ring detection workflow: graph construction, cluster detection, risk scoring, evidence gathering, and operator review in a single local application. It is usable in both live AI-enabled and quota-safe fallback modes.
