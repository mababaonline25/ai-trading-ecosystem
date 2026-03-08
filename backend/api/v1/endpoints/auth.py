"""
Authentication endpoints
JWT-based authentication with refresh tokens and 2FA
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta
from typing import Optional
import pyotp
import qrcode
import io
import base64

from ....core.auth.jwt import (
    create_access_token, create_refresh_token,
    verify_token, get_password_hash, verify_password
)
from ....core.auth.two_factor import (
    generate_2fa_secret, verify_2fa_code,
    generate_backup_codes
)
from ....core.auth.rate_limiter import rate_limit
from ....data.repositories.user_repo import UserRepository
from ....data.models.user import User, UserSession
from ....utils.logger import get_logger
from ....utils.email import send_email
from ....utils.sms import send_sms
from ....config import settings

router = APIRouter()
logger = get_logger(__name__)
user_repo = UserRepository()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@router.post("/register")
@rate_limit(requests=5, period=60)  # 5 requests per minute
async def register(
    email: str,
    username: str,
    password: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    phone: Optional[str] = None,
    country: Optional[str] = None,
    referral_code: Optional[str] = None
):
    """
    Register a new user account
    """
    logger.info(f"New registration attempt: {email}")
    
    # Validate email format
    if not validate_email(email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    
    # Validate password strength
    if not validate_password_strength(password):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters with uppercase, lowercase, number and special character"
        )
    
    # Check if user exists
    existing_user = await user_repo.get_by_email(email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    existing_username = await user_repo.get_by_username(username)
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Hash password
    hashed_password = get_password_hash(password)
    
    # Generate referral code
    user_referral_code = generate_referral_code()
    
    # Create user
    user_data = {
        "email": email,
        "username": username,
        "password_hash": hashed_password,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "country": country,
        "referral_code": user_referral_code,
        "referred_by": await get_user_by_referral(referral_code) if referral_code else None,
        "email_verification_token": generate_verification_token(),
        "email_verification_expires": datetime.utcnow() + timedelta(hours=24)
    }
    
    user = await user_repo.create(user_data)
    
    # Send verification email
    await send_verification_email(user.email, user.email_verification_token)
    
    # Log activity
    await log_user_activity(user.id, "registration", {
        "ip": request.client.host,
        "user_agent": request.headers.get("user-agent")
    })
    
    logger.info(f"User registered successfully: {user.id}")
    
    return {
        "message": "Registration successful. Please verify your email.",
        "user_id": str(user.id),
        "email": user.email,
        "username": user.username
    }


@router.post("/login")
@rate_limit(requests=10, period=60)  # 10 requests per minute
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    two_factor_code: Optional[str] = None
):
    """
    Login with username/password and optional 2FA
    """
    logger.info(f"Login attempt: {form_data.username}")
    
    # Get user by username or email
    user = await user_repo.get_by_username(form_data.username)
    if not user:
        user = await user_repo.get_by_email(form_data.username)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Check if account is locked
    if user.login_attempts >= 5:
        if user.last_login_attempt and (datetime.utcnow() - user.last_login_attempt) < timedelta(minutes=15):
            raise HTTPException(
                status_code=401,
                detail="Account temporarily locked. Try again in 15 minutes."
            )
        else:
            # Reset login attempts after lockout period
            user.login_attempts = 0
            await user_repo.update(user)
    
    # Verify password
    if not verify_password(form_data.password, user.password_hash):
        user.login_attempts += 1
        user.last_login_attempt = datetime.utcnow()
        await user_repo.update(user)
        
        logger.warning(f"Failed login attempt for {form_data.username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Check 2FA if enabled
    if user.two_factor_enabled:
        if not two_factor_code:
            raise HTTPException(
                status_code=401,
                detail="2FA code required",
                headers={"X-2FA-Required": "true"}
            )
        
        if not verify_2fa_code(user.two_factor_secret, two_factor_code):
            raise HTTPException(status_code=401, detail="Invalid 2FA code")
    
    # Check if email verified
    if not user.email_verified:
        raise HTTPException(
            status_code=401,
            detail="Email not verified. Please check your email."
        )
    
    # Check if account is active
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is disabled")
    
    if user.is_banned:
        raise HTTPException(
            status_code=401,
            detail=f"Account is banned. Reason: {user.ban_reason}"
        )
    
    # Reset login attempts on successful login
    user.login_attempts = 0
    user.last_login = datetime.utcnow()
    user.last_login_ip = request.client.host
    await user_repo.update(user)
    
    # Create session
    session = await create_user_session(
        user.id,
        request.client.host,
        request.headers.get("user-agent")
    )
    
    # Create tokens
    access_token = create_access_token(
        data={"sub": str(user.id), "session_id": str(session.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "session_id": str(session.id)},
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    
    # Log activity
    await log_user_activity(user.id, "login", {
        "ip": request.client.host,
        "user_agent": request.headers.get("user-agent")
    })
    
    logger.info(f"User logged in successfully: {user.id}")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user.to_dict()
    }


@router.post("/refresh")
async def refresh_token(refresh_token: str):
    """
    Get new access token using refresh token
    """
    payload = verify_token(refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    user_id = payload.get("sub")
    session_id = payload.get("session_id")
    
    # Verify session still exists
    session = await get_user_session(session_id)
    if not session or not session.is_active:
        raise HTTPException(status_code=401, detail="Session expired")
    
    # Create new access token
    access_token = create_access_token(
        data={"sub": user_id, "session_id": session_id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/logout")
async def logout(
    request: Request,
    token: str = Depends(oauth2_scheme)
):
    """
    Logout user and invalidate session
    """
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    session_id = payload.get("session_id")
    
    # Invalidate session
    await deactivate_user_session(session_id)
    
    # Log activity
    await log_user_activity(
        payload.get("sub"),
        "logout",
        {"ip": request.client.host}
    )
    
    return {"message": "Logged out successfully"}


@router.post("/verify-email/{token}")
async def verify_email(token: str):
    """
    Verify email address using verification token
    """
    user = await user_repo.get_by_email_verification_token(token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    if user.email_verification_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Verification token expired")
    
    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_expires = None
    user.verification_level = 1  # Email verified
    await user_repo.update(user)
    
    logger.info(f"Email verified for user: {user.id}")
    
    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
@rate_limit(requests=3, period=3600)  # 3 requests per hour
async def resend_verification(email: str):
    """
    Resend email verification link
    """
    user = await user_repo.get_by_email(email)
    if not user:
        # Don't reveal if email exists
        return {"message": "If email exists, verification link will be sent"}
    
    if user.email_verified:
        return {"message": "Email already verified"}
    
    # Generate new token
    user.email_verification_token = generate_verification_token()
    user.email_verification_expires = datetime.utcnow() + timedelta(hours=24)
    await user_repo.update(user)
    
    # Send email
    await send_verification_email(user.email, user.email_verification_token)
    
    return {"message": "Verification email sent"}


@router.post("/forgot-password")
@rate_limit(requests=3, period=3600)  # 3 requests per hour
async def forgot_password(email: str):
    """
    Request password reset
    """
    user = await user_repo.get_by_email(email)
    if not user:
        # Don't reveal if email exists
        return {"message": "If email exists, reset instructions will be sent"}
    
    # Generate reset token
    reset_token = generate_reset_token()
    user.password_reset_token = reset_token
    user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
    await user_repo.update(user)
    
    # Send email
    await send_password_reset_email(user.email, reset_token)
    
    return {"message": "Password reset instructions sent"}


@router.post("/reset-password")
async def reset_password(token: str, new_password: str):
    """
    Reset password using token
    """
    user = await user_repo.get_by_password_reset_token(token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    if user.password_reset_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Reset token expired")
    
    # Validate new password
    if not validate_password_strength(new_password):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters with uppercase, lowercase, number and special character"
        )
    
    # Update password
    user.password_hash = get_password_hash(new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    await user_repo.update(user)
    
    # Invalidate all sessions
    await invalidate_all_user_sessions(user.id)
    
    logger.info(f"Password reset for user: {user.id}")
    
    return {"message": "Password reset successfully"}


@router.post("/change-password")
async def change_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user)
):
    """
    Change password for authenticated user
    """
    if not verify_password(current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    if not validate_password_strength(new_password):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters with uppercase, lowercase, number and special character"
        )
    
    current_user.password_hash = get_password_hash(new_password)
    await user_repo.update(current_user)
    
    # Invalidate all other sessions
    await invalidate_other_sessions(current_user.id, current_session_id)
    
    logger.info(f"Password changed for user: {current_user.id}")
    
    return {"message": "Password changed successfully"}


@router.post("/enable-2fa")
async def enable_2fa(
    current_user: User = Depends(get_current_user)
):
    """
    Enable two-factor authentication
    Returns QR code and backup codes
    """
    if current_user.two_factor_enabled:
        raise HTTPException(status_code=400, detail="2FA already enabled")
    
    # Generate secret
    secret = generate_2fa_secret()
    
    # Generate backup codes
    backup_codes = generate_backup_codes()
    
    # Store hashed backup codes
    current_user.two_factor_secret = secret
    current_user.two_factor_backup_codes = [hash_code(code) for code in backup_codes]
    await user_repo.update(current_user)
    
    # Generate QR code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        current_user.email,
        issuer_name="AI Trading Ecosystem"
    )
    
    # Create QR code image
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_code = base64.b64encode(buffer.getvalue()).decode()
    
    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_code}",
        "backup_codes": backup_codes,
        "message": "Scan QR code with Google Authenticator or similar app"
    }


@router.post("/verify-2fa")
async def verify_2fa(
    code: str,
    current_user: User = Depends(get_current_user)
):
    """
    Verify and enable 2FA
    """
    if not current_user.two_factor_secret:
        raise HTTPException(status_code=400, detail="2FA not initialized")
    
    if verify_2fa_code(current_user.two_factor_secret, code):
        current_user.two_factor_enabled = True
        await user_repo.update(current_user)
        
        logger.info(f"2FA enabled for user: {current_user.id}")
        
        return {"message": "2FA enabled successfully"}
    else:
        raise HTTPException(status_code=400, detail="Invalid 2FA code")


@router.post("/disable-2fa")
async def disable_2fa(
    code: str,
    current_user: User = Depends(get_current_user)
):
    """
    Disable two-factor authentication
    """
    if not current_user.two_factor_enabled:
        raise HTTPException(status_code=400, detail="2FA not enabled")
    
    if verify_2fa_code(current_user.two_factor_secret, code):
        current_user.two_factor_enabled = False
        current_user.two_factor_secret = None
        current_user.two_factor_backup_codes = None
        await user_repo.update(current_user)
        
        logger.info(f"2FA disabled for user: {current_user.id}")
        
        return {"message": "2FA disabled successfully"}
    else:
        raise HTTPException(status_code=400, detail="Invalid 2FA code")


@router.get("/sessions")
async def get_active_sessions(
    current_user: User = Depends(get_current_user)
):
    """
    Get all active sessions for current user
    """
    sessions = await get_user_sessions(current_user.id)
    
    return {
        "current_session_id": current_session_id,
        "sessions": [
            {
                "id": str(s.id),
                "device_info": s.device_info,
                "ip_address": s.ip_address,
                "created_at": s.created_at.isoformat(),
                "last_activity": s.last_activity.isoformat(),
                "is_current": str(s.id) == current_session_id
            }
            for s in sessions
        ]
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Revoke a specific session
    """
    session = await get_user_session(session_id)
    
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if str(session.id) == current_session_id:
        raise HTTPException(status_code=400, detail="Cannot revoke current session")
    
    session.is_active = False
    await update_user_session(session)
    
    logger.info(f"Session revoked for user: {current_user.id}")
    
    return {"message": "Session revoked"}


@router.delete("/sessions")
async def revoke_all_sessions(
    current_user: User = Depends(get_current_user)
):
    """
    Revoke all sessions except current
    """
    await invalidate_other_sessions(current_user.id, current_session_id)
    
    logger.info(f"All other sessions revoked for user: {current_user.id}")
    
    return {"message": "All other sessions revoked"}


# Helper functions
def validate_email(email: str) -> bool:
    """Validate email format"""
    import re
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_password_strength(password: str) -> bool:
    """Validate password strength"""
    import re
    
    if len(password) < 8:
        return False
    
    if not re.search(r"[A-Z]", password):
        return False
    
    if not re.search(r"[a-z]", password):
        return False
    
    if not re.search(r"\d", password):
        return False
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    
    return True


def generate_referral_code() -> str:
    """Generate unique referral code"""
    import secrets
    import string
    
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))


def generate_verification_token() -> str:
    """Generate email verification token"""
    import secrets
    return secrets.token_urlsafe(32)


def generate_reset_token() -> str:
    """Generate password reset token"""
    import secrets
    return secrets.token_urlsafe(32)


def hash_code(code: str) -> str:
    """Hash backup code"""
    import hashlib
    return hashlib.sha256(code.encode()).hexdigest()