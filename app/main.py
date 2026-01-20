from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
from bson import ObjectId
import os
import shutil

from app.config import settings
from app.database.mongodb import MongoDB, get_db
from app.services.stt_service import stt_service
from app.services.gemini_service import gemini_service

app = FastAPI(
    title="Lecture Voice-to-Notes API",
    description="Convert lecture audio to structured notes",
    version="1.0.0"
)

# CORS - Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection events
@app.on_event("startup")
async def startup_db():
    await MongoDB.connect_db()

@app.on_event("shutdown")
async def shutdown_db():
    await MongoDB.close_db()

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Lecture Voice-to-Notes API",
        "status": "running",
        "endpoints": {
            "upload": "/api/lectures/upload",
            "get_notes": "/api/notes/{lecture_id}",
            "list_lectures": "/api/lectures/user/{user_id}"
        }
    }

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# Upload and process lecture
@app.post("/api/lectures/upload")
async def upload_lecture(
    file: UploadFile = File(...),
    title: str = Form(None),
    user_id: str = Form("default_user")
):
    """
    Upload audio file and process it into structured notes
    """
    # Validate file type
    if file.content_type not in settings.ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(settings.ALLOWED_AUDIO_TYPES)}"
        )
    
    # Read file content
    content = await file.read()
    
    # Validate file size
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE / (1024*1024)} MB"
        )
    
    try:
        # Save file temporarily
        file_extension = os.path.splitext(file.filename)[1]
        temp_filename = f"{datetime.utcnow().timestamp()}{file_extension}"
        temp_path = os.path.join(settings.UPLOAD_DIR, temp_filename)
        
        with open(temp_path, "wb") as f:
            f.write(content)
        
        print(f"📁 File saved: {temp_path}")
        
        # Create lecture document
        db = get_db()
        lecture_doc = {
            "user_id": user_id,
            "title": title or file.filename,
            "filename": file.filename,
            "upload_date": datetime.utcnow(),
            "status": "processing",
            "file_size": len(content),
            "file_path": temp_path
        }
        
        result = await db.lectures.insert_one(lecture_doc)
        lecture_id = str(result.inserted_id)
        
        print(f"📝 Lecture created with ID: {lecture_id}")
        
        # Step 1: Transcribe audio
        print("🎤 Starting transcription...")
        transcript_data = await stt_service.transcribe(temp_path)
        
        # Step 2: Generate structured notes
        print("📚 Generating structured notes...")
        structured_notes = await gemini_service.generate_notes(transcript_data["text"])
        
        # Step 3: Save to database
        note_doc = {
            "lecture_id": lecture_id,
            "user_id": user_id,
            "transcript": {
                "full_text": transcript_data["text"],
                "confidence": transcript_data["confidence"],
                "word_count": len(transcript_data["text"].split())
            },
            "structured_notes": structured_notes,
            "created_at": datetime.utcnow(),
            "last_edited": datetime.utcnow()
        }
        
        await db.notes.insert_one(note_doc)
        
        # Update lecture status
        await db.lectures.update_one(
            {"_id": ObjectId(lecture_id)},
            {"$set": {"status": "completed"}}
        )
        
        print("✅ Processing complete!")
        
        # Clean up temporary file
        try:
            os.remove(temp_path)
        except:
            pass
        
        return {
            "lecture_id": lecture_id,
            "status": "completed",
            "message": "Notes generated successfully",
            "preview": {
                "title": structured_notes.get("title"),
                "summary": structured_notes.get("summary")
            }
        }
        
    except Exception as e:
        # Update status to failed
        if 'lecture_id' in locals():
            await db.lectures.update_one(
                {"_id": ObjectId(lecture_id)},
                {"$set": {"status": "failed", "error": str(e)}}
            )
        
        # Clean up file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        print(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Get notes for a lecture
@app.get("/api/notes/{lecture_id}")
async def get_notes(lecture_id: str):
    """
    Retrieve structured notes for a specific lecture
    """
    db = get_db()
    
    try:
        note = await db.notes.find_one({"lecture_id": lecture_id})
        
        if not note:
            raise HTTPException(status_code=404, detail="Notes not found")
        
        # Convert ObjectId to string
        note["_id"] = str(note["_id"])
        
        return note
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Get all lectures for a user
@app.get("/api/lectures/user/{user_id}")
async def get_user_lectures(user_id: str):
    """
    Get all lectures for a specific user
    """
    db = get_db()
    
    try:
        lectures = await db.lectures.find(
            {"user_id": user_id}
        ).sort("upload_date", -1).to_list(100)
        
        # Convert ObjectIds to strings
        for lecture in lectures:
            lecture["_id"] = str(lecture["_id"])
            # Remove file path from response for security
            lecture.pop("file_path", None)
        
        return lectures
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Delete a lecture and its notes
@app.delete("/api/lectures/{lecture_id}")
async def delete_lecture(lecture_id: str):
    """
    Delete a lecture and associated notes
    """
    db = get_db()
    
    try:
        # Delete notes
        await db.notes.delete_many({"lecture_id": lecture_id})
        
        # Delete lecture
        result = await db.lectures.delete_one({"_id": ObjectId(lecture_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Lecture not found")
        
        return {"message": "Lecture deleted successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)