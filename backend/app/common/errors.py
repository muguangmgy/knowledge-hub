class AppError(Exception):
    """可映射为统一 JSON 响应的业务错误。"""

    def __init__(self, code: int, message: str, http_status: int = 400):
        """code 为业务错误码；http_status 为 HTTP 状态。"""
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


class ErrorCode:
    """业务错误码常量（与设计文档对齐）。"""

    BAD_REQUEST = 40001  # 参数错误（无效 mode / 混聊 / 删内置菜单或角色等）
    UNAUTHORIZED = 40101  # 未登录 / Token 无效 / 用户禁用
    BAD_CREDENTIALS = 40102  # 用户名或密码错误
    USERNAME_EXISTS = 40902  # 用户名已存在
    ROLE_EXISTS = 40903  # 角色 code 已存在
    NOT_FOUND = 40401
    DOC_EXISTS = 40901
    PAYLOAD_TOO_LARGE = 41301
    UNSUPPORTED_TYPE = 42201
    INGEST_FAILED = 50001  # 入库失败（含入库 Embedding）
    LLM_FAILED = 50010  # 问答阶段 LLM/Embedding
    INTERNAL = 50000
