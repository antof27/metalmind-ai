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
        releases = band_data.get("releases", [])
        members = band_data.get("lineup", [])
        
        # Build rich text for embedding
        text_parts = [
            f"{name} is a {' / '.join(genres)} band from {country}.",
        ]
        
        if formed:
            status = "disbanded" if disbanded else "active"
            text_parts.append(f"Formed in {formed}, currently {status}.")
        
        if bio:
            text_parts.append(f"Biography: {bio[:500]}")
        
        if releases:
            release_names = [a.get("title") for a in releases[:10]]
            text_parts.append(f"Notable releases: {', '.join(release_names)}.")
        
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
                "release_count": len(releases),
                "member_count": len(members),
                "reddit_mentions": reddit_mentions,
                "popularity_score": band_data.get("popularity_score", 0),
                "last_updated": datetime.utcnow().isoformat()
            }
        }
        
        return document
    
    # =========================================================================
    # RELEASE DOCUMENTS
    # =========================================================================
    
    def build_release_documents(self, band_data: Dict) -> List[Dict]:
        """
        Create individual documents for each release.
        Includes album wiki description and track list when available.
        """
        documents = []
        band_name = band_data.get("name")
        band_genres = band_data.get("genres", [])

        for release in band_data.get("releases", []):
            title = release.get("title")
            year = release.get("year")
            release_type = release.get("type", "Album")

            text = f"{title} is a {release_type} by {band_name}"
            if year:
                text += f", released in {year}"
            text += f". It is a {' / '.join(band_genres)} release."

            # Enrich with Last.fm album wiki description if available
            description = release.get("description", "")
            if description:
                text += f" {description}"

            # Add track list as context
            track_list = release.get("track_list", [])
            if track_list:
                text += f" Tracks include: {', '.join(t for t in track_list if t)}."

            doc = {
                "id": release.get("mbid") or f"{self._slugify(band_name)}-{self._slugify(title)}",
                "type": "release",
                "text": text,
                "metadata": {
                    "title": title,
                    "band": band_name,
                    "band_mbid": band_data.get("mbid"),
                    "year": year,
                    "type": release_type,
                    "genres": band_genres,
                    "cover_url": release.get("cover_url"),
                    "has_description": bool(description),
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
    # LYRICS DOCUMENTS (Genius)
    # =========================================================================

    def build_lyrics_documents(self, band_data: Dict) -> List[Dict]:
        """
        Create one Chroma document per top track with lyrics snippet.
        These power queries like:
          "Which bands write lyrics about war?"
          "Find songs with dark, nihilistic themes"
        """
        documents = []
        band_name = band_data.get("name", "Unknown")
        band_mbid = band_data.get("mbid")
        band_genres = band_data.get("genres", [])

        for track in band_data.get("top_tracks", []):
            lyrics = track.get("lyrics_snippet", "").strip()
            if not lyrics:
                continue

            title = track.get("title", "Unknown")
            text = (
                f"{band_name} \u2014 \"{title}\" lyrics:\n{lyrics}"
            )

            doc = {
                "id": f"lyrics-{self._slugify(band_name)}-{self._slugify(title)}",
                "type": "lyrics",
                "text": text,
                "metadata": {
                    "band_name": band_name,
                    "band_mbid": band_mbid,
                    "track_title": title,
                    "genres": band_genres,
                    "source": "genius",
                    "url": track.get("url", ""),
                },
            }
            documents.append(doc)

        return documents

    # =========================================================================
    # SOUND DOCUMENTS (AcousticBrainz)
    # =========================================================================

    def build_sound_documents(self, band_data: Dict) -> List[Dict]:
        """
        Create one Chroma document per track with dense audio embeddings.
        These power similarity matching queries against songs without LLM semantic encoding.
        """
        documents = []
        band_name = band_data.get("name", "Unknown")
        band_mbid = band_data.get("mbid")
        band_genres = band_data.get("genres", [])

        for track in band_data.get("top_tracks", []):
            embedding = track.get("embedding")
            if not embedding:
                continue

            title = track.get("title", "Unknown")

            doc = {
                "id": f"sound-{self._slugify(band_name)}-{self._slugify(title)}",
                "type": "sound",
                "text": f"{band_name} — {title}",
                "embedding": list(embedding),
                "metadata": {
                    "band_name": band_name,
                    "band_mbid": band_mbid,
                    "track_title": title,
                    "genres": band_genres,
                    "source": "acousticbrainz",
                },
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
        "releases": [
            {"title": "Blackwater Park", "year": 2001, "type": "Album"},
            {"title": "Ghost Reveries", "year": 2005, "type": "Album"}
        ],
        "lineup": [
            {"name": "Mikael Åkerfeldt", "role": "vocals/guitar", "join_year": 1990},
            {"name": "Martin Mendez", "role": "bass", "join_year": 1997}
        ],
        "reddit_mentions": 1523
    }
    
    # Build all documents
    band_doc = builder.build_band_document(band)
    release_docs = builder.build_release_documents(band)
    member_docs = builder.build_relationship_documents(band)
    
    print(f"Created {1 + len(release_docs) + len(member_docs)} documents for {band['name']}")