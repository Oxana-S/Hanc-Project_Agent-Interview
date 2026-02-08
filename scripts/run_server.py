"""Start the Hanc.AI web server."""

import sys
import os

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    uvicorn.run(
        "src.web.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
