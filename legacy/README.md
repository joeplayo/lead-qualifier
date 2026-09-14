# AI Lead Qualifier

An automated lead qualification pipeline that scores incoming sales leads using AI and writes results directly back to a Google Sheet — no manual review required.

## What It Does

- Reads new leads from a Google Sheet (Name, Company, Source, Notes)
- Sends each unprocessed lead to an LLM (Llama 3.1 via Groq) for scoring
- AI evaluates each lead and returns a score (1-10), status (Hot/Warm/Cold), recommended next action, and reasoning
- Writes results back to the corresponding row in the sheet automatically
- Runs on a daily schedule via GitHub Actions — fully automated

## Tech Stack

- **Python** — core script
- **Google Sheets API** via `gspread` — read/write lead data
- **Groq API** (Llama 3.1) — LLM-powered lead scoring
- **GitHub Actions** — automated daily scheduling
- **python-dotenv** — environment variable management

## Project Structure

```
lead-qualifier/
├── main.py                  # Core script
├── requirements.txt         # Dependencies
├── sample_leads.csv         # Sample lead data for testing
├── .github/
│   └── workflows/
│       └── config.yml       # GitHub Actions workflow
├── credentials/             # Google service account (gitignored)
└── config.env               # API keys (gitignored)
```

## How It Works

1. Script authenticates with Google Sheets via a service account
2. Pulls all rows where `Status` is empty (unprocessed leads)
3. For each lead, builds a prompt with lead details and sends to Groq API
4. Parses the JSON response and extracts score, status, next action, and reason
5. Writes results back to the correct row in the sheet
6. GitHub Actions runs the script daily at 9am UTC automatically

## Setup

### 1. Clone the repo
```bash
git clone https://github.com/yourusername/lead-qualifier.git
cd lead-qualifier
pip install -r requirements.txt
```

### 2. Google Sheets API
- Create a Google Cloud project and enable the Sheets and Drive APIs
- Create a service account and download the JSON key
- Save it to `credentials/service_account.json`
- Share your Google Sheet with the service account email as Editor

### 3. Groq API
- Sign up at [console.groq.com](https://console.groq.com) and generate a free API key
- Create a `config.env` file:
```
GROQ_API_KEY=your_key_here
```

### 4. Google Sheet Format
Your sheet should have these columns:
| Name | Company | Notes | Source | Score | Status | Next Action |

### 5. Run locally
```bash
python main.py
```

### 6. Automate with GitHub Actions
Add two repository secrets under Settings → Secrets:
- `GROQ_API_KEY` — your Groq API key
- `SERVICE_ACCOUNT` — contents of your `service_account.json` file

The workflow runs daily at 9am UTC and can also be triggered manually from the Actions tab.

## Example Output

| Name | Score | Status | Next Action |
|------|-------|--------|-------------|
| Maria Gonzalez | 8 | Hot | Schedule a discovery call within 24 hours |
| James Whitfield | 6 | Warm | Follow up to gather more details |
| Sarah Thompson | 2 | Cold | Send follow-up email to clarify intent |