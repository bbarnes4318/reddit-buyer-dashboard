import logging
import json
import os
import glob
import sys
import re
from datetime import datetime
from fastapi import FastAPI, Request, BackgroundTasks, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import threading
import requests
import time
import shutil
from sqlalchemy.orm import Session

from reddit_scraper import RedditScraper
from intent_detector import IntentDetector
from response_generator import ResponseGenerator
import config
from models import Base
from database import engine, get_db
from auth import get_current_active_user
import auth
import auth_routes
import account_routes
import models

# Is this App Engine?
is_app_engine = os.environ.get('GAE_ENV', '').startswith('standard')

# Create database tables
try:
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")
except Exception as e:
    print(f"Error creating database tables: {str(e)}")

# Configure logging for cloud environment
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # Use stdout for App Engine instead of file
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Reddit Buyer Intent Dashboard")

# Add session middleware with proper configuration
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"),
    session_cookie="session",
    max_age=86400 * 30,  # 30 days
    same_site="lax",
    https_only=True
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create templates directory - only if not on App Engine
if not is_app_engine:
    os.makedirs('templates', exist_ok=True)
    # Create static directory
    os.makedirs('static', exist_ok=True)
    # Copy logo to static directory if it exists
    if os.path.exists('logo.png') and not os.path.exists('static/logo.png'):
        shutil.copy('logo.png', 'static/logo.png')

# Mount static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates
templates = Jinja2Templates(
    directory="templates",
    autoescape=True,
    auto_reload=False,
    encoding='utf-8'
)

# Background task status
task_status = {
    "is_running": False,
    "last_run": None,
    "current_task": None,
    "results": None
}

# Cache for subreddit search results to reduce API calls
subreddit_cache = {
    "timestamp": 0,
    "popular": [],
    "search_results": {}
}

# Include the auth and account routers
app.include_router(auth_routes.router)
app.include_router(account_routes.router)

# Main dashboard route
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: models.User = Depends(get_current_active_user)):
    # Get user's Reddit accounts
    db = next(get_db())
    reddit_accounts = auth.get_reddit_accounts(db, current_user.id)
    
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "user": current_user,
            "reddit_accounts": reddit_accounts,
            "task_status": task_status
        }
    )

# Redirect root to login if not authenticated
@app.exception_handler(status.HTTP_401_UNAUTHORIZED)
async def unauthorized_handler(request, exc):
    return RedirectResponse(url="/auth/login")

# Redirect API/JSON routes to login with error message
@app.exception_handler(status.HTTP_403_FORBIDDEN)
async def forbidden_handler(request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authenticated"}
        )
    return RedirectResponse(url=f"/auth/login?error=Please+log+in+to+continue")

