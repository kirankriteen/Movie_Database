import mysql.connector
import requests
import time

# --- Load Secrets (API Key + DB Password) ---
secrets = {}
with open("dont.txt", "r") as file:
    for line in file:
        line = line.strip()
        if line and "=" in line:
            key, value = line.split("=", 1)
            secrets[key] = value

API_KEY = secrets.get("API_KEY")
MYSQL_PASSWORD = secrets.get("PASSWORD")

# --- DB Config ---
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': MYSQL_PASSWORD,
    'database': 'movie_db'
}

# --- Connect to MySQL ---
conn = mysql.connector.connect(**db_config)
cursor = conn.cursor()

# --- Fetch all genres from TMDB ---
print("🎭 Fetching genres...")
genre_url = f"https://api.themoviedb.org/3/genre/movie/list?api_key={API_KEY}&language=en-US"
genre_response = requests.get(genre_url).json()
genre_map = {g["id"]: g["name"] for g in genre_response.get("genres", [])}

# Insert genres (ignore duplicates)
for genre_name in genre_map.values():
    cursor.execute("INSERT IGNORE INTO genres (name) VALUES (%s)", (genre_name,))
conn.commit()
print("✅ Genres imported successfully!")

# --- Helper: normalize names to prevent duplicates ---
def normalize_name(name):
    return name.strip().lower() if name else None

# --- Helper function to get or insert a director ---
def get_or_create_director(name, gender=None, birth_year=None):
    name_norm = normalize_name(name)
    cursor.execute("SELECT director_id FROM directors WHERE LOWER(name) = %s", (name_norm,))
    result = cursor.fetchone()
    if result:
        return result[0]
    cursor.execute(
        "INSERT INTO directors (name, gender, birth_year) VALUES (%s, %s, %s)",
        (name, gender, birth_year)
    )
    conn.commit()
    return cursor.lastrowid

# --- Helper function to get or insert an actor ---
def get_or_create_actor(name, gender=None, birth_year=None):
    name_norm = normalize_name(name)
    cursor.execute("SELECT actor_id FROM actors WHERE LOWER(name) = %s", (name_norm,))
    result = cursor.fetchone()
    if result:
        return result[0]
    cursor.execute(
        "INSERT INTO actors (name, gender, birth_year) VALUES (%s, %s, %s)",
        (name, gender, birth_year)
    )
    conn.commit()
    return cursor.lastrowid

# --- Fetch Movies ---
print("🎬 Importing movies from TMDB...")

inserted = 0
for page in range(1, 6):  # 5 pages = ~100 movies
    print(f"📄 Page {page}")
    url = f"https://api.themoviedb.org/3/movie/top_rated?api_key={API_KEY}&language=en-US&page={page}"
    response = requests.get(url)
    movies = response.json().get("results", [])

    for m in movies:
        tmdb_id = m.get("id")
        title = m.get("title", "Unknown")
        release_date = m.get("release_date", None)
        year = int(release_date.split("-")[0]) if release_date else None
        rating = m.get("vote_average", 0.0)
        description = m.get("overview", "")
        language = m.get("original_language", "en")
        poster_path = m.get("poster_path", "")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

        # Skip if movie already exists
        cursor.execute("SELECT movie_id FROM movies WHERE tmdb_id = %s", (tmdb_id,))
        if cursor.fetchone():
            continue

        # --- Fetch credits for director & actors ---
        credits_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits?api_key={API_KEY}"
        credits_data = requests.get(credits_url).json()

        # --- Get Director Info ---
        director_id = None
        crew = credits_data.get("crew", [])
        for c in crew:
            if c.get("job") == "Director":
                name = c.get("name")
                gender_map = {1: "Female", 2: "Male"}
                gender = gender_map.get(c.get("gender"), "Unknown")
                director_id = get_or_create_director(name, gender)
                break

        # --- Insert Movie ---
        cursor.execute("""
            INSERT INTO movies (tmdb_id, title, year, rating, description, poster_url, runtime, director_id, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (tmdb_id, title, year, rating, description, poster_url, None, director_id, language))
        movie_id = cursor.lastrowid
        inserted += 1

        # --- Link Genres (IGNORE duplicates) ---
        for gid in m.get("genre_ids", []):
            genre_name = genre_map.get(gid)
            if genre_name:
                cursor.execute("SELECT genre_id FROM genres WHERE name=%s", (genre_name,))
                g_row = cursor.fetchone()
                if g_row:
                    cursor.execute("""
                        INSERT IGNORE INTO movie_genres (movie_id, genre_id)
                        VALUES (%s, %s)
                    """, (movie_id, g_row[0]))

        # --- Add Actors (Top 5 only) ---
        cast = credits_data.get("cast", [])[:5]
        for actor in cast:
            actor_name = actor.get("name")
            gender = {1: "Female", 2: "Male"}.get(actor.get("gender"), "Unknown")
            actor_id = get_or_create_actor(actor_name, gender)
            role = actor.get("character", None)
            cursor.execute("""
                INSERT IGNORE INTO movie_actors (movie_id, actor_id, role)
                VALUES (%s, %s, %s)
            """, (movie_id, actor_id, role))

        conn.commit()
        time.sleep(0.25)  # avoid TMDB API rate limit

print(f"✅ Imported {inserted} new movies successfully!")
cursor.close()
conn.close()
