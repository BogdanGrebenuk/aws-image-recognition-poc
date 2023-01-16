from enum import Enum


class RecognitionStatus(Enum):
    WAITING_FOR_UPLOAD = 'waiting-for-upload'
    UPLOAD_TIMED_OUT = 'upload-timed-out'
    IN_PROGRESS = 'in-progress'
    SUCCESS = 'success'
    FAILED_DUE_TO_CALLBACK_FAILURE = 'failed-due-to-callback-failure'
    FAILED_DUE_TO_CALLBACK_TIME_OUT = 'failed-due-to-callback-time-out'
    FAILED_DUE_TO_CALLBACK_CONNECTION = 'failed-due-to-callback-connection'
