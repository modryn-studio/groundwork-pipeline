"""
Local dev entrypoint. Uses SelectorEventLoop explicitly — required for psycopg
async on Windows (uvicorn 0.42+ passes loop_factory which bypasses global policy).
Use this for local dev: python run.py
Railway uses the Procfile (uvicorn directly, Linux has no ProactorEventLoop issue).
"""
import asyncio
import selectors
import sys

import uvicorn


def _selector_loop():
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


if __name__ == "__main__":
    config = uvicorn.Config("main:app", host="127.0.0.1", port=8001)
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=_selector_loop) as runner:
            runner.run(server.serve())
    else:
        server.run()
