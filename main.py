import os
import base64
import uuid
import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(
    title="TDS Project 1 FastAPI Server",
    description="Handles LLM-based app generation and GitHub deployment for TDS Project 1.",
    version="1.0.0",
)

# --- Environment Variables ---
SECRET = os.getenv("SECRET")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = os.getenv("GITHUB_USER")

if not all([SECRET, GITHUB_TOKEN, GITHUB_USER]):
    raise ValueError("Missing SECRET, GITHUB_TOKEN, or GITHUB_USER in .env")

# --- Constants ---
MIT_LICENSE = """MIT License

Copyright (c) 2025 TDS Student

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# --- Pydantic Models ---
class TaskPayload(BaseModel):
    email: str
    secret: str
    task: str
    round: int
    brief: str
    checks: List[str]
    evaluation_url: str
    attachments: List[Dict[str, Any]]
    nonce: str

class EvaluationResponse(BaseModel):
    email: str
    task: str
    round: int
    nonce: str
    repo_url: str
    commit_sha: str
    pages_url: str

# --- Helper: Call Google AI Studio (Gemini) ---
def generate_html_with_gemini(brief: str, attachments: List[Dict[str, Any]], existing_code: str = None) -> str:
    """
    Calls Google AI Studio (via REST) to generate index.html.
    Replace with your actual Google AI Studio endpoint or use local proxy.
    For now, simulate with a basic response — YOU MUST IMPLEMENT THIS.
    """
    # 🔥 TODO: Replace this with real Google AI Studio API call
    # Example prompt:
    prompt = f"""
    Create a single HTML file that fulfills this task:
    "{brief}"

    Requirements:
    - All CSS and JS must be inline (no external files)
    - If an image is needed, embed it as base64 if provided
    - Must work on GitHub Pages
    - Be minimal and functional

    Attachments (data URIs):
    {', '.join([att['url'] for att in attachments]) if attachments else 'None'}

    {'Existing code (update this): ' + existing_code if existing_code else ''}
    """
    
    # ⚠️ TEMPORARY: Return a placeholder. You MUST integrate Google AI Studio.
    return f"""<!DOCTYPE html>
<html>
<head><title>TDS App</title></head>
<body>
<h1>Generated from brief:</h1>
<p>{brief}</p>
<p>Attachments: {len(attachments)}</p>
{'<p>Round 2 update applied.</p>' if existing_code else ''}
<script>console.log("App loaded");</script>
</body>
</html>"""

# --- GitHub Helpers ---
def create_or_get_repo(repo_name: str) -> Dict[str, Any]:
    url = "https://api.github.com/user/repos"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "name": repo_name,
        "private": False,  # MUST be public for GitHub Pages
        "auto_init": False,
        "license_template": "mit"
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 201:
        print(f"✅ Created new repo: {repo_name}")
        return response.json()
    elif response.status_code == 422:
        # Repo exists — fetch it
        repo_url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}"
        r = requests.get(repo_url, headers=headers)
        if r.status_code == 200:
            print(f"✅ Using existing repo: {repo_name}")
            return r.json()
        else:
            raise Exception(f"Repo exists but inaccessible: {r.status_code}")
    else:
        raise Exception(f"Failed to create repo: {response.status_code} {response.text}")

def push_file(repo_name: str, file_path: str, content: str, message: str):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    
    # Check if file exists to get SHA (required for update)
    r = requests.get(url, headers=headers)
    data = {"message": message, "content": encoded}
    if r.status_code == 200:
        data["sha"] = r.json()["sha"]
    
    response = requests.put(url, json=data, headers=headers)
    if response.status_code not in [200, 201]:
        raise Exception(f"Failed to push {file_path}: {response.status_code} {response.text}")
    return response.json().get("commit", {}).get("sha") or response.json().get("content", {}).get("sha")

def enable_github_pages(repo_name: str):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}/pages"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {"source": {"branch": "main", "path": "/"}}
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 201:
        print("✅ GitHub Pages enabled")
    elif response.status_code == 409:
        print("ℹ️ GitHub Pages already enabled")
    else:
        print(f"⚠️ Failed to enable Pages: {response.status_code} {response.text}")

async def send_evaluation_response(evaluation_url: str, payload: EvaluationResponse):
    try:
        response = requests.post(evaluation_url, json=payload.dict())
        response.raise_for_status()
        print(f"✅ Sent evaluation response to {evaluation_url}")
    except Exception as e:
        print(f"❌ Error sending to evaluation URL: {e}")

# --- Main Endpoint ---
@app.post("/handle_task")
async def handle_task(payload: TaskPayload, background_tasks: BackgroundTasks):
    # 1. Validate secret
    if payload.secret != SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")

    # 2. Generate repo name
    repo_name = f"{payload.task}_{payload.nonce[:8]}"
    repo_full_name = f"{GITHUB_USER}/{repo_name}"
    pages_url = f"https://{GITHUB_USER}.github.io/{repo_name}/"

    try:
        # 3. Create or get repo
        repo_info = create_or_get_repo(repo_name)

        if payload.round == 1:
            # Generate code from LLM
            html_content = generate_html_with_gemini(payload.brief, payload.attachments)
            readme_content = f"""# {repo_name}

{payload.brief}

## Features
- Built with LLM assistance
- Deployed on GitHub Pages

## License
MIT
"""

            # Push files
            sha1 = push_file(repo_name, "index.html", html_content, "feat: Initial app")
            sha2 = push_file(repo_name, "README.md", readme_content, "docs: Add README")
            sha3 = push_file(repo_name, "LICENSE", MIT_LICENSE, "chore: Add MIT license")

            # Enable Pages
            enable_github_pages(repo_name)

            final_sha = sha1  # Use index.html commit SHA

        elif payload.round == 2:
            # Fetch existing index.html to update
            file_url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}/contents/index.html"
            r = requests.get(file_url, headers={"Authorization": f"token {GITHUB_TOKEN}"})
            existing_code = ""
            if r.status_code == 200:
                existing_code = base64.b64decode(r.json()["content"]).decode("utf-8")
            
            # Generate updated code
            html_content = generate_html_with_gemini(payload.brief, payload.attachments, existing_code)
            final_sha = push_file(repo_name, "index.html", html_content, "feat: Round 2 update")

            # Update README
            readme_content = f"""# {repo_name} (Updated)

{payload.brief}

## Round 2 Changes
- Updated based on feedback

## License
MIT
"""
            push_file(repo_name, "README.md", readme_content, "docs: Update README for Round 2")

        else:
            raise HTTPException(status_code=400, detail="Invalid round")

        # 4. Prepare evaluation response
        response_payload = EvaluationResponse(
            email=payload.email,
            task=payload.task,
            round=payload.round,
            nonce=payload.nonce,
            repo_url=f"https://github.com/{repo_full_name}",
            commit_sha=final_sha,
            pages_url=pages_url
        )

        # 5. Send in background
        background_tasks.add_task(send_evaluation_response, payload.evaluation_url, response_payload)

        return {"status": "success", "repo": repo_full_name}

    except Exception as e:
        print(f"🔥 Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"message": "TDS Project 1 Server — POST to /handle_task"}