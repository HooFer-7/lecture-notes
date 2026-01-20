from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from bson import ObjectId

from app.models.user import UserCreate, UserLogin, Token, UserResponse
from app.utils.auth import (
    get_password_hash, 
    verify_password, 
    create_access_token,
    get_current_user
)
from app.database.mongodb import get_db

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    """Register a new user"""
    db = get_db()
    
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user document
    user_doc = {
        "email": user.email,
        "password_hash": get_password_hash(user.password),
        "name": user.name,
        "created_at": datetime.utcnow(),
        "subscription_tier": "free"
    }
    
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)
    
    # Create access token
    access_token = create_access_token(data={"sub": user.email, "user_id": user_id})
    
    # Return token and user info
    return Token(
        access_token=access_token,
        user=UserResponse(
            id=user_id,
            email=user.email,
            name=user.name,
            created_at=user_doc["created_at"]
        )
    )

@router.post("/login", response_model=Token)
async def login(user: UserLogin):
    """Login user and return JWT token"""
    db = get_db()
    
    # Find user
    db_user = await db.users.find_one({"email": user.email})
    
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Create access token
    user_id = str(db_user["_id"])
    access_token = create_access_token(data={"sub": user.email, "user_id": user_id})
    
    return Token(
        access_token=access_token,
        user=UserResponse(
            id=user_id,
            email=db_user["email"],
            name=db_user["name"],
            created_at=db_user["created_at"]
        )
    )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user_email: str = Depends(get_current_user)):
    """Get current user information"""
    db = get_db()
    
    user = await db.users.find_one({"email": current_user_email})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        name=user["name"],
        created_at=user["created_at"]
    )