"""Accounts, profile, goals and invitations (cadence's own users; wger never sees them)."""

import re
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import auth, nutrition, security, store
from .config import settings
from .meals import local_now

router = APIRouter()

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_login_throttle = auth.Throttle(limit=8, window_s=15 * 60)
_register_throttle = auth.Throttle(limit=10, window_s=3600)


# ------------------------------------------------------------------ schemas

class RegisterIn(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=8, max_length=128)
    invite: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class PasswordIn(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=128)


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    sex: str
    birthdate: date
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(ge=30, le=300)
    activity: str
    goal: str
    target_weight_kg: float | None = Field(default=None, ge=30, le=300)
    kcal: float | None = Field(default=None, ge=800, le=6000)  # the user nudged the calculated calories


class GoalsIn(BaseModel):
    goal: str | None = None
    target_weight_kg: float | None = Field(default=None, ge=30, le=300)
    kcal: float | None = Field(default=None, ge=800, le=6000)
    protein_g: float | None = Field(default=None, ge=0, le=500)
    carbs_g: float | None = Field(default=None, ge=0, le=1000)
    fat_g: float | None = Field(default=None, ge=0, le=500)


class WeightIn(BaseModel):
    kg: float = Field(ge=30, le=300)
    day: date | None = None


class InviteIn(BaseModel):
    note: str | None = None


class TargetsOut(BaseModel):
    kcal: int
    protein_g: int
    carbs_g: int
    fat_g: int
    maintenance_kcal: int | None = None
    note: str | None = None


class ProfileOut(BaseModel):
    sex: str | None = None
    birthdate: str | None = None
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    activity: str | None = None
    goal: str | None = None
    target_weight_kg: float | None = None


class MeOut(BaseModel):
    id: int
    email: str
    name: str
    is_admin: bool
    onboarded: bool
    profile: ProfileOut
    targets: TargetsOut | None = None


# ------------------------------------------------------------------ helpers

def _today() -> date:
    return local_now().date()


def me_out(user: store.User) -> MeOut:
    age = None
    if user.birthdate:
        age = nutrition.age_on(date.fromisoformat(user.birthdate), _today())
    targets = None
    if user.goal_kcal:
        targets = TargetsOut(kcal=round(user.goal_kcal), protein_g=round(user.goal_protein or 0),
                             carbs_g=round(user.goal_carbs or 0), fat_g=round(user.goal_fat or 0))
    return MeOut(
        id=user.id, email=user.email, name=user.name, is_admin=user.is_admin, onboarded=user.onboarded,
        profile=ProfileOut(sex=user.sex, birthdate=user.birthdate, age=age, height_cm=user.height_cm,
                           weight_kg=store.latest_weight(user.id), activity=user.activity, goal=user.goal,
                           target_weight_kg=user.target_weight_kg),
        targets=targets,
    )


def _validate_profile(body: ProfileIn) -> None:
    if body.sex not in nutrition.SEXES:
        raise HTTPException(422, "Elige una opción de sexo")
    if body.activity not in nutrition.ACTIVITY:
        raise HTTPException(422, "Elige tu nivel de actividad")
    if body.goal not in nutrition.GOALS:
        raise HTTPException(422, "Elige tu objetivo")
    age = nutrition.age_on(body.birthdate, _today())
    if age < 13 or age > 110:
        raise HTTPException(422, "cadence es para personas de 13 años o más" if age < 13 else "Revisa tu fecha de nacimiento")


def _targets(body: ProfileIn) -> nutrition.Targets:
    return nutrition.compute_targets(body.sex, body.birthdate, body.height_cm, body.weight_kg, body.activity, body.goal, _today())


# ------------------------------------------------------------------ auth

@router.get("/api/auth/status")
def auth_status():
    """What the login screen needs to know before anyone is signed in."""
    return {"first_user": store.count_users() == 0, "invite_required": not settings.open_registration}


@router.post("/api/auth/register", response_model=MeOut)
def register(body: RegisterIn, request: Request, response: Response):
    email = body.email.strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(422, "Escribe un correo válido")
    ip = auth.client_ip(request)
    if _register_throttle.blocked(ip):
        raise HTTPException(429, "Demasiados intentos. Prueba de nuevo en un rato.")
    user, reason = store.create_user(
        email, body.name.strip(), security.hash_password(body.password), body.invite,
        allow_open=settings.open_registration, first_user_email=settings.admin_email or None,
    )
    if user is None:
        if reason == "bad_invite":
            _register_throttle.fail(ip)
        raise HTTPException(
            {"exists": 409, "bad_invite": 403, "not_admin_email": 403}.get(reason, 400),
            {"exists": "Ese correo ya tiene una cuenta. Inicia sesión.",
             "bad_invite": "Código de invitación inválido o ya usado.",
             "not_admin_email": "Esta instalación aún no tiene cuenta de administrador y ese correo no puede crearla."}.get(reason, "No se pudo crear la cuenta"),
        )
    auth.set_session(response, request, user.id)
    return me_out(user)


