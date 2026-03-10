from typing import List, Dict, Optional
from datetime import datetime
import json


class DocumentBuilder:
    """
    Builds documents for ChromaDB embedding and Neo4j storage
    Each document is a 'unit of knowledge' for RAG retrieval
    """
    
    def __init__(self):
        pass
    
    
    def build_band_document(self, band_data: Dict) -> Dict:
        """
        Create comprehensive band document for Chroma
        
        Returns document with:
        - id: unique identifier (mbid)
        - text: rich description for embedding
        - metadata: structured data for filtering
        """
        name = band_data.get("name", "Unknown")
        genres = band_data.get("genres", [])
        country = band_data.get("country", "Unknown")
        formed = band_data.get("formed_year")
        disbanded = band_data.get("disbanded_year")
        bio = band_data.get("biography", "")
        albums = band_data.get("albums", [])
        members = band_data.get("lineup", [])
        
        # Build rich text for embedding
        # This text determines what queries will match!
        text_parts = [
            f"{name} is a {' / '.join(genres)} band from {country}.",
        ]
        
        if formed:
            status = "disbanded" if disbanded else "active"
            text_parts.append(f"Formed in {formed}, currently {status}.")
        
        if bio:
            text_parts.append(f"Biography: {bio[:500]}")
        
        if albums:
            album_names = [a.get("title") for a in albums[:10]]
            text_parts.append(f"Notable releases: {', '.join(album_names)}.")
        
        if members:
            member_texts = []
            for m in members[:5]:
                role = m.get("role", "member")
                member_texts.append(f"{m['name']} ({role})")
            text_parts.append(f"Key members: {', '.join(member_texts)}.")
        
        # Add Reddit sentiment if available
        reddit_mentions = band_data.get("reddit_mentions", 0)
        if reddit_mentions > 0:
            text_parts.append(f"Discussed by {reddit_mentions} Reddit users.")
        
        document = {
            "id": band_data.get("mbid") or self._slugify(name),
            "type": "band",
            "text": " ".join(text_parts),
            "metadata": {
                "name": name,
                "mbid": band_data.get("mbid"),
                "genres": genres,
                "country": country,
                "formed_year": formed,
                "disbanded_year": disbanded,
                "album_count": len(albums),
                "member_count": len(members),
                "reddit_mentions": reddit_mentions,
                "popularity_score": band_data.get("popularity_score", 0),
                "last_updated": datetime.utcnow().isoformat()
            }
        }
        
        return document
    
    # =========================================================================
    # ALBUM DOCUMENTS
    # =========================================================================
    
    def build_album_documents(self, band_data: Dict) -> List[Dict]:
        """
        Create individual documents for each album
        """
        documents = []
        band_name = band_data.get("name")
        band_genres = band_data.get("genres", [])
        
        for album in band_data.get("albums", []):
            title = album.get("title")
            year = album.get("year")
            album_type = album.get("type", "album")
            
            text = f"{title} is a {album_type} by {band_name}"
            if year:
                text += f", released in {year}"
            text += f". It is a {' / '.join(band_genres)} release."
            
            doc = {
                "id": album.get("mbid") or f"{self._slugify(band_name)}-{self._slugify(title)}",
                "type": "album",
                "text": text,
                "metadata": {
                    "title": title,
                    "band": band_name,
                    "band_mbid": band_data.get("mbid"),
                    "year": year,
                    "type": album_type,
                    "genres": band_genres,
                    "cover_url": album.get("cover_url")
                }
            }
            documents.append(doc)
        
        return documents
    
    # =========================================================================
    # MEMBER/RELATIONSHIP DOCUMENTS (For "who played with whom")
    # =========================================================================
    
    def build_relationship_documents(self, band_data: Dict) -> List[Dict]:
        """
        Create documents describing member relationships
        Enables queries like "bands where Mikael Åkerfeldt played"
        """
        documents = []
        band_name = band_data.get("name")
        members = band_data.get("lineup", [])
        
        for member in members:
            name = member.get("name")
            role = member.get("role", "member")
            years = []
            if member.get("join_year"):
                years.append(str(member["join_year"]))
            if member.get("leave_year"):
                years.append(str(member["leave_year"]))
            year_str = "-".join(years) if years else "unknown years"
            
            # Document about this member in this band
            text = f"{name} played {role} for {band_name} during {year_str}. "
            text += f"They were part of the band's {' / '.join(band_data.get('genres', []))} sound."
            
            doc = {
                "id": f"member-{self._slugify(band_name)}-{self._slugify(name)}",
                "type": "membership",
                "text": text,
                "metadata": {
                    "musician_name": name,
                    "band_name": band_name,
                    "band_mbid": band_data.get("mbid"),
                    "role": role,
                    "years": year_str,
                    "genres": band_data.get("genres", [])
                }
            }
            documents.append(doc)
        
        return documents
    
    # =========================================================================
    # REDDIT DISCUSSION DOCUMENTS
    # =========================================================================
    
    def build_reddit_documents(self, posts: List[Dict], band_name: str) -> List[Dict]:
        """
        Create documents from Reddit discussions
        Captures community sentiment and opinions
        """
        documents = []
        
        for post in posts:
            text = f"Reddit discussion about {band_name}: {post['title']}"
            if post.get("content"):
                text += f". Content: {post['content'][:300]}"
            
            doc = {
                "id": f"reddit-{post['id']}",
                "type": "reddit",
                "text": text,
                "metadata": {
                    "band_mentioned": band_name,
                    "subreddit": post.get("subreddit"),
                    "author": post.get("author"),
                    "score": post.get("score"),
                    "created": post.get("created_utc").isoformat() if post.get("created_utc") else None,
                    "url": post.get("url"),
                    "sentiment": post.get("sentiment")  # If calculated
                }
            }
            documents.append(doc)
        
        return documents
    
    # =========================================================================
    # GENRE/SCENE DOCUMENTS
    # =========================================================================
    
    def build_genre_document(self, genre: str, bands: List[str], description: str = "") -> Dict:
        """
        Create document describing a genre/scene
        """
        text = f"{genre} is a metal subgenre. "
        if description:
            text += f"{description} "
        text += f"Notable bands include: {', '.join(bands[:20])}."
        
        return {
            "id": f"genre-{self._slugify(genre)}",
            "type": "genre",
            "text": text,
            "metadata": {
                "genre": genre,
                "band_examples": bands[:20],
                "band_count": len(bands)
            }
        }
    
    # =========================================================================
    # UTILITY
    # =========================================================================
    
    def _slugify(self, text: str) -> str:
        """Convert to URL-friendly ID"""
        return text.lower().replace(" ", "-").replace("'", "").replace(".", "")[:50]


# Example usage
if __name__ == "__main__":
    builder = DocumentBuilder()
    
    # Mock band data
    band = {
        "name": "Opeth",
        "mbid": "mbid-opeth-123",
        "genres": ["progressive death metal", "progressive rock"],
        "country": "SE",
        "formed_year": 1990,
        "biography": "Swedish progressive metal band from Stockholm",
        "albums": [
            {"title": "Blackwater Park", "year": 2001, "type": "album"},
            {"title": "Ghost Reveries", "year": 2005, "type": "album"}
        ],
        "lineup": [
            {"name": "Mikael Åkerfeldt", "role": "vocals/guitar", "join_year": 1990},
            {"name": "Martin Mendez", "role": "bass", "join_year": 1997}
        ],
        "reddit_mentions": 1523
    }
    
    # Build all documents
    band_doc = builder.build_band_document(band)
    album_docs = builder.build_album_documents(band)
    member_docs = builder.build_relationship_documents(band)
    
    print(f"Created {1 + len(album_docs) + len(member_docs)} documents for {band['name']}")