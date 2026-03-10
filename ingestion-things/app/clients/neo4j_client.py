import os
from typing import List, Dict, Optional
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class Neo4jClient:
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self.uri = uri or os.getenv("NEO4J_URI")
        self.user = user or os.getenv("NEO4J_USER")
        self.password = password or os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        print("✅ Neo4j client initialized")

        with self.driver.session() as session:
            result = session.run("RETURN 'Neo4j Local Connected' as msg")
            print(result.single()["msg"])

    def close(self):
        self.driver.close()
        print("✅ Neo4j client closed")

    # =========================================================================
    # BAND
    # =========================================================================

    def create_band(self, band: Dict) -> str:
        """Create or update a Band node. Returns the element ID."""
        query = """
        MERGE (b:Band {mbid: $mbid})
        ON CREATE SET
            b.name = $name,
            b.formed_year = $formed_year,
            b.country = $country,
            b.genres = $genres,
            b.created = datetime()
        ON MATCH SET
            b.name = $name,
            b.country = $country,
            b.genres = $genres
        RETURN elementId(b) as node_id
        """
        params = {
            "mbid": band.get("mbid"),
            "name": band.get("name"),
            "formed_year": band.get("formed_year"),
            "country": band.get("country"),
            "genres": band.get("genres", []),
        }
        with self.driver.session() as session:
            result = session.run(query, **params)
            return str(result.single()["node_id"])

    def find_band(self, mbid: str) -> Optional[Dict]:
        """Get a band node by MBID."""
        query = "MATCH (b:Band {mbid: $mbid}) RETURN properties(b) as props"
        with self.driver.session() as session:
            result = session.run(query, mbid=mbid)
            record = result.single()
            return dict(record["props"]) if record else None

    def get_all_bands(self) -> List[Dict]:
        """Return all bands (capped at 100)."""
        query = """
        MATCH (b:Band)
        RETURN b.name as name, b.mbid as mbid,
               b.country as country, b.formed_year as formed_year
        LIMIT 100
        """
        with self.driver.session() as session:
            result = session.run(query)
            return [dict(record) for record in result]

    # =========================================================================
    # MEMBERS
    # =========================================================================

    def create_member(self, band_mbid: str, member: Dict):
        """Create a Musician node and MEMBER_OF relationship."""
        query = """
        MATCH (b:Band {mbid: $band_mbid})
        MERGE (m:Musician {name: $name})
        MERGE (m)-[r:MEMBER_OF]->(b)
        SET r.role = $role
        RETURN elementId(m) as node_id
        """
        with self.driver.session() as session:
            result = session.run(
                query,
                band_mbid=band_mbid,
                name=member.get("name"),
                role=member.get("role", "member"),
            )
            record = result.single()
            return str(record["node_id"]) if record else None

    def get_band_members(self, band_mbid: str) -> List[Dict]:
        """Return all musicians who have a MEMBER_OF relationship with this band."""
        query = """
        MATCH (m:Musician)-[r:MEMBER_OF]->(b:Band {mbid: $mbid})
        RETURN m.name as name, r.role as role
        """
        with self.driver.session() as session:
            result = session.run(query, mbid=band_mbid)
            return [dict(record) for record in result]

    # =========================================================================
    # RELEASES
    # =========================================================================

    def create_release(self, band_mbid: str, release: Dict) -> Optional[str]:
        """Create a Release node and RELEASED relationship from the Band."""
        query = """
        MATCH (b:Band {mbid: $band_mbid})
        MERGE (r:Release {title: $title, band_mbid: $band_mbid})
        ON CREATE SET
            r.year      = $year,
            r.type      = $release_type,
            r.cover_url = $cover_url,
            r.mbid      = $mbid
        MERGE (b)-[:RELEASED]->(r)
        RETURN elementId(r) as node_id
        """
        params = {
            "band_mbid": band_mbid,
            "title": release.get("title"),
            "year": release.get("year"),
            "release_type": release.get("type", "Album"),
            "cover_url": release.get("cover_url"),
            "mbid": release.get("mbid"),
        }
        with self.driver.session() as session:
            result = session.run(query, **params)
            record = result.single()
            return str(record["node_id"]) if record else None

    # =========================================================================
    # GENRES
    # =========================================================================

    def connect_genre(self, band_mbid: str, genre: str):
        """Create a Genre node and HAS_GENRE relationship from Band."""
        query = """
        MATCH (b:Band {mbid: $band_mbid})
        MERGE (g:Genre {name: $genre})
        MERGE (b)-[:HAS_GENRE]->(g)
        """
        with self.driver.session() as session:
            session.run(query, band_mbid=band_mbid, genre=genre)

    # =========================================================================
    # SCENE / DISCOVERY QUERIES
    # =========================================================================

    def get_scene_bands(self, country: str, year_start: int, year_end: int) -> List[Dict]:
        """
        Return bands from a country formed within a year range.
        Includes each band's release list from Neo4j.
        """
        query = """
        MATCH (b:Band)
        WHERE b.country = $country
          AND b.formed_year >= $year_start
          AND b.formed_year <= $year_end
        OPTIONAL MATCH (b)-[:RELEASED]->(r:Release)
            WHERE r.year >= $year_start AND r.year <= $year_end
        WITH b, collect(r.title) as releases_from_period
        RETURN b.name as band,
               b.mbid as mbid,
               b.formed_year as formed_year,
               releases_from_period
        """
        with self.driver.session() as session:
            result = session.run(
                query,
                country=country,
                year_start=year_start,
                year_end=year_end,
            )
            return [dict(record) for record in result]

    def get_similar_bands(self, band_mbid: str, limit: int = 10) -> List[Dict]:
        """
        Find bands that share Genre nodes with this band.
        A simple graph-based similarity measure.
        """
        query = """
        MATCH (b:Band {mbid: $mbid})-[:HAS_GENRE]->(g:Genre)<-[:HAS_GENRE]-(other:Band)
        WHERE other.mbid <> $mbid
        WITH other, count(g) as shared_genres
        ORDER BY shared_genres DESC
        LIMIT $limit
        RETURN other.name as name, other.mbid as mbid, shared_genres
        """
        with self.driver.session() as session:
            result = session.run(query, mbid=band_mbid, limit=limit)
            return [dict(record) for record in result]


# Smoke test
if __name__ == "__main__":
    client = Neo4jClient()

    band_id = client.create_band({
        "mbid": "test-opeth-123",
        "name": "Opeth",
        "formed_year": 1990,
        "country": "SE",
        "genres": ["progressive death metal"],
    })
    print(f"Created band: {band_id}")

    client.create_member("test-opeth-123", {"name": "Mikael Åkerfeldt", "role": "vocals/guitar"})
    client.create_release("test-opeth-123", {"title": "Blackwater Park", "year": 2001, "type": "Album"})
    client.connect_genre("test-opeth-123", "progressive death metal")

    members = client.get_band_members("test-opeth-123")
    print(f"Members: {members}")

    bands = client.get_scene_bands("SE", 1985, 2000)
    print(f"Swedish bands 1985-2000: {len(bands)}")

    client.close()
