import json
import base64
from typing import Optional
from fastapi import Header, HTTPException, status, Depends
from pydantic import BaseModel
from app.schemas import RoleEnum

class CurrentUser(BaseModel):
    role: RoleEnum
    user_id: str
    name: str

def get_current_user(
    x_role: Optional[str] = Header(None, alias="X-Role"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(None, alias="X-User-Name"),
    authorization: Optional[str] = Header(None)
) -> CurrentUser:
    role = x_role
    user_id = x_user_id
    name = x_user_name

    # Support token in Authorization: Bearer <base64_json>
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
        try:
            decoded = base64.b64decode(token).decode("utf-8")
            data = json.loads(decoded)
            role = role or data.get("role")
            user_id = user_id or data.get("user_id")
            name = name or data.get("name")
        except Exception:
            pass

    if not role or not user_id:
        # Default for open explorer/swagger if not specified
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication headers (X-Role and X-User-Id) or Bearer token required."
        )

    try:
        parsed_role = RoleEnum(role.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {role}. Must be patient, doctor, or staff."
        )

    return CurrentUser(
        role=parsed_role,
        user_id=user_id,
        name=name or user_id
    )
