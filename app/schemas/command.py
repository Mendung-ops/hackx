from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.command import CommandAction, CommandSource, CommandStatus


class CommandCreate(BaseModel):
    device_id: int
    action: CommandAction
    source: CommandSource = CommandSource.MANUAL
    reason: str | None = Field(default=None, max_length=255)


class CommandRead(CommandCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: CommandStatus
    created_at: datetime
    executed_at: datetime | None = None
