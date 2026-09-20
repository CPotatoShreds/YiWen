"""业务错误：携带机器可读错误码。

响应体 {"detail": <人读文案>, "code": <错误码>}，并回写 X-Error-Code 响应头；
前端按 code 分支、按 detail 展示。存量 HTTPException（纯 detail 字符串）行为
不变，新代码建议统一抛 AppError。
"""


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)
