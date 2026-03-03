"""
FastAPI backend for agentic PPT generator.
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from agents import run_pipeline

app = FastAPI(title="Agentic PPT Generator", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class GenerateRequest(BaseModel):
    title: str
    topic: str
    description: str = ""
    num_slides: int = 8
    theme: str = "professional"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/generate")
async def generate_ppt(req: GenerateRequest):
    try:
        user_input = {
            "title": req.title,
            "topic": req.topic,
            "description": req.description,
            "num_slides": req.num_slides,
            "theme": req.theme,
        }

        result = run_pipeline(user_input)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        output_path = result.get("output_path", "")
        if not output_path or not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="PPT file was not generated.")

        return FileResponse(
            path=output_path,
            filename=f"{req.title.replace(' ', '_')}.pptx",
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
