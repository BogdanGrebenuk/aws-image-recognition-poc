"""Module with domain-related code."""

from enum import Enum


class RecognitionStatus(Enum):
    """Enum with possible statuses of recognition process."""
    WAITING_FOR_UPLOAD = 'waiting-for-upload'
    UPLOAD_TIMED_OUT = 'upload-timed-out'
    IN_PROGRESS = 'in-progress'
    INVALID_BLOB_HAS_BEEN_UPLOADED = 'invalid-blob-has-been-uploaded'
    TOO_LARGE_BLOB_HAS_BEEN_UPLOADED = 'too-large-blob-has-been-uploaded'
    SUCCESS = 'success'
    FAILED_DUE_TO_CALLBACK_FAILURE = 'failed-due-to-callback-failure'
    FAILED_DUE_TO_CALLBACK_TIME_OUT = 'failed-due-to-callback-time-out'
    FAILED_DUE_TO_CALLBACK_CONNECTION = 'failed-due-to-callback-connection'
    NOT_FOUND = 'not-found'
    UNEXPECTED_ERROR = 'unexpected-error'
