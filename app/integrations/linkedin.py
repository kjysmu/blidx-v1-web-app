class LinkedInClient:
    def get_oauth_url(self) -> str:
        # TODO: build LinkedIn OAuth URL
        raise NotImplementedError

    def exchange_code_for_token(self, code: str):
        # TODO: exchange code for access token
        raise NotImplementedError

    def publish_post(self, access_token: str, content: str):
        # TODO: LinkedIn posting endpoint
        raise NotImplementedError
