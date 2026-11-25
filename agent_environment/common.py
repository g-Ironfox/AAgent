from fastapi.responses import JSONResponse


def limit_error(limit: int) -> JSONResponse | None:
    if limit < 1 or limit > 300:
        return JSONResponse(status_code=400, content={"error": "limit must be between 1 and 300"})
    return None