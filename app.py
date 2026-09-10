"""
StockAI - Cloud Backend Entrypoint for Hugging Face Spaces.
Mounts the full FastAPI backend onto Gradio for 24/7 autonomous serving.
"""

# Compatibility patch for huggingface_hub >= 0.28 / 1.0.0 and Gradio 4.x
try:
    import huggingface_hub
    if not hasattr(huggingface_hub, "HfFolder"):
        class HfFolder:
            @classmethod
            def get_token(cls):
                try:
                    from huggingface_hub import get_token
                    return get_token()
                except Exception:
                    return None
            @classmethod
            def save_token(cls, token):
                try:
                    from huggingface_hub import login
                    login(token=token)
                except Exception:
                    pass
        huggingface_hub.HfFolder = HfFolder
except Exception:
    pass

import gradio as gr
from backend.main import app as fastapi_app


def api_health():
    return {
        "status": "online",
        "platform": "StockAI India Equities Intelligence",
        "version": "0.1.0",
        "docs_url": "/docs",
        "endpoints": {
            "indices": "/api/market/indices",
            "sectors": "/api/market/sectors",
            "stock_insight": "/api/stocks/{symbol}/insight?timeframe=1d",
            "ai_predict": "/api/ai/{symbol}/predict",
            "scanner": "/api/scanner/institutional",
        },
    }


# Create visual dashboard interface on the root path
demo = gr.Interface(
    fn=api_health,
    inputs=[],
    outputs="json",
    title="⚡ StockAI Intelligence Engine — Live Backend",
    description="24/7 Production API for NSE/BSE Equities Intelligence, LightGBM ML, and Institutional Order Flows.",
)

# Mount Gradio onto the existing FastAPI application
# All /api/* routes, WebSockets, and /docs remain fully active and accessible!
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
