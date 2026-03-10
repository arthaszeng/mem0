from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    must_change_password: bool = False
    user: dict


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username: str
    email: str | None = None
    password: str
    is_superadmin: bool = False


class UpdateUserRequest(BaseModel):
    email: str | None = None
    is_active: bool | None = None
    is_superadmin: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str


class CreateApiKeyRequest(BaseModel):
    name: str


class CreateApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    key: str
    created_at: str


class OAuthClientRegistrationRequest(BaseModel):
    client_name: str = ""
    redirect_uris: list[str] = []
    grant_types: list[str] = ["authorization_code", "refresh_token"]
    token_endpoint_auth_method: str = "none"


class TokenRequest(BaseModel):
    grant_type: str
    code: str | None = None
    redirect_uri: str | None = None
    code_verifier: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
