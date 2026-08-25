#!/usr/bin/env python3
"""Serve the built UI and API on 0.0.0.0:43147."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("server.main:app", host="0.0.0.0", port=43147, reload=False)
