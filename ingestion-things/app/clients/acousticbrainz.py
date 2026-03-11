"""
AcousticBrainzEmbedder — extracts dense numerical embeddings from 
AcousticBrainz features. No categorical variables. No genre classifiers.
Just continuous, normalized vectors for similarity search.
"""

import time
from typing import Dict, Optional, List, Union
from dataclasses import dataclass
from pathlib import Path
import json

import httpx
import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class AudioEmbedding:
    """Dense audio embedding (76D unit vector)."""
    vector: NDArray[np.float32]
    mbid: str
    
    def similarity(self, other: "AudioEmbedding") -> float:
        """Cosine similarity [-1, 1]."""
        return float(np.dot(self.vector, other.vector))
    
    def to_list(self) -> List[float]:
        return self.vector.tolist()


class AcousticBrainzEmbedder:
    """
    Converts AcousticBrainz JSON → 76D numerical embedding.
    
    Structure:
    - Rhythm (8D): BPM, beats, onset, danceability
    - Tonal (16D): Key (circular), scale, chords, tuning  
    - Timbre (32D): MFCCs, spectral features
    - Mood (14D): Continuous probabilities (aggressive, happy, sad, etc.)
    - Dynamics (4D): Loudness, range
    - Voice (2D): Instrumental/vocal probability
    """
    
    BASE_URL = "https://acousticbrainz.org/api/v1"
    DELAY = 0.5
    
    def __init__(self, cache_dir: Optional[Union[str, Path]] = None):
        self.client = httpx.Client(timeout=15.0, headers={"User-Agent": "MetalMind/0.1"})
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def embed(self, mbid: str) -> Optional[AudioEmbedding]:
        """Get 76D embedding for track MBID."""
        if self.cache_dir and (cached := self._from_cache(mbid)):
            return cached
        
        low = self._fetch(f"{mbid}/low-level")
        if low:
            time.sleep(self.DELAY)
        high = self._fetch(f"{mbid}/high-level")
        
        if not low and not high:
            return None
        
        vec = self._build_vector(low or {}, high or {})
        emb = AudioEmbedding(vector=vec, mbid=mbid)
        
        if self.cache_dir:
            self._to_cache(emb)
        return emb
    
    def _build_vector(self, low: Dict, high: Dict) -> NDArray[np.float32]:
        """Build 76D vector from raw AcousticBrainz features."""
        parts = []
        
        # 1. RHYTHM (8D)
        r = low.get("rhythm", {})
        parts.append(np.array([
            min(r.get("bpm", 120) / 200.0, 1.0),
            r.get("beats_loudness", {}).get("mean", 0.5),
            r.get("beats_loudness", {}).get("var", 0.1),
            min(r.get("onset_rate", 5.0) / 10.0, 1.0),
            r.get("danceability", 0.5),
            min(r.get("beats_count", 100) / 1000.0, 1.0),
            r.get("bpm_histogram_first_peak_bpm", {}).get("mean", 120) / 200.0,
            r.get("bpm_histogram_second_peak_bpm", {}).get("mean", 120) / 200.0,
        ]))
        
        # 2. TONAL (16D) — circular key encoding
        t = low.get("tonal", {})
        key_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        key = t.get("key_key", "C")
        key_idx = key_names.index(key) if key in key_names else 0
        
        chords = t.get("chords_histogram", [])
        if len(chords) == 24:
            chords = np.array(chords)
            chords = chords / (chords.sum() + 1e-10)
            chord_entropy = -np.sum(chords * np.log(chords + 1e-10))
        else:
            chord_entropy = 0.0
        
        parts.append(np.array([
            np.sin(2 * np.pi * key_idx / 12),  # Circular key encoding
            np.cos(2 * np.pi * key_idx / 12),
            1.0 if t.get("key_scale") == "major" else 0.0,
            t.get("key_strength", 0.5),
            chord_entropy / 3.0,
            t.get("chords_changes_rate", 0.5),
            (t.get("tuning_frequency", 440.0) - 440.0) / 440.0,
            t.get("tuning_equal_tempered_deviation", 0.0),
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0  # Pad to 16
        ]))
        
        # 3. TIMBRE (32D) — spectral features
        features = []
        mfcc = low.get("mfcc", {}).get("mean", [])[:6]
        features.extend(mfcc + [0.0] * (6 - len(mfcc)))
        
        s = low.get("spectral", {})
        for key in ["centroid", "rolloff", "flux", "complexity"]:
            v = s.get(key, {})
            features.append(v.get("mean", 0.0) if isinstance(v, dict) else float(v))
            features.append(v.get("var", 0.0) if isinstance(v, dict) else 0.0)
        
        # Pad/truncate to 32
        features = features[:32] + [0.0] * (32 - len(features))
        features = np.clip((np.array(features) + 10) / 20, 0, 1)  # Normalize to [0,1]
        parts.append(features)
        
        # 4. MOOD (14D) — CONTINUOUS probabilities, NOT binary
        hl = high.get("highlevel", {})
        mood_dims = ["mood_aggressive", "mood_happy", "mood_sad", 
                     "mood_relaxed", "mood_party", "mood_acoustic", "mood_electronic"]
        mood_vals = []
        for mood in mood_dims:
            data = hl.get(mood, {})
            prob = data.get("probability", 0.5)
            val = data.get("value", "")
            # Invert if negative class
            if val.startswith("not_"):
                prob = 1.0 - prob
            mood_vals.extend([prob, abs(prob - 0.5) * 2])  # [probability, confidence]
        
        parts.append(np.array(mood_vals))
        
        # 5. DYNAMICS (4D)
        l = low.get("loudness_ebu128", {})
        parts.append(np.array([
            np.clip((l.get("integrated", -14) + 30) / 25, 0, 1),
            np.clip(l.get("loudness_range", 8) / 20, 0, 1),
            0.0, 0.0
        ]))
        
        # 6. VOICE (2D)
        v = hl.get("voice_instrumental", {})
        vp = v.get("probability", 0.5)
        is_voice = v.get("value", "voice") == "voice"
        parts.append(np.array([
            vp if is_voice else 1.0 - vp,      # Voice probability
            vp if not is_voice else 1.0 - vp   # Instrumental probability
        ]))
        
        # Concatenate → 76D, then L2 normalize
        vec = np.concatenate(parts).astype(np.float32)
        vec = vec / (np.linalg.norm(vec) + 1e-10)
        return vec
    
    def _fetch(self, path: str) -> Optional[Dict]:
        try:
            r = self.client.get(f"{self.BASE_URL}/{path}")
            return None if r.status_code == 404 else r.json()
        except:
            return None
    
    def _from_cache(self, mbid: str) -> Optional[AudioEmbedding]:
        if not self.cache_dir:
            return None
        f = self.cache_dir / f"{mbid}.json"
        if f.exists():
            data = json.loads(f.read_text())
            return AudioEmbedding(vector=np.array(data["vector"], dtype=np.float32), mbid=mbid)
        return None
    
    def _to_cache(self, emb: AudioEmbedding):
        if self.cache_dir:
            f = self.cache_dir / f"{emb.mbid}.json"
            f.write_text(json.dumps({"vector": emb.to_list(), "mbid": emb.mbid}))
    
    def close(self):
        self.client.close()


