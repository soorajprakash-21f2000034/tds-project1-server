import os
import base64
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

# --- Helper: Generate HTML (Replace with LLM later) ---
def generate_html_with_gemini(brief: str, attachments: List[Dict[str, Any]], existing_code: str = None) -> str:
    prompt_context = f"Existing code:\n{existing_code}" if existing_code else "No existing code."
    return f"""<!DOCTYPE html>
<html>
<head><title>TDS App</title></head>
<body>
<h1>App for: {brief}</h1>
<p>Attachments: {len(attachments)}</p>
{'<p style="color:green;">✅ Round 2 update applied!</p>' if existing_code else ''}
<script>console.log("TDS Project 1 App Loaded");</script>
</body>
</html>"""

# --- GitHub Helpers ---
def create_or_get_repo(repo_name: str):
    url = "https://api.github.com/user/repos"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "name": repo_name,
        "private": False,
        "auto_init": False
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 201:
        return response.json()
    elif response.status_code == 422:  # Repo exists
        repo_url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}"
        r = requests.get(repo_url, headers=headers)
        if r.status_code == 200:
            return r.json()
        else:
            raise Exception(f"Repo exists but inaccessible: {r.status_code}")
    else:
        raise Exception(f"Failed to create repo: {response.status_code} {response.text}")

def push_file(repo_name: str, file_path: str, content: str, message: str):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    
    # Check if file exists (to get SHA for update)
    r = requests.get(url, headers=headers)
    data = {"message": message, "content": encoded}
    if r.status_code == 200:
        data["sha"] = r.json()["sha"]
    
    response = requests.put(url, json=data, headers=headers)
    if response.status_code not in [200, 201]:
        raise Exception(f"Failed to push {file_path}: {response.status_code} {response.text}")

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
        print(f"⚠️ Pages enable failed: {response.status_code}")

def get_latest_commit_sha(repo_name: str) -> str:
    url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}/commits/main"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()["sha"]

async def send_evaluation_response(evaluation_url: str, payload: EvaluationResponse):
    try:
        clean_url = evaluation_url.strip()
        response = requests.post(clean_url, json=payload.dict())
        response.raise_for_status()
        print(f"✅ Sent evaluation response")
    except Exception as e:
        print(f"❌ Error sending to evaluation URL: {e}")

# --- Main Endpoint ---
@app.post("/handle_task")
async def handle_task(payload: TaskPayload, background_tasks: BackgroundTasks):
    if payload.secret != SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")

    repo_name = f"{payload.task}_{payload.nonce[:8]}"
    pages_url = f"https://{GITHUB_USER}.github.io/{repo_name}/"

    try:
        create_or_get_repo(repo_name)

        if payload.round == 1:
            html_content = generate_html_with_gemini(payload.brief, payload.attachments)
            readme_content = f"""# {repo_name}

{payload.brief}

## Features
- Built with LLM assistance
- Deployed on GitHub Pages

## License
MIT
"""
            push_file(repo_name, "index.html", html_content, "feat: Initial app")
            push_file(repo_name, "README.md", readme_content, "docs: Add README")
            push_file(repo_name, "LICENSE", MIT_LICENSE, "chore: Add MIT license")
            enable_github_pages(repo_name)

        elif payload.round == 2:
            # Fetch existing code
            file_url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}/contents/index.html"
            r = requests.get(file_url, headers={"Authorization": f"token {GITHUB_TOKEN}"})
            existing_code = ""
            if r.status_code == 200:
                existing_code = base64.b64decode(r.json()["content"]).decode("utf-8")
            
            html_content = generate_html_with_gemini(payload.brief, payload.attachments, existing_code)
            push_file(repo_name, "index.html", html_content, "feat: Round 2 update")

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

        # Get real commit SHA
        final_sha = get_latest_commit_sha(repo_name)

        response_payload = EvaluationResponse(
            email=payload.email,
            task=payload.task,
            round=payload.round,
            nonce=payload.nonce,
            repo_url=f"https://github.com/{GITHUB_USER}/{repo_name}",
            commit_sha=final_sha,
            pages_url=pages_url
        )

        background_tasks.add_task(send_evaluation_response, payload.evaluation_url, response_payload)
        return {"status": "success", "repo": f"{GITHUB_USER}/{repo_name}"}

    except Exception as e:
        print(f"🔥 Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"message": "TDS Project 1 Server — POST to /handle_task"}