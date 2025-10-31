from flask import Flask, render_template, request, jsonify
import requests
import mysql.connector
import math
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import random
from email.utils import formataddr
from datetime import datetime

# --- Load Secrets ---
secrets = {}
with open("dont.txt", "r") as file:
    for line in file:
        line = line.strip()
        if line and "=" in line:
            key, value = line.split("=", 1)
            secrets[key] = value

API_KEY = secrets.get("API_KEY")
MYSQL_PASSWORD = secrets.get("PASSWORD")
EMAIL_USER = secrets.get("EMAIL_USER")
EMAIL_PASS = secrets.get("EMAIL_PASS")

app = Flask(__name__)

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': MYSQL_PASSWORD,
    'database': 'movie_db'
}


def get_db_connection():
    return mysql.connector.connect(**db_config)


# --- Home / Search Route ---
@app.route("/")
def index():
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if search:
        # --- Search movies by title, actor, or director ---
        query = f"""
            SELECT DISTINCT m.movie_id, m.title, m.year, m.rating, m.description,
                            m.poster_url, m.language,
                            d.name AS director_name,
                            GROUP_CONCAT(DISTINCT g.name SEPARATOR ', ') AS genres,
                            GROUP_CONCAT(DISTINCT a.name SEPARATOR ', ') AS actors
            FROM movies m
            LEFT JOIN directors d ON m.director_id = d.director_id
            LEFT JOIN movie_genres mg ON m.movie_id = mg.movie_id
            LEFT JOIN genres g ON mg.genre_id = g.genre_id
            LEFT JOIN movie_actors ma ON m.movie_id = ma.movie_id
            LEFT JOIN actors a ON ma.actor_id = a.actor_id
            WHERE m.title LIKE %s OR d.name LIKE %s OR a.name LIKE %s
            GROUP BY m.movie_id
            ORDER BY m.rating DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(query, (f"%{search}%", f"%{search}%", f"%{search}%", per_page, offset))
        movies = cursor.fetchall()

        # --- Get total count for pagination ---
        count_query = """
            SELECT COUNT(DISTINCT m.movie_id) AS total
            FROM movies m
            LEFT JOIN directors d ON m.director_id = d.director_id
            LEFT JOIN movie_actors ma ON m.movie_id = ma.movie_id
            LEFT JOIN actors a ON ma.actor_id = a.actor_id
            WHERE m.title LIKE %s OR d.name LIKE %s OR a.name LIKE %s
        """
        cursor.execute(count_query, (f"%{search}%", f"%{search}%", f"%{search}%"))
        total_movies = cursor.fetchone()["total"]
    else:
        # --- Default: show all movies ---
        cursor.execute(f"""
            SELECT m.movie_id, m.title, m.year, m.rating, m.description,
                   m.poster_url, m.language,
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
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        movies = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) AS total FROM movies")
        total_movies = cursor.fetchone()["total"]

    total_pages = math.ceil(total_movies / per_page)

    cursor.close()
    conn.close()

    return render_template(
        "index.html",
        movies=movies,
        page=page,
        total_pages=total_pages,
        search=search,
        genre_name=None,
        base_url="/",
        not_found=(search != "" and len(movies) == 0)
    )



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

