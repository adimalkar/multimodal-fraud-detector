# AI-Driven Multimodal Fraud Detection

This project is an advanced, multi-agent AI pipeline designed to detect generative AI fraud in insurance claims. It analyzes images, documents (PDFs), and videos to determine if the media is a genuine, real-world recording (like a dashcam) or an AI-generated fake.

We use a "Jury System" architecture: A **Vision Agent** (Qwen-VL-Plus) conducts forensic analysis on the physical and structural anomalies of the image. Its findings are then passed to a panel of **Critic Agents** (Qwen Turbo, DeepSeek R1, GLM 4.6), which independently evaluate the evidence and hold a majority vote to produce the final classification.

## Features
- **Multi-Modal Support**: Analyzes Images, Videos (via frame extraction), and Documents (PDFs).
- **Ensemble Voting Architecture**: Combines an overarching Vision Model with three separate Text LLM Critics to prevent single-model bias.
- **Dashcam Override Protocol**: Specifically tuned to differentiate between genuine motion blur/low-resolution artifacts (common in real dashcams) and unnaturally smooth AI-generated surfaces.
- **Batch Processing**: Scalable SQLite database integration allows processing of hundreds of backlog claims autonomously.
- **Interactive Dashboard**: A clean Streamlit UI for single-file analysis and live batch reporting.

---

## Installation & Setup

### 1. Prerequisites
- Python 3.10+
- `pdftoppm` (Required for processing PDF documents)
  - Ubuntu/Debian: `sudo apt-get install poppler-utils`
  - macOS: `brew install poppler`

### 2. Clone and Install
```bash
git clone https://github.com/anirudhksharma/multimodal-fraud-detector.git
cd multimodal-fraud-detector
pip install -r requirements.txt
```

### 3. API Keys
Create a `.env` file in the root directory and add your API keys:
```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
FEATHERLESS_API_KEY=your_featherless_api_key_here
```

---

---

## The Dataset: Chubb_Data

This project was built and validated against a custom dataset of roughly 500 files, encompassing a mix of genuine claims and AI-generated fraud.

- **Classes**: The dataset is split into two primary ground truth labels: `Real` and `Fake` (AI Generated).
- **Media Types**: Each class contains subdirectories for different media formats:
  - `Images/` (Car accidents, Property Damage)
  - `Documents/` (Fraudulent invoices, manipulated repair estimates)
  - `Video/` (Dashcam footage, CCTV recordings)
- **Generative Sources**: The fake dataset contains high-quality generations from tools like Midjourney, DALL-E, and various deepfake/video generation models designed specifically to test the limits of modern fraud detection.

## Few-Shot Prompting Configuration ⚠️ IMPORTANT

This pipeline utilizes **Few-Shot Prompting** to provide the Vision Agent with baseline examples of the "Real" and "Fake" data described above. However, for this to work on your local machine, **you must download the dataset and configure the correct absolute path in the backend.**

### Step 1: Download the Dataset
Download the `Chubb_Data` dataset from the following Google Drive link:
[Chubb_Data Dataset (Google Drive)](https://drive.google.com/drive/folders/1W3hGlRtZkInuP28CBjwJWIADTCIe1bSC?usp=sharing)

Extract the dataset locally on your machine.

### Step 2: Update the Few-Shot Path
Open `backend/qwen_agent.py` and locate the `get_few_shot_examples()` function (around Line 110). 

You **must** change the `base_dir` variable to match the absolute path where you extracted the `Chubb_Data` folder on your machine:

```python
def get_few_shot_examples():
    # ⚠️ CHANGE THIS TO YOUR LOCAL ABSOLUTE PATH ⚠️
    base_dir = "/path/to/your/extracted/Chubb_Data" 
    fake_dir = os.path.join(base_dir, "Fake")
    real_dir = os.path.join(base_dir, "Real")
    ...
```
*If you do not update this path, the Vision pipeline will fail or run without contextual examples!*

---

## Technical Architecture & APIs

This project avoids locking into a single AI provider by utilizing high-performance API routing services.

### OpenRouter Integration
We use **[OpenRouter](https://openrouter.ai/)** as our primary API gateway. OpenRouter allows us to seamlessly hot-swap industry-leading models without changing our fundamental API implementation. 
- **Vision Agent**: Powered by `qwen/qwen-vl-plus` via OpenRouter for state-of-the-art forensic image and structural analysis.
- **Critic Agents**: We route our text analysis through OpenRouter to highly capable LLMs like `qwen/qwen-turbo` and `google/gemini-2.5-pro` (GLM 4.6 equivalent) for the jury voting process.

### Featherless AI Integration
To ensure complete independence in the jury process, one of our three Critic Agents is routed through **[Featherless AI](https://featherless.ai/)**, a specialized provider for high-performance open-source models. 
- **DeepSeek R1-0528** is deployed via Featherless AI Serverless Endpoints. This guarantees that at least one voter in the ensemble is evaluating the evidence through an entirely different cognitive architecture and hosting environment, preventing API-level "groupthink" or correlated failures.

---

## Project Structure

```text
multimodal-fraud-detector/
├── backend/
│   ├── app.py                     # Legacy FastAPI router (optional usage)
│   ├── qwen_agent.py              # The core Brain: Vision & Critic LLM prompts and API calls
│   ├── evaluate_fake_images.py    # Standalone script for testing
│   └── evaluate_real_images.py    # Standalone script for testing
├── database/
│   ├── init_db.py                 # Crawls the Chubb_Data directory and initializes the SQLite DB
│   ├── batch_processor.py         # Autonomous script that runs inference on unanalyzed DB records
│   ├── export_to_csv.py           # Generates stakeholder reports from the active SQLite DB
│   ├── import_eval_results.py     # Integrates external team evaluation results into the DB
│   └── fraud_detection.db         # The local SQLite state database (Generated post-init)
├── frontend/
│   └── app.py                     # The Streamlit Dashboard (Uploads, Batch UI, Database Viewer)
├── test_video.py                  # Utility for testing individual video frame extraction
├── .env                           # API Keys (Gitignored)
├── requirements.txt               # Dependencies
└── README.md                      # Documentation
```

---

## Usage

### 1. Initialize the Database
Before running the batch scripts or viewing the dashboard, initialize the SQLite database tracking system:
```bash
python database/init_db.py
```

### 2. Launch the Streamlit Dashboard
To run single-image analysis visually, or to view the live dashboard statistics:
```bash
python -m streamlit run frontend/app.py
```

### 3. Run Autonomous Batch Processing
To process all remaining unprocessed records in the database completely autonomously:
```bash
python database/batch_processor.py
```

### 4. Export Reports
To extract the SQL data to a CSV for stakeholder reporting:
```bash
python database/export_to_csv.py
```
