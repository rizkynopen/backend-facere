from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional


# --- RESPONSE SCHEMA (STANDARD) ---
class StandardResponse(BaseModel):
    status: str = "success"  # success atau error
    message: str
    data: Optional[dict] = None


# --- SKEMA UNTUK AUTHENTICATION ---
class RegisterUser(BaseModel):
    email: EmailStr = Field(..., description="Email valid")
    password: str = Field(..., min_length=6, description="Password minimal 6 karakter")
    nama_lengkap: str = Field(..., min_length=3, description="Nama minimal 3 karakter")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "password123",
                "nama_lengkap": "Budi Santoso",
            }
        }


class LoginUser(BaseModel):
    email: EmailStr
    password: str

    class Config:
        json_schema_extra = {
            "example": {"email": "user@example.com", "password": "password123"}
        }


# --- SKEMA UNTUK CHANGE PASSWORD ---
class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)

    class Config:
        json_schema_extra = {
            "example": {"old_password": "password123", "new_password": "newpassword456"}
        }


# --- SKEMA UNTUK LAPORAN (REPORTS) ---
class LaporanBaru(BaseModel):
    # user_id dihapus karena sekarang diambil dari token (lebih aman)
    category_id: int = Field(..., description="ID kategori laporan")
    deskripsi: str = Field(
        ..., min_length=10, description="Deskripsi minimal 10 karakter"
    )
    latitude: float = Field(..., ge=-90, le=90, description="Latitude koordinat")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude koordinat")
    foto_url: Optional[str] = Field(None, description="URL foto laporan")

    class Config:
        json_schema_extra = {
            "example": {
                "category_id": 1,
                "deskripsi": "Jalan di depan kantor lurah rusak berat, berlubang.",
                "latitude": -0.5,
                "longitude": 101.4,
                "foto_url": "https://storage.example.com/foto.jpg",
            }
        }


# --- SKEMA UNTUK ADMIN (UPDATE STATUS) ---
class UpdateStatusLaporan(BaseModel):
    # user_id dihapus karena sekarang diambil dari token
    status: Literal["Menunggu", "Sedang Diperbaiki", "Selesai"] = Field(
        ..., description="Status: Menunggu, Sedang Diperbaiki, atau Selesai"
    )

    class Config:
        json_schema_extra = {"example": {"status": "Sedang Diperbaiki"}}


# --- SKEMA UNTUK UPDATE PROFIL ---
class UpdateProfileRequest(BaseModel):
    nama_lengkap: str = Field(..., min_length=3, description="Nama minimal 3 karakter")

    class Config:
        json_schema_extra = {"example": {"nama_lengkap": "Budi Santoso"}}


# --- SKEMA UNTUK FORGOT PASSWORD ---
class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="Email yang terdaftar")

    class Config:
        json_schema_extra = {"example": {"email": "user@example.com"}}


# --- SKEMA UNTUK RESET PASSWORD ---
class ResetPasswordRequest(BaseModel):
    access_token: str = Field(..., description="Token dari link reset password")
    refresh_token: str = Field(..., description="Refresh token dari link reset password")
    new_password: str = Field(..., min_length=6, description="Password baru minimal 6 karakter")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "token-dari-email",
                "refresh_token": "refresh-token-dari-email",
                "new_password": "passwordbaru123",
            }
        }