@router.post("/api/auth/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    keys = (f"ip:{auth.client_ip(request)}", f"mail:{email}")
    if any(_login_throttle.blocked(k) for k in keys):
        raise HTTPException(429, "Demasiados intentos fallidos. Espera unos minutos.")
    user, stored = store.get_user_by_email(email)
    # Same work and same message whether the e-mail exists or not.
    ok = security.verify_password(body.password, stored or "scrypt$16384$8$1$00$00")
    if user is None or not ok:
        for k in keys:
            _login_throttle.fail(k)
        raise HTTPException(401, "Correo o contraseña incorrectos")
    for k in keys:
        _login_throttle.reset(k)
    auth.set_session(response, request, user.id)
    return me_out(user)


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    auth.clear_session(response, request)
    return {"status": "ok"}


@router.get("/api/auth/me", response_model=MeOut)
def me(user: store.User = Depends(auth.current_user)):
    return me_out(user)


@router.post("/api/auth/password")
def change_password(body: PasswordIn, request: Request, response: Response, user: store.User = Depends(auth.current_user)):
    _, stored = store.get_user_by_email(user.email)
    if not security.verify_password(body.current, stored or ""):
        raise HTTPException(403, "La contraseña actual no es correcta")
    store.update_user(user.id, password_hash=security.hash_password(body.new))
    store.delete_user_sessions(user.id)  # signs out every device, this one included...
    auth.set_session(response, request, user.id)  # ...and keeps this one signed in
    return {"status": "ok"}


# ------------------------------------------------------------------ profile and goals

@router.post("/api/plan/preview", response_model=TargetsOut)
def preview_plan(body: ProfileIn, user: store.User = Depends(auth.current_user)):
    _validate_profile(body)
    computed = _targets(body)
    if body.kcal:  # the user nudged the calories: same protein per kg, the rest re-split
        protein, carbs, fat = nutrition.macros_for_kcal(body.kcal, body.weight_kg, body.goal)
        computed = nutrition.Targets(kcal=round(body.kcal), protein_g=protein, carbs_g=carbs, fat_g=fat,
                                     maintenance_kcal=computed.maintenance_kcal, note=computed.note)
    return TargetsOut(**computed.__dict__)


@router.put("/api/profile", response_model=MeOut)
def save_profile(body: ProfileIn, user: store.User = Depends(auth.current_user)):
    """First-run questionnaire and later edits: stores the data and the calculated plan."""
    _validate_profile(body)
    computed = _targets(body)
    kcal = body.kcal or computed.kcal
    if body.kcal:
        protein, carbs, fat = nutrition.macros_for_kcal(body.kcal, body.weight_kg, body.goal)
    else:
        protein, carbs, fat = computed.protein_g, computed.carbs_g, computed.fat_g
    fields = dict(
        sex=body.sex, birthdate=body.birthdate.isoformat(), height_cm=body.height_cm, activity=body.activity,
        goal=body.goal, target_weight_kg=body.target_weight_kg, goal_kcal=kcal, goal_protein=protein,
        goal_carbs=carbs, goal_fat=fat, onboarded=True,
    )
    if body.name:
        fields["name"] = body.name.strip()
    store.update_user(user.id, **fields)
    store.set_weight(user.id, _today().isoformat(), body.weight_kg)
    return me_out(store.get_user(user.id))


@router.put("/api/goals", response_model=MeOut)
def save_goals(body: GoalsIn, user: store.User = Depends(auth.current_user)):
    if not user.onboarded or not user.birthdate:
        raise HTTPException(409, "Completa primero tu perfil")
    goal = body.goal or user.goal
    if goal not in nutrition.GOALS:
        raise HTTPException(422, "Objetivo no válido")
    weight = store.latest_weight(user.id) or 70
    kcal, protein, carbs, fat = user.goal_kcal, user.goal_protein, user.goal_carbs, user.goal_fat
    if body.goal and body.goal != user.goal:  # a new goal means a new calculation
        computed = nutrition.compute_targets(user.sex, date.fromisoformat(user.birthdate), user.height_cm, weight,
                                             user.activity, goal, _today())
        kcal, protein, carbs, fat = computed.kcal, computed.protein_g, computed.carbs_g, computed.fat_g
    if body.kcal is not None:
        kcal = body.kcal
        protein, carbs, fat = nutrition.macros_for_kcal(kcal, weight, goal)
    if body.protein_g is not None: protein = body.protein_g
    if body.carbs_g is not None: carbs = body.carbs_g
    if body.fat_g is not None: fat = body.fat_g
    fields = dict(goal=goal, goal_kcal=kcal, goal_protein=protein, goal_carbs=carbs, goal_fat=fat)
    if body.target_weight_kg is not None:
        fields["target_weight_kg"] = body.target_weight_kg
    store.update_user(user.id, **fields)
    return me_out(store.get_user(user.id))


@router.put("/api/name", response_model=MeOut)
def rename(body: dict, user: store.User = Depends(auth.current_user)):
    name = str(body.get("name", "")).strip()
    if not 1 <= len(name) <= 40:
        raise HTTPException(422, "Escribe un nombre de hasta 40 caracteres")
    store.update_user(user.id, name=name)
    return me_out(store.get_user(user.id))


@router.get("/api/weights")
def weights(days: int = 180, user: store.User = Depends(auth.current_user)):
    since = _today() - timedelta(days=max(1, min(days, 3650)))
    return store.weights_since(user.id, since.isoformat())


@router.delete("/api/weight/{day}")
def delete_weight(day: date, user: store.User = Depends(auth.current_user)):
    if not store.delete_weight(user.id, day.isoformat()):
        raise HTTPException(404, "No hay un peso en ese día")
    return {"status": "deleted"}


@router.post("/api/weight", response_model=MeOut)
def log_weight(body: WeightIn, user: store.User = Depends(auth.current_user)):
    day = (body.day or _today())
    if day > _today():
        raise HTTPException(422, "No se puede registrar un peso en el futuro")
    store.set_weight(user.id, day.isoformat(), body.kg)
    return me_out(store.get_user(user.id))


# ------------------------------------------------------------------ administration

@router.get("/api/admin/overview")
def admin_overview(_: store.User = Depends(auth.require_admin)):
    return {
        "invites": store.list_invites(),
        "users": [{"id": u.id, "name": u.name, "email": u.email, "is_admin": u.is_admin, "created_at": u.created_at}
                  for u in store.list_users()],
        "open_registration": settings.open_registration,
    }


@router.post("/api/admin/invites")
def create_invite(body: InviteIn, admin: store.User = Depends(auth.require_admin)):
    code = security.new_invite_code()
    store.create_invite(code, body.note, admin.id)
    return {"code": code}


@router.delete("/api/admin/invites/{code}")
def delete_invite(code: str, _: store.User = Depends(auth.require_admin)):
    if not store.delete_invite(code):
        raise HTTPException(404, "Esa invitación no existe o ya se usó")
    return {"status": "deleted"}


@router.post("/api/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, _: store.User = Depends(auth.require_admin)):
    """A single-use code (valid 24 h) the person types on the sign-in screen to choose a new
    password. Their current password keeps working until they do."""
    target = store.get_user(user_id)
    if target is None:
        raise HTTPException(404, "Usuario no encontrado")
    code = security.new_invite_code()
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    store.create_reset(user_id, security.token_hash(_norm_code(code)), expires)
    return {"code": code, "email": target.email}


def _norm_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


class ResetIn(BaseModel):
    email: str
    code: str
    password: str = Field(min_length=8, max_length=128)


@router.post("/api/auth/reset", response_model=MeOut)
def use_reset_code(body: ResetIn, request: Request, response: Response):
    email = body.email.strip().lower()
    keys = (f"ip:{auth.client_ip(request)}", f"mail:{email}")
    if any(_login_throttle.blocked(k) for k in keys):
        raise HTTPException(429, "Demasiados intentos fallidos. Espera unos minutos.")
    user, _ = store.get_user_by_email(email)
    ok = user is not None and store.consume_reset(user.id, security.token_hash(_norm_code(body.code)))
    if not ok:
        for k in keys:
            _login_throttle.fail(k)
        raise HTTPException(403, "Ese código no es válido, ya se usó o venció. Pide uno nuevo al administrador.")
    for k in keys:
        _login_throttle.reset(k)
    store.update_user(user.id, password_hash=security.hash_password(body.password))
    store.delete_user_sessions(user.id)
    auth.set_session(response, request, user.id)
    return me_out(user)
