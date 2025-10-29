from flask import Flask, render_template
import mysql.connector
import requests

# --- Load Secrets ---
secrets = {}
with open("dont.txt", "r") as file:
    for line in file:
        line = line.strip()  # remove newline
        if line and "=" in line:
            key, value = line.split("=", 1)
            secrets[key] = value

# Access your secrets
API_KEY = secrets.get("API_KEY")
MYSQL_PASSWORD = secrets.get("PASSWORD")

app = Flask(__name__)

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': MYSQL_PASSWORD,  
    'database': 'movie_db'
}

@app.route('/')
def index():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM movies")
        movies = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('index.html', movies=movies)
    except Exception as e:
        return f"Database error: {e}"


@app.route('/import-tmdb')
def import_tmdb():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        all_movies = []

        # Fetch 5 pages of top-rated movies (100 total)
        for page in range(1, 6):
            url = f"https://api.themoviedb.org/3/movie/top_rated?api_key={API_KEY}&language=en-US&page={page}"
            response = requests.get(url)
            data = response.json().get('results', [])
            all_movies.extend(data)

        for m in all_movies:
            title = m.get('title', 'Unknown')
            release_date = m.get('release_date', None)
            year = int(release_date.split('-')[0]) if release_date else None
            rating = m.get('vote_average', 0.0)
            description = m.get('overview', '')
            genre = 'Unknown'  # we'll improve this later

            cursor.execute("""
                INSERT INTO movies (title, year, genre, rating, description)
                VALUES (%s, %s, %s, %s, %s)
            """, (title, year, genre, rating, description))

        conn.commit()
        cursor.close()
        conn.close()

        return f"✅ Imported {len(all_movies)} movies successfully!"
    except Exception as e:
        return f"❌ Error importing movies: {e}"

if __name__ == '__main__':
    app.run(debug=True)