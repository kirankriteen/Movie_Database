from flask import Flask, render_template, request
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

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': MYSQL_PASSWORD,
    'database': 'movie_db'
}


def get_db_connection():
    return mysql.connector.connect(**db_config)


@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --- Pagination Setup ---
        page = request.args.get('page', 1, type=int)
        per_page = 10
        offset = (page - 1) * per_page

        # --- Search Handling ---
        search = request.args.get('q', '').strip()

        # Base query
        base_query = """
            FROM movies m
            LEFT JOIN directors d ON m.director_id = d.director_id
            LEFT JOIN movie_genres mg ON m.movie_id = mg.movie_id
            LEFT JOIN genres g ON mg.genre_id = g.genre_id
            LEFT JOIN movie_actors ma ON m.movie_id = ma.movie_id
            LEFT JOIN actors a ON ma.actor_id = a.actor_id
        """

        # If searching, add WHERE clause
        if search:
            where_clause = "WHERE m.title LIKE %s OR d.name LIKE %s OR a.name LIKE %s"
            params = (f"%{search}%", f"%{search}%", f"%{search}%")
        else:
            where_clause = ""
            params = ()

        # --- Count total results for pagination ---
        count_query = f"SELECT COUNT(DISTINCT m.movie_id) {base_query} {where_clause}"
        cursor.execute(count_query, params)
        total_movies = cursor.fetchone()['COUNT(DISTINCT m.movie_id)']

        total_pages = (total_movies + per_page - 1) // per_page

        # --- Fetch paginated data ---
        movie_query = f"""
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
            {base_query}
            {where_clause}
            GROUP BY m.movie_id
            ORDER BY m.rating DESC
            LIMIT %s OFFSET %s;
        """
        cursor.execute(movie_query, params + (per_page, offset))
        movies = cursor.fetchall()

        cursor.close()
        conn.close()

        # --- Pass everything to template ---
        return render_template(
            'index.html',
            movies=movies,
            page=page,
            total_pages=total_pages,
            search=search
        )

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

@app.route('/genre/<genre_name>')
def genre_page(genre_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --- Pagination ---
        page = request.args.get('page', 1, type=int)
        per_page = 10
        offset = (page - 1) * per_page

        # --- Count total movies in this genre ---
        count_query = """
            SELECT COUNT(DISTINCT m.movie_id) AS total
            FROM movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            JOIN genres g ON mg.genre_id = g.genre_id
            WHERE g.name = %s
        """
        cursor.execute(count_query, (genre_name,))
        total_movies = cursor.fetchone()['total']
        total_pages = (total_movies + per_page - 1) // per_page

        # --- Fetch paginated movies ---
        movie_query = """
            SELECT 
                m.movie_id,
                m.title,
                m.year,
                m.rating,
                m.description,
                m.poster_url,
                m.language,
                d.name AS director_name,
                GROUP_CONCAT(DISTINCT g2.name SEPARATOR ', ') AS genres,
                GROUP_CONCAT(DISTINCT a.name SEPARATOR ', ') AS actors
            FROM movies m
            LEFT JOIN directors d ON m.director_id = d.director_id
            LEFT JOIN movie_genres mg ON m.movie_id = mg.movie_id
            LEFT JOIN genres g ON mg.genre_id = g.genre_id
            LEFT JOIN movie_actors ma ON m.movie_id = ma.movie_id
            LEFT JOIN actors a ON ma.actor_id = a.actor_id
            LEFT JOIN movie_genres mg2 ON m.movie_id = mg2.movie_id
            LEFT JOIN genres g2 ON mg2.genre_id = g2.genre_id
            WHERE g.name = %s
            GROUP BY m.movie_id
            ORDER BY m.rating DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(movie_query, (genre_name, per_page, offset))
        movies = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            'index.html',
            movies=movies,
            page=page,
            total_pages=total_pages,
            search='',
            genre_name=genre_name
        )
    except Exception as e:
        return f"Database error: {e}"

@app.route('/director/<director_name>')
def director_page(director_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --- Pagination ---
        page = request.args.get('page', 1, type=int)
        per_page = 10
        offset = (page - 1) * per_page

        # --- Count total movies by this director ---
        count_query = """
            SELECT COUNT(DISTINCT m.movie_id) AS total
            FROM movies m
            JOIN directors d ON m.director_id = d.director_id
            WHERE d.name = %s
        """
        cursor.execute(count_query, (director_name,))
        total_movies = cursor.fetchone()['total']
        total_pages = (total_movies + per_page - 1) // per_page

        # --- Fetch paginated movies ---
        movie_query = """
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
            WHERE d.name = %s
            GROUP BY m.movie_id
            ORDER BY m.rating DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(movie_query, (director_name, per_page, offset))
        movies = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            'index.html',
            movies=movies,
            page=page,
            total_pages=total_pages,
            search='',
            genre_name=None,
            base_url=f"/director/{director_name}"
        )
    except Exception as e:
        return f"Database error: {e}"


