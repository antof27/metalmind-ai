"""
MetalMind Visualization Dashboard
----------------------------------
A Streamlit + Plotly dashboard that connects to the live Neo4j database
to visualize all ingested metal band data in real time.

Run:
    cd ingestion-things
    streamlit run dashboard.py
"""

import os
import sys
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
from neo4j import GraphDatabase

# Import orchestrator for RAG queries
from app.core.orchestrator import StorageOrchestrator

load_dotenv()

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MetalMind Dashboard",
    page_icon="🤘",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Dark metal theme */
    .stApp {
        background: linear-gradient(135deg, #0a0a0f 0%, #0f0f1a 50%, #0a0a12 100%);
        color: #e0e0ef;
    }

    /* Header */
    .hero {
        padding: 2rem 0 1rem 0;
        text-align: center;
    }
    .hero h1 {
        font-size: 3.5rem;
        font-weight: 900;
        background: linear-gradient(90deg, #ff2a2a, #ff6b00, #ffaa00);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        letter-spacing: -1px;
        margin: 0;
    }
    .hero p {
        color: #888;
        font-size: 1.1rem;
        margin-top: 0.5rem;
    }

    /* Cards */
    .metric-card {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid #2a2a4a;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        transition: all 0.3s ease;
    }
    .metric-card:hover {
        border-color: #ff4444;
        box-shadow: 0 0 20px rgba(255, 68, 68, 0.15);
    }
    .metric-number {
        font-size: 2.5rem;
        font-weight: 700;
        color: #ff4444;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 0.3rem;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: #111120;
        border-bottom: 1px solid #2a2a4a;
        gap: 0;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: #888;
        border-radius: 0;
        font-weight: 600;
        font-size: 0.9rem;
        padding: 0.75rem 1.5rem;
    }
    .stTabs [aria-selected="true"] {
        background: transparent !important;
        color: #ff4444 !important;
        border-bottom: 2px solid #ff4444;
    }

    /* Plotly chart backgrounds */
    .js-plotly-plot {
        border-radius: 12px;
        overflow: hidden;
    }

    /* Dataframe */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }

    /* Section titles */
    .section-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #e0e0ef;
        margin-bottom: 0.3rem;
    }
    .section-sub {
        font-size: 0.85rem;
        color: #666;
        margin-bottom: 1.5rem;
    }

    /* Divider */
    hr {
        border-color: #2a2a4a !important;
        margin: 2rem 0 !important;
    }

    /* Status badge */
    .badge-live {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(0,255,100,0.1);
        border: 1px solid rgba(0,255,100,0.3);
        color: #00ff64;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .dot {
        width: 7px;
        height: 7px;
        background: #00ff64;
        border-radius: 50%;
        animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #0d0d1a;
        border-right: 1px solid #2a2a4a;
    }

    /* Chat Messages */
    .stChatMessage {
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .stChatMessage[data-testid="stChatMessage"]:nth-child(even) {
        background-color: rgba(255, 68, 68, 0.05); /* user message tint */
    }
    .context-expander {
        font-size: 0.85rem;
        color: #888;
    }
</style>
""", unsafe_allow_html=True)

# ── Neo4j connection ───────────────────────────────────────────────────────────
@st.cache_resource
def get_driver():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    return GraphDatabase.driver(uri, auth=(user, password))


def run_query(query: str, params: dict = {}) -> list[dict]:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(query, **params)
        return [dict(r) for r in result]


# ── Data fetchers (cached) ─────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def fetch_bands() -> pd.DataFrame:
    rows = run_query("""
        MATCH (b:Band)
        RETURN b.name AS name,
               b.mbid AS mbid,
               b.country AS country,
               b.formed_year AS formed_year,
               b.genres AS genres
        ORDER BY b.name
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=30)
def fetch_releases() -> pd.DataFrame:
    rows = run_query("""
        MATCH (b:Band)-[:RELEASED]->(r:Release)
        RETURN b.name AS band,
               r.title AS title,
               r.year AS year,
               r.type AS type,
               b.country AS country
        ORDER BY r.year
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=30)
def fetch_genres() -> pd.DataFrame:
    rows = run_query("""
        MATCH (b:Band)-[:HAS_GENRE]->(g:Genre)
        RETURN g.name AS genre, count(b) AS band_count
        ORDER BY band_count DESC
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=30)
def fetch_members() -> pd.DataFrame:
    rows = run_query("""
        MATCH (m:Musician)-[r:MEMBER_OF]->(b:Band)
        RETURN m.name AS musician, b.name AS band, r.role AS role
        ORDER BY b.name
    """)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=30)
