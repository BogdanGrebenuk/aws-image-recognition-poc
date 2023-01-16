from dataclasses import dataclass, asdict


@dataclass
class Dto:

    def as_dict(self):
        return asdict(self)


@dataclass
class UploadInitializingResult(Dto):
    blob_id: str
    upload_url: str
    callback_url: str


@dataclass
class RecognitionStepFunctionResult(Dto):
    blob_id: str
    labels: list
