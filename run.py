import os
import sys

# Try importing required modules and give helpful error messages if they fail
try:
    import uvicorn
except ImportError:
    print("Error: uvicorn module not found. Please run: pip install uvicorn")
    sys.exit(1)

try:
    # Import the FastAPI app directly
    from dashboard import app
except ImportError as e:
    module_name = str(e).split("'")[-2] if "'" in str(e) else str(e)
    print(f"Error: {e}")
    print(f"\nMissing module: {module_name}")
    print(f"Please run: pip install {module_name}")
    print("\nMake sure you've activated your virtual environment.")
    
    if module_name == "praw":
        print("\nPRAW (Python Reddit API Wrapper) is required for Reddit integration.")
        print("Install it with: pip install praw")
    
    sys.exit(1)

if __name__ == "__main__":
    try:
        # Check for port in environment variable or use default
        port = int(os.environ.get("PORT", 8000))
        
        # Start uvicorn server
        print(f"Starting Reddit Buyer Intent Dashboard on http://localhost:{port}")
        print("Press Ctrl+C to stop the server")
        
        uvicorn.run(
            "dashboard:app",
            host="0.0.0.0",
            port=port,
            reload=True  # Enable auto-reload during development
        )
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1) 