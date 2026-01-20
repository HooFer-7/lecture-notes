import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    ASSEMBLYAI_API_KEY: str = os.getenv("ASSEMBLYAI_API_KEY", "")
    
    # Database
    MONGODB_URL: str = os.getenv("MONGODB_URL", "")
    DATABASE_NAME: str = "lecture_notes"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-secret-key")
    
    # File Upload
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100 MB
    ALLOWED_AUDIO_TYPES: list = ["audio/mpeg", "audio/wav", "audio/mp4", "audio/x-m4a", "audio/webm"]
    
    # Paths
    UPLOAD_DIR: str = "uploads"
    
settings = Settings()

# Create upload directory if it doesn't exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)