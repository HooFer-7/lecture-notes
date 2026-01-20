import httpx
import asyncio
from app.config import settings

class AssemblyAIService:
    """Speech-to-Text using AssemblyAI"""
    
    BASE_URL = "https://api.assemblyai.com/v2"
    
    def __init__(self):
        self.headers = {
            "authorization": settings.ASSEMBLYAI_API_KEY,
            "content-type": "application/json"
        }
    
    async def upload_file(self, file_path: str) -> str:
        """Upload audio file to AssemblyAI"""
        upload_url = f"{self.BASE_URL}/upload"
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            with open(file_path, "rb") as f:
                # Read the entire file content
                file_data = f.read()
                
                # Send as raw binary data, NOT as multipart form
                response = await client.post(
                    upload_url,
                    headers={
                        "authorization": settings.ASSEMBLYAI_API_KEY,
                        # No content-type header needed, or use application/octet-stream
                    },
                    content=file_data  # Use 'content' not 'files'
                )
                response.raise_for_status()
                return response.json()["upload_url"]
    
    async def create_transcript(self, audio_url: str) -> str:
        """Create transcription job"""
        transcript_url = f"{self.BASE_URL}/transcript"
        
        data = {
            "audio_url": audio_url,
            "speaker_labels": True,  # Identify different speakers
            "auto_highlights": True,  # Extract key phrases
            "punctuate": True,
            "format_text": True
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                transcript_url,
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            return response.json()["id"]
    
    async def get_transcript(self, transcript_id: str) -> dict:
        """Poll for transcript completion"""
        url = f"{self.BASE_URL}/transcript/{transcript_id}"
        
        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                result = response.json()
                
                status = result["status"]
                
                if status == "completed":
                    return result
                elif status == "error":
                    raise Exception(f"Transcription failed: {result.get('error')}")
                
                # Wait 5 seconds before checking again
                await asyncio.sleep(5)
    
    async def transcribe(self, file_path: str) -> dict:
        """Complete transcription pipeline"""
        print("📤 Uploading audio file...")
        audio_url = await self.upload_file(file_path)
        
        print("🎙️ Creating transcription job...")
        transcript_id = await self.create_transcript(audio_url)
        
        print("⏳ Waiting for transcription (this may take a few minutes)...")
        result = await self.get_transcript(transcript_id)
        
        print("✅ Transcription completed!")
        
        return {
            "text": result["text"],
            "words": result.get("words", []),
            "utterances": result.get("utterances", []),
            "confidence": result.get("confidence", 0)
        }

# Initialize service
stt_service = AssemblyAIService()