# Skip template creation in App Engine - templates should be included in the deployment
if not is_app_engine and not os.path.exists("templates/index.html"):
    # Note: We're using r""" to make sure no escape sequences are interpreted
    with open("templates/index.html", "w") as f:
        f.write(r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Buyer Intent Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css" rel="stylesheet" />
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f8f9fa;
        }
        h1, h2, h3 {
            color: #2c3e50;
        }
        .container {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
        }
        .card {
            background: #fff;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            padding: 20px;
            margin-bottom: 20px;
            flex: 1;
            min-width: 300px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
        }
        input, select {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        .select2-container {
            width: 100% !important;
        }
        button {
            background: #3498db;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background: #2980b9;
        }
        .status {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 4px;
            font-weight: 600;
            text-align: center;
        }
        .status-running {
            background: #2ecc71;
            color: white;
        }
        .status-idle {
            background: #ecf0f1;
            color: #7f8c8d;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
        .details-btn {
            background: #27ae60;
            padding: 5px 10px;
            font-size: 14px;
        }
        .message-text {
            white-space: pre-wrap;
            max-height: 150px;
            overflow-y: auto;
            padding: 10px;
            background: #f9f9f9;
            border-radius: 4px;
            border: 1px solid #eee;
            margin-top: 10px;
        }
        .intent-high {
            color: #e74c3c;
            font-weight: bold;
        }
        .intent-medium {
            color: #f39c12;
            font-weight: bold;
        }
        .intent-low {
            color: #3498db;
        }
        .refresh-status {
            margin-left: 10px;
            font-size: 14px;
            color: #7f8c8d;
        }
        #refresh-btn {
            background: #95a5a6;
            font-size: 14px;
            padding: 5px 10px;
        }
        .subreddit-badge {
            display: inline-block;
            background: #3498db;
            color: white;
            border-radius: 20px;
            padding: 5px 12px;
            margin: 5px;
            font-size: 14px;
            position: relative;
        }
        .subscribers {
            font-size: 12px;
            color: #7f8c8d;
            margin-left: 5px;
        }
        #keyword-search {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        #keyword-search input {
            flex-grow: 1;
        }
        #keyword-search button {
            flex-shrink: 0;
        }
        #subreddit-results {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
            margin-bottom: 20px;
        }
        .subreddit-card {
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 10px;
            width: calc(33.333% - 10px);
            background: #f9f9f9;
            position: relative;
        }
        .subreddit-card h4 {
            margin-top: 0;
            margin-bottom: 5px;
            font-size: 16px;
            color: #2c3e50;
        }
        .subreddit-card p {
            margin: 5px 0;
            font-size: 13px;
            color: #7f8c8d;
        }
        .subreddit-card .add-btn {
            background: #27ae60;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 12px;
            cursor: pointer;
            margin-top: 5px;
        }
        .subreddit-card .add-btn:hover {
            background: #219955;
        }
        .subreddit-card .add-btn.added {
            background: #95a5a6;
            cursor: default;
        }
        .remove-badge {
            background: #e74c3c;
            color: white;
            border: none;
            border-radius: 50%;
            width: 18px;
            height: 18px;
            font-size: 10px;
            line-height: 1;
            position: absolute;
            top: -5px;
            right: -5px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        #monitored-subreddits {
            display: flex;
            flex-wrap: wrap;
            margin-bottom: 20px;
            min-height: 40px;
            padding: 5px;
            border-radius: 4px;
            background-color: #f8f9fa;
            border: 1px dashed #ccc;
        }
        .empty-message {
            color: #95a5a6;
            font-style: italic;
            padding: 10px;
        }
        .pagination {
            display: flex;
            justify-content: center;
            margin-top: 15px;
            gap: 5px;
        }
        .pagination button {
            background: #f2f2f2;
            color: #333;
            border: 1px solid #ddd;
            padding: 5px 10px;
            border-radius: 4px;
        }
        .pagination button.active {
            background: #3498db;
            color: white;
            border-color: #3498db;
        }
        .pagination button:disabled {
            background: #f8f9fa;
            color: #ccc;
            border-color: #eee;
            cursor: not-allowed;
        }
        .navbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            margin-bottom: 20px;
            border-bottom: 1px solid #ddd;
        }
        .navbar h1 {
            margin: 0;
        }
        .nav-links {
            margin-right: 10px;
        }
        .nav-links a {
            margin-right: 15px;
            color: #3498db;
            text-decoration: none;
        }
        .nav-links a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="navbar">
        <h1>Reddit Buyer Intent Dashboard</h1>
        <div class="nav-links">
            <a href="/">Dashboard</a>
            <a href="/prompt-tester">Prompt Tester</a>
        </div>
    </div>
    
    <div class="card">
        <div class="section-header">
            <h2>Monitored Subreddits</h2>
            <button id="clear-all-btn">Clear All</button>
        </div>
        <div id="monitored-subreddits">
            <div class="empty-message">No subreddits added yet. Use the search below to find and add subreddits.</div>
        </div>
        
        <div class="section-header">
            <h2>Find Subreddits</h2>
        </div>
        <div id="keyword-search">
            <input type="text" id="keyword-input" placeholder="Enter keyword or subreddit name...">
            <button id="search-btn">Search</button>
        </div>
        <div id="subreddit-results"></div>
        <div class="pagination" id="pagination"></div>
    </div>
    
    <div class="container">
        <div class="card">
            <h2>Run Monitoring</h2>
            <form id="run-form">
                <div class="form-group">
                    <label for="min-intent">Minimum Intent Level:</label>
                    <select id="min-intent" name="min_intent">
                        <option value="HIGH">HIGH</option>
                        <option value="MEDIUM" selected>MEDIUM</option>
                        <option value="LOW">LOW</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="min-confidence">Minimum Confidence:</label>
                    <input type="number" id="min-confidence" name="min_confidence" min="0.1" max="1.0" step="0.1" value="0.6">
                </div>
                <div class="form-group">
                    <label for="limit">Posts per Subreddit:</label>
                    <input type="number" id="limit" name="limit" min="5" max="100" value="25">
                </div>
                <div class="form-group">
                    <label for="send-messages">
                        <input type="checkbox" id="send-messages" name="send_messages"> Send DMs to Users
                    </label>
                </div>
                <button type="submit" id="run-btn">Run Monitoring Cycle</button>
            </form>
        </div>
        
        <div class="card">
            <h2>System Status</h2>
            <p>Status: <span class="status" id="status-indicator"></span>
                <button id="refresh-btn">Refresh</button>
                <span id="refresh-status" class="refresh-status"></span>
            </p>
            <div id="current-task-info"></div>
            <div id="last-run-info"></div>
        </div>
    </div>
    
    <div class="card">
        <h2>Responses</h2>
        <div id="responses-container">
            <p>No responses available yet. Run a monitoring cycle to generate responses.</p>
        </div>
    </div>
    
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
        // Store selected subreddits
        let selectedSubreddits = [];
        let currentPage = 0;
        let currentKeyword = '';
        let hasMoreResults = false;
        
        // Initial load - get default subreddits
        $(document).ready(function() {
            loadDefaultSubreddits();
            updateMonitoredSubreddits();
            
            // Add event listeners
            $('#search-btn').on('click', searchSubreddits);
            $('#keyword-input').on('keypress', function(e) {
                if (e.which === 13) {
                    searchSubreddits();
                    e.preventDefault();
                }
            });
            $('#clear-all-btn').on('click', clearAllSubreddits);
        });
        
        // Function to load default subreddits from config
        function loadDefaultSubreddits() {
            fetch('/api/default-subreddits')
                .then(response => response.json())
                .then(data => {
                    selectedSubreddits = data.map(name => ({ name }));
                    updateMonitoredSubreddits();
                });
        }
        
        // Function to update the monitored subreddits display
        function updateMonitoredSubreddits() {
            const container = $('#monitored-subreddits');
            
            if (selectedSubreddits.length === 0) {
                container.html('<div class="empty-message">No subreddits added yet. Use the search below to find and add subreddits.</div>');
                return;
            }
            
            container.empty();
            selectedSubreddits.forEach(subreddit => {
                const badge = $('<div class="subreddit-badge"></div>')
                    .text('r/' + subreddit.name);
                
                const removeBtn = $('<button class="remove-badge">×</button>')
                    .on('click', function() {
                        removeSubreddit(subreddit.name);
                    });
                
                badge.append(removeBtn);
                container.append(badge);
            });
        }
        
        // Function to add a subreddit to the monitored list
        function addSubreddit(subreddit) {
            // Check if already added
            if (!selectedSubreddits.some(s => s.name === subreddit.name)) {
                selectedSubreddits.push(subreddit);
                updateMonitoredSubreddits();
                
                // Update button state in search results
                $('.add-btn[data-name="' + subreddit.name + '"]')
                    .addClass('added')
                    .text('Added')
                    .prop('disabled', true);
            }
        }
        
        // Function to remove a subreddit from the monitored list
        function removeSubreddit(name) {
            selectedSubreddits = selectedSubreddits.filter(s => s.name !== name);
            updateMonitoredSubreddits();
            
            // Update button state in search results if visible
            $('.add-btn[data-name="' + name + '"]')
                .removeClass('added')
                .text('Add')
                .prop('disabled', false);
        }
        
        // Function to clear all monitored subreddits
        function clearAllSubreddits() {
            if (confirm('Are you sure you want to clear all monitored subreddits?')) {
                selectedSubreddits = [];
                updateMonitoredSubreddits();
                
                // Update all buttons in search results
                $('.add-btn.added')
                    .removeClass('added')
                    .text('Add')
                    .prop('disabled', false);
            }
        }
        
        // Function to search for subreddits
        function searchSubreddits(page = 0) {
            const keyword = $('#keyword-input').val().trim();
            if (!keyword) return;
            
            currentKeyword = keyword;
            currentPage = page;
            
            // Show loading state
            $('#subreddit-results').html('<p>Searching for subreddits...</p>');
            $('#pagination').empty();
            
            fetch('/api/search-subreddits?query=' + encodeURIComponent(keyword) + '&page=' + page)
                .then(response => response.json())
                .then(data => {
                    displaySearchResults(data);
                })
                .catch(error => {
                    console.error('Error searching for subreddits:', error);
                    $('#subreddit-results').html('<p>Error searching for subreddits. Please try again.</p>');
                });
        }
        
        // Function to display search results
        function displaySearchResults(data) {
            const resultsContainer = $('#subreddit-results');
            resultsContainer.empty();
            
            // Extract results and pagination info
            const results = data.results || data;
            hasMoreResults = data.has_more !== undefined ? data.has_more : false;
            
            if (results.length === 0) {
                resultsContainer.html('<p>No subreddits found for your search term.</p>');
                return;
            }
            
            // Create a card for each subreddit
            results.forEach(subreddit => {
                const card = $('<div class="subreddit-card"></div>');
                
                const header = $('<h4></h4>').text('r/' + subreddit.name);
                
                const subscribers = $('<p></p>').text(
                    formatSubscribers(subreddit.subscribers) + ' subscribers'
                );
                
                const description = $('<p></p>').text(
                    subreddit.description || 'No description available'
                );
                
                const isAlreadyAdded = selectedSubreddits.some(s => s.name === subreddit.name);
                
                const addButton = $('<button class="add-btn"></button>')
                    .text(isAlreadyAdded ? 'Added' : 'Add')
                    .attr('data-name', subreddit.name)
                    .toggleClass('added', isAlreadyAdded)
                    .prop('disabled', isAlreadyAdded)
                    .on('click', function() {
                        addSubreddit({
                            name: subreddit.name,
                            subscribers: subreddit.subscribers,
                            description: subreddit.description
                        });
                    });
                
                card.append(header, subscribers, description, addButton);
                resultsContainer.append(card);
            });
            
            // Create pagination controls
            updatePagination();
        }
        
        // Function to update pagination controls
        function updatePagination() {
            const paginationContainer = $('#pagination');
            paginationContainer.empty();
            
            // Only show pagination if there are more results
            if (!hasMoreResults && currentPage === 0) return;
            
            // Previous button
            const prevBtn = $('<button>Previous</button>')
                .prop('disabled', currentPage === 0)
                .on('click', function() {
                    if (currentPage > 0) {
                        searchSubreddits(currentPage - 1);
                    }
                });
            
            // Current page indicator
            const pageIndicator = $('<span></span>').text(' Page ' + (currentPage + 1) + ' ');
            
            // Next button
            const nextBtn = $('<button>Next</button>')
                .prop('disabled', !hasMoreResults)
                .on('click', function() {
                    if (hasMoreResults) {
                        searchSubreddits(currentPage + 1);
                    }
                });
            
            paginationContainer.append(prevBtn, pageIndicator, nextBtn);
        }
        
        // Format subscriber count
        function formatSubscribers(count) {
            if (!count) return 'Unknown';
            
            if (count >= 1000000) {
                return (count / 1000000).toFixed(1) + 'M';
            } else if (count >= 1000) {
                return (count / 1000).toFixed(1) + 'K';
            }
            return count;
        }
        
        // Function to update status
        function updateStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    // Update status indicator
                    const statusIndicator = document.getElementById('status-indicator');
                    if (data.is_running) {
                        statusIndicator.textContent = 'RUNNING';
                        statusIndicator.className = 'status status-running';
                    } else {
                        statusIndicator.textContent = 'IDLE';
                        statusIndicator.className = 'status status-idle';
                    }
                    
                    // Update current task info
                    const currentTaskInfo = document.getElementById('current-task-info');
                    if (data.current_task) {
                        let subredditsText = 'Default';
                        if (data.current_task.subreddits && data.current_task.subreddits.length > 0) {
                            subredditsText = data.current_task.subreddits.map(s => `r/${s}`).join(', ');
                        }
                        
                        currentTaskInfo.innerHTML = `<h3>Current Task</h3>
                            <p>Subreddits: ${subredditsText}</p>
                            <p>Min Intent: ${data.current_task.min_intent}</p>
                            <p>Min Confidence: ${data.current_task.min_confidence}</p>
                            <p>Sending DMs: ${data.current_task.send_messages ? 'Yes' : 'No'}</p>`;
                    } else {
                        currentTaskInfo.innerHTML = '';
                    }
                    
                    // Update last run info
                    const lastRunInfo = document.getElementById('last-run-info');
                    if (data.last_run) {
                        lastRunInfo.innerHTML = `<h3>Last Run</h3>
                            <p>Time: ${new Date(data.last_run).toLocaleString()}</p>`;
                        
                        if (data.results) {
                            lastRunInfo.innerHTML += `
                                <p>Posts Scraped: ${data.results.posts_scraped}</p>
                                <p>High Intent Content: ${data.results.high_intent_content}</p>
                                <p>Responses Generated: ${data.results.responses_generated}</p>
                                <p>Messages Sent: ${data.results.messages_sent}</p>
                                <p>Duration: ${data.results.duration_seconds ? data.results.duration_seconds.toFixed(2) + 's' : 'N/A'}</p>`;
                        }
                    } else {
                        lastRunInfo.innerHTML = '<p>No monitoring runs yet</p>';
                    }
                    
                    document.getElementById('refresh-status').textContent = 'Last updated: ' + new Date().toLocaleTimeString();
                })
                .catch(error => {
                    console.error('Error fetching status:', error);
                    document.getElementById('refresh-status').textContent = 'Error refreshing data';
                });
        }
        
        // Function to load responses
        function loadResponses() {
            fetch('/api/responses')
                .then(response => response.json())
                .then(data => {
                    const responsesContainer = document.getElementById('responses-container');
                    
                    if (data.length === 0) {
                        responsesContainer.innerHTML = '<p>No responses available yet. Run a monitoring cycle to generate responses.</p>';
                        return;
                    }
                    
                    let html = '<table><thead><tr>' +
                        '<th>Author</th>' +
                        '<th>Intent</th>' +
                        '<th>Subject</th>' +
                        '<th>Action</th>' +
                        '</tr></thead><tbody>';
                    
                    data.forEach((response, index) => {
                        const intentClass = response.intent_category === 'HIGH' ? 'intent-high' : 
                                           response.intent_category === 'MEDIUM' ? 'intent-medium' : 'intent-low';
                        
                        html += `<tr>
                            <td>u/${response.author}</td>
                            <td class="${intentClass}">${response.intent_category}</td>
                            <td>${response.subject}</td>
                            <td>
                                <button class="details-btn" onclick="showMessageDetails(${index})">View Message</button>
                            </td>
                        </tr>
                        <tr id="message-row-${index}" style="display: none;">
                            <td colspan="4">
                                <div class="message-text">${response.message}</div>
                            </td>
                        </tr>`;
                    });
                    
                    html += '</tbody></table>';
                    responsesContainer.innerHTML = html;
                })
                .catch(error => {
                    console.error('Error fetching responses:', error);
                });
        }
        
        // Function to show message details
        function showMessageDetails(index) {
            const messageRow = document.getElementById(`message-row-${index}`);
            if (messageRow.style.display === 'none') {
                messageRow.style.display = 'table-row';
            } else {
                messageRow.style.display = 'none';
            }
        }
        
        // Add event listener for form submission
        document.getElementById('run-form').addEventListener('submit', function(e) {
            e.preventDefault();
            
            if (selectedSubreddits.length === 0) {
                alert('Please add at least one subreddit to monitor.');
                return;
            }
            
            const form = e.target;
            const subreddits = selectedSubreddits.map(s => s.name);
            const minIntent = form.min_intent.value;
            const minConfidence = parseFloat(form.min_confidence.value);
            const limit = parseInt(form.limit.value);
            const sendMessages = form.send_messages.checked;
            
            const data = {
                subreddits: subreddits,
                min_intent: minIntent,
                min_confidence: minConfidence,
                limit: limit,
                send_messages: sendMessages
            };
            
            fetch('/api/run', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(result => {
                alert('Monitoring task started!');
                updateStatus();
            })
            .catch(error => {
                console.error('Error starting monitoring:', error);
                alert('Error starting monitoring task');
            });
        });
        
        // Add event listener for refresh button
        document.getElementById('refresh-btn').addEventListener('click', function() {
            updateStatus();
            loadResponses();
        });
        
        // Initial load
        updateStatus();
        loadResponses();
        
        // Auto-refresh every 30 seconds
        setInterval(() => {
            updateStatus();
            loadResponses();
        }, 30000);
    </script>
</body>
</html>
    """)

@app.get("/api/default-subreddits")
async def get_default_subreddits():
    """Get the default list of subreddits from config."""
    return config.MONITORED_SUBREDDITS

@app.get("/api/search-subreddits")
async def search_subreddits(query: str = "", page: int = 0):
    """
    Search for subreddits using Reddit API.
    
    Args:
        query (str): Search query for subreddits
        page (int): Page number for pagination (0-based)
        
    Returns:
        dict: Dict containing list of subreddits and pagination info
    """
    global subreddit_cache
    
    # Maximum results per page
    results_per_page = 100
    
    # If no query, return popular subreddits
    if not query:
        # Check if we have cached popular subreddits that are still fresh (less than 1 hour old)
        current_time = time.time()
        if subreddit_cache["popular"] and current_time - subreddit_cache["timestamp"] < 3600:
            return subreddit_cache["popular"]
        
        try:
            popular_subreddits = []
            for subreddit in scraper.reddit.subreddits.popular(limit=100):
                popular_subreddits.append({
                    "name": subreddit.display_name,
                    "subscribers": subreddit.subscribers,
                    "description": subreddit.public_description[:100] + "..." if subreddit.public_description and len(subreddit.public_description) > 100 else subreddit.public_description
                })
            
            # Cache the results
            subreddit_cache["popular"] = popular_subreddits
            subreddit_cache["timestamp"] = current_time
            
            return popular_subreddits
        except Exception as e:
            logger.error(f"Error getting popular subreddits: {str(e)}")
            # Return default list if API call fails
            return [{"name": s, "subscribers": None, "description": ""} for s in config.MONITORED_SUBREDDITS]
    
    # Create cache key that includes the page
    cache_key = f"{query}_p{page}"
    
    # Check if we have this query cached
    if cache_key in subreddit_cache["search_results"]:
        return subreddit_cache["search_results"][cache_key]
    
    try:
        search_results = []
        
        # Calculate how many results to skip based on the page number
        skip_count = page * results_per_page
        
        # We need to request more results than we need to account for the skip
        fetch_limit = skip_count + results_per_page
        
        # Keep track of processed results to implement our own pagination
        processed_count = 0
        
        # Get subreddits with the search term in their name/description
        for subreddit in scraper.reddit.subreddits.search(query, limit=fetch_limit):
            # Skip results for previous pages
            if processed_count < skip_count:
                processed_count += 1
                continue
                
            search_results.append({
                "name": subreddit.display_name,
                "subscribers": subreddit.subscribers,
                "description": subreddit.public_description[:100] + "..." if subreddit.public_description and len(subreddit.public_description) > 100 else subreddit.public_description
            })
            
            # Stop if we've collected enough results for this page
            if len(search_results) >= results_per_page:
                break
        
        # Also search for exact matches in subreddit names (e.g., 'python' should find r/python)
        # This is only done for the first page to ensure the most relevant results appear first
        if page == 0 and query:
            try:
                exact_match = scraper.reddit.subreddit(query)
                # Check if this subreddit exists and isn't already in our results
                if hasattr(exact_match, 'display_name') and not any(r['name'] == exact_match.display_name for r in search_results):
                    # Insert at the beginning as it's likely the most relevant result
                    search_results.insert(0, {
                        "name": exact_match.display_name,
                        "subscribers": exact_match.subscribers,
                        "description": exact_match.public_description[:100] + "..." if exact_match.public_description and len(exact_match.public_description) > 100 else exact_match.public_description
                    })
            except:
                # Subreddit might not exist or be private
                pass
        
        # Add pagination metadata
        result = {
            "results": search_results,
            "has_more": len(search_results) == results_per_page,  # If we got the max results, there might be more
            "page": page
        }
        
        # Cache the results
        subreddit_cache["search_results"][cache_key] = result
        
        return result
    except Exception as e:
        logger.error(f"Error searching for subreddits: {str(e)}")
        return {"results": [], "has_more": False, "page": page}

@app.post("/api/run")
async def run_monitoring(data: dict, background_tasks: BackgroundTasks):
    """Start a monitoring task in the background."""
    if task_status["is_running"]:
        return JSONResponse(
            status_code=400,
            content={"error": "A monitoring task is already running"}
        )
    
    # Extract parameters
    subreddits = data.get("subreddits")
    min_intent = data.get("min_intent", "MEDIUM")
    min_confidence = data.get("min_confidence", 0.6)
    limit = data.get("limit")
    send_messages = data.get("send_messages", False)
    
    # Update task status
    task_status["is_running"] = True
    task_status["current_task"] = {
        "subreddits": subreddits,
        "min_intent": min_intent,
        "min_confidence": min_confidence,
        "limit": limit,
        "send_messages": send_messages
    }
    
    # Define the task function
    def run_task():
        try:
            # Run monitoring cycle
            results = {
                "posts_scraped": 0,
                "high_intent_content": 0,
                "responses_generated": 0,
                "messages_sent": 0,
                "duration_seconds": 0
            }
            
            start_time = time.time()
            
            # Scrape posts from subreddits
            for subreddit in subreddits:
                posts = scraper.get_subreddit_posts(subreddit, limit=limit)
                results["posts_scraped"] += len(posts)
                
                # Analyze each post
                for post in posts:
                    intent_analysis = intent_detector.analyze(post)
                    if intent_analysis["intent_category"] == min_intent and intent_analysis["confidence"] >= min_confidence:
                        results["high_intent_content"] += 1
                        if send_messages:
                            response = response_generator.generate_response(post, intent_analysis)
                            results["responses_generated"] += 1
                            # Send message logic here
                            results["messages_sent"] += 1
            
            results["duration_seconds"] = time.time() - start_time
            
            # Update task status when complete
            task_status["is_running"] = False
            task_status["last_run"] = datetime.now().isoformat()
            task_status["current_task"] = None
            task_status["results"] = results
            
        except Exception as e:
            logger.error(f"Error in background task: {str(e)}")
            task_status["is_running"] = False
            task_status["current_task"] = None
    
    # Start the task in a background thread
    thread = threading.Thread(target=run_task)
    thread.daemon = True
    thread.start()
    
    return {"status": "started"}

@app.get("/api/status")
async def get_status():
    """Get the current status of the monitoring task."""
    return task_status

@app.get("/api/responses")
async def get_responses():
    """Get the latest responses from the most recent monitoring cycle."""
    # Get the most recent responses file
    response_files = glob.glob("data/responses_*.json")
    response_files.sort(reverse=True)
    
    if not response_files:
        return []
    
    try:
        with open(response_files[0], "r") as f:
            responses = json.load(f)
        return responses
    except Exception as e:
        logger.error(f"Error loading responses: {str(e)}")
        return []

@app.get("/prompt-tester", response_class=HTMLResponse)
async def get_prompt_tester(request: Request):
    """Render the prompt testing page."""
    return templates.TemplateResponse("prompt_tester.html", {"request": request})

@app.post("/api/test-intent-prompt")
async def test_intent_prompt(data: dict):
    """
    Test a custom intent detection prompt with Gemini.
    
    Args:
        data (dict): Contains custom prompt template, sample content, and context
        
    Returns:
        dict: The analysis result from Gemini
    """
    try:
        # Initialize intent detector if needed
        if not hasattr(reddit_app, "intent_detector"):
            reddit_app.intent_detector = IntentDetector()
        
        # Extract data from request
        prompt_template = data.get("prompt_template", "")
        content = data.get("content", "")
        context = data.get("context", {})
        
        # Use the custom prompt to detect intent
        result = await test_custom_prompt(
            reddit_app.intent_detector,
            prompt_template,
            content,
            context,
            "intent"
        )
        
        return result
    except Exception as e:
        logger.error(f"Error testing intent prompt: {str(e)}")
        return {"error": str(e)}

@app.post("/api/test-response-prompt")
async def test_response_prompt(data: dict):
    """
    Test a custom response generation prompt with Gemini.
    
    Args:
        data (dict): Contains custom prompt template, sample content, and intent analysis
        
    Returns:
        dict: The generated response from Gemini
    """
    try:
        # Initialize response generator if needed
        if not hasattr(reddit_app, "response_generator"):
            reddit_app.response_generator = ResponseGenerator()
        
        # Extract data from request
        prompt_template = data.get("prompt_template", "")
        content = data.get("content", "")
        context = data.get("context", {})
        intent_analysis = data.get("intent_analysis", {})
        
        # Create a mock content data object with the intent analysis
        content_data = {
            "type": context.get("type", "post"),
            "title": context.get("title", ""),
            "content": content,
            "author": context.get("author", "Redditor"),
            "intent_analysis": intent_analysis
        }
        
        # Use the custom prompt to generate a response
        result = await test_custom_prompt(
            reddit_app.response_generator,
            prompt_template,
            content_data,
            {},
            "response"
        )
        
        return result
    except Exception as e:
        logger.error(f"Error testing response prompt: {str(e)}")
        return {"error": str(e)}

async def test_custom_prompt(model_instance, prompt_template, content, context, prompt_type):
    """
    Helper function to test a custom prompt with Gemini.
    
    Args:
        model_instance: Instance of IntentDetector or ResponseGenerator
        prompt_template (str): The custom prompt template
        content: The content to analyze or respond to
        context (dict): Additional context for the prompt
        prompt_type (str): Either "intent" or "response"
        
    Returns:
        dict: The result from Gemini
    """
    try:
        # Replace model configuration if needed
        original_model = model_instance.model
        
        # Format the prompt based on content type
        formatted_prompt = ""
        
        if prompt_type == "intent":
            # Format the intent detection prompt
            content_text = content
            if context:
                subreddit_info = f"Subreddit: r/{context.get('subreddit', '')}" if context.get('subreddit') else ""
                title_info = f"Post title: {context.get('title', '')}" if context.get('title') else ""
                formatted_prompt = prompt_template.format(
                    content=content_text,
                    subreddit_info=subreddit_info,
                    title_info=title_info,
                    **context
                )
            else:
                formatted_prompt = prompt_template.format(content=content_text)
        else:
            # Format the response generation prompt
            if isinstance(content, dict):
                # Extract fields from content_data
                content_type = content.get('type', 'post')
                author = content.get('author', 'Redditor')
                content_text = content.get('content', '')
                title = content.get('title', '')
                
                # Extract intent analysis data
                intent_analysis = content.get('intent_analysis', {})
                intent_category = intent_analysis.get('intent_category', 'NONE')
                products_services = intent_analysis.get('products_services', [])
                needs = intent_analysis.get('needs', [])
                timeframe = intent_analysis.get('timeframe', 'unknown')
                
                # Format content text based on type
                if content_type == 'post':
                    text_to_display = f"Title: {title}\n\nContent: {content_text}"
                else:
                    text_to_display = f"Comment: {content_text}"
                
                # Format the prompt
                formatted_prompt = prompt_template.format(
                    content=text_to_display,
                    intent_category=intent_category,
                    products_services=', '.join(products_services) if products_services else 'Unknown',
                    needs=', '.join(needs) if needs else 'Unknown',
                    timeframe=timeframe,
                    author=author,
                    **content
                )
            else:
                formatted_prompt = prompt_template.format(content=content)
        
        # Call Gemini with the formatted prompt
        response = model_instance.model.generate_content(formatted_prompt)
        
        # Extract the response text
        response_text = response.text
        
        # For intent detection, try to parse as JSON
        if prompt_type == "intent":
            try:
                # Find JSON content within the response
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    result = json.loads(json_str)
                else:
                    # If no JSON found, try to parse the whole response
                    result = json.loads(response_text)
                
                return {
                    "raw_prompt": formatted_prompt,
                    "raw_response": response_text,
                    "parsed_result": result
                }
            except json.JSONDecodeError:
                return {
                    "raw_prompt": formatted_prompt,
                    "raw_response": response_text,
                    "error": "Could not parse response as JSON"
                }
        else:
            # For response generation, try to parse as JSON but return raw text if that fails
            try:
                # Find JSON content within the response
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    result = json.loads(json_str)
                    
                    return {
                        "raw_prompt": formatted_prompt,
                        "raw_response": response_text,
                        "parsed_result": result
                    }
                else:
                    return {
                        "raw_prompt": formatted_prompt,
                        "raw_response": response_text
                    }
            except json.JSONDecodeError:
                return {
                    "raw_prompt": formatted_prompt,
                    "raw_response": response_text
                }
                
    except Exception as e:
        logger.error(f"Error in test_custom_prompt: {str(e)}")
        return {
            "raw_prompt": prompt_template,
            "error": str(e)
        }

@app.get("/api/default-prompts")
async def get_default_prompts():
    """Get the default prompts used by the system."""
    # Create instances if they don't exist
    if not hasattr(reddit_app, "intent_detector"):
        reddit_app.intent_detector = IntentDetector()
    if not hasattr(reddit_app, "response_generator"):
        reddit_app.response_generator = ResponseGenerator()
    
    # Get a sample intent detection prompt
    sample_intent_context = {
        "type": "post",
        "subreddit": "buildapc",
        "title": "Looking for recommendations on a new gaming PC"
    }
    sample_intent_content = "I'm thinking about upgrading my 5-year old gaming rig. My budget is around $1500. I mainly play FPS games and want something that can handle modern titles at high settings. Any recommendations on what parts I should get?"
    
    sample_intent_prompt = """
    Analysis task: Detect buyer intent in the following Reddit {context.get('type', 'content') if context else 'content'}.
    {subreddit_info}
    {title_info}
    
    Content: {content}
    
    Please analyze this content for buyer intent and return a structured JSON object with the following:
    
    1. intent_category: One of ["HIGH", "MEDIUM", "LOW", "NONE"] based on how likely this person is to make a purchase soon
    2. confidence: A number from 0.0 to 1.0 representing your confidence in this classification
    3. products_services: A list of specific products, services, or solutions mentioned or implied
    4. needs: A list of the user's needs, pain points, or requirements
    5. timeframe: The likely purchasing timeframe (immediate, near future, distant future, unknown)
    6. recommended_response: A brief suggestion on how to approach this potential buyer
    
    HIGH intent means actively looking to purchase very soon.
    MEDIUM intent means researching options with a plan to purchase.
    LOW intent means curious but not actively planning to purchase.
    NONE means no detectable buyer intent.
    
    Return ONLY a valid JSON object with these fields, nothing else.
    """
    
    # Get a sample response generation prompt
    sample_response_context = {
        "type": "post",
        "author": "gamer123",
        "title": "Looking for recommendations on a new gaming PC"
    }
    sample_response_content = "I'm thinking about upgrading my 5-year old gaming rig. My budget is around $1500. I mainly play FPS games and want something that can handle modern titles at high settings. Any recommendations on what parts I should get?"
    
    sample_intent_analysis = {
        "intent_category": "HIGH",
        "confidence": 0.9,
        "products_services": ["Gaming PC", "Computer parts", "GPU"],
        "needs": ["Performance for FPS games", "Modern games at high settings", "Within $1500 budget"],
        "timeframe": "near future",
        "recommended_response": "Offer specific PC build recommendations within their budget focused on gaming performance."
    }
    
    sample_response_prompt = """
    Task: Generate a professional, personalized direct message (DM) to send to a Reddit user who has shown interest in making a purchase.
    
    Reddit User's Content:
    {content}
    
    Buyer Intent Analysis:
    - Intent Level: {intent_category}
    - Products/Services of Interest: {products_services}
    - Needs/Requirements: {needs}
    - Purchasing Timeframe: {timeframe}
    
    Requirements for the DM:
    1. Use a friendly, helpful tone without being pushy or salesy
    2. Briefly mention you noticed their post/comment about {products_services}
    3. Offer genuine value or insights related to their specific needs
    4. Include 1-2 relevant resources or links that might help them
    5. End with a clear call-to-action to schedule an appointment or consultation
    6. The message should be brief (150-200 words maximum)
    7. Include a professional subject line
    
    Return a JSON object with:
    1. "subject": The subject line for the DM
    2. "message": The complete message content ready to send
    
    Return ONLY valid JSON with these fields, nothing else.
    """
    
    return {
        "intent_detection": {
            "prompt_template": sample_intent_prompt,
            "sample_content": sample_intent_content,
            "sample_context": sample_intent_context
        },
        "response_generation": {
            "prompt_template": sample_response_prompt,
            "sample_content": sample_response_content,
            "sample_context": sample_response_context,
            "sample_intent_analysis": sample_intent_analysis
        }
    }

# IMPORTANT: ONLY create template files when NOT in App Engine
if not is_app_engine:
    # Create the prompt tester HTML template
    with open("templates/prompt_tester.html", "w") as f:
        f.write(r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prompt Tester - Reddit Buyer Intent</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f8f9fa;
        }
        h1, h2, h3 {
            color: #2c3e50;
        }
        .tabs {
            display: flex;
            margin-bottom: 20px;
            border-bottom: 2px solid #ddd;
        }
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            margin-right: 5px;
            border-radius: 5px 5px 0 0;
            background: #f2f2f2;
        }
        .tab.active {
            background: #3498db;
            color: white;
            font-weight: bold;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        .card {
            background: #fff;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
        textarea {
            width: 100%;
            height: 300px;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
            font-family: monospace;
            font-size: 14px;
            margin-bottom: 10px;
            resize: vertical;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
        }
        input, select {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        button {
            background: #3498db;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background: #2980b9;
        }
        pre {
            background: #f5f5f5;
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 14px;
            white-space: pre-wrap;
        }
        .json-viewer {
            background: #f5f5f5;
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
            height: 300px;
            overflow-y: auto;
        }
        .controls {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        .nav-links {
            margin-bottom: 20px;
        }
        .nav-links a {
            margin-right: 15px;
            color: #3498db;
            text-decoration: none;
        }
        .nav-links a:hover {
            text-decoration: underline;
        }
        .loading {
            display: none;
            margin-left: 10px;
            color: #7f8c8d;
        }
        .error {
            color: #e74c3c;
            font-weight: bold;
            padding: 10px;
            background: #fadbd8;
            border-radius: 4px;
            margin-top: 10px;
        }
        .hint {
            font-size: 12px;
            color: #7f8c8d;
            margin-top: 5px;
        }
        .json-key {
            color: #2980b9;
        }
        .json-value {
            color: #27ae60;
        }
        .json-string {
            color: #c0392b;
        }
        .navbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            margin-bottom: 20px;
            border-bottom: 1px solid #ddd;
        }
        .navbar h1 {
            margin: 0;
        }
    </style>
</head>
<body>
    <div class="navbar">
        <h1>Prompt Tester</h1>
        <div class="nav-links">
            <a href="/">Dashboard</a>
            <a href="/prompt-tester">Prompt Tester</a>
        </div>
    </div>
    
    <div class="tabs">
        <div class="tab active" data-tab="intent-detection">Intent Detection</div>
        <div class="tab" data-tab="response-generation">Response Generation</div>
    </div>
    
    <div id="intent-detection" class="tab-content active">
        <div class="container">
            <div class="card">
                <h2>Intent Detection Prompt</h2>
                <div class="controls">
                    <button id="load-default-intent-prompt">Load Default Prompt</button>
                    <button id="test-intent-prompt">Test Prompt</button>
                    <button id="save-intent-prompt" class="save-btn">Save as Default</button>
                    <span id="intent-loading" class="loading">Testing...</span>
                </div>
                <div class="form-group">
                    <label for="intent-prompt">Prompt Template:</label>
                    <textarea id="intent-prompt" placeholder="Enter your custom prompt template here..."></textarea>
                    <div class="hint">Use {content} as a placeholder for the Reddit content. You can also use {subreddit_info}, {title_info}, and other context fields.</div>
                </div>
                <div class="form-group">
                    <label for="intent-content">Test Content:</label>
                    <textarea id="intent-content" placeholder="Enter a sample Reddit post or comment to analyze..."></textarea>
                </div>
                <div class="form-group">
                    <label for="intent-context">Context (JSON):</label>
                    <textarea id="intent-context" placeholder="Enter context as JSON (optional)..."></textarea>
                    <div class="hint">Example: {"type": "post", "subreddit": "buildapc", "title": "Looking for recommendations"}</div>
                </div>
            </div>
            <div class="card">
                <h2>Result</h2>
                <div id="intent-error" class="error" style="display: none;"></div>
                <h3>Raw Prompt:</h3>
                <pre id="intent-raw-prompt">Test a prompt to see the result</pre>
                <h3>Raw Response:</h3>
                <pre id="intent-raw-response"></pre>
                <h3>Parsed Result:</h3>
                <div id="intent-parsed-result" class="json-viewer"></div>
            </div>
        </div>
    </div>
    
    <div id="response-generation" class="tab-content">
        <div class="container">
            <div class="card">
                <h2>Response Generation Prompt</h2>
                <div class="controls">
                    <button id="load-default-response-prompt">Load Default Prompt</button>
                    <button id="test-response-prompt">Test Prompt</button>
                    <button id="save-response-prompt" class="save-btn">Save as Default</button>
                    <span id="response-loading" class="loading">Testing...</span>
                </div>
                <div class="form-group">
                    <label for="response-prompt">Prompt Template:</label>
                    <textarea id="response-prompt" placeholder="Enter your custom prompt template here..."></textarea>
                    <div class="hint">Use {content}, {intent_category}, {products_services}, {needs}, {timeframe}, and other fields as placeholders.</div>
                </div>
                <div class="form-group">
                    <label for="response-content">Test Content:</label>
                    <textarea id="response-content" placeholder="Enter a sample Reddit post or comment to respond to..."></textarea>
                </div>
                <div class="form-group">
                    <label for="response-context">Content Context (JSON):</label>
                    <textarea id="response-context" placeholder="Enter content context as JSON (optional)..."></textarea>
                    <div class="hint">Example: {"type": "post", "author": "username", "title": "Post title"}</div>
                </div>
                <div class="form-group">
                    <label for="intent-analysis">Intent Analysis (JSON):</label>
                    <textarea id="intent-analysis" placeholder="Enter intent analysis as JSON..."></textarea>
                    <div class="hint">This represents the output from the intent detection step.</div>
                </div>
            </div>
            <div class="card">
                <h2>Result</h2>
                <div id="response-error" class="error" style="display: none;"></div>
                <h3>Raw Prompt:</h3>
                <pre id="response-raw-prompt">Test a prompt to see the result</pre>
                <h3>Raw Response:</h3>
                <pre id="response-raw-response"></pre>
                <h3>Parsed Result:</h3>
                <div id="response-parsed-result" class="json-viewer"></div>
            </div>
        </div>
    </div>
    
    <script>
        // Tab functionality
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', function() {
                // Remove active class from all tabs
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                // Add active class to clicked tab
                this.classList.add('active');
                
                // Hide all tab content
                document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
                // Show the corresponding tab content
                document.getElementById(this.dataset.tab).classList.add('active');
            });
        });
        
        // Format JSON for display
        function formatJSON(json) {
            if (typeof json === 'string') {
                try {
                    json = JSON.parse(json);
                } catch (e) {
                    return json;
                }
            }
            
            return JSON.stringify(json, null, 2)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
                    let cls = 'json-value';
                    if (/^"/.test(match)) {
                        if (/:$/.test(match)) {
                            cls = 'json-key';
                        } else {
                            cls = 'json-string';
                        }
                    }
                    return '<span class="' + cls + '">' + match + '</span>';
                });
        }
        
        // Load default prompts
        document.getElementById('load-default-intent-prompt').addEventListener('click', loadDefaultIntentPrompt);
        document.getElementById('load-default-response-prompt').addEventListener('click', loadDefaultResponsePrompt);
        
        function loadDefaultIntentPrompt() {
            fetch('/api/default-prompts')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('intent-prompt').value = data.intent_detection.prompt_template;
                    document.getElementById('intent-content').value = data.intent_detection.sample_content;
                    document.getElementById('intent-context').value = JSON.stringify(data.intent_detection.sample_context, null, 2);
                })
                .catch(error => {
                    console.error('Error loading default prompts:', error);
                    showError('intent-error', 'Error loading default prompts: ' + error.message);
                });
        }
        
        function loadDefaultResponsePrompt() {
            fetch('/api/default-prompts')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('response-prompt').value = data.response_generation.prompt_template;
                    document.getElementById('response-content').value = data.response_generation.sample_content;
                    document.getElementById('response-context').value = JSON.stringify(data.response_generation.sample_context, null, 2);
                    document.getElementById('intent-analysis').value = JSON.stringify(data.response_generation.sample_intent_analysis, null, 2);
                })
                .catch(error => {
                    console.error('Error loading default prompts:', error);
                    showError('response-error', 'Error loading default prompts: ' + error.message);
                });
        }
        
        // Test intent detection prompt
        document.getElementById('test-intent-prompt').addEventListener('click', testIntentPrompt);
        
        function testIntentPrompt() {
            const promptTemplate = document.getElementById('intent-prompt').value;
            const content = document.getElementById('intent-content').value;
            let context = {};
            
            try {
                const contextText = document.getElementById('intent-context').value.trim();
                if (contextText) {
                    context = JSON.parse(contextText);
                }
            } catch (e) {
                showError('intent-error', 'Invalid JSON in context: ' + e.message);
                return;
            }
            
            if (!promptTemplate || !content) {
                showError('intent-error', 'Prompt template and content are required');
                return;
            }
            
            // Show loading state
            document.getElementById('intent-loading').style.display = 'inline';
            document.getElementById('intent-error').style.display = 'none';
            
            // Clear previous results
            document.getElementById('intent-raw-prompt').textContent = 'Loading...';
            document.getElementById('intent-raw-response').textContent = '';
            document.getElementById('intent-parsed-result').innerHTML = '';
            
            // Send request to API
            fetch('/api/test-intent-prompt', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    prompt_template: promptTemplate,
                    content: content,
                    context: context
                })
            })
            .then(response => response.json())
            .then(data => {
                // Hide loading state
                document.getElementById('intent-loading').style.display = 'none';
                
                // Check for error
                if (data.error) {
                    showError('intent-error', data.error);
                    return;
                }
                
                // Display results
                document.getElementById('intent-raw-prompt').textContent = data.raw_prompt || 'No prompt returned';
                document.getElementById('intent-raw-response').textContent = data.raw_response || 'No response returned';
                
                if (data.parsed_result) {
                    document.getElementById('intent-parsed-result').innerHTML = formatJSON(data.parsed_result);
                } else {
                    document.getElementById('intent-parsed-result').textContent = 'No parsed result available';
                }
            })
            .catch(error => {
                // Hide loading state
                document.getElementById('intent-loading').style.display = 'none';
                console.error('Error testing intent prompt:', error);
                showError('intent-error', 'Error testing prompt: ' + error.message);
            });
        }
        
        // Test response generation prompt
        document.getElementById('test-response-prompt').addEventListener('click', testResponsePrompt);
        
        function testResponsePrompt() {
            const promptTemplate = document.getElementById('response-prompt').value;
            const content = document.getElementById('response-content').value;
            let context = {};
            let intentAnalysis = {};
            
            try {
                const contextText = document.getElementById('response-context').value.trim();
                if (contextText) {
                    context = JSON.parse(contextText);
                }
            } catch (e) {
                showError('response-error', 'Invalid JSON in context: ' + e.message);
                return;
            }
            
            try {
                const analysisText = document.getElementById('intent-analysis').value.trim();
                if (analysisText) {
                    intentAnalysis = JSON.parse(analysisText);
                }
            } catch (e) {
                showError('response-error', 'Invalid JSON in intent analysis: ' + e.message);
                return;
            }
            
            if (!promptTemplate || !content) {
                showError('response-error', 'Prompt template and content are required');
                return;
            }
            
            // Show loading state
            document.getElementById('response-loading').style.display = 'inline';
            document.getElementById('response-error').style.display = 'none';
            
            // Clear previous results
            document.getElementById('response-raw-prompt').textContent = 'Loading...';
            document.getElementById('response-raw-response').textContent = '';
            document.getElementById('response-parsed-result').innerHTML = '';
            
            // Send request to API
            fetch('/api/test-response-prompt', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    prompt_template: promptTemplate,
                    content: content,
                    context: context,
                    intent_analysis: intentAnalysis
                })
            })
            .then(response => response.json())
            .then(data => {
                // Hide loading state
                document.getElementById('response-loading').style.display = 'none';
                
                // Check for error
                if (data.error) {
                    showError('response-error', data.error);
                    return;
                }
                
                // Display results
                document.getElementById('response-raw-prompt').textContent = data.raw_prompt || 'No prompt returned';
                document.getElementById('response-raw-response').textContent = data.raw_response || 'No response returned';
                
                if (data.parsed_result) {
                    document.getElementById('response-parsed-result').innerHTML = formatJSON(data.parsed_result);
                } else {
                    document.getElementById('response-parsed-result').textContent = 'No parsed result available';
                }
            })
            .catch(error => {
                // Hide loading state
                document.getElementById('response-loading').style.display = 'none';
                console.error('Error testing response prompt:', error);
                showError('response-error', 'Error testing prompt: ' + error.message);
            });
        }
        
        // Helper function to show errors
        function showError(elementId, message) {
            const errorElement = document.getElementById(elementId);
            errorElement.textContent = message;
            errorElement.style.display = 'block';
        }
        
        // Load default prompts on page load
        document.addEventListener('DOMContentLoaded', function() {
            loadDefaultIntentPrompt();
            loadDefaultResponsePrompt();
        });
        
        // Add event listeners for saving prompts
        document.getElementById('save-intent-prompt').addEventListener('click', function() {
            savePromptAsDefault('intent');
        });
        
        document.getElementById('save-response-prompt').addEventListener('click', function() {
            savePromptAsDefault('response');
        });
        
        // Function to save a prompt as the new default
        function savePromptAsDefault(promptType) {
            let promptTemplate;
            
            if (promptType === 'intent') {
                promptTemplate = document.getElementById('intent-prompt').value;
                if (!promptTemplate) {
                    showError('intent-error', 'Please enter a prompt template to save');
                    return;
                }
            } else {
                promptTemplate = document.getElementById('response-prompt').value;
                if (!promptTemplate) {
                    showError('response-error', 'Please enter a prompt template to save');
                    return;
                }
            }
            
            // Send request to save the prompt
            fetch('/api/save-default-prompt', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    prompt_type: promptType,
                    prompt_template: promptTemplate
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    if (promptType === 'intent') {
                        showError('intent-error', data.error);
                    } else {
                        showError('response-error', data.error);
                    }
                    return;
                }
                
                // Show success message
                alert('Prompt saved as default! It will be used for all future analysis.');
            })
            .catch(error => {
                console.error('Error saving prompt:', error);
                if (promptType === 'intent') {
                    showError('intent-error', 'Error saving prompt: ' + error.message);
                } else {
                    showError('response-error', 'Error saving prompt: ' + error.message);
                }
            });
        }
    </script>
</body>
</html>
    """)

