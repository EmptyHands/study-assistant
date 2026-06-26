"""Study Assistant 自定义异常类"""


class StudyAssistantException(Exception):
    def __init__(self, message: str, error_code: str = None, status_code: int = 500):
        self.message = message
        self.error_code = error_code or "INTERNAL_ERROR"
        self.status_code = status_code
        super().__init__(self.message)


class AgentException(StudyAssistantException):
    def __init__(self, message: str, error_code: str = "AGENT_ERROR"):
        super().__init__(message, error_code, 500)


class VectorStoreException(StudyAssistantException):
    def __init__(self, message: str):
        super().__init__(message, "VECTOR_STORE_ERROR", 500)


class DatabaseException(StudyAssistantException):
    def __init__(self, message: str):
        super().__init__(message, "DATABASE_ERROR", 500)


class LLMException(StudyAssistantException):
    def __init__(self, message: str):
        super().__init__(message, "LLM_ERROR", 500)


class FileParseException(StudyAssistantException):
    def __init__(self, message: str):
        super().__init__(message, "FILE_PARSE_ERROR", 400)


class GitCloneException(StudyAssistantException):
    def __init__(self, message: str):
        super().__init__(message, "GIT_CLONE_ERROR", 400)


class NotFoundException(StudyAssistantException):
    def __init__(self, message: str):
        super().__init__(message, "NOT_FOUND", 404)


class ValidationException(StudyAssistantException):
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR", 400)


class TimeoutException(StudyAssistantException):
    def __init__(self, message: str = "请求超时"):
        super().__init__(message, "TIMEOUT", 408)
