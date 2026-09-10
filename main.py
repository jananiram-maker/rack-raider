import os
import uvicorn
from my_agent.agent import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[*] Starting naturallyEasy AI Wardrobe Assistant API on 0.0.0.0:{port}...")
    uvicorn.run("my_agent.agent:app", host="0.0.0.0", port=port, log_level="info")
