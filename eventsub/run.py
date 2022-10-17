from dotenv import load_dotenv
import uvicorn

# For local development only

if __name__ == "__main__":
    # load environment variables from .env
    load_dotenv()
    uvicorn.run(
        "app.main:app",
        port=8000,
        log_level="info",
        reload=True,
        forwarded_allow_ips="*",
        proxy_headers=True,
        host="0.0.0.0",
    )
