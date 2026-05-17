from fastapi import FastAPI
from app.database import Base, engine
from app.routes import chat

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MindBridge API")
app.include_router(chat.router)

@app.get("/")
def root():
    return {"status": "MindBridge is running"}