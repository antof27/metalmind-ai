"""
Reddit Client - FREE TIER
https://www.reddit.com/dev/api/

PRICING:
- Free tier: 100 requests/minute (OAuth), 10 requests/minute (read-only)
- No monthly cost for basic usage
- Higher tiers available if needed

GET TOKEN:
1. Go to https://www.reddit.com/prefs/apps
2. Click "create another app..." (bottom of page)
3. Select type: "script"
4. Name: "MetalMind"
5. Description: "Metal music research"
6. About URL: http://localhost (doesn't matter)
7. Redirect URI: http://localhost:8000/callback (doesn't matter for scripts)
8. Click "create app"
9. You get:
   - client_id (under "personal use script")
   - client_secret (labeled "secret")
"""
import os
import praw
from typing import List, Dict
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # Loads credentials from .env


class RedditClient:
    def __init__(self, client_id: str = None, client_secret: str = None, user_agent: str = None):
        self.reddit = praw.Reddit(
            client_id=client_id or os.getenv("REDDIT_CLIENT_ID"),
            client_secret=client_secret or os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=user_agent or os.getenv("REDDIT_USER_AGENT", "MetalMind/0.1.0"),
        )
        
        # Metal subreddits we care about
        self.subreddits = [
            "progmetal", "metalcore", "deathmetal", "blackmetal",
            "thrashmetal", "powermetal", "doommetal", "metal",
            "technicaldeathmetal", "melodicdeathmetal", "djent",
            "postmetal", "sludge", "stonermetal", "avantgarde"
        ]
        
        print(f"✅ Reddit client initialized (read-only)")
    
    def get_hot_posts(self, subreddit: str, limit: int = 25) -> List[Dict]:
        """Get hot posts from a subreddit"""
        posts = []
        sub = self.reddit.subreddit(subreddit)
        
        for post in sub.hot(limit=limit):
            posts.append({
                "id": post.id,
                "title": post.title,
                "content": post.selftext[:500] if post.selftext else None,  # Truncate long posts
                "author": str(post.author),
                "subreddit": subreddit,
                "created_utc": datetime.fromtimestamp(post.created_utc),
                "score": post.score,
                "num_comments": post.num_comments,
                "url": f"https://reddit.com{post.permalink}",
                "is_news": self._is_news_post(post.title),
                "mentioned_bands": self._extract_band_mentions(post.title + " " + post.selftext)
            })
        
        return posts
    
    def search_band_mentions(self, band_name: str, limit: int = 50) -> List[Dict]:
        """Search for band mentions across metal subreddits"""
        all_mentions = []
        
        for sub_name in self.subreddits:
            try:
                sub = self.reddit.subreddit(sub_name)
                for post in sub.search(band_name, limit=limit//len(self.subreddits)):
                    all_mentions.append({
                        "id": post.id,
                        "title": post.title,
                        "subreddit": sub_name,
                        "score": post.score,
                        "url": f"https://reddit.com{post.permalink}",
                        "created_utc": datetime.fromtimestamp(post.created_utc)
                    })
            except Exception as e:
                print(f"Error searching r/{sub_name}: {e}")
                continue
        
        # Sort by popularity
        all_mentions.sort(key=lambda x: x["score"], reverse=True)
        return all_mentions[:limit]
    
    def get_trending(self, limit: int = 20) -> List[Dict]:
        """Get trending posts across all metal subreddits"""
        all_posts = []
        
        for sub_name in self.subreddits:
            posts = self.get_hot_posts(sub_name, limit=5)
            all_posts.extend(posts)
        
        all_posts.sort(key=lambda x: x["score"], reverse=True)
        return all_posts[:limit]
    
    def get_subreddit_info(self, subreddit: str) -> Dict:
        """Get metadata about a subreddit"""
        sub = self.reddit.subreddit(subreddit)
        return {
            "name": sub.display_name,
            "subscribers": sub.subscribers,
            "description": sub.public_description,
            "created": datetime.fromtimestamp(sub.created_utc)
        }
    
    def _is_news_post(self, title: str) -> bool:
        """Detect if post is likely news"""
        news_keywords = ["new album", "announces", "releases", "single", 
                        "tour", "signs with", "premieres", "drops", "stream"]
        return any(kw in title.lower() for kw in news_keywords)
    
    def _extract_band_mentions(self, text: str) -> List[str]:
        """Simple band name extraction from text"""
        # This is basic - you can improve with NER later
        import re
        
        # Look for capitalized words (potential band names)
        words = re.findall(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,2}\b', text)
        
        # Filter out common words
        exclude = {"The", "And", "New", "Album", "Single", "Video", "This", 
                  "That", "For", "From", "With", "Metal", "Music", "Band"}
        
        potential = [w for w in words if w not in exclude and len(w) > 2]
        return list(set(potential))[:10]  # Max 10 mentions


# Example usage
if __name__ == "__main__":
    # Requires environment variables set!
    client = RedditClient()
    
    # Get hot posts from progmetal
    posts = client.get_hot_posts("progmetal", limit=5)
    for p in posts:
        print(f"[{p['score']}] {p['title'][:60]}...")