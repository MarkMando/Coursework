from flask import Flask, request, jsonify, render_template_string
import requests
import math
import re
from collections import defaultdict, Counter

app = Flask(__name__)

# Replace with actual URLs of your subsystems
SUBSYSTEMS = [
    "http://localhost/subsystem1/api"
]

# ---------------------------
# Inverted Index Data Stores
# ---------------------------

inverted_index = defaultdict(set)
doc_contents = {}
doc_freqs = defaultdict(int)
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
            doc_id = f"{base_url}_{doc['doc_id']}"
            content_url = f"{base_url}/documents/{doc['doc_id']}/content"
            content = requests.get(content_url).json().get("text_content", "")
            tokens = tokenize(content)

            doc_contents[doc_id] = {
                "metadata": doc,
                "tokens": tokens
            }

            tf = Counter(tokens)
            doc_lengths[doc_id] = len(tokens)
            for term in tf:
                inverted_index[term].add(doc_id)
                doc_freqs[term] += 1

            total_docs += 1

# ----------------------
# Search + TF-IDF Scoring with Partial Match
# ----------------------
@app.route("/api/search", methods=["GET"])
def search():
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"msg": "Missing query"}), 400

    if not doc_contents:
        fetch_all_documents()

    query_tokens = tokenize(query)
    scores = defaultdict(float)

    for doc_id, base_doc in doc_contents.items():
        metadata = base_doc["metadata"]
        content_tokens = base_doc["tokens"]
        content_text = " ".join(content_tokens)
        title = metadata.get("title", "").lower()
        author = metadata.get("author", "").lower()

        if (query in title or query in author or query in content_text):
            tfidf_score = sum([
                (content_tokens.count(term) / doc_lengths[doc_id]) *
                (math.log((1 + total_docs) / (1 + doc_freqs.get(term, 0))) + 1)
                for term in query_tokens
            ])
            scores[doc_id] = tfidf_score + 1

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]

    results = []
    for doc_id, score in ranked:
        base_doc = doc_contents[doc_id]
        metadata = base_doc["metadata"]
        results.append({
            "doc_id": doc_id,
            "title": metadata.get("title", "Untitled"),
            "author": metadata.get("author", "Unknown"),
            "score": round(score, 4),
            "metadata": {
                "filename": metadata.get("filename"),
                "upload_date": metadata.get("upload_date"),
                "file_path": metadata.get("file_path")
            }
        })

    return jsonify(results)

@app.route("/api/rebuild-index", methods=["POST"])
def rebuild_index():
    fetch_all_documents()
    return jsonify({"msg": "Index rebuilt", "total_documents": total_docs})

@app.route("/api/index", methods=["GET"])
def show_inverted_index():
    return jsonify({term: list(doc_ids) for term, doc_ids in inverted_index.items()})

@app.route("/")
def search_ui():
    return render_template_string("""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <title>Subsystem 3 Search</title>
    <link href=\"/static/css/bootstrap.min.css\" rel=\"stylesheet\">
    <style>
        body { background-color: #f8f9fa; padding-top: 5%; }
        .search-box { max-width: 600px; margin: auto; }
        .result-card { margin-bottom: 1rem; }
    </style>
</head>
<body>
<div class=\"container text-center\">
    <h1 class=\"mb-4\">Subsystem 3</h1>
    <div class=\"search-box bg-white p-4 shadow rounded\">
        <h4 class=\"mb-3\">Search Documents</h4>
        <div class=\"input-group mb-3\">
            <input type=\"text\" id=\"query\" class=\"form-control form-control-lg\" placeholder=\"Enter search terms\" required>
            <button class=\"btn btn-primary btn-lg\" onclick=\"search()\">Search</button>
        </div>
    </div>
    <div id=\"results\" class=\"mt-5 text-start\" style=\"max-width: 700px; margin: auto;\"></div>
</div>
<script>
async function search() {
    const q = document.getElementById(\"query\").value.trim();
    const resultsDiv = document.getElementById(\"results\");
    resultsDiv.innerHTML = \"<div class='text-center'>Searching...</div>\";
    if (q.length > 0) {
        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
            const data = await response.json();

            if (!Array.isArray(data)) {
                resultsDiv.innerHTML = `<div class='alert alert-danger'>Error: ${data.message || 'Something went wrong.'}</div>`;
                return;
            }

            if (data.length === 0) {
                resultsDiv.innerHTML = \"<div class='alert alert-warning'>No results found.</div>\";
                return;
            }

            resultsDiv.innerHTML = "";
            data.forEach(item => {
                resultsDiv.innerHTML += `
                    <div class='card result-card shadow-sm'>
                        <div class='card-body'>
                            <h5>${item.title}</h5>
                            <p><strong>Author:</strong> ${item.author || "Unknown"}</p>
                            <p><strong>Score:</strong> ${item.score}</p>
                            ${item.metadata.filename ? `<p><strong>Filename:</strong> ${item.metadata.filename}</p>` : ""}
                            ${item.metadata.upload_date ? `<p><strong>Uploaded:</strong> ${item.metadata.upload_date}</p>` : ""}
                        </div>
                    </div>
                `;
            });
        } catch (err) {
            resultsDiv.innerHTML = \"<div class='alert alert-danger'>Error fetching results.</div>\";
        }
    } else {
        resultsDiv.innerHTML = \"<div class='alert alert-warning'>Enter some keyword or phrase to search for.</div>\";
    }
}
</script>
</body>
</html>
""")

if __name__ == "__main__":
    app.run(port=5002, debug=True)
