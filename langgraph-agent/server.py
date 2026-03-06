"""FastAPI wrapper for LangGraph agent service."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import run_agent

app = FastAPI(title="LangGraph Agent Service", version="1.0.0")


class RunRequest(BaseModel):
    prompt: str
    user_id: str = "arthaszeng"


class RunResponse(BaseModel):
    task_id: str
    response: str
    message_count: int


@app.post("/agent/run", response_model=RunResponse)
async def agent_run(req: RunRequest):
    try:
        result = await run_agent(req.prompt, req.user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agent/health")
async def health():
    return {"status": "ok", "service": "langgraph-agent"}
