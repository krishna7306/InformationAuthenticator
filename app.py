"""
Information Authenticator - Flask Backend
Verifies claims by searching academic papers via Semantic Scholar and CrossRef APIs
"""

from flask import Flask, request, jsonify, render_template, session
import requests
import sqlite3
from datetime import datetime
import os
import re
from collections import Counter
import secrets

import google.generativeai as genai

# IMPORTANT: Replace with your actual API key
GEMINI_API_KEY = "AIzaSyDJR-qgZh06RCuxcphxrDbXFhQWl-c5onI"
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)

# Session configuration for chatbot
app.secret_key = secrets.token_hex(16)
app.config['SESSION_TYPE'] = 'filesystem'

# =============================================================================
# DATABASE SETUP
# =============================================================================

DB_NAME = 'queries.db'

def init_database():
    """Initialize SQLite database and create queries table if it doesn't exist"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_text TEXT NOT NULL,
            result_count INTEGER NOT NULL,
            confidence_level TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✓ Database '{DB_NAME}' initialized successfully")

def save_query_to_db(query_text, result_count, confidence_level):
    """Save a search query and its results to the database"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO queries (query_text, result_count, confidence_level, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (query_text, result_count, confidence_level, datetime.now()))
        
        conn.commit()
        conn.close()
        print(f"✓ Saved query to database: '{query_text}' ({result_count} results)")
    except Exception as e:
        print(f"✗ Database error: {e}")

# =============================================================================
# CONFIDENCE CALCULATION
# =============================================================================

def calculate_confidence(result_count):
    """
    Calculate confidence level based on number of results found
    
    Rules:
    - 0 results: Not supported
    - 1-3 results: Weak Evidence
    - 4-9 results: Moderate Evidence
    - 10+ results: Strong Evidence
    """
    if result_count == 0:
        return "Not supported"
    elif 1 <= result_count <= 3:
        return "Weak Evidence"
    elif 4 <= result_count <= 9:
        return "Moderate Evidence"
    else:  # 10 or more
        return "Strong Evidence"

# =============================================================================
# API CALLS - SEMANTIC SCHOLAR
# =============================================================================