def fetch_stats() -> dict:
    band_count = run_query("MATCH (b:Band) RETURN count(b) AS n")[0]["n"]
    release_count = run_query("MATCH (r:Release) RETURN count(r) AS n")[0]["n"]
    member_count = run_query("MATCH (m:Musician) RETURN count(m) AS n")[0]["n"]
    genre_count = run_query("MATCH (g:Genre) RETURN count(g) AS n")[0]["n"]

    # Try to grab Chroma collection sizes for new metrics
    lyrics_count = 0
    try:
        orch = get_orchestrator()
        lyrics_count = orch.collections["lyrics"].count()
    except Exception:
        pass

    return {
        "bands": band_count,
        "releases": release_count,
        "members": member_count,
        "genres": genre_count,
        "lyrics": lyrics_count,
    }


# ── RAG Orchestrator ───────────────────────────────────────────────────────────
@st.cache_resource
def get_orchestrator():
    """Load the orchestrator once for RAG queries and Chroma access"""
    return StorageOrchestrator()


@st.cache_data(ttl=30)
def fetch_lyrics() -> pd.DataFrame:
    try:
        orch = get_orchestrator()
        lyrics_data = orch.collections["lyrics"].get()
        if not lyrics_data or not lyrics_data.get("documents"):
            return pd.DataFrame()
            
        rows = []
        for i, text in enumerate(lyrics_data["documents"]):
            meta = lyrics_data["metadatas"][i] if lyrics_data.get("metadatas") else {}
            rows.append({
                "band": meta.get("band_name", ""),
                "track": meta.get("track_title", ""),
                "lyrics": text.replace(f"{meta.get('band_name', '')} — \"{meta.get('track_title', '')}\" lyrics:\n", "").strip()
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30)
def fetch_sounds() -> pd.DataFrame:
    try:
        orch = get_orchestrator()
        sounds_data = orch.collections["sounds"].get(include=['metadatas', 'documents', 'embeddings'])
        if not sounds_data or not sounds_data.get("documents"):
            return pd.DataFrame()
            
        rows = []
        for i, text in enumerate(sounds_data["documents"]):
            meta = sounds_data["metadatas"][i] if sounds_data.get("metadatas") else {}
            emb = sounds_data.get("embeddings", [])
            vector_preview = ""
            if emb and i < len(emb) and emb[i]:
                vec = emb[i]
                vector_preview = f"[{vec[0]:.2f}, {vec[1]:.2f}, ...] ({len(vec)}D)"
                
            rows.append({
                "band": meta.get("band_name", ""),
                "track": meta.get("track_title", ""),
                "description": "Dense Audio Vector",
                "vector": vector_preview
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


# ── Country ISO mapping ────────────────────────────────────────────────────────
COUNTRY_NAMES = {
    "GB": "United Kingdom", "US": "United States", "SE": "Sweden",
    "NO": "Norway", "FI": "Finland", "DE": "Germany", "US": "United States",
    "DK": "Denmark", "AU": "Australia", "CA": "Canada", "JP": "Japan",
    "FR": "France", "IT": "Italy", "NL": "Netherlands", "BR": "Brazil",
    "AT": "Austria", "CH": "Switzerland", "PL": "Poland", "CZ": "Czech Republic",
    "GR": "Greece", "PT": "Portugal", "ES": "Spain", "IS": "Iceland",
    "HU": "Hungary", "UA": "Ukraine", "RU": "Russia", "XE": "England",
    "XW": "Wales", "XS": "Scotland",
}

# ── Plot theme shared config ───────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter", color="#c0c0d0", size=13),
    margin=dict(l=20, r=20, t=40, b=20),
    title_x=0.0,
)

METAL_COLORS = [
    "#ff2a2a", "#ff6b00", "#ffaa00", "#ff00aa", "#c400ff",
    "#4488ff", "#00ccff", "#00ff8c", "#aaaaff", "#ff8844",
]


# ── App layout ─────────────────────────────────────────────────────────────────
def main():
    # Hero header
    st.markdown("""
    <div class="hero">
        <h1>🤘 MetalMind Dashboard</h1>
        <p>Real-time visualization of your heavy metal knowledge graph</p>
        <div style="margin-top:0.8rem">
            <span class="badge-live"><span class="dot"></span>Live — Neo4j</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Refresh button top-right area
    col_space, col_btn = st.columns([8, 1])
    with col_btn:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()

    # ── Stats row ────────────────────────────────────────────────────────────
    try:
        stats = fetch_stats()
    except Exception as e:
        st.error(f"❌ Cannot connect to Neo4j: {e}")
        st.info("Make sure Neo4j is running and your `.env` is configured.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, (label, icon, val) in zip(
        [c1, c2, c3, c4, c5],
        [
            ("Bands", "🎸", stats["bands"]),
            ("Releases", "💿", stats["releases"]),
            ("Musicians", "🎤", stats["members"]),
            ("Genres", "🏷️", stats["genres"]),
            ("Lyrics", "📝", stats["lyrics"]),
        ],
    ):
        with col:
            st.markdown(f"""
            <div class="metric-card" style="padding: 1rem 0.5rem">
                <div style="font-size:1.8rem">{icon}</div>
                <div class="metric-number" style="font-size:1.8rem">{val:,}</div>
                <div class="metric-label" style="font-size:0.75rem">{label}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🌍 World Map",
        "📅 Timeline",
        "🎸 Genres",
        "💿 Releases",
        "🔗 Data Explorer",
        "🧠 AI Assistant",
    ])

    bands_df = fetch_bands()
    releases_df = fetch_releases()
    genres_df = fetch_genres()
    members_df = fetch_members()

    # ─── TAB 1: World Map ────────────────────────────────────────────────────
    with tab1:
        st.markdown('<div class="section-title">Band Origins — World Map</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-sub">Countries of origin for all ingested bands</div>', unsafe_allow_html=True)

        if bands_df.empty:
            st.info("No band data yet. Make sure mass_ingest.py is running.")
        else:
            country_counts = Counter()
            for _, row in bands_df.iterrows():
                if row.get("country"):
                    country_counts[row["country"]] += 1

            if country_counts:
                map_df = pd.DataFrame(
                    [{"country": COUNTRY_NAMES.get(k, k), "count": v}
                     for k, v in country_counts.items()]
                )
                fig = px.choropleth(
                    map_df,
                    locations="country",
                    locationmode="country names",
                    color="count",
                    hover_name="country",
                    hover_data={"count": True},
                    color_continuous_scale=[
                        [0, "#1a1a2e"],
                        [0.2, "#3d1a1a"],
                        [0.5, "#8b0000"],
                        [0.8, "#cc2200"],
                        [1.0, "#ff2a2a"],
                    ],
                    labels={"count": "Bands"},
                )
                fig.update_layout(
                    **PLOTLY_LAYOUT,
                    height=480,
                    geo=dict(
                        bgcolor="rgba(0,0,0,0)",
                        showframe=False,
                        showcoastlines=True,
                        coastlinecolor="#2a2a4a",
                        showland=True,
                        landcolor="#111120",
                        showocean=True,
                        oceancolor="#0a0a14",
                        showlakes=False,
                        showcountries=True,
                        countrycolor="#1e1e35",
                    ),
                    coloraxis_colorbar=dict(
                        title=dict(text="Bands", font=dict(color="#888")),
                        tickfont=dict(color="#888"),
                        bgcolor="rgba(0,0,0,0)",
                        bordercolor="#2a2a4a",
                    ),
                )
                st.plotly_chart(fig, use_container_width=True)

                # Country leaderboard
                st.markdown("#### Country Leaderboard")
                col_left, col_right = st.columns(2)
                with col_left:
                    leaderboard = (
                        map_df.sort_values("count", ascending=False)
                        .rename(columns={"country": "Country", "count": "Bands"})
                        [["Country", "Bands"]]
                    )
                    st.dataframe(leaderboard, use_container_width=True, hide_index=True)
            else:
                st.info("No country data available yet.")

    # ─── TAB 2: Timeline ─────────────────────────────────────────────────────
    with tab2:
        st.markdown('<div class="section-title">Formation Timeline</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-sub">When were bands in the database formed?</div>', unsafe_allow_html=True)

        if bands_df.empty:
            st.info("No data yet.")
        else:
            formed = bands_df.dropna(subset=["formed_year"]).copy()
            formed["formed_year"] = formed["formed_year"].astype(int)
            formed["decade"] = (formed["formed_year"] // 10 * 10).astype(str) + "s"

            col_a, col_b = st.columns(2)

            with col_a:
                # Bands by decade
                decade_counts = formed.groupby("decade").size().reset_index(name="count")
                decade_counts = decade_counts.sort_values("decade")
                fig2 = px.bar(
                    decade_counts,
                    x="decade",
                    y="count",
                    title="Bands Formed by Decade",
                    labels={"decade": "Decade", "count": "Number of Bands"},
                    color="count",
                    color_continuous_scale=["#1a0000", "#ff2a2a"],
                )
                fig2.update_layout(**PLOTLY_LAYOUT, height=360, showlegend=False)
                fig2.update_traces(marker_line_width=0)
                st.plotly_chart(fig2, use_container_width=True)

            with col_b:
                # Bands by exact year (scatter)
                year_counts = formed.groupby("formed_year").size().reset_index(name="count")
                fig3 = px.scatter(
                    year_counts,
                    x="formed_year",
                    y="count",
                    size="count",
                    title="Bands per Founding Year",
                    labels={"formed_year": "Year", "count": "Bands"},
                    color="count",
                    color_continuous_scale=["#440000", "#ff4444"],
                )
                fig3.update_layout(**PLOTLY_LAYOUT, height=360, showlegend=False)
                st.plotly_chart(fig3, use_container_width=True)

            # Release timeline
            if not releases_df.empty:
                st.markdown("#### Release Activity Over Time")
                rel_year = releases_df.dropna(subset=["year"]).copy()
                rel_year["year"] = rel_year["year"].astype(int)
                rel_year = rel_year[rel_year["year"] > 1960]
                type_year = rel_year.groupby(["year", "type"]).size().reset_index(name="count")

                fig4 = px.area(
                    type_year,
                    x="year",
                    y="count",
                    color="type",
                    title="Releases by Type Over Time",
                    labels={"year": "Year", "count": "Releases", "type": "Type"},
                    color_discrete_sequence=METAL_COLORS,
                )
                fig4.update_layout(**PLOTLY_LAYOUT, height=320)
                st.plotly_chart(fig4, use_container_width=True)

    # ─── TAB 3: Genres ───────────────────────────────────────────────────────
    with tab3:
        st.markdown('<div class="section-title">Genre Distribution</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-sub">How metal subgenres are distributed across the database</div>', unsafe_allow_html=True)

        col_a, col_b = st.columns([3, 2])

        with col_a:
            if not genres_df.empty:
                top_genres = genres_df.head(20)
                fig5 = px.bar(
                    top_genres.sort_values("band_count"),
                    x="band_count",
                    y="genre",
                    orientation="h",
                    title="Top 20 Genres",
                    labels={"band_count": "Number of Bands", "genre": ""},
                    color="band_count",
                    color_continuous_scale=["#1a0000", "#ff2a2a"],
                )
                fig5.update_layout(**PLOTLY_LAYOUT, height=500, showlegend=False)
                fig5.update_traces(marker_line_width=0)
                st.plotly_chart(fig5, use_container_width=True)
            else:
                # Fallback: parse genres from band properties
                if not bands_df.empty and "genres" in bands_df.columns:
                    all_genres = []
                    for g in bands_df["genres"].dropna():
                        if isinstance(g, list):
                            all_genres.extend(g)
                        elif isinstance(g, str):
                            all_genres.extend([x.strip() for x in g.split(",")])
                    genre_counts = Counter(all_genres).most_common(20)
                    if genre_counts:
                        gdf = pd.DataFrame(genre_counts, columns=["genre", "count"])
                        fig5b = px.bar(
                            gdf.sort_values("count"),
                            x="count",
                            y="genre",
                            orientation="h",
                            title="Top Genres (from band properties)",
                            labels={"count": "Bands", "genre": ""},
                            color="count",
                            color_continuous_scale=["#1a0000", "#ff2a2a"],
                        )
                        fig5b.update_layout(**PLOTLY_LAYOUT, height=500, showlegend=False)
                        st.plotly_chart(fig5b, use_container_width=True)
                    else:
                        st.info("No genre data yet.")
                else:
                    st.info("No genre data yet.")

        with col_b:
            # Pie chart
            gdata = genres_df if not genres_df.empty else pd.DataFrame()
            if gdata.empty and not bands_df.empty and "genres" in bands_df.columns:
                all_genres = []
                for g in bands_df["genres"].dropna():
                    if isinstance(g, list):
                        all_genres.extend(g)
                    elif isinstance(g, str):
                        all_genres.extend([x.strip() for x in g.split(",")])
                gdata = pd.DataFrame(Counter(all_genres).most_common(10), columns=["genre", "band_count"])

            if not gdata.empty:
                top10 = gdata.head(10)
                fig6 = px.pie(
                    top10,
                    names="genre",
                    values="band_count",
                    title="Top 10 Genres",
                    color_discrete_sequence=METAL_COLORS,
                    hole=0.4,
                )
                fig6.update_layout(
                    **PLOTLY_LAYOUT,
                    height=400,
                    legend=dict(font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
                )
                fig6.update_traces(textfont_size=12, marker=dict(line=dict(color="#0a0a0f", width=2)))
                st.plotly_chart(fig6, use_container_width=True)

    # ─── TAB 4: Releases ─────────────────────────────────────────────────────
    with tab4:
        st.markdown('<div class="section-title">Discography Overview</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-sub">Release breakdown by type and band</div>', unsafe_allow_html=True)

        if releases_df.empty:
            st.info("No release data yet.")
        else:
            col_a, col_b = st.columns(2)

            with col_a:
                # Release type distribution
                type_counts = releases_df["type"].value_counts().reset_index()
                type_counts.columns = ["type", "count"]
                fig7 = px.pie(
                    type_counts,
                    names="type",
                    values="count",
                    title="Release Types",
                    color_discrete_sequence=METAL_COLORS,
                    hole=0.35,
                )
                fig7.update_layout(
                    **PLOTLY_LAYOUT,
                    height=360,
                    legend=dict(font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
                )
                fig7.update_traces(marker=dict(line=dict(color="#0a0a0f", width=2)))
                st.plotly_chart(fig7, use_container_width=True)

            with col_b:
                # Releases per band
                band_rel = releases_df.groupby("band").size().reset_index(name="count")
                band_rel = band_rel.sort_values("count", ascending=True)
                fig8 = px.bar(
                    band_rel,
                    x="count",
                    y="band",
                    orientation="h",
                    title="Releases per Band",
                    labels={"count": "Releases", "band": ""},
                    color="count",
                    color_continuous_scale=["#1a0000", "#ff6b00"],
                )
                fig8.update_layout(**PLOTLY_LAYOUT, height=360, showlegend=False)
                fig8.update_traces(marker_line_width=0)
                st.plotly_chart(fig8, use_container_width=True)

            # Band release breakdown by type
            if len(releases_df["band"].unique()) > 0:
                st.markdown("#### Band Discography Breakdown")
                pivot = releases_df.groupby(["band", "type"]).size().reset_index(name="count")
                fig9 = px.bar(
                    pivot,
                    x="band",
                    y="count",
                    color="type",
                    title="Release Types per Band",
                    labels={"count": "Releases", "band": "", "type": "Type"},
                    color_discrete_sequence=METAL_COLORS,
                    barmode="stack",
                )
                fig9.update_layout(**PLOTLY_LAYOUT, height=380)
                st.plotly_chart(fig9, use_container_width=True)

    # ─── TAB 5: Explorer ─────────────────────────────────────────────────────
    with tab5:
        st.markdown('<div class="section-title">Data Explorer</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-sub">Browse the raw graph data</div>', unsafe_allow_html=True)

        sub1, sub2, sub3, sub4 = st.tabs(["🎸 Bands", "💿 Releases", "🎤 Members", "📝 Lyrics"])

        with sub1:
            if not bands_df.empty:
                display = bands_df.copy()
                if "genres" in display.columns:
                    display["genres"] = display["genres"].apply(
                        lambda g: ", ".join(g) if isinstance(g, list) else str(g or "")
                    )
                st.dataframe(
                    display[["name", "country", "formed_year", "genres"]].rename(columns={
                        "name": "Band", "country": "Country",
                        "formed_year": "Formed", "genres": "Genres",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No band data yet.")

        with sub2:
            if not releases_df.empty:
                st.dataframe(
                    releases_df[["band", "title", "year", "type"]].rename(columns={
                        "band": "Band", "title": "Release", "year": "Year", "type": "Type"
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No release data yet.")

        with sub3:
            if not members_df.empty:
                st.dataframe(
                    members_df.rename(columns={
                        "musician": "Musician", "band": "Band", "role": "Role"
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No member data yet.")

        with sub4:
            lyrics_df = fetch_lyrics()
            if not lyrics_df.empty:
                st.dataframe(
                    lyrics_df.rename(columns={"band": "Band", "track": "Track", "lyrics": "Lyrics Snippet"}),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No lyrics data yet. Make sure GENIUS_ACCESS_TOKEN is set in .env and bands are ingested.")

    # ─── TAB 6: AI Assistant (RAG Chat) ──────────────────────────────────────
    with tab6:
        st.markdown('<div class="section-title">MetalMind AI</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="section-sub">Ask questions about bands, lyrics, releases, and sound '
            'profiles. Powered by Llama 3.2 and your live Chroma+Neo4j data.</div>',
            unsafe_allow_html=True
        )

        col_chat, col_sources = st.columns([2, 1])

        # Initialize chat history
        if "messages" not in st.session_state:
            st.session_state.messages = []
            st.session_state.last_context = ""
            st.session_state.last_sources = []

        with col_chat:
            # Display chat history
            for message in st.session_state.messages:
                with st.chat_message(message["role"], avatar="🤘" if message["role"] == "assistant" else "👤"):
                    st.markdown(message["content"])

            # Chat input
            if prompt := st.chat_input("Ask about heavy metal... e.g. 'What are the lyrical themes of Gojira?'"):
                # Add user message to chat history
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user", avatar="👤"):
                    st.markdown(prompt)

                # Generate response
                with st.chat_message("assistant", avatar="🤘"):
                    with st.spinner("Consulting the ancient scrolls..."):
                        try:
                            orchestrator = get_orchestrator()
                            # Query RAG
                            result = orchestrator.query_rag(prompt, n_results=7)
                            answer = result["answer"]
                            # Save context for sidebar
                            st.session_state.last_context = result["context"]
                            st.session_state.last_sources = result.get("sources", [])
                            st.session_state.retrieved_docs = result.get("retrieved_documents", [])
                            
                            st.markdown(answer)
                            st.session_state.messages.append({"role": "assistant", "content": answer})
                        except Exception as e:
                            st.error(f"Error querying LLM: {e}")
                            st.info("Ensure Ollama is running and 'llama3.2' is installed.")

        with col_sources:
            st.markdown("#### 📚 Retrieval Sources")
            if st.session_state.last_sources:
                st.write("**Collections hit:**")
                for s in st.session_state.last_sources:
                    st.markdown(f"- `{s}`")
                
                with st.expander("View Raw Context"):
                    st.markdown(f"""<div class="context-expander">{st.session_state.last_context}</div>""", unsafe_allow_html=True)
                
                with st.expander("Retrieved Documents"):
                    for i, doc in enumerate(st.session_state.get("retrieved_docs", [])):
                        st.markdown(f"**Doc {i+1} ({doc.get('collection', 'unknown')} | Score: {doc.get('score', 0):.2f})**")
                        st.text(doc.get("text", "")[:300] + "...")
                        st.markdown("---")
            else:
                st.info("No query made yet. Ask a question to see retrieval context here.")

    # Footer
    st.markdown("---")
    st.markdown(
        "<p style='text-align:center; color:#444; font-size:0.8rem'>MetalMind Dashboard • "
        "Connected to Neo4j • Data updates every 30s</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
