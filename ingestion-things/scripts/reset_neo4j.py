from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()
URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASS = os.getenv("NEO4J_PASSWORD", "metalmind123")
driver = GraphDatabase.driver(URI, auth=(USER, PASS))

with driver.session() as session:
    session.run("MATCH (n) DETACH DELETE n;")
    print("Neo4j wiped.")
driver.close()