def search_semantic_scholar(query, limit=10):
    """
    Search for papers using Semantic Scholar API
    Returns list of papers with title, url, year, and abstract
    """
    try:
        api_url = "https://api.semanticscholar.org/graph/v1/paper/search"
        
        params = {
            'query': query,
            'limit': limit,
            'fields': 'title,url,year,abstract,paperId'
        }
        
        headers = {
            'User-Agent': 'Information-Authenticator/1.0'
        }
        
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            papers = []
            
            if 'data' in data:
                for paper in data['data']:
                    papers.append({
                        'title': paper.get('title', 'No title available'),
                        'url': paper.get('url', f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}"),
                        'year': paper.get('year', 'N/A'),
                        'abstract': paper.get('abstract', 'No abstract available')[:500]  # Limit abstract length
                    })
            
            print(f"✓ Semantic Scholar: Found {len(papers)} papers")
            return papers
        else:
            print(f"✗ Semantic Scholar API error: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"✗ Semantic Scholar error: {e}")
        return []

# =============================================================================
# API CALLS - CROSSREF (OPTIONAL BACKUP)
# =============================================================================

def search_crossref(query, limit=5):
    """
    Search for papers using CrossRef API as backup source
    Returns list of papers with title, url, year, and abstract
    """
    try:
        api_url = "https://api.crossref.org/works"
        
        params = {
            'query': query,
            'rows': limit,
            'select': 'title,DOI,published,abstract'
        }
        
        headers = {
            'User-Agent': 'Information-Authenticator/1.0 (mailto:user@example.com)'
        }
        
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            papers = []
            
            if 'message' in data and 'items' in data['message']:
                for item in data['message']['items']:
                    # Extract year from published date
                    year = 'N/A'
                    if 'published' in item and 'date-parts' in item['published']:
                        year = item['published']['date-parts'][0][0]
                    
                    papers.append({
                        'title': item.get('title', ['No title available'])[0],
                        'url': f"https://doi.org/{item.get('DOI', '')}",
                        'year': year,
                        'abstract': item.get('abstract', 'No abstract available')[:500]
                    })
            
            print(f"✓ CrossRef: Found {len(papers)} papers")
            return papers
        else:
            print(f"✗ CrossRef API error: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"✗ CrossRef error: {e}")
        return []

# =============================================================================
# GEMINI AI SUMMARY GENERATION
# =============================================================================

def generate_summary(papers):
    """
    Generate AI-powered summary using Google Gemini
    
    Args:
        papers: List of paper dictionaries with 'title' and 'abstract' fields
    
    Returns:
        String containing the AI-generated summary
    """
    print("\n✅ Gemini summary function called")

    if not papers:
        print("⚠️ No papers → skipping Gemini")
        return "No papers available to summarize."

    # Combine paper titles and abstracts
    content = ""
    for p in papers:
        title = p.get('title', 'No title')
        abstract = p.get('abstract', 'No abstract')
        content += f"Title: {title}\nAbstract: {abstract}\n\n"

    # Create prompt for Gemini
    prompt = f"""
    Summarize the following academic research papers into a clear,
    concise 5-7 line explanation suitable for a general audience:

    {content}

    Provide a coherent summary that highlights the main findings and consensus.
    """

    try:
        print("✅ Creating Gemini model…")
        model = genai.GenerativeModel("models/gemini-2.5-flash")


        print("✅ Sending request to Gemini…")
        response = model.generate_content(prompt)

        summary = response.text.strip()
        print(f"✅ Gemini summary generated ({len(summary)} characters)")
        return summary

    except Exception as e:
        print("\n🔥 GEMINI ERROR 🔥")
        print(f"Error: {e}")
        print("🔥 END ERROR 🔥\n")
        return "AI summary unavailable due to Gemini API error."

# =============================================================================
# MAIN VERIFICATION LOGIC
# =============================================================================

def verify_information(query, limit=20):
    """
    Main function to verify information by searching multiple academic sources
    Combines results from Semantic Scholar and CrossRef
    
    Args:
        query: The search query string
        limit: Maximum number of papers to return
    """
    print(f"\n📝 Processing query: '{query}' (limit: {limit} papers)")
    
    # Calculate how to split the limit between APIs
    # Prioritize Semantic Scholar (70%) and CrossRef (30%)
    semantic_limit = int(limit * 0.7)
    crossref_limit = limit - semantic_limit
    
    # Search both APIs
    semantic_papers = search_semantic_scholar(query, limit=semantic_limit)
    crossref_papers = search_crossref(query, limit=crossref_limit)
    
    # Combine results (prioritize Semantic Scholar, add unique CrossRef results)
    all_papers = semantic_papers.copy()
    
    # Add CrossRef papers that aren't duplicates (basic title matching)
    existing_titles = {p['title'].lower() for p in all_papers}
    for paper in crossref_papers:
        if paper['title'].lower() not in existing_titles:
            all_papers.append(paper)
    
    # Limit to requested number of results
    all_papers = all_papers[:limit]
    
    # Calculate confidence
    result_count = len(all_papers)
    confidence = calculate_confidence(result_count)
    
    print(f"📊 Total results: {result_count} | Confidence: {confidence}")
    
    # Save to database
    save_query_to_db(query, result_count, confidence)
    
    # Generate AI summary using Gemini
    summary = generate_summary(all_papers)
    
    # Prepare response
    if result_count > 0:
        return {
            'found': True,
            'confidence': confidence,
            'result_count': result_count,
            'summary': summary,
            'results': all_papers
        }
    else:
        return {
            'found': False,
            'confidence': confidence,
            'result_count': 0,
            'summary': "No research papers found to generate a summary.",
            'results': []
        }

# =============================================================================
# FLASK ROUTES
# =============================================================================

@app.route('/')
def index():
    """Serve the frontend HTML page"""
    return render_template('index.html')

@app.route('/verify', methods=['POST'])
def verify():
    """
    Main endpoint to verify information
    Expects: POST with form data containing 'statement' field
    Returns: JSON with verification results
    """
    try:
        # Get query from form data
        query = request.form.get('statement', '').strip()
        
        # Set fixed limit to fetch maximum available papers
        limit = 20
        
        if not query:
            return jsonify({
                'error': 'No query provided',
                'found': False
            }), 400
        
        print(f"\n🔍 Received verification request:")
        print(f"   Query: {query}")
        print(f"   Fetching up to {limit} papers")
        
        # Perform verification with fixed limit
        result = verify_information(query, limit)
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"✗ Error in /verify endpoint: {e}")
        return jsonify({
            'error': 'Internal server error',
            'found': False
        }), 500

# =============================================================================
# CHATBOT ROUTES
# =============================================================================

@app.route('/chatbot', methods=['POST'])
def chatbot():
    """
    Chatbot endpoint using Google Gemini AI
    Maintains conversation history in Flask session
    
    Expects: JSON with 'message' field
    Returns: JSON with 'reply' field
    """
    try:
        # Get user message from request
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({
                'error': 'No message provided',
                'reply': 'Please enter a message.'
            }), 400
        
        # Initialize chat history in session if not exists
        if 'chat_history' not in session:
            session['chat_history'] = []
        
        # Get chat history
        chat_history = session['chat_history']
        
        # Build conversation prompt with history
        conversation_prompt = "You are a helpful AI assistant for an Information Authenticator app that verifies claims using academic research. Be concise, friendly, and informative.\n\n"
        
        # Add previous conversation context (last 10 messages)
        for entry in chat_history[-10:]:
            conversation_prompt += f"User: {entry['user']}\nAssistant: {entry['assistant']}\n\n"
        
        # Add current message
        conversation_prompt += f"User: {user_message}\nAssistant:"
        
        print(f"\n💬 Chatbot request: '{user_message}'")
        
        # Call Gemini AI
        model = genai.GenerativeModel("models/gemini-2.5-flash")

        response = model.generate_content(conversation_prompt)
        bot_reply = response.text.strip()
        
        print(f"🤖 Chatbot response: '{bot_reply[:100]}...'")
        
        # Save to chat history
        chat_history.append({
            'user': user_message,
            'assistant': bot_reply
        })
        session['chat_history'] = chat_history
        session.modified = True
        
        return jsonify({
            'reply': bot_reply
        }), 200
        
    except Exception as e:
        print(f"✗ Chatbot error: {e}")
        return jsonify({
            'error': 'Failed to generate response',
            'reply': 'Sorry, I encountered an error. Please try again.'
        }), 500

@app.route('/chatbot/clear', methods=['POST'])
def clear_chat():
    """Clear chat history for current session"""
    session['chat_history'] = []
    session.modified = True
    return jsonify({'status': 'Chat history cleared'}), 200

@app.route('/stats', methods=['GET'])
def stats():
    """
    Optional endpoint to view database statistics
    Returns recent queries and overall statistics
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Get total queries
        cursor.execute('SELECT COUNT(*) FROM queries')
        total_queries = cursor.fetchone()[0]
        
        # Get recent queries
        cursor.execute('''
            SELECT query_text, result_count, confidence_level, timestamp 
            FROM queries 
            ORDER BY timestamp DESC 
            LIMIT 10
        ''')
        recent_queries = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'total_queries': total_queries,
            'recent_queries': [
                {
                    'query': q[0],
                    'results': q[1],
                    'confidence': q[2],
                    'timestamp': q[3]
                } for q in recent_queries
            ]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# =============================================================================
# APPLICATION STARTUP
# =============================================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🔍 INFORMATION AUTHENTICATOR - Backend Server")
    print("="*60)
    
    # Initialize database
    init_database()
    
    print("\n🚀 Starting Flask server...")
    print("📍 Access the app at: http://127.0.0.1:5000")
    print("📊 View stats at: http://127.0.0.1:5000/stats")
    print("💬 Chatbot integrated")
    print("\nPress CTRL+C to stop the server\n")
    
    # Run Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)