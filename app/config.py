"""Configuração da aplicação carregada de variáveis de ambiente.

Todas as chaves têm valores-padrão razoáveis para desenvolvimento.
Em produção, defina-as via ``.env`` ou diretamente no painel do
provedor de hospedagem (Render, Railway, etc.).
"""
import os


class Config:
    # Chave usada por extensões do Flask (sessões, CSRF, etc.).
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

    # ---- HBase ----------------------------------------------------
    HBASE_HOST = os.getenv("HBASE_HOST", "localhost")
    HBASE_PORT = int(os.getenv("HBASE_PORT", "9090"))
    # Prefixo evita colisão de nomes em ambientes compartilhados.
    HBASE_TABLE_PREFIX = os.getenv("HBASE_TABLE_PREFIX", "iot")

    # ---- OpenWeatherMap ------------------------------------------
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
    OPENWEATHER_DEFAULT_CITY = os.getenv("OPENWEATHER_DEFAULT_CITY", "Curitiba,BR")

    # ---- ThingSpeak (opcional) -----------------------------------
    THINGSPEAK_WRITE_KEY = os.getenv("THINGSPEAK_WRITE_KEY", "")
    THINGSPEAK_CHANNEL_ID = os.getenv("THINGSPEAK_CHANNEL_ID", "")

    @classmethod
    def table(cls, name: str) -> str:
        """Devolve o nome completo da tabela, com o prefixo aplicado."""
        return f"{cls.HBASE_TABLE_PREFIX}_{name}"