# --- Fetch Movie from TMDB ---
@app.route("/fetch_movie")
def fetch_movie():
    title = request.args.get("title", "").strip()
    if not title:
        return "No title provided."

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # --- Check if movie already exists ---
    cursor.execute("SELECT * FROM movies WHERE title LIKE %s", (title,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return f"<script>alert('Movie already exists in database!');window.location='/?q={title}';</script>"

    # --- Search movie in TMDB ---
    search_url = f"https://api.themoviedb.org/3/search/movie?api_key={API_KEY}&query={title}&language=en-US"
    res = requests.get(search_url).json()
    results = res.get("results", [])
    if not results:
        return f"<script>alert('❌ This movie does not exist in TMDB.');window.location='/';</script>"

    movie_data = results[0]
    tmdb_id = movie_data["id"]

    # --- Fetch detailed movie info ---
    details_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={API_KEY}&language=en-US"
    credits_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits?api_key={API_KEY}"
    details = requests.get(details_url).json()
    credits = requests.get(credits_url).json()

    # --- Insert director ---
    director_id = None
    for crew in credits.get("crew", []):
        if crew.get("job") == "Director":
            dname = crew.get("name")
            cursor.execute("SELECT director_id FROM directors WHERE name=%s", (dname,))
            d = cursor.fetchone()
            if d:
                director_id = d["director_id"]
            else:
                cursor.execute("INSERT INTO directors (name) VALUES (%s)", (dname,))
                director_id = cursor.lastrowid
            break

    # --- Insert movie ---
    cursor.execute("""
        INSERT INTO movies (tmdb_id, title, year, rating, description, poster_url, runtime, director_id, language)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        tmdb_id,
        details.get("title"),
        int(details.get("release_date", "0")[:4]) if details.get("release_date") else None,
        details.get("vote_average", 0.0),
        details.get("overview", ""),
        f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}" if details.get("poster_path") else None,
        details.get("runtime"),
        director_id,
        details.get("original_language")
    ))
    movie_id = cursor.lastrowid

    # --- Insert genres ---
    for g in details.get("genres", []):
        cursor.execute("SELECT genre_id FROM genres WHERE name=%s", (g["name"],))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO genres (name) VALUES (%s)", (g["name"],))
            genre_id = cursor.lastrowid
        else:
            genre_id = row["genre_id"]
        cursor.execute("INSERT IGNORE INTO movie_genres (movie_id, genre_id) VALUES (%s, %s)", (movie_id, genre_id))

    # --- Insert top 5 actors ---
    for actor in credits.get("cast", [])[:5]:
        aname = actor["name"]
        cursor.execute("SELECT actor_id FROM actors WHERE name=%s", (aname,))
        a = cursor.fetchone()
        if a:
            actor_id = a["actor_id"]
        else:
            cursor.execute("INSERT INTO actors (name) VALUES (%s)", (aname,))
            actor_id = cursor.lastrowid
        cursor.execute("INSERT IGNORE INTO movie_actors (movie_id, actor_id, role) VALUES (%s, %s, %s)",
                       (movie_id, actor_id, actor.get("character")))

    conn.commit()
    cursor.close()
    conn.close()

    return f"<script>alert('✅ Movie fetched and added successfully!');window.location='/?q={title}';</script>"

@app.route("/send_mail", methods=["POST"])
def send_mail():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"message": "Email is required"}), 400

    # --- Fetch 10 random movies ---
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            m.title, 
            m.year, 
            m.language, 
            m.rating, 
            m.poster_url, 
            d.name AS director_name
        FROM movies m
        LEFT JOIN directors d ON m.director_id = d.director_id
        ORDER BY RAND()
        LIMIT 10
    """)
    movies = cursor.fetchall()
    cursor.close()
    conn.close()

    # --- Compose HTML email ---
    html = """
    <div style="font-family:Arial, sans-serif; color:#333;">
        <h2 style="text-align:center; color:#007bff;">🎬 10 Random Movies from Our Database</h2>
        <table border="1" cellspacing="0" cellpadding="8" style="width:100%; border-collapse:collapse; margin-top:15px;">
            <thead style="background-color:#f4f4f4;">
                <tr>
                    <th>Poster</th>
                    <th>Title</th>
                    <th>Year</th>
                    <th>Language</th>
                    <th>Rating ⭐</th>
                    <th>Director</th>
                </tr>
            </thead>
            <tbody>
    """

    for m in movies:
        html += f"""
        <tr style="text-align:center;">
            <td>{'<img src="' + m['poster_url'] + '" width="80" style="border-radius:6px;">' if m['poster_url'] else '—'}</td>
            <td><strong>{m['title']}</strong></td>
            <td>{m['year'] or '—'}</td>
            <td>{m['language'].upper() if m['language'] else '—'}</td>
            <td>{m['rating']:.1f}</td>
            <td>{m['director_name'] or '—'}</td>
        </tr>
        """

    html += """
            </tbody>
        </table>
        <p style="margin-top:20px; text-align:center;">🍿 Enjoy your movie recommendations!<br>
        <small>Sent by Movie Database – Powered by Flask</small></p>
    </div>
    """

    # --- Email details ---
    sender_email = EMAIL_USER
    password = EMAIL_PASS
    sender_display = formataddr(("Movie Database 🎬", sender_email))  # 👈 Display name

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎬 10 Random Movies from Our Database – {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    msg["From"] = sender_display   # 👈 Use display name here
    msg["To"] = email
    msg.attach(MIMEText(html, "html"))

    # --- Send email ---
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_display, email, msg.as_string())
        return jsonify({"message": f"✅ Email sent successfully to {email}!"})

    except smtplib.SMTPAuthenticationError as e:
        print(f"[AUTH ERROR] {e}")
        return jsonify({
            "message": "❌ Authentication failed: Please check Gmail username or App Password."
        }), 500
    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({"message": f"❌ Failed to send email: {str(e)}"}), 500



if __name__ == '__main__':
    app.run(debug=True)
