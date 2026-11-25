import math

from bson import ObjectId
from bson.errors import InvalidId
from fastapi.responses import JSONResponse


def is_number_value(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, float) and math.isfinite(value)
    )


def parse_object_id(value: str, error_message: str) -> ObjectId | JSONResponse:
    try:
        return ObjectId(value)
    except InvalidId:
        return JSONResponse(status_code=400, content={"error": error_message})
