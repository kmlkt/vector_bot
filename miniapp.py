from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles


def mount_miniapp(app: FastAPI):
    app.mount("/miniapp", StaticFiles(directory="miniapp"))

    @app.get("/miniapp")
    async def redirect_to_index():
        return RedirectResponse("/miniapp/index.html")