# Integration with your existing pipeline
class TrackEnricher:
    """Enriches your existing track dicts with embeddings."""
    
    def __init__(self, cache_dir: str = "./ab_cache"):
        self.embedder = AcousticBrainzEmbedder(cache_dir=cache_dir)
    
    def enrich(self, tracks: List[Dict]) -> List[Dict]:
        """
        Input: Your existing track dicts with 'mbid', 'genre', etc.
        Output: Same dicts + 'embedding' (76D vector) + 'embedding_mbid'
        """
        results = []
        for track in tracks:
            t = dict(track)
            if mbid := t.get("mbid"):
                if emb := self.embedder.embed(mbid):
                    t["embedding"] = emb.to_list()
                    t["embedding_dim"] = 76
                    t["embedding_source"] = "acousticbrainz"
            results.append(t)
        return results
    
    def find_similar(self, tracks: List[Dict], query_mbid: str, top_k: int = 5) -> List[Dict]:
        """Find most similar tracks by embedding cosine similarity."""
        query_emb = self.embedder.embed(query_mbid)
        if not query_emb:
            return []
        
        # Calculate similarities
        scored = []
        for t in tracks:
            if t.get("embedding") and t.get("mbid") != query_mbid:
                other_vec = np.array(t["embedding"], dtype=np.float32)
                sim = float(np.dot(query_emb.vector, other_vec))
                scored.append((sim, t))
        
        # Return top_k by similarity
        scored.sort(reverse=True, key=lambda x: x[0])
        return [{"similarity": s, **t} for s, t in scored[:top_k]]
    
    def close(self):
        self.embedder.close()