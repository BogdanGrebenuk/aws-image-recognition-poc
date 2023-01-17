class RecognitionBaseException(Exception):

    def __init__(self, message, payload=None):
        if payload is None:
            payload = {}
        super().__init__(message)
        self.payload = payload


class CallbackUrlIsNotValid(RecognitionBaseException):
    ... # todo


class BlobWasNotFound(RecognitionBaseException):
    ... # todo


class BlobIsNotUploadedYet(RecognitionBaseException):
    ... # todo


class BlobUploadTimedOut(RecognitionBaseException):
    ... # todo


class BlobRecognitionIsInProgress(RecognitionBaseException):
    ... # todo


class InvalidBlobHasBeenUploaded(RecognitionBaseException):
    ... # todo


class TooLargeBlobHasBeenUploaded(RecognitionBaseException):
    ... # todo


class RecognitionStepHasBeenFailed(RecognitionBaseException):
    ... # todo
