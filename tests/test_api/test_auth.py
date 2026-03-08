"""
Authentication API Tests
Comprehensive tests for all authentication endpoints
"""

import pytest
from fastapi import status
from datetime import datetime, timedelta
import time

from backend.core.auth.jwt import create_access_token, verify_token


class TestAuthAPI:
    """Test authentication endpoints"""
    
    def test_register_success(self, client, user_data):
        """Test successful user registration"""
        response = client.post("/api/v1/auth/register", json=user_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == user_data["email"]
        assert data["username"] == user_data["username"]
        assert "user_id" in data
        assert "message" in data
    
    def test_register_duplicate_email(self, client, user_data, test_user):
        """Test registration with existing email"""
        user_data["email"] = test_user.email
        response = client.post("/api/v1/auth/register", json=user_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already registered" in response.text.lower()
    
    def test_register_duplicate_username(self, client, user_data, test_user):
        """Test registration with existing username"""
        user_data["username"] = test_user.username
        response = client.post("/api/v1/auth/register", json=user_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already taken" in response.text.lower()
    
    def test_register_invalid_email(self, client, user_data):
        """Test registration with invalid email"""
        user_data["email"] = "invalid-email"
        response = client.post("/api/v1/auth/register", json=user_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_register_weak_password(self, client, user_data):
        """Test registration with weak password"""
        user_data["password"] = "weak"
        response = client.post("/api/v1/auth/register", json=user_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_login_success(self, client, test_user):
        """Test successful login"""
        response = client.post("/api/v1/auth/login", data={
            "username": test_user.username,
            "password": "Test@123456"
        })
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
    
    def test_login_wrong_password(self, client, test_user):
        """Test login with wrong password"""
        response = client.post("/api/v1/auth/login", data={
            "username": test_user.username,
            "password": "wrongpassword"
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user"""
        response = client.post("/api/v1/auth/login", data={
            "username": "nonexistent",
            "password": "Test@123456"
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_login_account_locked(self, client, test_user):
        """Test login with locked account"""
        # Simulate multiple failed attempts
        for _ in range(6):
            client.post("/api/v1/auth/login", data={
                "username": test_user.username,
                "password": "wrong"
            })
        
        response = client.post("/api/v1/auth/login", data={
            "username": test_user.username,
            "password": "Test@123456"
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "locked" in response.text.lower()
    
    def test_login_unverified_email(self, client, user_data):
        """Test login with unverified email"""
        # Create unverified user
        user_data["email_verified"] = False
        response = client.post("/api/v1/auth/register", json=user_data)
        
        response = client.post("/api/v1/auth/login", data={
            "username": user_data["username"],
            "password": user_data["password"]
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "verify" in response.text.lower()
    
    def test_refresh_token_success(self, client, test_user):
        """Test successful token refresh"""
        # First login
        login_response = client.post("/api/v1/auth/login", data={
            "username": test_user.username,
            "password": "Test@123456"
        })
        refresh_token = login_response.json()["refresh_token"]
        
        # Refresh token
        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token
        })
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_refresh_token_invalid(self, client):
        """Test refresh with invalid token"""
        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": "invalid_token"
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_refresh_token_expired(self, client, test_user):
        """Test refresh with expired token"""
        # Create expired token
        expired_token = create_access_token(
            data={"sub": str(test_user.id)},
            expires_delta=timedelta(seconds=-1)
        )
        
        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": expired_token
        })
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_logout_success(self, client, auth_headers):
        """Test successful logout"""
        response = client.post("/api/v1/auth/logout", headers=auth_headers)
        
        assert response.status_code == status.HTTP_200_OK
        assert "success" in response.text.lower()
    
    def test_logout_without_token(self, client):
        """Test logout without authentication"""
        response = client.post("/api/v1/auth/logout")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_verify_email_success(self, client, user_data):
        """Test email verification"""
        # Register user
        register_response = client.post("/api/v1/auth/register", json=user_data)
        user_id = register_response.json()["user_id"]
        
        # Get verification token (in real app, would be emailed)
        # For test, we need to get it from database
        from backend.data.repositories.user_repo import UserRepository
        from backend.data.database import SessionLocal
        
        db = SessionLocal()
        user_repo = UserRepository(db)
        user = user_repo.get(user_id)
        token = user.email_verification_token
        db.close()
        
        # Verify email
        response = client.post(f"/api/v1/auth/verify-email/{token}")
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_verify_email_invalid_token(self, client):
        """Test email verification with invalid token"""
        response = client.post("/api/v1/auth/verify-email/invalid_token")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_resend_verification(self, client, user_data):
        """Test resend verification email"""
        # Register user
        client.post("/api/v1/auth/register", json=user_data)
        
        response = client.post("/api/v1/auth/resend-verification", json={
            "email": user_data["email"]
        })
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_forgot_password(self, client, test_user):
        """Test forgot password"""
        response = client.post("/api/v1/auth/forgot-password", json={
            "email": test_user.email
        })
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_forgot_password_nonexistent(self, client):
        """Test forgot password with non-existent email"""
        response = client.post("/api/v1/auth/forgot-password", json={
            "email": "nonexistent@example.com"
        })
        
        # Should still return success for security
        assert response.status_code == status.HTTP_200_OK
    
    def test_reset_password(self, client, test_user):
        """Test password reset"""
        # Request reset
        client.post("/api/v1/auth/forgot-password", json={
            "email": test_user.email
        })
        
        # Get reset token from database
        from backend.data.repositories.user_repo import UserRepository
        from backend.data.database import SessionLocal
        
        db = SessionLocal()
        user_repo = UserRepository(db)
        user = user_repo.get(test_user.id)
        token = user.password_reset_token
        db.close()
        
        # Reset password
        response = client.post("/api/v1/auth/reset-password", json={
            "token": token,
            "new_password": "NewTest@123456"
        })
        
        assert response.status_code == status.HTTP_200_OK
        
        # Try login with new password
        login_response = client.post("/api/v1/auth/login", data={
            "username": test_user.username,
            "password": "NewTest@123456"
        })
        
        assert login_response.status_code == status.HTTP_200_OK
    
    def test_change_password(self, client, auth_headers, test_user):
        """Test change password"""
        response = client.post("/api/v1/auth/change-password", 
            json={
                "current_password": "Test@123456",
                "new_password": "Changed@123456"
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Try login with new password
        login_response = client.post("/api/v1/auth/login", data={
            "username": test_user.username,
            "password": "Changed@123456"
        })
        
        assert login_response.status_code == status.HTTP_200_OK
    
    def test_change_password_wrong_current(self, client, auth_headers):
        """Test change password with wrong current password"""
        response = client.post("/api/v1/auth/change-password", 
            json={
                "current_password": "wrong",
                "new_password": "Changed@123456"
            },
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_enable_2fa(self, client, auth_headers):
        """Test enable 2FA"""
        response = client.post("/api/v1/auth/enable-2fa", headers=auth_headers)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "secret" in data
        assert "qr_code" in data
        assert "backup_codes" in data
    
    def test_verify_2fa(self, client, auth_headers):
        """Test verify and enable 2FA"""
        # Enable 2FA first
        enable_response = client.post("/api/v1/auth/enable-2fa", headers=auth_headers)
        secret = enable_response.json()["secret"]
        
        # Generate valid code
        import pyotp
        totp = pyotp.TOTP(secret)
        code = totp.now()
        
        # Verify
        response = client.post("/api/v1/auth/verify-2fa", 
            json={"code": code},
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_verify_2fa_invalid_code(self, client, auth_headers):
        """Test verify 2FA with invalid code"""
        response = client.post("/api/v1/auth/verify-2fa", 
            json={"code": "123456"},
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_disable_2fa(self, client, auth_headers):
        """Test disable 2FA"""
        # Enable 2FA first
        enable_response = client.post("/api/v1/auth/enable-2fa", headers=auth_headers)
        secret = enable_response.json()["secret"]
        
        # Generate valid code
        import pyotp
        totp = pyotp.TOTP(secret)
        code = totp.now()
        
        # Verify
        client.post("/api/v1/auth/verify-2fa", 
            json={"code": code},
            headers=auth_headers
        )
        
        # Disable
        response = client.post("/api/v1/auth/disable-2fa", 
            json={"code": code},
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_sessions(self, client, auth_headers):
        """Test get active sessions"""
        response = client.get("/api/v1/auth/sessions", headers=auth_headers)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "sessions" in data
        assert "current_session_id" in data
    
    def test_revoke_session(self, client, auth_headers):
        """Test revoke a session"""
        # Get sessions first
        sessions_response = client.get("/api/v1/auth/sessions", headers=auth_headers)
        sessions = sessions_response.json()["sessions"]
        
        if len(sessions) > 1:
            # Find non-current session
            for session in sessions:
                if not session["is_current"]:
                    response = client.delete(
                        f"/api/v1/auth/sessions/{session['id']}",
                        headers=auth_headers
                    )
                    assert response.status_code == status.HTTP_200_OK
                    break
    
    def test_revoke_all_sessions(self, client, auth_headers):
        """Test revoke all other sessions"""
        response = client.delete("/api/v1/auth/sessions", headers=auth_headers)
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_rate_limiting(self, client, user_data):
        """Test rate limiting on login endpoint"""
        # Make multiple rapid requests
        for _ in range(15):
            response = client.post("/api/v1/auth/login", data={
                "username": "test",
                "password": "test"
            })
        
        # Should be rate limited
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS