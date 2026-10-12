"""统一响应体：{ code, message, data }。业务成功固定 code=0。"""

from typing import Any

from fastapi.responses import JSONResponse


def ok(data: Any = None, message: str = "success") -> dict[str, Any]:
    """业务成功响应（HTTP 通常 200）。"""
    return {"code": 0, "message": message, "data": data if data is not None else {}}


def fail(code: int, message: str, http_status: int = 400) -> JSONResponse:
    """业务失败：HTTP status 与业务 code 分离。"""
    return JSONResponse(
        status_code=http_status,
        content={"code": code, "message": message, "data": {}},
    )
