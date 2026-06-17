import html
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings
from app.demo_store import demo_store

router = APIRouter()
security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin credentials are not configured",
        )

    username_ok = secrets.compare_digest(
        credentials.username.encode(), settings.ADMIN_USERNAME.encode()
    )
    password_ok = secrets.compare_digest(
        credentials.password.encode(), settings.ADMIN_PASSWORD.encode()
    )
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@router.get("", response_class=HTMLResponse)
def admin_home(_: str = Depends(require_admin)) -> HTMLResponse:
    state = demo_store.snapshot()
    profile = state["profile"]
    content_bank = state["content_bank"]
    posts = [post for post in state["posts"] if post["status"] != "deleted"]

    rows = "".join(
        "<tr>"
        f"<td>{html.escape(post.get('title', 'Untitled'))}</td>"
        f"<td>{html.escape(post.get('status', 'unknown'))}</td>"
        f"<td>{html.escape(post.get('generation_provider', 'template'))}</td>"
        f"<td>{post.get('char_count', 0)}</td>"
        "</tr>"
        for post in posts
    )
    memories = "".join(
        "<li>"
        f"<strong>{html.escape(entry.get('category', 'general'))}</strong>: "
        f"{html.escape(entry.get('raw_text', ''))}"
        "</li>"
        for entry in content_bank[:20]
    )
    body = f"""
    <!doctype html>
    <html>
      <head>
        <title>Blidx Admin</title>
        <style>
          body {{ font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; color: #141124; }}
          .grid {{ display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 12px; margin: 20px 0; }}
          .card {{ border: 1px solid #e6e0f4; border-radius: 16px; padding: 16px; background: #fff; box-shadow: 0 8px 24px rgba(35, 24, 64, .06); }}
          .metric {{ font-size: 28px; font-weight: 800; }}
          table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
          th, td {{ border-bottom: 1px solid #eee8fb; padding: 10px; text-align: left; vertical-align: top; }}
          th {{ color: #6c5c85; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }}
          li {{ margin: 8px 0; }}
        </style>
      </head>
      <body>
        <h1>Blidx Admin</h1>
        <p>Monitoring view for demo profile, Content Bank entries, and generated posts.</p>
        <div class="grid">
          <div class="card"><div class="metric">1</div><div>User profile</div></div>
          <div class="card"><div class="metric">{len(content_bank)}</div><div>Content Bank entries</div></div>
          <div class="card"><div class="metric">{len(posts)}</div><div>Visible posts</div></div>
          <div class="card"><div class="metric">{html.escape(profile.get('company_name', ''))}</div><div>Company</div></div>
        </div>
        <section class="card">
          <h2>Profile</h2>
          <p><strong>{html.escape(profile.get('first_name', ''))}</strong> · {html.escape(profile.get('role', ''))}</p>
          <p>{html.escape(profile.get('company_description', ''))}</p>
        </section>
        <section class="card" style="margin-top:16px">
          <h2>Content Bank</h2>
          <ul>{memories or '<li>No entries yet.</li>'}</ul>
        </section>
        <section class="card" style="margin-top:16px">
          <h2>Posts</h2>
          <table>
            <thead><tr><th>Title</th><th>Status</th><th>Provider</th><th>Chars</th></tr></thead>
            <tbody>{rows or '<tr><td colspan="4">No posts yet.</td></tr>'}</tbody>
          </table>
        </section>
      </body>
    </html>
    """
    return HTMLResponse(body)
