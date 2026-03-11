
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl


# ============================================================================
# CORE ENTITIES
# ============================================================================

class Band(BaseModel):
    """A metal band - the central entity"""
    name: str = Field(..., description="Band name", example="Opeth")
    mbid: Optional[str] = Field(None, description="MusicBrainz ID")
    
    # Basic info
    genres: List[str] = Field(default=[], description="Metal subgenres", example=["progressive death metal", "progressive rock"])
    formed_year: Optional[int] = Field(None, ge=1900, le=2030, example=1990)
    disbanded_year: Optional[int] = Field(None, ge=1900, le=2030)
    country: Optional[str] = Field(None, example="SE")
    city: Optional[str] = Field(None, example="Stockholm")
    
    # Media
    biography: Optional[str] = None
    cover_art_url: Optional[HttpUrl] = None
    logo_url: Optional[HttpUrl] = None
    
    # External links
    metal_archives_url: Optional[HttpUrl] = None
    bandcamp_url: Optional[HttpUrl] = None
    spotify_url: Optional[HttpUrl] = None
    
    # Computed metrics
    popularity_score: float = Field(0.0, ge=0, le=100)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Opeth",
                "genres": ["progressive death metal"],
                "formed_year": 1990,
                "country": "SE"
            }
        }


class Album(BaseModel):
    """An album by a band"""
    title: str = Field(..., example="Blackwater Park")
    year: Optional[int] = Field(None, ge=1900, le=2030, example=2001)
    type: str = Field("album", example="album")  # album, ep, single, live
    cover_url: Optional[HttpUrl] = None
    mbid: Optional[str] = None  # MusicBrainz release ID


class Musician(BaseModel):
    """A person in the metal scene"""
    name: str = Field(..., example="Mikael Åkerfeldt")
    instruments: List[str] = Field(default=[], example=["vocals", "guitar"])
    active_years: Optional[str] = Field(None, example="1990-present")


# ============================================================================
# REDDIT ENTITIES
# ============================================================================

class RedditPost(BaseModel):
    """A Reddit post mentioning metal"""
    id: str = Field(..., description="Reddit post ID")
    title: str = Field(..., example="What is Opeth's heaviest album?")
    content: Optional[str] = Field(None, description="Self-text or comments")
    subreddit: str = Field(..., example="progmetal")
    author: str = Field(..., example="metalhead123")
    created_utc: datetime
    score: int = Field(0, ge=0, description="Upvotes")
    num_comments: int = Field(0, ge=0)
    url: Optional[HttpUrl] = None
    mentioned_bands: List[str] = Field(default=[], example=["Opeth", "Meshuggah"])


# ============================================================================
# REQUEST/RESPONSE MODELS (For API Endpoints)
# ============================================================================

class CollectBandRequest(BaseModel):
    """POST /collect request body"""
    band_name: str = Field(..., min_length=1, example="Opeth")
    include_reddit: bool = Field(True, description="Include Reddit mentions")
    include_cover_art: bool = Field(True, description="Download album covers")


class CollectBandResponse(BaseModel):
    """POST /collect response"""
    success: bool
    band: Optional[Band] = None
    message: str
    sources_used: List[str] = Field(default=[], example=["musicbrainz", "reddit"])
    time_taken_seconds: float


class RedditSearchRequest(BaseModel):
    """GET /reddit request parameters"""
    subreddit: str = Field(..., example="progmetal")
    limit: int = Field(10, ge=1, le=100, description="Number of posts to fetch")


class RedditSearchResponse(BaseModel):
    """GET /reddit response"""
    subreddit: str
    posts_count: int
    posts: List[RedditPost]


class HealthResponse(BaseModel):
    """GET /health response"""
    status: str = Field("healthy", example="healthy")
    services: Dict[str, bool] = Field(default={}, example={"chroma": True, "reddit": True})
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# ERROR MODELS
# ============================================================================

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str = Field(..., example="Band not found")
    detail: Optional[str] = None
    suggestion: Optional[str] = Field(None, example="Try searching for 'Opeth' instead of 'Oppeth'")


# ============================================================================
# UNIFIED DATA (Combines multiple sources)
# ============================================================================

class UnifiedBandData(BaseModel):
    """Complete band data merged from all sources"""
    # Core
    name: str
    mbid: Optional[str] = None
    
    # From MusicBrainz
    genres: List[str] = []
    formed_year: Optional[int] = None
    country: Optional[str] = None
    albums: List[Album] = []
    
    # From Reddit
    reddit_mentions: int = 0
    reddit_posts: List[RedditPost] = []
    
    # From CoreRadio
    recent_releases: List[Dict[str, Any]] = []
    
    # Metadata
    last_updated: datetime = Field(default_factory=datetime.utcnow)