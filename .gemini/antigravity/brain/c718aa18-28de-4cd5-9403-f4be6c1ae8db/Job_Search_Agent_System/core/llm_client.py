"""
Client unifié pour les appels LLM.
Priorité : API GPT (OpenAI) si OPENAI_API_KEY, sinon Groq si GROQ_API_KEY, sinon Ollama.
Groq conservé en option (non destructif) ; fallback OpenAI si Groq en 429.
"""
import os
import json
import time
from openai import OpenAI
from dotenv import load_dotenv

try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False
    Groq = None

load_dotenv()


def _is_rate_limit_error(exc: Exception) -> bool:
    """Détecte une erreur 429 Too Many Requests."""
    msg = str(exc).lower()
    return "429" in msg or "too many requests" in msg or "rate limit" in msg


class OpenAIClient:
    """
    Client centralisé : OpenAI (GPT) prioritaire, Groq en option, Ollama en fallback local.
    Rien n'est supprimé : si tu remets GROQ_API_KEY sans OPENAI_API_KEY, Groq est utilisé.
    """
    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self._openai_client = OpenAI(api_key=self.openai_key) if self.openai_key else None

        # Priorité : OpenAI (GPT) d'abord, puis Groq si dispo, puis Ollama
        if self.openai_key:
            self.provider = "openai"
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            self.client = self._openai_client
        elif self.groq_key and _GROQ_AVAILABLE and Groq is not None:
            self.provider = "groq"
            self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            self.client = Groq(api_key=self.groq_key)
        else:
            self.provider = "ollama"
            self.model = os.getenv("OLLAMA_MODEL", "llama3")
            self.client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

    def _do_chat(self, client, model: str, messages: list, response_format, json_mode: bool) -> str | None:
        """Exécute l'appel chat. Retourne le content ou None."""
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=response_format if json_mode else None,
            timeout=60,
        )
        return response.choices[0].message.content

    def chat_completion(self, prompt: str, system_prompt: str = "Tu es un assistant expert en recrutement et automatisation.", json_mode: bool = True) -> dict:
        """
        Effectue un appel de complétion chat. Retry sur 429.
        Si provider Groq et 429 : fallback OpenAI si OPENAI_API_KEY disponible (protège le projet).
        """
        response_format = {"type": "json_object"} if json_mode else None
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        for attempt in range(3):
            try:
                content = self._do_chat(self.client, self.model, messages, response_format, json_mode)
                if content:
                    if json_mode:
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        return json.loads(content)
                    return {"content": content}
            except Exception as e:
                if _is_rate_limit_error(e) and attempt < 2:
                    delay = 2 ** (attempt + 1)
                    print(f"LLM 429 rate limit, retry {attempt + 1}/2 dans {delay}s...")
                    time.sleep(delay)
                    continue
                # Fallback OpenAI si Groq et qu'on a la clé (non destructif, protège le projet)
                if self.provider == "groq" and self._openai_client:
                    print(f"Groq échec ({e}), fallback OpenAI...")
                    try:
                        model_oa = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
                        content = self._do_chat(self._openai_client, model_oa, messages, response_format, json_mode)
                        if content:
                            if json_mode:
                                if "```json" in content:
                                    content = content.split("```json")[1].split("```")[0].strip()
                                return json.loads(content)
                            return {"content": content}
                    except Exception as e2:
                        print(f"Fallback OpenAI échec: {e2}")
                print(f"Erreur LLM ({self.provider}): {e}")
                return {}
        return {}

    def get_embedding(self, text: str, model: str = "text-embedding-3-small") -> list:
        """
        Génère un embedding (OpenAI). OPENAI_API_KEY requise (Groq n'expose pas d'embeddings compatibles).
        """
        if not self.openai_key:
            print("Erreur: OPENAI_API_KEY requis pour les embeddings.")
            return []

        try:
            client_oa = OpenAI(api_key=self.openai_key)
            text = text.replace("\n", " ")
            return client_oa.embeddings.create(input=[text], model=model).data[0].embedding
        except Exception as e:
            print(f"Erreur OpenAI Embedding: {e}")
            return []
