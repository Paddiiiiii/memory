from fastapi import APIRouter

from app.api.v1 import admin, asr, auth, export, markers, media, postprocess, projects, sessions, state, transcript

api_router = APIRouter()
for mod in (auth, projects, sessions, transcript, state, export, media, postprocess, markers, admin, asr):
    api_router.include_router(mod.router)
