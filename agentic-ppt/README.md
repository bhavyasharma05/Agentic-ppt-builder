# Agentic PPT Generator

AI-powered multi-agent presentation generator. Runs 100% locally.

## Project Structure

```
agentic-ppt/
├── backend/
│   ├── main.py              # FastAPI server
│   ├── agents.py            # LangGraph multi-layer pipeline
│   ├── ppt_builder.py       # python-pptx presentation builder
│   ├── requirements.txt
│   ├── .env.example
│   └── static/
│       └── images/           # Generated slide images
└── frontend/
    ├── package.json
    ├── next.config.js
    ├── tailwind.config.js
    ├── postcss.config.js
    ├── tsconfig.json
    └── app/
        ├── layout.tsx
        ├── globals.css
        └── page.tsx
```

## Setup & Run

### 1. Configure API Keys

```bash
cd backend
copy .env.example .env
```

Edit `.env` and paste your API keys:

```
LLM_API_KEY=sk-your-openai-key
LLM_MODEL=gpt-4o-mini
IMAGE_API_KEY=sk-your-openai-key
IMAGE_API_URL=https://api.openai.com/v1/images/generations
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
```

Backend runs at: http://localhost:8000

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:3000

### 4. Generate

1. Open http://localhost:3000
2. Fill in title, topic, description, slide count, theme
3. Click **Generate Presentation**
4. PPT auto-downloads when ready
