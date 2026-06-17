from urllib.parse import urlencode

import httpx

from app.core.config import settings


class LinkedInClient:
    authorization_url = "https://www.linkedin.com/oauth/v2/authorization"
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    userinfo_url = "https://api.linkedin.com/v2/userinfo"
    posts_url = "https://api.linkedin.com/v2/ugcPosts"

    @property
    def configured(self) -> bool:
        return bool(
            settings.LINKEDIN_CLIENT_ID
            and settings.LINKEDIN_CLIENT_SECRET
            and settings.LINKEDIN_REDIRECT_URI
        )

    def get_oauth_url(self, state: str) -> str:
        if not self.configured:
            raise RuntimeError("LinkedIn OAuth environment variables are not configured")
        query = urlencode(
            {
                "response_type": "code",
                "client_id": settings.LINKEDIN_CLIENT_ID,
                "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
                "state": state,
                "scope": settings.LINKEDIN_SCOPES,
            }
        )
        return f"{self.authorization_url}?{query}"

    def exchange_code_for_token(self, code: str):
        if not self.configured:
            raise RuntimeError("LinkedIn OAuth environment variables are not configured")
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                self.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
                    "client_id": settings.LINKEDIN_CLIENT_ID,
                    "client_secret": settings.LINKEDIN_CLIENT_SECRET,
                },
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            return response.json()

    def get_userinfo(self, access_token: str):
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                self.userinfo_url,
                headers={"authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()

    def publish_post(self, access_token: str, content: str):
        profile = self.get_userinfo(access_token)
        author = profile.get("sub")
        if not author:
            raise RuntimeError("LinkedIn userinfo response did not include a subject")

        payload = {
            "author": f"urn:li:person:{author}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": content},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                self.posts_url,
                headers={
                    "authorization": f"Bearer {access_token}",
                    "content-type": "application/json",
                    "x-restli-protocol-version": "2.0.0",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json() if response.content else {"status": "published"}
            if response.headers.get("x-restli-id"):
                data["id"] = response.headers["x-restli-id"]
            return data


def linkedin_share_url() -> str:
    return "https://www.linkedin.com/feed/"
