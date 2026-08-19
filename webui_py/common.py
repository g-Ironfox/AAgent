from bson import ObjectId
from bson.errors import InvalidId
from fastapi.responses import JSONResponse


def limit_error(limit: int) -> JSONResponse | None:
    if limit < 1 or limit > 300:
        return JSONResponse(status_code=400, content={"error": "limit must be between 1 and 300"})
    return None


def parse_object_id(value: str, error_message: str) -> ObjectId | JSONResponse:
    try:
        return ObjectId(value)
    except InvalidId:
        return JSONResponse(status_code=400, content={"error": error_message})