"""
riva/asr.py

Streaming NVIDIA Riva Speech-to-Text client.
"""

from dataclasses import dataclass
from importlib import metadata, util
from pathlib import Path
import sys
import time
from typing import Iterable, Iterator

from config import (
    RIVA_SERVER,
    SAMPLE_RATE,
    CHANNELS,
    SOURCE_LANGUAGE,
)


def _load_riva_client():
    """Load the installed NVIDIA Riva client package.

    The project has a local `riva` package, so a normal `import riva.client`
    resolves to this workspace instead of the pip-installed client library.
    """

    distribution = metadata.distribution("nvidia-riva-client")

    init_path = None

    for package_file in distribution.files or []:

        if str(package_file).endswith("riva/client/__init__.py"):

            init_path = distribution.locate_file(package_file)
            break

    if init_path is None:

        raise ModuleNotFoundError(
            "Unable to locate the installed nvidia-riva-client package"
        )

    spec = util.spec_from_file_location(
        "riva.client",
        init_path,
        submodule_search_locations=[str(Path(init_path).parent)],
    )

    if spec is None or spec.loader is None:

        raise ModuleNotFoundError(
            "Unable to load the installed riva.client module"
        )

    module = util.module_from_spec(spec)
    sys.modules["riva.client"] = module
    spec.loader.exec_module(module)

    return module


riva = _load_riva_client()


@dataclass
class ASRResult:
    """Represents one Riva recognition result."""

    text: str
    is_final: bool
    stability: float = 0.0
    timestamp: float = 0.0


class RivaASR:
    """Streaming Riva ASR client."""

    def __init__(
        self,
        server: str = RIVA_SERVER,
        language: str = SOURCE_LANGUAGE,
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
    ):

        self.server = server
        self.language = language
        self.sample_rate = sample_rate
        self.channels = channels

        # Connect to Riva.
        self.auth = riva.Auth(
            uri=self.server
        )

        self.service = riva.ASRService(
            self.auth
        )

        # Speech recognition configuration.
        self.config = riva.RecognitionConfig(
            encoding=riva.AudioEncoding.LINEAR_PCM,
            sample_rate_hertz=self.sample_rate,
            language_code=self.language,
            max_alternatives=1,
            enable_automatic_punctuation=True,
            audio_channel_count=self.channels,
        )

        # Enable streaming + interim results.
        self.streaming_config = (
            riva.StreamingRecognitionConfig(
                config=self.config,
                interim_results=True,
            )
        )

    def _requests(
        self,
        audio_chunks: Iterable[bytes]
    ):
        """
        Convert microphone audio chunks into
        Riva streaming requests.
        """

        # First request sends the configuration.
        yield riva.StreamingRecognizeRequest(
            streaming_config=self.streaming_config
        )

        # Following requests contain audio.
        for chunk in audio_chunks:

            if chunk:

                yield riva.StreamingRecognizeRequest(
                    audio_content=chunk
                )

    def transcribe(
        self,
        audio_chunks: Iterable[bytes]
    ) -> Iterator[ASRResult]:
        """
        Send microphone audio to Riva and yield
        partial and final recognition results.
        """

        responses = (
            self.service.streaming_response_generator(
                audio_chunks,
                self.streaming_config,
            )
        )

        for response in responses:

            for result in response.results:

                if not result.alternatives:
                    continue

                alternative = result.alternatives[0]

                text = alternative.transcript.strip()

                if not text:
                    continue

                yield ASRResult(
                    text=text,
                    is_final=result.is_final,
                    stability=getattr(
                        result,
                        "stability",
                        0.0
                    ),
                    timestamp=time.perf_counter(),
                )


def test_live_asr():

    from audio.microphone import Microphone

    print("=" * 60)
    print("REAL-TIME RIVA ASR TEST")
    print("=" * 60)

    print(f"Riva server : {RIVA_SERVER}")
    print(f"Language    : {SOURCE_LANGUAGE}")

    print("=" * 60)

    print("Speak into the microphone.")
    print("Press Ctrl+C to stop.\n")

    microphone = Microphone()
    asr = RivaASR()

    try:

        microphone.start()

        for result in asr.transcribe(
            microphone.frames()
        ):

            if result.is_final:

                print(
                    f"\n[FINAL] {result.text}"
                )

            else:

                print(
                    f"\r[PARTIAL] "
                    f"{result.text:<80}",
                    end="",
                    flush=True,
                )

    except KeyboardInterrupt:

        print("\nStopping...")

    finally:

        microphone.stop()


if __name__ == "__main__":
    test_live_asr()