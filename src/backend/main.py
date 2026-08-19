from fastapi import FastAPI
from backend.db.database import Base, engine

Base.metadata.create_all(bind=engine)

app =FastAPI(title="Chatbot WMiI UJ - API")

@app.get("/health")
def health():
    return {"status": "ok"}