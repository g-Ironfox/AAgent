from bson import ObjectId
from bson.errors import InvalidId
from fastapi.responses import JSONResponse


def parse_object_id(value: str, error_message: str) -> ObjectId | JSONResponse:
    try:
        return ObjectId(value)
    except InvalidId:
        return JSONResponse(status_code=400, content={"error": error_message})