"""Module with custom exceptions."""


class RecognitionBaseException(Exception):
    """Base exception for package-related errors.

    Attributes:
        payload (dict): Additional data of error context.

    """

    def __init__(self, message, payload=None):
        if payload is None:
            payload = {}
        super().__init__(message)
        self.payload = payload


class CallbackUrlIsNotValid(RecognitionBaseException):
    """Called when invalid callback url is passed in."""


class BlobWasNotFound(RecognitionBaseException):
    """Called when requested blob is not found."""""


class BlobIsNotUploadedYet(RecognitionBaseException):
    """Called when requested blob has not been uploaded yet."""


class BlobUploadTimedOut(RecognitionBaseException):
    """Called when requested blob upload is timed out."""


class BlobRecognitionIsInProgress(RecognitionBaseException):
    """Called when blob recognition process hasn't completed yet."""


class InvalidBlobHasBeenUploaded(RecognitionBaseException):
    """Called when invalid blob has been uploaded."""


class TooLargeBlobHasBeenUploaded(RecognitionBaseException):
    """Called when too large blob has been uploaded."""


class RecognitionStepHasBeenFailed(RecognitionBaseException):
    """Called when recognition step has been failed."""


class UnexpectedErrorOccurred(RecognitionBaseException):
    """Called when unexpected error occurred while recognition."""
