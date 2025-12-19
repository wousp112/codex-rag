from enum import Enum


class ErrorCode(str, Enum):
    CONFIG_MISSING = "CONFIG_MISSING"
    CONFIG_INVALID = "CONFIG_INVALID"
    INIT_EXISTS = "INIT_EXISTS"
    PARSE_MISSING_KEY = "PARSE_MISSING_KEY"
    PARSE_NO_FILES = "PARSE_NO_FILES"
    CHUNK_NO_PARSED = "CHUNK_NO_PARSED"
    EMBED_NO_CHUNKS = "EMBED_NO_CHUNKS"
    QUERY_NO_BUILD = "QUERY_NO_BUILD"
    QUERY_NO_INDEX = "QUERY_NO_INDEX"
    QUERY_CITABLE_VIOLATION = "QUERY_CITABLE_VIOLATION"
    VERIFY_NO_DOC = "VERIFY_NO_DOC"
    META_DOC_NOT_FOUND = "META_DOC_NOT_FOUND"
    GENERAL = "GENERAL_ERROR"


class RagError(Exception):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.GENERAL):
        super().__init__(message)
        self.code = code