# Add a link to the prompt tester in the main dashboard
if not is_app_engine:
    try:
        with open("templates/index.html", "r", encoding="utf-8", errors="ignore") as f:
            dashboard_html = f.read()

        # Add the link to the navbar
        dashboard_html = dashboard_html.replace(
            '<h1>Reddit Buyer Intent Dashboard</h1>',
            '''
            <div class="navbar">
                <h1>Reddit Buyer Intent Dashboard</h1>
                <div class="nav-links">
                    <a href="/">Dashboard</a>
                    <a href="/prompt-tester">Prompt Tester</a>
                </div>
            </div>
            '''
        )

        # Add the navbar CSS
        dashboard_html = dashboard_html.replace(
            '.pagination button:disabled {',
            '''.navbar {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 10px 0;
                    margin-bottom: 20px;
                    border-bottom: 1px solid #ddd;
                }
                .navbar h1 {
                    margin: 0;
                }
                .nav-links {
                    margin-right: 10px;
                }
                .nav-links a {
                    margin-right: 15px;
                    color: #3498db;
                    text-decoration: none;
                }
                .nav-links a:hover {
                    text-decoration: underline;
                }
                .pagination button:disabled {'''
        )

        # Write the updated dashboard HTML
        with open("templates/index.html", "w", encoding="utf-8") as f:
            f.write(dashboard_html)
    except Exception as e:
        logger.error(f"Error modifying index.html template: {str(e)}")
        # Continue even if template modification fails

