from enum import Enum


class RecognitionStatus(Enum):
    WAITING_FOR_UPLOAD = 'waiting-for-upload'
    UPLOAD_TIMED_OUT = 'upload-timed-out'
    IN_PROGRESS = 'in-progress'
    # todo: make other
