from app.app import app

# Vercel's Python runtime picks up the Flask app defined at module level.
# Keep this thin entrypoint to avoid duplicate startup logic.
