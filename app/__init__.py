"""Factory da aplicação Flask.

Centraliza a criação da app, o registro de blueprints (rotas) e a
configuração de tratadores de erro. Seguir o padrão *application
factory* permite criar instâncias diferentes para produção, testes
e scripts sem efeitos colaterais de importação.
"""
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from .config import Config
from .database import init_db
from .routes.sensores import bp as sensores_bp
from .routes.atuadores import bp as atuadores_bp
from .routes.leituras import bp as leituras_bp
from .routes.clima import bp as clima_bp


def create_app() -> Flask:
    """Constrói e devolve a aplicação Flask pronta para servir."""
    # Carrega variáveis do .env (no-op em produção quando já exportadas).
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object(Config)
    # CORS liberado para permitir consumo a partir de páginas web/Postman.
    CORS(app)

    # Inicializa estrutura de tabelas no backend (HBase ou in-memory).
    # Falha silenciosa para que o serviço suba mesmo com banco fora do ar
    # — o endpoint /health mostrará o problema.
    try:
        init_db(app)
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("Banco indisponível no startup: %s", exc)

    # Cada blueprint agrupa endpoints de um recurso (SRP).
    app.register_blueprint(sensores_bp)
    app.register_blueprint(atuadores_bp)
    app.register_blueprint(leituras_bp)
    app.register_blueprint(clima_bp)

    @app.get("/")
    def index():
        """Endpoint raiz — descreve o serviço e lista os endpoints."""
        return jsonify({
            "servico": "API de Gerência de Sensores IoT",
            "versao": "1.0.0",
            "endpoints": {
                "sensores": [
                    "POST /sensores",
                    "GET /sensores",
                    "GET /sensores/<id>",
                    "PUT /sensores/<id>",
                    "DELETE /sensores/<id>",
                    "POST /sensores/<id>/dados",
                    "GET /sensores/<id>/dados",
                ],
                "atuadores": [
                    "POST /atuadores",
                    "GET /atuadores",
                    "GET /atuadores/<id>",
                    "POST /atuadores/<id>/comando",
                ],
                "leituras": ["GET /leituras"],
                "externos": [
                    "GET /clima?cidade=Curitiba,BR",
                    "POST /clima/sincronizar/<sensor_id>",
                ],
                "health": "GET /health",
            },
        })

    @app.get("/health")
    def health():
        """Health check — confirma API e conectividade com o backend."""
        from .database import get_connection
        status = {"api": "ok", "banco": "ok"}
        try:
            conn = get_connection()
            conn.tables()
            conn.close()
        except Exception as exc:  # noqa: BLE001
            status["banco"] = f"erro: {exc}"
        return jsonify(status)

    # ---- Tratadores globais de erro ------------------------------------
    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"erro": "recurso não encontrado"}), 404

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"erro": str(e.description)}), 400

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Erro interno", exc_info=e)
        return jsonify({"erro": "erro interno do servidor"}), 500

    return app
