from flask import Flask, render_template
import mysql.connector

# --- Load Secrets ---
secrets = {}
with open("dont.txt", "r") as file:
    for line in file:
        line = line.strip()
        if line and "=" in line:
            key, value = line.split("=", 1)
            secrets[key] = value

MYSQL_PASSWORD = secrets.get("PASSWORD")

app = Flask(__name__)

# --- Database Config ---
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': MYSQL_PASSWORD,
    'database': 'movie_db'
}


# --- Helper: Get Database Connection ---
def get_db_connection():
    return mysql.connector.connect(**db_config)


# --- Home Page: Show All Movies ---
@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Join movies, directors, genres, and actors
        cursor.execute("""
            SELECT 
                m.movie_id,
                m.title,
                m.year,
                m.rating,
                m.description,
                m.poster_url,
                m.language,
                d.name AS director_name,
                GROUP_CONCAT(DISTINCT g.name SEPARATOR ', ') AS genres,
                GROUP_CONCAT(DISTINCT a.name SEPARATOR ', ') AS actors
            FROM movies m
            LEFT JOIN directors d ON m.director_id = d.director_id
            LEFT JOIN movie_genres mg ON m.movie_id = mg.movie_id
            LEFT JOIN genres g ON mg.genre_id = g.genre_id
            LEFT JOIN movie_actors ma ON m.movie_id = ma.movie_id
            LEFT JOIN actors a ON ma.actor_id = a.actor_id
            GROUP BY m.movie_id
            ORDER BY m.rating DESC
            LIMIT 50;
        """)

        movies = cursor.fetchall()
        cursor.close()
        conn.close()

        return render_template('index.html', movies=movies)

    except Exception as e:
        return f"Database error: {e}"


@app.route('/movie/<int:movie_id>')
def movie_details(movie_id):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # Fetch main movie info
        cursor.execute("""
            SELECT m.*, d.name AS director_name
            FROM movies m
            LEFT JOIN directors d ON m.director_id = d.director_id
            WHERE m.movie_id = %s
        """, (movie_id,))
        movie = cursor.fetchone()

        if not movie:
            return "❌ Movie not found", 404

        # Fetch genres
        cursor.execute("""
            SELECT g.name 
            FROM movie_genres mg 
            JOIN genres g ON mg.genre_id = g.genre_id 
            WHERE mg.movie_id = %s
        """, (movie_id,))
        genres = [row['name'] for row in cursor.fetchall()]

        # Fetch actors
        cursor.execute("""
            SELECT a.name, ma.role 
            FROM movie_actors ma
            JOIN actors a ON ma.actor_id = a.actor_id
            WHERE ma.movie_id = %s
        """, (movie_id,))
        actors = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template('movie.html', movie=movie, genres=genres, actors=actors)
    except Exception as e:
        return f"Database error: {e}"



if __name__ == '__main__':
    app.run(debug=True)