@app.route('/actor/<actor_name>')
def actor_page(actor_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --- Pagination ---
        page = request.args.get('page', 1, type=int)
        per_page = 10
        offset = (page - 1) * per_page

        # --- Count total movies for this actor ---
        count_query = """
            SELECT COUNT(DISTINCT m.movie_id) AS total
            FROM movies m
            JOIN movie_actors ma ON m.movie_id = ma.movie_id
            JOIN actors a ON ma.actor_id = a.actor_id
            WHERE a.name = %s
        """
        cursor.execute(count_query, (actor_name,))
        total_movies = cursor.fetchone()['total']
        total_pages = (total_movies + per_page - 1) // per_page

        # --- Fetch paginated movies ---
        movie_query = """
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
                GROUP_CONCAT(DISTINCT a2.name SEPARATOR ', ') AS actors
            FROM movies m
            LEFT JOIN directors d ON m.director_id = d.director_id
            LEFT JOIN movie_genres mg ON m.movie_id = mg.movie_id
            LEFT JOIN genres g ON mg.genre_id = g.genre_id
            LEFT JOIN movie_actors ma2 ON m.movie_id = ma2.movie_id
            LEFT JOIN actors a2 ON ma2.actor_id = a2.actor_id
            JOIN movie_actors ma ON m.movie_id = ma.movie_id
            JOIN actors a ON ma.actor_id = a.actor_id
            WHERE a.name = %s
            GROUP BY m.movie_id
            ORDER BY m.rating DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(movie_query, (actor_name, per_page, offset))
        movies = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            'index.html',
            movies=movies,
            page=page,
            total_pages=total_pages,
            search='',
            genre_name=None,
            base_url=f"/actor/{actor_name}"
        )
    except Exception as e:
        return f"Database error: {e}"

@app.route('/language/<language_name>')
def language_page(language_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --- Pagination ---
        page = request.args.get('page', 1, type=int)
        per_page = 10
        offset = (page - 1) * per_page

        # --- Count total movies for this language ---
        count_query = """
            SELECT COUNT(*) AS total
            FROM movies
            WHERE language = %s
        """
        cursor.execute(count_query, (language_name,))
        total_movies = cursor.fetchone()['total']
        total_pages = (total_movies + per_page - 1) // per_page

        # --- Fetch paginated movies ---
        movie_query = """
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
            WHERE m.language = %s
            GROUP BY m.movie_id
            ORDER BY m.rating DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(movie_query, (language_name, per_page, offset))
        movies = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            'index.html',
            movies=movies,
            page=page,
            total_pages=total_pages,
            search='',
            genre_name=None,
            base_url=f"/language/{language_name}"
        )
    except Exception as e:
        return f"Database error: {e}"

@app.route('/year/<int:year>')
def year_page(year):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --- Pagination ---
        page = request.args.get('page', 1, type=int)
        per_page = 10
        offset = (page - 1) * per_page

        # --- Count total movies for this year ---
        count_query = """
            SELECT COUNT(*) AS total
            FROM movies
            WHERE year = %s
        """
        cursor.execute(count_query, (year,))
        total_movies = cursor.fetchone()['total']
        total_pages = (total_movies + per_page - 1) // per_page

        # --- Fetch paginated movies ---
        movie_query = """
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
            WHERE m.year = %s
            GROUP BY m.movie_id
            ORDER BY m.rating DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(movie_query, (year, per_page, offset))
        movies = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            'index.html',
            movies=movies,
            page=page,
            total_pages=total_pages,
            search='',
            genre_name=None,
            base_url=f"/year/{year}"
        )
    except Exception as e:
        return f"Database error: {e}"



if __name__ == '__main__':
    app.run(debug=True)
