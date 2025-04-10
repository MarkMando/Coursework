from flask import Flask, request, jsonify
import requests
import math
import re
from collections import defaultdict, Counter

app = Flask(__name__)

# Replace with actual URLs of your subsystems
SUBSYSTEMS = [
    "http://localhost:5001/api",  # Subsystem 1
    "http://localhost:5000/api"   # Subsystem 2
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
    app.run(port=5002, debug=True)
