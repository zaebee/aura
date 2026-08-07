from typing import Optional
from pydantic import BaseModel


class CommentParams(BaseModel):
    repo: str
    issue_number: Optional[int] = None
    commit_sha: Optional[str] = None
    body: str = ""


class ReplyParams(BaseModel):
    repo: str
    pull_number: int
    comment_id: int
    body: str
