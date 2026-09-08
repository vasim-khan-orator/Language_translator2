class RivaTTS:
    def __init__(self, uri: str) -> None:
        self.uri = uri

    def synthesize(self, text: str, language: str) -> bytes:
        """Synthesize translated text with NVIDIA Riva TTS."""
        del text, language
        raise NotImplementedError("Connect NVIDIA Riva TTS here")
