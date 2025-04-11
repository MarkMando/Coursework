from flask import Flask, request, jsonify
import requests
import math
import re
from collections import defaultdict, Counter

app = Flask(__name__)

# Replace with actual URLs of your subsystems
SUBSYSTEMS = [
    #"http://localhost:5001/api",  # Subsystem 1
    "http://localhost/subsystem1/api"   # Subsystem 2
]

# ---------------------------
# Inverted Index Data Stores
# ---------------------------

# Stores: term → set of doc_ids where term appears
inverted_index = defaultdict(set)

# Stores full tokenized content and metadata for each doc_id
doc_contents = {}

# Stores document frequency: term → number of documents containing the term
doc_freqs = defaultdict(int)

# Stores document length: doc_id → total number of tokens
doc_lengths = {}

total_docs = 0

def tokenize(text):
    return re.findall(r'\b\w+\b', text.lower())

# -------------------------------
# Build Inverted Index from APIs
# -------------------------------
def fetch_all_documents():
    global total_docs
    total_docs = 0
    inverted_index.clear()
    doc_contents.clear()
    doc_freqs.clear()
    doc_lengths.clear()

    for base_url in SUBSYSTEMS:
        docs = requests.get(f"{base_url}/documents").json()
        for doc in docs:
            doc_id = f"{base_url}_{doc['doc_id']}"  # Unique doc ID
            content_url = f"{base_url}/documents/{doc['doc_id']}/content"
            content = requests.get(content_url).json().get("text_content", "")
            tokens = tokenize(content)

            # Store tokens and metadata
            doc_contents[doc_id] = {
                "metadata": doc,
                "tokens": tokens
            }

            # Update inverted index and term stats
            tf = Counter(tokens)
            doc_lengths[doc_id] = len(tokens)
            for term in tf:
                inverted_index[term].add(doc_id)     # Add doc to posting list
                doc_freqs[term] += 1                  # Increment doc frequency

            total_docs += 1

# ----------------------
# Search + TF-IDF Scoring
# ----------------------
def compute_tfidf_score(query_tokens):
    scores = defaultdict(float)
    for term in query_tokens:
        if term not in inverted_index:
            continue

        # Inverse Document Frequency
        idf = math.log((1 + total_docs) / (1 + doc_freqs[term])) + 1

        # Term Frequency * IDF for each doc containing the term
        for doc_id in inverted_index[term]:
            tf = doc_contents[doc_id]["tokens"].count(term)
            tf_weight = tf / doc_lengths[doc_id]
            scores[doc_id] += tf_weight * idf
    return scores

# ------------------------
# API Endpoints
# ------------------------

@app.route("/api/rebuild-index", methods=["POST"])
def rebuild_index():
    fetch_all_documents()
    return jsonify({"msg": "Index rebuilt", "total_documents": total_docs})

@app.route("/api/search", methods=["GET"])
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"msg": "Missing query"}), 400

    if not doc_contents:
        fetch_all_documents()

    query_tokens = tokenize(query)
    scores = compute_tfidf_score(query_tokens)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for doc_id, score in ranked[:10]:
        base_doc = doc_contents[doc_id]
        results.append({
            "doc_id": doc_id,
            "title": base_doc["metadata"]["title"],
            "author": base_doc["metadata"]["author"],
            "score": round(score, 4)
        })

    return jsonify(results)

# Optional: debug endpoint to inspect the inverted index
@app.route("/api/index", methods=["GET"])
def show_inverted_index():
    return jsonify({term: list(doc_ids) for term, doc_ids in inverted_index.items()})

if __name__ == "__main__":
    from flask import render_template_string
    @app.route("/")
    def search_ui():
       return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Subsystem 3 Search</title>
        <link href="/static/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {
                background-color: #f8f9fa;
                padding-top: 5%;
            }
            .search-box {
                max-width: 600px;
                margin: auto;
            }
            .result-card {
                margin-bottom: 1rem;
            }
        </style>
    </head>
    <body>
        <div class="container text-center">
            <h1 class="mb-4">Subsystem 3</h1>
            <div class="search-box bg-white p-4 shadow rounded">
                <h4 class="mb-3">Search Documents</h4>
                <div class="input-group mb-3">
                    <input type="text" id="query" class="form-control form-control-lg" placeholder="Enter search terms" required>
                    <button class="btn btn-primary btn-lg" onclick="search()">Search</button>
                </div>
            </div>

            <div id="results" class="mt-5 text-start" style="max-width: 700px; margin: auto;"></div>
        </div>

        <script>
            async function search() {
                const q = document.getElementById("query").value.trim();
                const resultsDiv = document.getElementById("results");
                resultsDiv.innerHTML = "<div class='text-center'>Searching...</div>";
                if(q.length > 0)
                {
                    try {
                    const response = await fetch(`/api/search?q=` + encodeURIComponent(q));
                    const data = await response.json();

                    if (!Array.isArray(data)) {
                        resultsDiv.innerHTML = "<div class='alert alert-danger'>Error: " + (data.message || "Something went wrong.") + "</div>";
                        return;
                    }

                    if (data.length === 0) {
                        resultsDiv.innerHTML = "<div class='alert alert-warning'>No results found.</div>";
                        return;
                    }

                    resultsDiv.innerHTML = "";
                    data.forEach(item => {
                        const metadata = item.metadata || {};
                        const downloadLink = metadata.file_path ? `<a href="${metadata.file_path}" download class="btn btn-sm btn-outline-secondary">Download</a>` : "";
                        resultsDiv.innerHTML += `
                            <div class="card result-card shadow-sm">
                                <div class="card-body">
                                    <h5>${item.title}</h5>
                                    <p><strong>Author:</strong> ${item.author || "Unknown"}</p>
                                    <p><strong>Score:</strong> ${item.score}</p>
                                    ${metadata.filename ? `<p><strong>Filename:</strong> ${metadata.filename}</p>` : ""}
                                    ${metadata.upload_date ? `<p><strong>Uploaded:</strong> ${metadata.upload_date}</p>` : ""}
                                    ${downloadLink}
                                </div>
                            </div>
                        `;
                    });
                } catch (err) {
                    resultsDiv.innerHTML = "<div class='alert alert-danger'>Error fetching results.</div>";
                }
                }
                else
                {
                    resultsDiv.innerHTML = "<div class='alert alert-warning'>Enter some key word or phrase to search for.</div>";
                }  
            }
        </script>
    </body>
    </html>
    """)

    app.run(port=5002, debug=True)
