from pydantic import BaseModel


class RedditContent(BaseModel):
    reddit_title: str
    reddit_body: str
    image_prompt: str
