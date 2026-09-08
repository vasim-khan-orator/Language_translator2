from config import Settings
from conversation.manager import ConversationManager
from conversation.models import Utterance
from conversation.renderer import render
from riva.asr import RivaASR
from riva.tts import RivaTTS
from translation.ollama import OllamaTranslator


class TranslationPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.asr = RivaASR(settings.riva_uri)
        self.translator = OllamaTranslator(model=settings.ollama_model)
        self.tts = RivaTTS(settings.riva_uri)
        self.conversation = ConversationManager()

    def process(self, audio: bytes) -> bytes:
        source_text = self.asr.transcribe(audio, self.settings.source_language)
        translated_text = self.translator.translate(
            source_text, self.settings.target_language
        )
        utterance = Utterance(source_text, translated_text)
        self.conversation.add(utterance)
        print(render(utterance))
        return self.tts.synthesize(translated_text, self.settings.target_language)

    def run(self) -> None:
        """Run the capture loop once microphone integration is implemented."""
        raise NotImplementedError("Connect Microphone and Speaker here")
