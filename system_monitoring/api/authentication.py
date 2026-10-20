"""Sign-in, session restoration and logout endpoints."""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from system_monitoring.auth import COOKIE, require_admin, same_origin, token_hash

router = APIRouter(prefix="/api/auth", tags=["Administrator access"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=1, max_length=1024)


@router.post("/login")
def login(request: Request, credentials: Credentials, response: Response):
    same_origin(request)
    result = request.app.state.authentication.login(
        credentials.username, credentials.password.get_secret_value()
    )
    response.set_cookie(
        COOKIE,
        result.pop("token"),
        httponly=True,
        samesite="strict",
        secure=request.app.state.settings.secure_cookies,
        max_age=request.app.state.settings.session_seconds,
    )
    return result


@router.get("/session")
def session(request: Request):
    result = request.app.state.authentication.session(request)
    return {key: result[key] for key in ("username", "csrf_token", "expires_at")}


@router.post("/logout", status_code=204, dependencies=[Depends(require_admin)])
def logout(request: Request, response: Response):
    with request.app.state.database.connect() as connection:
        connection.execute(
            "DELETE FROM sessions WHERE token_hash=?", (token_hash(request.cookies[COOKIE]),)
        )
    response.delete_cookie(
        COOKIE, secure=request.app.state.settings.secure_cookies, httponly=True, samesite="strict"
    )
