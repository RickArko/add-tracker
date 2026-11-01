from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

Category = Literal[
    "alcohol",
    "nicotine",
    "cannabis",
    "opioid",
    "benzodiazepine",
    "stimulant",
    "caffeine",
    "gambling",
    "behavior",
    "other",
]
Goal = Literal["quit", "reduce", "manage", "observe"]
EntryKind = Literal["use", "urge"]

Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=40,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    ),
]
NewPassword = Annotated[str, StringConstraints(min_length=10, max_length=200)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Unit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Amount = Annotated[float, Field(gt=0, le=100_000)]
Limit = Annotated[float, Field(ge=0, le=100_000)]
Craving = Annotated[int, Field(ge=0, le=10)]
Trigger = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictBody):
    username: Username
    password: NewPassword


class LoginBody(StrictBody):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


class PasswordChange(StrictBody):
    current_password: str = Field(max_length=200)
    new_password: NewPassword


class AccountDelete(StrictBody):
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    username: str
    has_recovery_code: bool = False
    has_email: bool = False


class WithRecoveryCode(UserOut):
    recovery_code: str


class AuthStatus(BaseModel):
    user: UserOut | None
    signup_open: bool
    first_run: bool
    email_enabled: bool


# Plain ASCII only, lowercased, so the address hashed is exactly the address mailed.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=254,
        pattern=r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$",
    ),
]


class RecoverBody(StrictBody):
    username: str = Field(max_length=40)
    recovery_code: str = Field(max_length=60)
    new_password: NewPassword


class PasswordConfirm(StrictBody):
    password: str = Field(max_length=200)


class EmailAdd(StrictBody):
    email: Email
    password: str = Field(max_length=200)


class EmailRequest(StrictBody):
    email: Email


class TokenBody(StrictBody):
    token: str = Field(max_length=100)


class TokenReset(StrictBody):
    token: str = Field(max_length=100)
    new_password: NewPassword


class TrackerCreate(StrictBody):
    name: Name
    category: Category = "other"
    goal: Goal = "reduce"
    unit: Unit = "time"
    default_amount: Amount = 1
    daily_limit: Limit | None = None


class TrackerUpdate(StrictBody):
    name: Name | None = None
    category: Category | None = None
    goal: Goal | None = None
    unit: Unit | None = None
    default_amount: Amount | None = None
    daily_limit: Limit | None = None
    archived: bool | None = None


class TrackerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: Category
    goal: Goal
    unit: str
    default_amount: float
    daily_limit: float | None
    created_at: datetime
    archived_at: datetime | None
    baseline_amount: float | None
    step_amount: float | None
    clear_days: int | None
    plan_started_on: str | None


class NoUseBody(StrictBody):
    day: date


class PlanBody(StrictBody):
    baseline_amount: Amount
    step_amount: Annotated[float, Field(ge=0.01, le=100_000)]
    clear_days: Annotated[int, Field(ge=1, le=90)] = 7


class TodayTracker(TrackerOut):
    uses_today: int
    amount_today: float
    urges_today: int
    last_use_at: datetime | None
    game: dict


class EntryCreate(StrictBody):
    tracker_id: Annotated[int, Field(ge=1, le=2**63 - 1)]
    kind: EntryKind = "use"
    occurred_at: AwareDatetime | None = None
    amount: Amount | None = None
    craving: Craving | None = None
    trigger: Trigger | None = None
    note: Note | None = None
    client_id: Annotated[str, StringConstraints(min_length=8, max_length=64)] | None = None


class EntryUpdate(StrictBody):
    occurred_at: AwareDatetime | None = None
    amount: Amount | None = None
    craving: Craving | None = None
    trigger: Trigger | None = None
    note: Note | None = None

    @field_validator("occurred_at")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("occurred_at cannot be cleared")
        return value


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tracker_id: int
    kind: EntryKind
    occurred_at: datetime
    amount: float | None
    craving: int | None
    trigger: str | None
    note: str | None
