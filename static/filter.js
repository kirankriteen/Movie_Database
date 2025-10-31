document.addEventListener("DOMContentLoaded", () => {
    const applyBtn = document.getElementById("apply-filter");
    const resultsContainer = document.getElementById("filtered-results"); // back to original id

    const genreInput = document.getElementById("genre-input");
    const actorInput = document.getElementById("actor-input");
    const genreTags = document.getElementById("genre-tags");
    const actorTags = document.getElementById("actor-tags");

    let genres = [];
    let actors = [];

    // --- Tag creation function ---
    function createTag(name, type) {
        const tag = document.createElement("span");
        tag.classList.add("tag");
        tag.textContent = name;

        const x = document.createElement("button");
        x.textContent = "×";
        x.classList.add("remove-tag");
        x.onclick = () => {
            if (type === "genre") {
                genres = genres.filter(g => g !== name);
                genreTags.removeChild(tag);
            } else {
                actors = actors.filter(a => a !== name);
                actorTags.removeChild(tag);
            }
        };

        tag.appendChild(x);
        return tag;
    }

    // --- Add genre on Enter ---
    genreInput.addEventListener("keydown", e => {
        if (e.key === "Enter" && genreInput.value.trim()) {
            e.preventDefault();
            const value = genreInput.value.trim();
            if (!genres.includes(value)) {
                genres.push(value);
                genreTags.insertBefore(createTag(value, "genre"), genreInput);
            }
            genreInput.value = "";
        }
    });

    // --- Add actor on Enter ---
    actorInput.addEventListener("keydown", e => {
        if (e.key === "Enter" && actorInput.value.trim()) {
            e.preventDefault();
            const value = actorInput.value.trim();
            if (!actors.includes(value)) {
                actors.push(value);
                actorTags.insertBefore(createTag(value, "actor"), actorInput);
            }
            actorInput.value = "";
        }
    });

    const spinner = document.createElement("div");
    spinner.className = "spinner";
    spinner.style.display = "none";
    resultsContainer.parentElement.insertBefore(spinner, resultsContainer);

    function showSpinner() {
        spinner.style.display = "block";
        resultsContainer.style.display = "none";
    }

    function hideSpinner() {
        spinner.style.display = "none";
        resultsContainer.style.display = "block";
    }

    // --- Apply Filter ---
    applyBtn.onclick = async () => {
        const payload = {
            title: document.getElementById("filter-title").value,
            year: document.getElementById("filter-year").value,
            language: document.getElementById("filter-language").value,
            director: document.getElementById("filter-director").value,
            genres,
            actors
        };

        showSpinner();
        try {
            const res = await fetch("/filter_movies", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const movies = await res.json();
            hideSpinner();

            resultsContainer.innerHTML = "<h2>🎬 Filtered Results</h2>";

            if (!movies.length) {
                resultsContainer.innerHTML += "<p>No results found 😞</p>";
                return;
            }

            // Add “Add Selected” button
            const addBtn = document.createElement("button");
            addBtn.textContent = "➕ Add Selected Movies";
            addBtn.className = "add-selected-btn";
            addBtn.style.marginBottom = "10px";
            resultsContainer.appendChild(addBtn);

            const list = document.createElement("div");
            list.classList.add("movie-grid");

            movies.forEach((m, idx) => {
                const card = document.createElement("div");
                card.classList.add("movie-card");
                card.innerHTML = `
                    <label class="movie-item">
                        <input type="checkbox" class="movie-checkbox" data-title="${m.title}">
                        <img src="${m.poster || '/static/default.jpg'}" alt="Poster">
                        <div class="info">
                            <h3>${idx + 1}. ${m.title}</h3>
                            <p><b>Year:</b> ${m.year || '—'}</p>
                            <p><b>Lang:</b> ${m.language || '—'}</p>
                            <p><b>Rating:</b> ⭐ ${m.rating || '—'}</p>
                            <p><b>Director:</b> ${m.director || 'Unknown Director'}</p>
                            <p>${m.description || ''}</p>
                        </div>
                    </label>
                `;
                list.appendChild(card);
            });

            resultsContainer.appendChild(list);

            // --- Handle Add Selected ---
            addBtn.addEventListener("click", async () => {
                const selected = Array.from(document.querySelectorAll(".movie-checkbox:checked"))
                    .map(cb => cb.dataset.title);

                if (selected.length === 0) {
                    alert("Please select at least one movie!");
                    return;
                }

                for (const title of selected) {
                    const resp = await fetch(`/fetch_movie?title=${encodeURIComponent(title)}`);
                    const text = await resp.text();

                    if (text.includes("✅")) console.log(`${title} added successfully`);
                    else if (text.includes("already exists")) console.log(`${title} already exists`);
                    else console.log(`Error adding ${title}`);
                }

                alert("✅ Selected movies processed. Check your database page!");
            });
        } catch (err) {
            hideSpinner();
            console.error(err);
            resultsContainer.innerHTML = "<p style='color:red;'>⚠️ Error fetching results. Try again.</p>";
        }
    };
});