# Add a new API endpoint for saving prompts
@app.post("/api/save-default-prompt")
async def save_default_prompt(data: dict):
    """
    Save a custom prompt as the new default for the application.
    
    Args:
        data (dict): Contains prompt_type, prompt_template, and other fields
        
    Returns:
        dict: Success message
    """
    try:
        prompt_type = data.get("prompt_type", "")
        prompt_template = data.get("prompt_template", "")
        
        if not prompt_type or not prompt_template:
            return {"error": "Missing prompt type or template"}
        
        # Skip file operations in App Engine environment
        if not is_app_engine:
            # Create prompts directory if it doesn't exist
            os.makedirs('prompts', exist_ok=True)
            
            # Save the prompt to a JSON file
            if prompt_type == "intent":
                with open("prompts/intent_prompt.json", "w") as f:
                    json.dump({"prompt_template": prompt_template}, f, indent=2)
            elif prompt_type == "response":
                with open("prompts/response_prompt.json", "w") as f:
                    json.dump({"prompt_template": prompt_template}, f, indent=2)
        
        # Update in-memory templates
        if prompt_type == "intent":
            # Also update the intent detector if it exists
            if hasattr(reddit_app, "intent_detector"):
                reddit_app.intent_detector.custom_prompt_template = prompt_template
        elif prompt_type == "response":
            # Also update the response generator if it exists
            if hasattr(reddit_app, "response_generator"):
                reddit_app.response_generator.custom_prompt_template = prompt_template
        else:
            return {"error": "Invalid prompt type"}
            
        return {"success": True, "message": f"Saved {prompt_type} prompt as default"}
    except Exception as e:
        logger.error(f"Error saving default prompt: {str(e)}")
        return {"error": str(e)}

def start_dashboard():
    """Start the FastAPI dashboard server."""
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    start_dashboard() 

