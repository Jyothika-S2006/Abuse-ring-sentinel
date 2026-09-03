# Abuse Ring Sentinel

![Abuse Ring Sentinel architecture](docs/architecture-hero.png)

Abuse Ring Sentinel helps investigators find coordinated abuse by connecting account, payment, device, IP, payout, and transaction signals. It detects suspicious communities, scores their risk, and presents the evidence in a local dashboard where analysts can review and record decisions.

This repo is designed for both:
- live AI-assisted investigation when Gemini quota is available
- demo-safe fallback operation when live Gemini calls are rate-limited or unavailable

### Architecture at a glance

The system ingests synthetic CSV records into SQLite, builds a NetworkX multi-signal graph, detects communities with Louvain, extracts nine cluster features, and scores them with XGBoost. Gemini investigator and critic agents add structured evidence review before FastAPI serves the results to the analyst dashboard.

For a detailed architecture breakdown, see [ARCHITECTURE.md](ARCHITECTURE.md).

## What the project does

- Builds a multi-entity graph using shared accounts, devices, IPs, payout destinations, and transaction behavior
- Detects suspicious abuse-ring communities with community detection and clustering logic
- Scores each cluster using a feature matrix focused on risk, density, transaction flow, and decline activity
- Saves cluster data and evidence in SQLite
- Exposes a lightweight frontend for operator review and investigation
- Provides a structured AI investigation/critique flow when Gemini is available

## Pipeline

The detailed Mermaid pipeline is maintained in [ARCHITECTURE.md](ARCHITECTURE.md) so the repository has one authoritative diagram.

## Component Breakdown

`agent/` contains the investigator and critic orchestration plus the evidence-gathering tools. It is separate from the API so AI analysis can remain an optional interpretation layer over deterministic cluster data.

`backend/` owns the FastAPI application, SQLAlchemy models, cluster APIs, investigation endpoint, and audit history. Keeping persistence and HTTP boundaries here lets the frontend consume a stable local service.

`pipeline/` handles CSV ingestion, graph construction, Louvain detection, feature extraction, model training, scoring, and evaluation. The stages are separated so each part can be rerun or tested independently.

`frontend/` is a static HTML/CSS/JavaScript dashboard served by FastAPI. It keeps the demo lightweight while still exposing cluster metrics, the entity graph, investigation output, and analyst actions.

## Design Decisions

Graph-based detection was chosen over a simple rule engine because abuse rings often emerge from combinations of weak relationships across several entity types. A graph makes shared devices, IPs, cards, payouts, and transfers visible as connected communities instead of evaluating each signal in isolation.

The project uses a focused tool-calling investigator rather than a large multi-agent framework because the workflow needs one controlled evidence-gathering pass with a small, explicit tool surface. This keeps the local system easier to run, test, and audit.

A second-pass critic is included to challenge the first investigation, surface counter-considerations, and adjust confidence before a recommendation reaches the analyst. This adds a skeptical review step without hiding the final decision behind an opaque autonomous chain.

## Evaluation & Limitations

The checked-in `evaluation_results.json` contains results for 13 evaluated clusters: 10 positive fraud clusters and 3 negative legitimate clusters. The evaluation code scores all detected clusters currently stored in SQLite; therefore, this artifact is not a held-out test split in the strict machine-learning sense. The evaluated set size is 13 clusters.

Reported metrics:

- Precision: `1.0000`
- Recall: `0.9000`
- F1 score: `0.9474`
- Confusion matrix: true negatives `3`, false positives `0`, false negatives `1`, true positives `9`

The transaction dataset contains 3,819 transactions with an average transaction amount of `$159.15`. With 0 false positives, the estimated legitimate transaction volume wrongly flagged is `$0.00` (`0 × $159.15`).

This evaluation set is small (13 clusters: 10 fraud and 3 legitimate) and skewed toward fraud patterns for edge-case testing; these metrics demonstrate the evaluation methodology rather than production-grade performance estimates. A larger, balanced validation set is needed to establish reliable precision/recall.

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
├── ARCHITECTURE.md
├── docs/
│   └── architecture-hero.png
└── save_investigation.py
```

The hero image is a local documentation asset referenced by the README. Keep it at `docs/architecture-hero.png` so GitHub renders the image at the top of the project page.

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
