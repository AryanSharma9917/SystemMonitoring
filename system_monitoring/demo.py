"""Isolated sample service for an operator-controlled outage demonstration."""

import asyncio
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

app = FastAPI(title="Monitoring demonstration target")
app.state.mode = "healthy"


class Mode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["healthy", "failing", "slow"]


@app.get("/health")
async def health():
    mode = app.state.mode
    if mode == "slow":
        await asyncio.sleep(5)
    return JSONResponse({"mode": mode}, status_code=503 if mode == "failing" else 200)


@app.post("/mode", response_model=Mode)
def set_mode(configuration: Mode):
    app.state.mode = configuration.mode
    return configuration


@app.get("/live")
def live():
    """Container readiness must not depend on the simulated service failure mode."""
    return {"status": "ok"}
