from pydantic import BaseModel, EmailStr, Field, field_validator

DOZWOLONE_DOMENY = ("@uj.edu.pl", "@student.uj.edu.pl")


class RegisterRequest(BaseModel):
    email: EmailStr
    haslo: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def sprawdz_domene(cls, wartosc: str) -> str:
        if not wartosc.lower().endswith(DOZWOLONE_DOMENY):
            raise ValueError("Rejestracja tylko dla adresów @uj.edu.pl lub @student.uj.edu.pl")
        return wartosc


class MessageResponse(BaseModel):
    detail: str
